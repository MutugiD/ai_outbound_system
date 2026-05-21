"""PipelineTransition model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class PipelineTransition(SQLModel, table=True):
    __tablename__ = "pipeline_transitions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lead_id: uuid.UUID = Field(foreign_key="leads.id")
    from_stage: Optional[str] = Field(default=None, max_length=50)
    to_stage: str = Field(max_length=50)
    reason: Optional[str] = Field(default=None)
    transitioned_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_pipeline_lead", "lead_id"),
    )