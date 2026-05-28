"""SuppressionList model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class SuppressionList(SQLModel, table=True):
    __tablename__ = "suppression_list"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id")
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    reason: str = Field(max_length=50)  # unsubscribe, bounce, complaint, manual
    source: str = Field(default=None, max_length=100)  # campaign_id or 'manual'
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_suppression_email", "email"),
        Index("idx_suppression_phone", "phone"),
    )
