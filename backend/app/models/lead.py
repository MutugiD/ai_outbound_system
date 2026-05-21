"""Lead model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Index, Text
from sqlmodel import Field, SQLModel


class Lead(SQLModel, table=True):
    __tablename__ = "leads"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id", index=True)
    company_id: Optional[uuid.UUID] = Field(default=None, foreign_key="companies.id")
    contact_id: Optional[uuid.UUID] = Field(default=None, foreign_key="contacts.id")
    status: str = Field(default="new", max_length=50)
    # new, enriching, enriched, researching, researched, scoring, ready,
    # contacting, replied, interested, meeting_booked, proposal_sent, won, lost, suppressed
    pipeline_stage: str = Field(default="new", max_length=50)
    # new, enriched, researched, scored, ready_for_outreach, contacted,
    # replied, interested, meeting_booked, proposal_sent, won, lost, suppressed
    lead_score: int = Field(default=0)
    score_band: str = Field(default="low", max_length=20)  # very_hot, hot, warm, weak, low
    assigned_user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    last_contacted_at: Optional[datetime] = Field(default=None)
    next_action: Optional[str] = Field(default=None, max_length=255)
    next_action_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_leads_team", "team_id"),
        Index("idx_leads_status", "status"),
        Index("idx_leads_pipeline", "pipeline_stage"),
        Index("idx_leads_score", "lead_score"),
        Index("idx_leads_company", "company_id"),
        Index("idx_leads_contact", "contact_id"),
        Index("idx_leads_assigned", "assigned_user_id"),
    )