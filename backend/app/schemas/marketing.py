"""Schemas for the marketing + outreach pipeline (multi-client / team-scoped)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict


class MarketingSettingsUpdate(BaseModel):
    """Partial update merged into Team.settings['marketing']."""

    marketing: dict[str, Any] = Field(default_factory=dict)


class BrandBrainDeriveRequest(BaseModel):
    website_url: str
    additional_context: Optional[str] = None  # Extra info about the product from user input
    store: bool = True


class BrandBrainDeriveResponse(BaseModel):
    brand_brain: dict[str, Any]


class AudienceScanCreate(BaseModel):
    platforms: list[str] = Field(default_factory=list)  # reddit, hn, x, linkedin
    keywords: list[str] = Field(default_factory=list)
    subreddits: list[str] = Field(default_factory=list)
    timeframe: str = "week"  # hour/day/week/month/year/all
    per_scan_max_results: Optional[int] = None


class AudienceScanJobResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    status: str
    params: dict[str, Any]
    found_count: int
    kept_count: int
    deduped_count: int
    stop_reason: Optional[str]
    error: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class AudienceSignalResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: uuid.UUID
    team_id: uuid.UUID
    platform: str
    source_url: str
    external_id: Optional[str]
    title: Optional[str]
    body_excerpt: Optional[str]
    author: Optional[str]
    community: Optional[str]
    engagement: Optional[int]
    matched_keywords: list[Any]
    intent_label: Optional[str]
    confidence: Optional[float]
    metadata: dict[str, Any] = Field(default_factory=dict, alias="extra")
    created_at: datetime
    source_created_at: Optional[datetime]


class PostDraftGenerateRequest(BaseModel):
    platform: str
    goal: str = "drive_interest"
    audience_signal_id: Optional[uuid.UUID] = None
    variants: int = Field(default=3, ge=1, le=5)


class PostDraftResponse(BaseModel):
    id: uuid.UUID
    platform: str
    goal: Optional[str]
    audience_signal_id: Optional[uuid.UUID]
    content: str
    variant: int
    created_at: datetime


class MarketingOverviewResponse(BaseModel):
    day: date
    scans_requested: int
    scans_completed: int
    signals_saved: int
    drafts_generated: int
    llm_tokens_used: int
