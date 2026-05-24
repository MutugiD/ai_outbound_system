"""OutreachMessage model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Index, JSON
from sqlmodel import Field, SQLModel


class OutreachMessage(SQLModel, table=True):
    __tablename__ = "outreach_messages"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lead_id: uuid.UUID = Field(foreign_key="leads.id")
    campaign_id: Optional[uuid.UUID] = Field(default=None, foreign_key="campaigns.id")
    campaign_step_id: Optional[uuid.UUID] = Field(default=None, foreign_key="campaign_steps.id")
    channel: str = Field(max_length=20)  # email, linkedin, sms
    subject: Optional[str] = Field(default=None)
    body: str = Field(sa_column_kwargs={"nullable": False})
    personalization_sources: list = Field(default=[], sa_column=Column(JSON))
    provider: Optional[str] = Field(default=None, max_length=50)  # resend, sendgrid, smartlead
    provider_message_id: Optional[str] = Field(default=None, max_length=255)
    to_email: Optional[str] = Field(default=None, max_length=320)
    error: Optional[str] = Field(default=None, max_length=2048)
    status: str = Field(default="draft", max_length=30)
    # draft, pending_approval, approved, scheduled, sent, delivered, opened, clicked, replied, bounced, failed
    approved_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    approved_at: Optional[datetime] = Field(default=None)
    sent_at: Optional[datetime] = Field(default=None)
    delivered_at: Optional[datetime] = Field(default=None)
    opened_at: Optional[datetime] = Field(default=None)
    clicked_at: Optional[datetime] = Field(default=None)
    resend_id: Optional[str] = Field(default=None, index=True, description="Resend message ID for tracking")
    error_message: Optional[str] = Field(default=None, description="Error message if send failed")
    scheduled_at: Optional[datetime] = Field(default=None, description="When to send the message")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_messages_lead", "lead_id"),
        Index("idx_messages_campaign", "campaign_id"),
        Index("idx_messages_status", "status"),
    )
