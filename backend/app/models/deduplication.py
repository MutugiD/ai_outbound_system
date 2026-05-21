"""DeduplicationMatch model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlmodel import Field, SQLModel


class DeduplicationMatch(SQLModel, table=True):
    __tablename__ = "deduplication_matches"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    new_lead_id: uuid.UUID = Field(foreign_key="leads.id")
    existing_lead_id: uuid.UUID = Field(foreign_key="leads.id")
    match_type: str = Field(max_length=50)  # email, domain, linkedin, fuzzy_name_company, phone
    confidence: Decimal = Field(sa_column_kwargs={"nullable": False})
    resolved: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
