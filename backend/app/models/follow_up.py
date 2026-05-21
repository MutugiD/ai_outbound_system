"""FollowUpTask model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Index, JSON
from sqlmodel import Field, SQLModel


class FollowUpTask(SQLModel, table=True):
    __tablename__ = "follow_up_tasks"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lead_id: uuid.UUID = Field(foreign_key="leads.id")
    campaign_enrollment_id: Optional[uuid.UUID] = Field(default=None, foreign_key="campaign_enrollments.id")
    task_type: str = Field(max_length=50)
    # send_message, book_meeting, draft_objection_response, schedule_reminder, suppress_lead
    due_at: Optional[datetime] = Field(default=None)
    status: str = Field(default="pending", max_length=20)  # pending, in_progress, completed, cancelled
    data: dict = Field(default={}, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)

    __table_args__ = (
        Index("idx_followup_lead", "lead_id"),
        Index("idx_followup_due", "due_at"),
    )
