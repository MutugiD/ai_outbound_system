"""Intelligence service task stubs.

These placeholders establish queue ownership for the intelligence service while
the existing monolith AI tasks are gradually extracted into this boundary.
"""

from app.workers.celery_app import celery_app
from shared.events import INTELLIGENCE_QUEUE


@celery_app.task(
    name="services.intelligence_service.tasks.healthcheck",
    queue=INTELLIGENCE_QUEUE,
)
def healthcheck() -> dict[str, str]:
    """Lightweight task to verify queue wiring for the intelligence service."""
    return {"service": "intelligence", "status": "ok"}
