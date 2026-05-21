"""Job model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Index, JSON
from sqlmodel import Field, SQLModel


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    job_type: str = Field(max_length=50)  # lead_enrichment, signal_detection, etc.
    status: str = Field(default="pending", max_length=20)
    # pending, running, completed, failed, retrying, skipped, cancelled
    lead_id: Optional[uuid.UUID] = Field(default=None, foreign_key="leads.id")
    campaign_id: Optional[uuid.UUID] = Field(default=None, foreign_key="campaigns.id")
    company_id: Optional[uuid.UUID] = Field(default=None, foreign_key="companies.id")
    error: Optional[str] = Field(default=None)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    next_retry_at: Optional[datetime] = Field(default=None)
    result: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    __table_args__ = (
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_type", "job_type"),
    )