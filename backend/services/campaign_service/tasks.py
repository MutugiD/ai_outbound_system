"""Campaign service task stubs.

The campaign orchestration code is still being extracted from the monolith.
This module claims the dedicated queue and provides a safe verification task.
"""

from app.workers.celery_app import celery_app
from shared.events import CAMPAIGN_QUEUE


@celery_app.task(
    name="services.campaign_service.tasks.healthcheck",
    queue=CAMPAIGN_QUEUE,
)
def healthcheck() -> dict[str, str]:
    """Lightweight task to verify queue wiring for the campaign service."""
    return {"service": "campaign", "status": "ok"}
