"""Pydantic schemas for Analytics API responses — Wakili-Mkononi navy/gold dashboard."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Overview Stats ─────────────────────────────────────────────────────────

class OverviewStatsResponse(BaseModel):
    """Top-line dashboard KPIs."""
    total_leads: int = 0
    new_leads_today: int = 0
    hot_leads: int = 0
    messages_sent: int = 0
    reply_rate: float = 0.0
    interested_replies: int = 0
    booked_calls: int = 0
    pipeline_value: int = 0
    conversion_rate: float = 0.0
    top_source: Optional[str] = None
    top_campaign: Optional[str] = None


# ── Campaign Analytics ──────────────────────────────────────────────────────

class CampaignStatsItem(BaseModel):
    """Per-campaign analytics row."""
    campaign_id: uuid.UUID
    campaign_name: str
    enrolled: int = 0
    messages_sent: int = 0
    open_rate: float = 0.0
    reply_rate: float = 0.0
    positive_reply_rate: float = 0.0
    booked_calls: int = 0
    bounce_rate: float = 0.0


class CampaignAnalyticsResponse(BaseModel):
    """Campaign analytics response — recharts-compatible."""
    campaigns: list[CampaignStatsItem]


# ── Source Analytics ────────────────────────────────────────────────────────

class SourceStatsItem(BaseModel):
    """Per-source analytics row."""
    source: str
    leads: int = 0
    reply_rate: float = 0.0
    conversion_rate: float = 0.0


class SourceAnalyticsResponse(BaseModel):
    """Source analytics response."""
    sources: list[SourceStatsItem]


# ── Channel Analytics ──────────────────────────────────────────────────────

class ChannelStatsItem(BaseModel):
    """Per-channel analytics row."""
    channel: str
    messages: int = 0
    reply_rate: float = 0.0
    conversion_rate: float = 0.0


class ChannelAnalyticsResponse(BaseModel):
    """Channel analytics response."""
    channels: list[ChannelStatsItem]


# ── Pipeline Analytics ──────────────────────────────────────────────────────

class PipelineStageItem(BaseModel):
    """Pipeline stage distribution row."""
    stage: str
    count: int = 0


class StageConversionItem(BaseModel):
    """Conversion rate between two stages."""
    from_stage: str
    to_stage: str
    rate: float = 0.0


class PipelineAnalyticsResponse(BaseModel):
    """Pipeline analytics response — recharts funnel data."""
    stages: list[PipelineStageItem]
    conversions: list[StageConversionItem]


# ── Lead Score Distribution ────────────────────────────────────────────────

class ScoreBandItem(BaseModel):
    """Count of leads per score band."""
    score_band: str
    count: int = 0


class ScoreDistributionResponse(BaseModel):
    """Lead score distribution response — recharts bar chart."""
    distribution: list[ScoreBandItem]


# ── Signal Category Distribution ───────────────────────────────────────────

class SignalCategoryItem(BaseModel):
    """Count of buying signals per category."""
    category: str
    count: int = 0


class SignalDistributionResponse(BaseModel):
    """Buying signal distribution response — recharts pie/bar."""
    signals: list[SignalCategoryItem]