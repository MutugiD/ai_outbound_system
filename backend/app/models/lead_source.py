"""LeadSource model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Index, Numeric
from sqlmodel import Field, SQLModel


class LeadSource(SQLModel, table=True):
    __tablename__ = "lead_sources"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lead_id: uuid.UUID = Field(foreign_key="leads.id")
    source_type: str = Field(max_length=50)  # csv_import, reddit, website_crawler, google_search, apollo, manual, etc.
    source_url: Optional[str] = Field(default=None, max_length=2048)
    source_name: Optional[str] = Field(default=None, max_length=500)
    raw_text: Optional[str] = Field(default=None)
    detected_signal_text: Optional[str] = Field(default=None)
    confidence: Decimal = Field(default=Decimal("1.0"), sa_column=Column(Numeric))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_sources_lead", "lead_id"),
        Index("idx_sources_type", "source_type"),
    )
