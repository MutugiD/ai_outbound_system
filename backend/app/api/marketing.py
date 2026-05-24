"""Marketing pipeline API (multi-client / quota-aware).

Implements:
  Brand Brain -> Audience Signals -> Drafts -> Analytics

Audience discovery runs async via Celery to support many teams with different
scrape volumes while enforcing hard per-team budgets.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import PaginationParams, get_current_user, paginated_response
from app.models.marketing import AudienceScanJob, AudienceSignal, MarketingUsageDaily, SocialPostDraft
from app.models.team import Team
from app.models.user import User
from app.rate_limit import rate_limit
from app.security_utils import sanitize_log
from app.schemas.marketing import (
    AudienceScanCreate,
    AudienceScanJobResponse,
    AudienceSignalResponse,
    BrandBrainDeriveRequest,
    BrandBrainDeriveResponse,
    MarketingOverviewResponse,
    MarketingSettingsUpdate,
    PostDraftGenerateRequest,
    PostDraftResponse,
)
from app.services.marketing.brand_brain import derive_brand_brain
from app.services.marketing.budgets import deep_merge_dict, enforce_scan_request_budget, get_marketing_settings
from app.workers.marketing_tasks import run_audience_scan as run_audience_scan_task

router = APIRouter(prefix="/marketing", tags=["marketing"])


@router.put("/settings", response_model=dict)
async def update_marketing_settings(
    body: MarketingSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Merge a partial marketing settings update into Team.settings['marketing']."""
    result = await db.execute(select(Team).where(Team.id == current_user.team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    settings = dict(team.settings or {})
    marketing_current = dict(settings.get("marketing") or {})
    marketing_next = deep_merge_dict(marketing_current, body.marketing or {})
    settings["marketing"] = marketing_next

    team.settings = settings
    team.updated_at = datetime.utcnow()
    db.add(team)
    await db.flush()
    await db.refresh(team)

    return {"marketing": get_marketing_settings(team)}


@router.post("/brand-brain/derive", response_model=BrandBrainDeriveResponse)
async def brand_brain_derive(
    body: BrandBrainDeriveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rl=Depends(rate_limit(limit=10, window_seconds=60, scope="marketing_brand_brain")),
):
    """Derive a draft Brand Brain from a website URL (SSRF-safe crawl)."""
    result = await db.execute(select(Team).where(Team.id == current_user.team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    brain = await derive_brand_brain(body.website_url)

    if body.store:
        settings = dict(team.settings or {})
        marketing_current = dict(settings.get("marketing") or {})
        marketing_current["brand_brain"] = brain
        settings["marketing"] = marketing_current
        team.settings = settings
        team.updated_at = datetime.utcnow()
        db.add(team)
        await db.flush()

    return BrandBrainDeriveResponse(brand_brain=brain)


def _resolve_scan_params(team: Team, body: AudienceScanCreate) -> dict[str, Any]:
    marketing = get_marketing_settings(team)
    budgets = marketing.get("budgets") or {}

    enabled_platforms = list((marketing.get("platforms") or {}).get("enabled") or [])
    platforms = body.platforms or enabled_platforms or ["reddit", "hn"]

    discovery = dict(marketing.get("discovery") or {})
    brand_brain = dict(marketing.get("brand_brain") or {})

    keywords = body.keywords or discovery.get("keywords") or brand_brain.get("keywords") or []
    subreddits = body.subreddits or discovery.get("subreddits") or []
    timeframe = body.timeframe or discovery.get("timeframe") or "week"

    default_per_scan = int(budgets.get("per_scan_max_results") or 25)
    requested_per_scan = body.per_scan_max_results or default_per_scan
    per_scan_max_results = max(1, min(int(requested_per_scan), default_per_scan))

    return {
        "platforms": platforms,
        "keywords": keywords,
        "subreddits": subreddits,
        "timeframe": timeframe,
        "per_scan_max_results": per_scan_max_results,
    }


@router.post("/audience-scans", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_audience_scan(
    body: AudienceScanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rl=Depends(rate_limit(limit=20, window_seconds=60, scope="marketing_audience_scans")),
):
    """Enqueue an async audience scan for the current team (quota enforced)."""
    result = await db.execute(select(Team).where(Team.id == current_user.team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    today = date.today()
    await enforce_scan_request_budget(db, team, today)

    params = _resolve_scan_params(team, body)
    job = AudienceScanJob(team_id=team.id, params=params, status="queued")
    db.add(job)
    await db.flush()
    await db.refresh(job)

    try:
        async_result = run_audience_scan_task.delay(str(job.id))
    except Exception:
        job.status = "failed"
        job.error = "Task queue unavailable"
        db.add(job)
        raise HTTPException(status_code=503, detail="Task queue unavailable")

    return {"job_id": str(job.id), "task_id": async_result.id, "status": job.status}


@router.get("/audience-scans/{job_id}", response_model=AudienceScanJobResponse)
async def get_audience_scan_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(AudienceScanJob).where(AudienceScanJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job or job.team_id != current_user.team_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return AudienceScanJobResponse.model_validate(job, from_attributes=True)


@router.get("/audience-signals", response_model=dict)
async def list_audience_signals(
    platform: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    params: PaginationParams = Depends(),
):
    q = select(AudienceSignal).where(AudienceSignal.team_id == current_user.team_id)
    if platform:
        q = q.where(AudienceSignal.platform == platform)
    if search:
        term = f"%{search}%"
        q = q.where(
            (AudienceSignal.title.ilike(term))
            | (AudienceSignal.body_excerpt.ilike(term))
            | (AudienceSignal.community.ilike(term))
        )

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(AudienceSignal.created_at.desc()).offset(params.offset).limit(params.limit)
    result = await db.execute(q)
    items = [AudienceSignalResponse.model_validate(x, from_attributes=True).model_dump() for x in result.scalars()]
    return paginated_response(items, total, params)


def _draft_from_context(platform: str, goal: str, voice_rules: list[str], context: str, variant: int) -> str:
    # Deterministic fallback (works without OPENAI_API_KEY). Keep it short and human.
    base = [
        f"Hook: {context}",
        "",
        f"I'm building something for {goal}.",
        "Curious if anyone else is dealing with this — what have you tried so far?",
    ]
    if platform.lower() in ("reddit", "hn"):
        base.append("")
        base.append("Not selling here — genuinely want to learn from your experience.")
    if voice_rules:
        base.append("")
        base.append(f"(Voice rules: {', '.join(voice_rules[:3])})")
    text = "\n".join(base).strip()
    if variant:
        text = text.replace("Curious if anyone else is dealing with this", "Quick question for folks here")
    return text[:4000]


@router.post("/post-drafts/generate", response_model=dict)
async def generate_post_drafts(
    body: PostDraftGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rl=Depends(rate_limit(limit=30, window_seconds=60, scope="marketing_post_drafts")),
):
    """Generate draft social posts from Brand Brain + optional AudienceSignal context."""
    team_result = await db.execute(select(Team).where(Team.id == current_user.team_id))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    marketing = get_marketing_settings(team)
    voice_rules = list((marketing.get("brand_brain") or {}).get("voice_rules") or [])

    signal = None
    if body.audience_signal_id:
        sres = await db.execute(select(AudienceSignal).where(AudienceSignal.id == body.audience_signal_id))
        signal = sres.scalar_one_or_none()
        if not signal or signal.team_id != current_user.team_id:
            raise HTTPException(status_code=404, detail="Audience signal not found")

    context = "a common pain founders have with marketing"
    if signal:
        parts = [signal.title or "", signal.community or ""]
        context = sanitize_log(" — ".join([p for p in parts if p]).strip()) or context

    # Usage row (draft counters)
    today = date.today()
    usage_res = await db.execute(
        select(MarketingUsageDaily).where(
            MarketingUsageDaily.team_id == current_user.team_id, MarketingUsageDaily.day == today
        )
    )
    usage = usage_res.scalar_one_or_none()
    if not usage:
        usage = MarketingUsageDaily(team_id=current_user.team_id, day=today)
        db.add(usage)
        await db.flush()

    drafts: list[SocialPostDraft] = []
    for i in range(body.variants):
        content = _draft_from_context(body.platform, body.goal, voice_rules, context, i)
        draft = SocialPostDraft(
            team_id=current_user.team_id,
            platform=body.platform,
            goal=body.goal,
            audience_signal_id=body.audience_signal_id,
            content=content,
            variant=i,
            extra={"source": "template_v1"},
        )
        db.add(draft)
        drafts.append(draft)

    usage.drafts_generated += len(drafts)
    usage.updated_at = datetime.utcnow()
    db.add(usage)
    await db.flush()

    out = [
        PostDraftResponse(
            id=d.id,
            platform=d.platform,
            goal=d.goal,
            audience_signal_id=d.audience_signal_id,
            content=d.content,
            variant=d.variant,
            created_at=d.created_at,
        ).model_dump()
        for d in drafts
    ]
    return {"items": out, "count": len(out)}


@router.get("/analytics/overview", response_model=MarketingOverviewResponse)
async def marketing_overview(
    day: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return per-day marketing usage counters for the current team."""
    day = day or date.today()
    result = await db.execute(
        select(MarketingUsageDaily).where(
            MarketingUsageDaily.team_id == current_user.team_id, MarketingUsageDaily.day == day
        )
    )
    usage = result.scalar_one_or_none() or MarketingUsageDaily(team_id=current_user.team_id, day=day)
    return MarketingOverviewResponse(
        day=usage.day,
        scans_requested=usage.scans_requested,
        scans_completed=usage.scans_completed,
        signals_saved=usage.signals_saved,
        drafts_generated=usage.drafts_generated,
        llm_tokens_used=usage.llm_tokens_used,
    )
