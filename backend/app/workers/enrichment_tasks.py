"""Enrichment-related Celery tasks (placeholders for Phase 2+)."""

import logging

from app.workers.celery_app import celery_app
from app.workers.base_task import BaseTask

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.enrichment_tasks.enrich_lead",
    queue="enrichment",
)
def enrich_lead(self, lead_id: str, **kwargs):
    """Enrich a lead with data from external providers.

    Parameters
    ----------
    lead_id : str
        UUID of the lead to enrich.

    Phase 2 will add: Apollo / Hunter / PDL enrichment pipeline.
    """
    logger.info("Task enrich_lead started — lead_id=%s", lead_id)
    logger.info("Task enrich_lead completed (placeholder)")
    return {"lead_id": lead_id, "status": "completed"}


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.enrichment_tasks.verify_email",
    queue="enrichment",
)
def verify_email(self, email: str, lead_id: str, **kwargs):
    """Verify a lead's email address via Hunter / Dropcontact.

    Parameters
    ----------
    email : str
        The email address to verify.
    lead_id : str
        UUID of the associated lead.

    Phase 2 will add: verification API calls, bounce detection.
    """
    logger.info("Task verify_email started — email=%s lead_id=%s", email, lead_id)
    logger.info("Task verify_email completed (placeholder)")
    return {"email": email, "lead_id": lead_id, "status": "completed"}
