"""ActivityLog model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Index, JSON
from sqlmodel import Field, SQLModel


class ActivityLog(SQLModel, table=True):
    __tablename__ = "activity_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id")
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    lead_id: Optional[uuid.UUID] = Field(default=None, foreign_key="leads.id")
    action: str = Field(max_length=100)
    details: dict = Field(default={}, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_activity_lead", "lead_id"),
        Index("idx_activity_team", "team_id"),
        Index("idx_activity_created", "created_at"),
    )