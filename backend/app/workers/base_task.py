"""Base Celery task with automatic job-status tracking and retry logic."""

import logging
import uuid
from datetime import datetime, timedelta

from celery import Task
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

# ── Synchronous engine for Celery workers ─────────────────────────────────
# Celery tasks are synchronous; we need a regular (sync) SQLAlchemy session.
_sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    pool_size=5,
    max_overflow=3,
    pool_pre_ping=True,
)
_sync_session_factory = sessionmaker(bind=_sync_engine, expire_on_commit=False)


class BaseTask(Task):
    """Celery Task subclass that wraps execution with Job status tracking.

    Every task that receives a ``job_id`` kwarg will automatically:
    1. Mark the Job as *running* when execution begins.
    2. Mark the Job as *completed* on success (storing an optional result).
    3. Mark the Job as *failed* on exception, and retry with exponential
       backoff (up to 3 retries by default).

    Tasks that don't receive a ``job_id`` are executed without job tracking.
    """

    abstract = True
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_factor = 2  # 2s → 4s → 8s
    max_retries = 3
    retry_jitter = True

    def _get_sync_session(self) -> Session:
        """Return a new synchronous SQLAlchemy session."""
        return _sync_session_factory()

    def _update_job_status(
        self,
        job_id: uuid.UUID,
        status: str,
        error: str | None = None,
        result: dict | None = None,
    ) -> None:
        """Update a Job record inside a sync session."""
        from app.models.job import Job as JobModel  # local import to avoid circular

        session = self._get_sync_session()
        try:
            job = session.get(JobModel, job_id)
            if job is None:
                logger.warning("Job %s not found for status update", job_id)
                return

            job.status = status

            if status == "running":
                job.started_at = datetime.utcnow()
            elif status in ("completed", "failed", "skipped", "cancelled"):
                job.completed_at = datetime.utcnow()

            if error is not None:
                job.error = error[:2000] if error else None  # cap length

            if result is not None:
                job.result = result

            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to update job %s status to %s", job_id, status)
            raise
        finally:
            session.close()

    def __call__(self, *args, **kwargs):
        """Entry-point that wraps the actual task body with job tracking."""
        job_id = kwargs.pop("job_id", None)

        if job_id:
            self._update_job_status(job_id, "running")

        try:
            result = super().__call__(*args, **kwargs)

            if job_id:
                self._update_job_status(
                    job_id,
                    "completed",
                    result={"detail": "Task completed successfully"} if result is None else result,
                )

            return result

        except Exception as exc:
            if job_id:
                retries = self.request.retries or 0
                if retries < self.max_retries:
                    # Will retry — mark as retrying
                    next_retry = datetime.utcnow() + timedelta(
                        seconds=(2 ** retries) * self.retry_backoff_factor
                    )
                    # We still need to mark the current attempt as failed
                    self._update_job_status(job_id, "failed", error=str(exc))
                else:
                    self._update_job_status(job_id, "failed", error=str(exc))
            raise