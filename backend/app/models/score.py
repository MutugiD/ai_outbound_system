"""LeadScore model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class LeadScore(SQLModel, table=True):
    __tablename__ = "lead_scores"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lead_id: uuid.UUID = Field(foreign_key="leads.id")
    total_score: int = Field(sa_column_kwargs={"nullable": False})
    score_band: str = Field(max_length=20)  # very_hot, hot, warm, weak, low
    buying_intent_score: Optional[int] = Field(default=None)
    urgency_score: Optional[int] = Field(default=None)
    operational_pain_score: Optional[int] = Field(default=None)
    scaling_pressure_score: Optional[int] = Field(default=None)
    budget_probability_score: Optional[int] = Field(default=None)
    website_weakness_score: Optional[int] = Field(default=None)
    contactability_score: Optional[int] = Field(default=None)
    recency_score: Optional[int] = Field(default=None)
    explanation: Optional[str] = Field(default=None)
    model_used: Optional[str] = Field(default=None, max_length=100)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_scores_lead", "lead_id"),
    )