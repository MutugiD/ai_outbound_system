"""WhatsApp session model for Evolution API integration."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class WhatsAppSession(SQLModel, table=True):
    __tablename__ = "whatsapp_sessions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id")
    instance_name: str = Field(max_length=100, unique=True)
    phone_number: Optional[str] = Field(default=None, max_length=50)
    status: str = Field(default="disconnected", max_length=20)  # disconnected, connecting, connected, banned
    qr_code: Optional[str] = Field(default=None)
    paired_at: Optional[datetime] = Field(default=None)
    last_ping: Optional[datetime] = Field(default=None)
    created_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_wa_sessions_team", "team_id"),
        Index("idx_wa_sessions_status", "status"),
    )
