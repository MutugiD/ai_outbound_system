"""Company Pydantic schemas for API request/response validation."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class CompanyCreate(BaseModel):
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    sub_industry: Optional[str] = None
    description: Optional[str] = None
    employee_count: Optional[int] = None
    employee_count_range: Optional[str] = None
    revenue_estimate: Optional[Decimal] = None
    revenue_range: Optional[str] = None
    funding_status: Optional[str] = None
    funding_total: Optional[Decimal] = None
    location: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    facebook_url: Optional[str] = None
    logo_url: Optional[str] = None
    phone: Optional[str] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    industry: Optional[str] = None
    sub_industry: Optional[str] = None
    description: Optional[str] = None
    employee_count: Optional[int] = None
    employee_count_range: Optional[str] = None
    revenue_estimate: Optional[Decimal] = None
    revenue_range: Optional[str] = None
    funding_status: Optional[str] = None
    funding_total: Optional[Decimal] = None
    location: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    facebook_url: Optional[str] = None
    logo_url: Optional[str] = None
    phone: Optional[str] = None


class CompanyResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    sub_industry: Optional[str] = None
    description: Optional[str] = None
    employee_count: Optional[int] = None
    employee_count_range: Optional[str] = None
    revenue_estimate: Optional[Decimal] = None
    revenue_range: Optional[str] = None
    funding_status: Optional[str] = None
    funding_total: Optional[Decimal] = None
    location: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    facebook_url: Optional[str] = None
    logo_url: Optional[str] = None
    phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    total: int
    page: int
    per_page: int
    pages: int