"""Enrichment-related Celery tasks.

These tasks run on the Celery worker (sync entrypoint) but call async service
layers using a private event loop, consistent with the existing outreach tasks.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from decimal import Decimal

from app.database import async_session
from app.models.enrichment import EnrichmentRecord
from app.services.enrichment.enrichment_service import EnrichmentService
from app.services.enrichment.hunter_adapter import HunterAdapter
from app.workers.base_task import BaseTask
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.enrichment_tasks.enrich_lead",
    queue="enrichment",
)
def enrich_lead(self, lead_id: str, **kwargs):
    """Run the enrichment pipeline for a lead and persist results."""

    async def _run():
        async with async_session() as db:
            svc = EnrichmentService(db)
            result = await svc.enrich_lead(uuid.UUID(lead_id))
            await db.commit()
            return result

    logger.info("Task enrich_lead started — lead_id=%s", lead_id)
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Task enrich_lead completed — lead_id=%s", lead_id)
        return result
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.enrichment_tasks.verify_email",
    queue="enrichment",
)
def verify_email(self, email: str, lead_id: str, **kwargs):
    """Verify an email address and store the result as an EnrichmentRecord."""

    async def _run():
        adapter = HunterAdapter()
        result = await adapter.verify_email(email)

        # Best-effort persistence (does not block returning the verification).
        async with async_session() as db:
            try:
                record = EnrichmentRecord(
                    lead_id=uuid.UUID(lead_id),
                    provider=result.get("source", "hunter"),
                    enrichment_type="email_verification",
                    data=result,
                    confidence=Decimal(str(result.get("confidence", 0.0))),
                    enriched_at=datetime.utcnow(),
                )
                db.add(record)
                await db.commit()
            except Exception:
                await db.rollback()

        return result

    logger.info("Task verify_email started — email=%s lead_id=%s", email, lead_id)
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        logger.info("Task verify_email completed — email=%s lead_id=%s", email, lead_id)
        return result
    finally:
        loop.close()
