"""Company model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Index, Numeric, Text
from sqlmodel import Field, SQLModel


class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id", index=True)
    name: str = Field(max_length=500)
    domain: Optional[str] = Field(default=None, unique=True, max_length=500)
    industry: Optional[str] = Field(default=None, max_length=255)
    sub_industry: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None)
    employee_count: Optional[int] = Field(default=None)
    employee_count_range: Optional[str] = Field(default=None, max_length=50)
    revenue_estimate: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric))
    revenue_range: Optional[str] = Field(default=None, max_length=50)
    funding_status: Optional[str] = Field(default=None, max_length=50)
    funding_total: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric))
    location: Optional[str] = Field(default=None, max_length=500)
    country: Optional[str] = Field(default=None, max_length=100)
    timezone: Optional[str] = Field(default=None, max_length=100)
    linkedin_url: Optional[str] = Field(default=None, max_length=1024)
    twitter_url: Optional[str] = Field(default=None, max_length=1024)
    facebook_url: Optional[str] = Field(default=None, max_length=1024)
    logo_url: Optional[str] = Field(default=None, max_length=1024)
    phone: Optional[str] = Field(default=None, max_length=50)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_companies_team", "team_id"),
        Index("idx_companies_domain", "domain"),
        Index("idx_companies_industry", "industry"),
    )
