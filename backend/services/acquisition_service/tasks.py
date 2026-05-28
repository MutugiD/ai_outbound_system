"""Acquisition tasks for scrape job orchestration."""

import asyncio
import logging
import uuid
from datetime import datetime

from sqlalchemy import select

from app.workers.base_task import BaseTask
from app.workers.celery_app import celery_app
from shared.db import async_session
from shared.events import ACQUISITION_QUEUE
from services.acquisition_service.google_maps_scraper import GoogleMapsPlaywrightScraper
from services.acquisition_service.models import (
    AcquisitionJob,
    GoogleMapsLocationTarget,
    GoogleMapsRawProfile,
    GoogleMapsSource,
)
from services.acquisition_service.service import build_queries, filter_profiles_for_target

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="services.acquisition_service.tasks.scrape_google_maps_source",
    queue=ACQUISITION_QUEUE,
)
def scrape_google_maps_source(self, source_id: str, **kwargs):
    """Run a low-volume Google Maps scrape job for one acquisition source."""

    async def _mark_failed(message: str):
        async with async_session() as db:
            source = (
                await db.execute(select(GoogleMapsSource).where(GoogleMapsSource.id == uuid.UUID(source_id)))
            ).scalar_one_or_none()
            if source:
                source.status = "failed"
                source.updated_at = datetime.utcnow()
                db.add(source)

            job = (
                await db.execute(
                    select(AcquisitionJob)
                    .where(AcquisitionJob.source_id == uuid.UUID(source_id))
                    .order_by(AcquisitionJob.created_at.desc())
                )
            ).scalars().first()
            if job:
                job.status = "failed"
                job.error = message[:2048]
                job.completed_at = datetime.utcnow()
                db.add(job)
            await db.commit()

    async def _run():
        prepared_locations: list[dict] = []
        query_count = 0

        async with async_session() as db:
            source = (
                await db.execute(select(GoogleMapsSource).where(GoogleMapsSource.id == uuid.UUID(source_id)))
            ).scalar_one_or_none()
            if not source:
                return {"source_id": source_id, "status": "not_found"}

            source.status = "running"
            source.updated_at = datetime.utcnow()
            db.add(source)

            job = (
                await db.execute(
                    select(AcquisitionJob)
                    .where(AcquisitionJob.source_id == source.id)
                    .order_by(AcquisitionJob.created_at.desc())
                )
            ).scalars().first()
            if not job:
                job = AcquisitionJob(source_id=source.id)
            job.status = "running"
            job.task_id = self.request.id
            job.started_at = job.started_at or datetime.utcnow()
            db.add(job)

            locations = list(
                (
                    await db.execute(
                        select(GoogleMapsLocationTarget).where(GoogleMapsLocationTarget.source_id == source.id)
                    )
                )
                .scalars()
                .all()
            )
            for location in locations:
                location.query_templates = build_queries(source.industry_class, location.location_query)
                location.status = "running"
                db.add(location)
                prepared_locations.append(
                    {
                        "id": location.id,
                        "location_query": location.location_query,
                        "queries": list(location.query_templates),
                        "max_results": min(source.max_results_per_location, 10),
                    }
                )

            await db.commit()

        scraped_results: dict[uuid.UUID, list[dict]] = {item["id"]: [] for item in prepared_locations}
        async with GoogleMapsPlaywrightScraper() as scraper:
            for location in prepared_locations:
                for query in location["queries"]:
                    profiles = await scraper.scrape_query(query, max_results=location["max_results"])
                    filtered_profiles, rejected_profiles = filter_profiles_for_target(
                        profiles=profiles,
                        industry_class=source.industry_class,
                        location_query=location["location_query"],
                    )
                    if rejected_profiles:
                        logger.info(
                            "Rejected %s profiles for %s: %s",
                            len(rejected_profiles),
                            location["location_query"],
                            rejected_profiles,
                        )
                    scraped_results[location["id"]].extend(filtered_profiles)
                    query_count += 1

        total_profiles = 0
        async with async_session() as db:
            source = (
                await db.execute(select(GoogleMapsSource).where(GoogleMapsSource.id == uuid.UUID(source_id)))
            ).scalar_one()
            locations = {
                location.id: location
                for location in (
                    await db.execute(
                        select(GoogleMapsLocationTarget).where(GoogleMapsLocationTarget.source_id == source.id)
                    )
                )
                .scalars()
                .all()
            }
            job = (
                await db.execute(
                    select(AcquisitionJob)
                    .where(AcquisitionJob.source_id == source.id)
                    .order_by(AcquisitionJob.created_at.desc())
                )
            ).scalars().first()

            for location_id, profiles in scraped_results.items():
                location = locations[location_id]
                inserted_for_location = 0
                for profile in profiles:
                    duplicate = (
                        await db.execute(
                            select(GoogleMapsRawProfile).where(
                                GoogleMapsRawProfile.source_id == source.id,
                                GoogleMapsRawProfile.google_maps_url == profile["google_maps_url"],
                            )
                        )
                    ).scalar_one_or_none()
                    if duplicate:
                        continue

                    db.add(
                        GoogleMapsRawProfile(
                            source_id=source.id,
                            location_target_id=location.id,
                            query=profile["query"],
                            business_name=profile["business_name"],
                            category=profile.get("category"),
                            phone=profile.get("phone"),
                            website=profile.get("website"),
                            google_maps_url=profile.get("google_maps_url"),
                            address=profile.get("address"),
                            area=profile.get("area"),
                            rating=profile.get("rating"),
                            review_count=profile.get("review_count"),
                            business_status=profile.get("business_status", "active"),
                            raw_payload=profile.get("raw_payload", {}),
                            scraped_at=datetime.utcnow(),
                        )
                    )
                    inserted_for_location += 1
                    total_profiles += 1

                location.results_count = inserted_for_location
                location.status = "completed" if inserted_for_location else "empty"
                db.add(location)

            source.status = "review" if total_profiles else "empty"
            source.updated_at = datetime.utcnow()
            db.add(source)
            if job:
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                db.add(job)

            await db.commit()

        logger.info(
            "Completed source %s with %s query runs and %s profiles",
            source_id,
            query_count,
            total_profiles,
        )
        return {
            "source_id": source_id,
            "status": "review" if total_profiles else "empty",
            "query_runs": query_count,
            "profiles": total_profiles,
        }

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run())
    except Exception as exc:
        loop.run_until_complete(_mark_failed(str(exc)))
        raise
    finally:
        loop.close()
