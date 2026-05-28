"""Channel service task stubs.

Channel execution will move here as WhatsApp-first orchestration is extracted
from the monolith. The healthcheck task keeps the queue path deployable now.
"""

from app.workers.celery_app import celery_app
from shared.events import CHANNEL_QUEUE


@celery_app.task(
    name="services.channel_service.tasks.healthcheck",
    queue=CHANNEL_QUEUE,
)
def healthcheck() -> dict[str, str]:
    """Lightweight task to verify queue wiring for the channel service."""
    return {"service": "channel", "status": "ok"}
