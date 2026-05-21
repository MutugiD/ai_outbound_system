"""Job management service — CRUD for background Job records."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job

# ── Valid job statuses ─────────────────────────────────────────────────────
JOB_STATUSES = {
    "pending",
    "running",
    "completed",
    "failed",
    "retrying",
    "skipped",
    "cancelled",
}


async def create_job(
    db: AsyncSession,
    job_type: str,
    lead_id: Optional[uuid.UUID] = None,
    campaign_id: Optional[uuid.UUID] = None,
    company_id: Optional[uuid.UUID] = None,
) -> Job:
    """Create a new Job record in pending state.

    Parameters
    ----------
    db : AsyncSession
        Async database session.
    job_type : str
        Short identifier for the kind of work (e.g. "lead_enrichment").
    lead_id, campaign_id, company_id : UUID | None
        Optional scope keys linking the job to domain objects.

    Returns
    -------
    Job
        The persisted Job instance (flushed, not committed).
    """
    job = Job(
        job_type=job_type,
        status="pending",
        lead_id=lead_id,
        campaign_id=campaign_id,
        company_id=company_id,
    )
    db.add(job)
    await db.flush()
    return job


async def update_job_status(
    db: AsyncSession,
    job_id: uuid.UUID,
    status: str,
    error: Optional[str] = None,
    result: Optional[dict] = None,
) -> Optional[Job]:
    """Update the status (and optionally error/result) of an existing Job.

    Parameters
    ----------
    db : AsyncSession
    job_id : UUID
    status : str
        Must be one of JOB_STATUSES.
    error : str | None
        Error message to store when status is "failed".
    result : dict | None
        Arbitrary JSON result payload for successful jobs.

    Returns
    -------
    Job | None
        The updated Job, or None if not found.
    """
    result_row = await db.execute(select(Job).where(Job.id == job_id))
    job = result_row.scalar_one_or_none()
    if job is None:
        return None

    job.status = status

    if status == "running":
        job.started_at = datetime.utcnow()
    elif status in ("completed", "failed", "skipped", "cancelled"):
        job.completed_at = datetime.utcnow()

    if error is not None:
        job.error = error

    if result is not None:
        job.result = result

    db.add(job)
    await db.flush()
    return job


async def get_pending_jobs(
    db: AsyncSession,
    job_type: Optional[str] = None,
    limit: int = 100,
) -> list[Job]:
    """Fetch pending (and retry-ready) jobs, optionally filtered by type.

    Parameters
    ----------
    db : AsyncSession
    job_type : str | None
        Filter by job_type if provided.
    limit : int
        Maximum number of rows to return.

    Returns
    -------
    list[Job]
    """
    query = select(Job).where(
        (Job.status == "pending") | ((Job.status == "retrying") & (Job.next_retry_at <= datetime.utcnow()))
    )

    if job_type is not None:
        query = query.where(Job.job_type == job_type)

    query = query.order_by(Job.created_at.asc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def mark_job_retrying(
    db: AsyncSession,
    job_id: uuid.UUID,
    next_retry_at: datetime,
) -> Optional[Job]:
    """Mark a failed job as 'retrying' with a scheduled next attempt time.

    Parameters
    ----------
    db : AsyncSession
    job_id : UUID
    next_retry_at : datetime
        When the job should be picked up again.

    Returns
    -------
    Job | None
    """
    result_row = await db.execute(select(Job).where(Job.id == job_id))
    job = result_row.scalar_one_or_none()
    if job is None:
        return None

    job.status = "retrying"
    job.retry_count += 1
    job.next_retry_at = next_retry_at
    job.completed_at = None  # clear completion timestamp

    db.add(job)
    await db.flush()
    return job
