"""Reply and ReplyClassification models per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class Reply(SQLModel, table=True):
    __tablename__ = "replies"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lead_id: uuid.UUID = Field(foreign_key="leads.id")
    message_id: Optional[uuid.UUID] = Field(default=None, foreign_key="outreach_messages.id")
    channel: str = Field(max_length=20)
    subject: Optional[str] = Field(default=None)
    body: str = Field(sa_column_kwargs={"nullable": False})
    from_email: Optional[str] = Field(default=None, max_length=320)
    from_name: Optional[str] = Field(default=None, max_length=255)
    received_at: datetime = Field(default_factory=datetime.utcnow)


class ReplyClassification(SQLModel, table=True):
    __tablename__ = "reply_classifications"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    reply_id: uuid.UUID = Field(foreign_key="replies.id")
    lead_id: uuid.UUID = Field(foreign_key="leads.id")
    classification: str = Field(max_length=50)
    subtype: Optional[str] = Field(default=None, max_length=50)
    confidence: Decimal = Field(sa_column_kwargs={"nullable": False})
    summary: Optional[str] = Field(default=None)
    recommended_action: Optional[str] = Field(default=None, max_length=255)
    draft_response: Optional[str] = Field(default=None)
    model_used: Optional[str] = Field(default=None, max_length=100)
    reviewed_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    reviewed_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_reply_class_reply", "reply_id"),
        Index("idx_reply_class_lead", "lead_id"),
    )