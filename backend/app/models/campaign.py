"""Campaign, CampaignStep, and CampaignEnrollment models per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Index, JSON
from sqlmodel import Field, SQLModel


class Campaign(SQLModel, table=True):
    __tablename__ = "campaigns"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id", index=True)
    name: str = Field(max_length=255)
    description: Optional[str] = Field(default=None)
    status: str = Field(default="draft", max_length=20)  # draft, active, paused, completed, archived
    goal: Optional[str] = Field(default=None, max_length=100)  # book_meeting, generate_interest, nurture, etc.
    tone: str = Field(default="professional", max_length=50)  # professional, casual, direct, consultative
    approval_mode: str = Field(default="manual", max_length=20)  # manual, auto
    send_limits: dict = Field(default={}, sa_column=Column(JSON))

    created_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CampaignStep(SQLModel, table=True):
    __tablename__ = "campaign_steps"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    campaign_id: uuid.UUID = Field(foreign_key="campaigns.id")
    step_order: int = Field(sa_column_kwargs={"nullable": False})
    channel: str = Field(max_length=20)  # email, linkedin, sms
    delay_days: int = Field(default=0)
    template_type: str = Field(max_length=50)  # initial_email, followup_1, followup_2, linkedin_dm, breakup, etc.
    subject_template: Optional[str] = Field(default=None)
    body_template: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CampaignEnrollment(SQLModel, table=True):
    __tablename__ = "campaign_enrollments"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    campaign_id: uuid.UUID = Field(foreign_key="campaigns.id")
    lead_id: uuid.UUID = Field(foreign_key="leads.id")
    status: str = Field(default="pending", max_length=20)  # pending, in_progress, completed, stopped, paused
    current_step: int = Field(default=0)
    next_step_at: Optional[datetime] = Field(default=None)
    enrolled_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)

    __table_args__ = (
        Index("idx_enrollments_campaign", "campaign_id"),
        Index("idx_enrollments_lead", "lead_id"),
    )