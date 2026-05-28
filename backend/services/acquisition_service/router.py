"""Acquisition service router."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from shared.auth import get_current_user
from services.acquisition_service.models import (
    AcquisitionJob,
    GoogleMapsLocationTarget,
    GoogleMapsRawProfile,
    GoogleMapsSource,
)
from services.acquisition_service.schemas import (
    GoogleMapsPromoteRequest,
    GoogleMapsLocationTargetResponse,
    GoogleMapsRawProfileResponse,
    GoogleMapsSourceCreate,
    GoogleMapsSourceResponse,
)
from services.crm_service.ingestion import build_google_maps_raw_lead, ingest_raw_leads
from services.acquisition_service.tasks import scrape_google_maps_source

router = APIRouter(prefix="/google-maps", tags=["acquisition"])


@router.post("/sources", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def create_google_maps_source(
    body: GoogleMapsSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = GoogleMapsSource(
        team_id=current_user.team_id,
        name=body.name,
        industry_class=body.industry_class,
        promotion_mode=body.promotion_mode,
        max_results_per_location=body.max_results_per_location,
        require_phone=body.require_phone,
        require_address=body.require_address,
        country_code=body.country_code,
        status="queued",
        created_by=current_user.id,
        updated_at=datetime.utcnow(),
    )
    db.add(source)
    await db.flush()

    for location in body.locations:
        db.add(
            GoogleMapsLocationTarget(
                source_id=source.id,
                location_label=location.location_label,
                location_query=location.location_query,
                radius_km=location.radius_km,
                status="queued",
            )
        )

    await db.flush()
    task = scrape_google_maps_source.delay(str(source.id))

    job = AcquisitionJob(
        source_id=source.id,
        task_id=task.id,
        status="queued",
    )
    db.add(job)
    await db.flush()

    return {"source_id": str(source.id), "job_id": str(job.id), "task_id": task.id, "status": "queued"}


@router.get("/sources/{source_id}", response_model=GoogleMapsSourceResponse)
async def get_google_maps_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = (
        await db.execute(
            select(GoogleMapsSource).where(
                GoogleMapsSource.id == source_id,
                GoogleMapsSource.team_id == current_user.team_id,
            )
        )
    ).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    locations = list(
        (
            await db.execute(select(GoogleMapsLocationTarget).where(GoogleMapsLocationTarget.source_id == source.id))
        )
        .scalars()
        .all()
    )
    response = GoogleMapsSourceResponse.model_validate(source, from_attributes=True)
    response.locations = [
        GoogleMapsLocationTargetResponse.model_validate(location, from_attributes=True)
        for location in locations
    ]
    return response


@router.get("/sources/{source_id}/profiles", response_model=list[GoogleMapsRawProfileResponse])
async def list_google_maps_profiles(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = (
        await db.execute(
            select(GoogleMapsSource).where(
                GoogleMapsSource.id == source_id,
                GoogleMapsSource.team_id == current_user.team_id,
            )
        )
    ).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    profiles = list(
        (
            await db.execute(select(GoogleMapsRawProfile).where(GoogleMapsRawProfile.source_id == source.id))
        )
        .scalars()
        .all()
    )
    return [GoogleMapsRawProfileResponse.model_validate(profile, from_attributes=True) for profile in profiles]


@router.post("/sources/{source_id}/promote", response_model=dict)
async def promote_google_maps_profiles(
    source_id: uuid.UUID,
    body: GoogleMapsPromoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = (
        await db.execute(
            select(GoogleMapsSource).where(
                GoogleMapsSource.id == source_id,
                GoogleMapsSource.team_id == current_user.team_id,
            )
        )
    ).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    stmt = select(GoogleMapsRawProfile).where(GoogleMapsRawProfile.source_id == source.id)
    if body.profile_ids:
        stmt = stmt.where(GoogleMapsRawProfile.id.in_(body.profile_ids))

    profiles = list((await db.execute(stmt)).scalars().all())
    if not profiles:
        raise HTTPException(status_code=404, detail="No profiles found to promote")

    raw_leads = [
        build_google_maps_raw_lead(
            business_name=profile.business_name,
            query=profile.query,
            area=profile.area,
            phone=profile.phone,
            website=profile.website,
            google_maps_url=profile.google_maps_url,
            address=profile.address,
            category=profile.category,
            review_count=profile.review_count,
            rating=profile.rating,
            provider_record_id=str(profile.id),
            scraped_at=profile.scraped_at,
        )
        for profile in profiles
    ]

    result = await ingest_raw_leads(raw_leads, current_user.team_id, current_user.id, db)
    for profile in profiles:
        profile.promotion_status = "promoted"
        db.add(profile)

    source.status = "promoted" if result["created"] or result["merged"] else source.status
    source.updated_at = datetime.utcnow()
    db.add(source)
    await db.commit()

    return {
        "source_id": str(source.id),
        "profiles_processed": len(profiles),
        **result,
    }
