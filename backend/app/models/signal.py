"""BuyingSignal model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Index, Numeric
from sqlmodel import Field, SQLModel


class BuyingSignal(SQLModel, table=True):
    __tablename__ = "buying_signals"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lead_id: uuid.UUID = Field(foreign_key="leads.id")
    category: str = Field(max_length=100)
    # hiring_ops_role, crm_pain, founder_burnout, onboarding_complaints,
    # workflow_inefficiency, support_overload, scaling_issues,
    # slow_lead_response, rapid_hiring, funding_event,
    # tool_stack_overload, manual_processes, poor_website_conversion,
    # poor_booking_flow, no_automation_layer, no_chatbot,
    # heavy_support_requests, negative_reviews, high_response_latency,
    # fragmented_tools
    evidence: str = Field(sa_column_kwargs={"nullable": False})
    source: str = Field(max_length=50)  # reddit, job_board, review, website, social, enrichment
    source_url: Optional[str] = Field(default=None, max_length=2048)
    confidence: Decimal = Field(default=Decimal("0.5"), sa_column=Column(Numeric))
    detection_method: str = Field(default="rule", max_length=20)  # rule, llm
    detected_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_signals_lead", "lead_id"),
        Index("idx_signals_category", "category"),
        Index("idx_signals_confidence", "confidence"),
    )