"""Scraping-related Celery tasks (placeholders for Phase 2+)."""

import logging

from app.workers.celery_app import celery_app
from app.workers.base_task import BaseTask

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.scraping_tasks.process_csv_import",
    queue="scraping",
)
def process_csv_import(self, file_path: str, team_id: str, **kwargs):
    """Import leads from a CSV file.

    Parameters
    ----------
    file_path : str
        Path to the uploaded CSV file (e.g. in object storage).
    team_id : str
        UUID of the team this import belongs to.

    Phase 2 will add: CSV parsing, deduplication, lead creation.
    """
    logger.info("Task process_csv_import started — file_path=%s team_id=%s", file_path, team_id)
    logger.info("Task process_csv_import completed (placeholder)")
    return {"file_path": file_path, "team_id": team_id, "status": "completed"}


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.scraping_tasks.run_daily_lead_discovery",
    queue="scraping",
)
def run_daily_lead_discovery(self, **kwargs):
    """Discover new leads from configured sources.

    Scheduled via Celery Beat at 06:00 UTC daily.
    Phase 2 will add: Apollo API search, Google SERP scraping, etc.
    """
    logger.info("Task run_daily_lead_discovery started (placeholder)")
    logger.info("Task run_daily_lead_discovery completed (placeholder)")
    return {"status": "completed", "note": "placeholder"}
