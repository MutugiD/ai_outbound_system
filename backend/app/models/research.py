"""AIResearchReport model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Index, JSON, Numeric
from sqlmodel import Field, SQLModel


class AIResearchReport(SQLModel, table=True):
    __tablename__ = "ai_research_reports"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lead_id: uuid.UUID = Field(foreign_key="leads.id")
    version: int = Field(default=1)
    company_summary: Optional[str] = Field(default=None)
    target_customer: Optional[str] = Field(default=None)
    likely_operational_pain: list = Field(default=[], sa_column=Column(JSON))
    revenue_leakage_hypothesis: list = Field(default=[], sa_column=Column(JSON))
    competitor_observations: list = Field(default=[], sa_column=Column(JSON))
    recommended_outreach_angle: Optional[str] = Field(default=None)
    confidence: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric))
    model_used: Optional[str] = Field(default=None, max_length=100)
    sources_used: list = Field(default=[], sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (Index("idx_research_lead", "lead_id"),)
