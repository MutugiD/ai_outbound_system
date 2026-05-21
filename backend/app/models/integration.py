"""Integration model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, JSON, Numeric
from sqlmodel import Field, SQLModel


class Integration(SQLModel, table=True):
    __tablename__ = "integrations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id")
    service: str = Field(max_length=50)  # apollo, hunter, sendgrid, twilio, etc.
    config: dict = Field(default={}, sa_column=Column(JSON))

    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # UNIQUE(team_id, service) enforced via __table_args__ or DB migration