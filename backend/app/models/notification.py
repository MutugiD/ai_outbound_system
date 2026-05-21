"""Notification model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Index, JSON
from sqlmodel import Field, SQLModel


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id")
    type: str = Field(max_length=50)
    # hot_lead, interested_reply, campaign_complete, enrichment_failed, daily_summary
    title: str = Field(max_length=255)
    message: Optional[str] = Field(default=None)
    data: dict = Field(default={}, sa_column=Column(JSON))

    is_read: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (Index("idx_notifications_user", "user_id", "is_read", "created_at"),)
