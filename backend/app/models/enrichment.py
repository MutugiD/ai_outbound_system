"""EnrichmentRecord model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Index, JSON, Numeric
from sqlmodel import Field, SQLModel


class EnrichmentRecord(SQLModel, table=True):
    __tablename__ = "enrichment_records"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lead_id: uuid.UUID = Field(foreign_key="leads.id")
    provider: str = Field(max_length=50)  # apollo, hunter, pdl, dropcontact, builtwith
    enrichment_type: str = Field(max_length=50)  # contact, company, tech_stack, ads
    data: dict = Field(default={}, sa_column=Column(JSON))

    confidence: Decimal = Field(default=Decimal("0.5"), sa_column=Column(Numeric))
    enriched_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(default=None)

    __table_args__ = (
        Index("idx_enrichment_lead", "lead_id"),
        Index("idx_enrichment_provider", "provider"),
    )
