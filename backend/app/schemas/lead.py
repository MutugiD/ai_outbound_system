"""Lead Pydantic schemas for API request/response validation."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Create ────────────────────────────────────────────────────────────────


class LeadCreate(BaseModel):
    company_id: Optional[uuid.UUID] = None
    contact_id: Optional[uuid.UUID] = None
    status: str = "new"
    pipeline_stage: str = "new"
    assigned_user_id: Optional[uuid.UUID] = None
    next_action: Optional[str] = None
    next_action_at: Optional[datetime] = None

    # Nested creation helpers (optional)
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    company_industry: Optional[str] = None
    contact_first_name: Optional[str] = None
    contact_last_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_title: Optional[str] = None
    contact_linkedin_url: Optional[str] = None


# ── Update ────────────────────────────────────────────────────────────────


class LeadUpdate(BaseModel):
    status: Optional[str] = None
    pipeline_stage: Optional[str] = None
    lead_score: Optional[int] = None
    score_band: Optional[str] = None
    assigned_user_id: Optional[uuid.UUID] = None
    next_action: Optional[str] = None
    next_action_at: Optional[datetime] = None
    company_id: Optional[uuid.UUID] = None
    contact_id: Optional[uuid.UUID] = None


# ── Response ──────────────────────────────────────────────────────────────


class LeadResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    company_id: Optional[uuid.UUID] = None
    contact_id: Optional[uuid.UUID] = None
    status: str
    pipeline_stage: str
    lead_score: int
    score_band: str
    assigned_user_id: Optional[uuid.UUID] = None
    last_contacted_at: Optional[datetime] = None
    next_action: Optional[str] = None
    next_action_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadDetailResponse(LeadResponse):
    """Lead with nested company/contact summary."""

    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    contact_full_name: Optional[str] = None
    contact_email: Optional[str] = None


# ── List ──────────────────────────────────────────────────────────────────


class LeadListResponse(BaseModel):
    items: list[LeadResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ── Filters ───────────────────────────────────────────────────────────────


class LeadFilters(BaseModel):
    status: Optional[list[str]] = None
    score_band: Optional[list[str]] = None
    pipeline_stage: Optional[list[str]] = None
    source: Optional[list[str]] = None
    industry: Optional[list[str]] = None
    search: Optional[str] = None
    assigned_user_id: Optional[uuid.UUID] = None
    min_score: Optional[int] = None
    max_score: Optional[int] = None
