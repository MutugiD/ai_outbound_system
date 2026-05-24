"""Analytics API endpoints — Wakili-Mkononi navy/gold dashboard charts."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import PaginationParams, get_current_user, paginated_response
from app.models.user import User
from app.schemas.analytics import (
    OverviewStatsResponse,
    CampaignAnalyticsResponse,
    CampaignStatsItem,
    SourceAnalyticsResponse,
    SourceStatsItem,
    ChannelAnalyticsResponse,
    ChannelStatsItem,
    PipelineAnalyticsResponse,
    PipelineStageItem,
    StageConversionItem,
    ScoreDistributionResponse,
    ScoreBandItem,
    SignalDistributionResponse,
    SignalCategoryItem,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ── Overview ───────────────────────────────────────────────────────────────


@router.get("/overview", response_model=OverviewStatsResponse)
async def get_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Top-line dashboard KPIs."""
    svc = AnalyticsService(db)
    stats = await svc.get_overview_stats(current_user.team_id)
    return OverviewStatsResponse(**stats)


# ── Campaign Analytics ─────────────────────────────────────────────────────


@router.get("/campaigns", response_model=CampaignAnalyticsResponse)
async def get_campaign_analytics(
    campaign_id: Optional[uuid.UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-campaign performance metrics — recharts-compatible."""
    svc = AnalyticsService(db)
    date_range = (date_from, date_to) if date_from and date_to else None
    results = await svc.get_campaign_analytics(
        team_id=current_user.team_id,
        campaign_id=campaign_id,
        date_range=date_range,
    )
    return CampaignAnalyticsResponse(campaigns=[CampaignStatsItem(**r) for r in results])


# ── Source Analytics ──────────────────────────────────────────────────────


@router.get("/sources", response_model=SourceAnalyticsResponse)
async def get_source_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lead source performance."""
    svc = AnalyticsService(db)
    results = await svc.get_source_analytics(current_user.team_id)
    return SourceAnalyticsResponse(sources=[SourceStatsItem(**r) for r in results])


# ── Channel Analytics ──────────────────────────────────────────────────────


@router.get("/channels", response_model=ChannelAnalyticsResponse)
async def get_channel_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Channel performance (email, linkedin, sms)."""
    svc = AnalyticsService(db)
    results = await svc.get_channel_analytics(current_user.team_id)
    return ChannelAnalyticsResponse(channels=[ChannelStatsItem(**r) for r in results])


# ── Pipeline Analytics ─────────────────────────────────────────────────────


@router.get("/pipeline", response_model=PipelineAnalyticsResponse)
async def get_pipeline_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pipeline stage distribution with conversion rates."""
    svc = AnalyticsService(db)
    result = await svc.get_pipeline_analytics(current_user.team_id)
    return PipelineAnalyticsResponse(
        stages=[PipelineStageItem(**s) for s in result["stages"]],
        conversions=[StageConversionItem(**c) for c in result["conversions"]],
    )


# ── Score Distribution ──────────────────────────────────────────────────────


@router.get("/scores", response_model=ScoreDistributionResponse)
async def get_score_distribution(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lead score band distribution — recharts bar chart."""
    svc = AnalyticsService(db)
    results = await svc.get_lead_score_distribution(current_user.team_id)
    return ScoreDistributionResponse(distribution=[ScoreBandItem(**r) for r in results])


# ── Signal Distribution ────────────────────────────────────────────────────


@router.get("/signals", response_model=SignalDistributionResponse)
async def get_signal_distribution(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Buying signal category distribution — recharts pie/bar chart."""
    svc = AnalyticsService(db)
    results = await svc.get_signal_category_distribution(current_user.team_id)
    return SignalDistributionResponse(signals=[SignalCategoryItem(**r) for r in results])
