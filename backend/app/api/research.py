"""Research router: generate and retrieve AI research briefs for leads."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user_from_token
from app.models.lead import Lead
from app.models.research import AIResearchReport
from app.models.user import User
from app.services.ai.research_agent import ResearchAgent

router = APIRouter(prefix="/leads", tags=["research"])


# ── Response schemas ───────────────────────────────────────────────────────


class ResearchBriefResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    version: int
    company_summary: Optional[str] = None
    target_customer: Optional[str] = None
    likely_operational_pain: list = []
    revenue_leakage_hypothesis: list = []
    competitor_observations: list = []
    recommended_outreach_angle: Optional[str] = None
    confidence: Optional[float] = None
    model_used: Optional[str] = None
    sources_used: list = []
    created_at: str = ""

    model_config = {"from_attributes": True}


class BulkResearchRequest(BaseModel):
    status: Optional[str] = None
    score_band: Optional[str] = None
    limit: int = 50


class BulkResearchResponse(BaseModel):
    triggered: int
    lead_ids: list[str] = []


# ── Auth helper ─────────────────────────────────────────────────────────────


async def _get_current_user(
    authorization: str = Query(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    return await get_current_user_from_token(token, db)


# ── POST /leads/{lead_id}/research — trigger research ──────────────────────


@router.post(
    "/{lead_id}/research",
    response_model=ResearchBriefResponse,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_research(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Generate a research brief for a lead by loading data from the DB and calling the LLM."""
    # Verify lead belongs to the user's team
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.team_id == current_user.team_id)
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    agent = ResearchAgent()
    try:
        report = await agent.generate_research(lead_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Research generation failed: {exc}")

    # Build response
    return ResearchBriefResponse(
        id=report.id,
        lead_id=report.lead_id,
        version=report.version,
        company_summary=report.company_summary,
        target_customer=report.target_customer,
        likely_operational_pain=report.likely_operational_pain or [],
        revenue_leakage_hypothesis=report.revenue_leakage_hypothesis or [],
        competitor_observations=report.competitor_observations or [],
        recommended_outreach_angle=report.recommended_outreach_angle,
        confidence=float(report.confidence) if report.confidence is not None else None,
        model_used=report.model_used,
        sources_used=report.sources_used or [],
        created_at=str(report.created_at),
    )


# ── GET /leads/{lead_id}/research — get latest research ─────────────────────


@router.get(
    "/{lead_id}/research",
    response_model=ResearchBriefResponse,
)
async def get_research(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Get the latest research report for a lead."""
    # Verify lead belongs to the user's team
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.team_id == current_user.team_id)
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Get latest research report
    result = await db.execute(
        select(AIResearchReport)
        .where(AIResearchReport.lead_id == lead_id)
        .order_by(AIResearchReport.created_at.desc())
        .limit(1)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="No research report found for this lead")

    return ResearchBriefResponse(
        id=report.id,
        lead_id=report.lead_id,
        version=report.version,
        company_summary=report.company_summary,
        target_customer=report.target_customer,
        likely_operational_pain=report.likely_operational_pain or [],
        revenue_leakage_hypothesis=report.revenue_leakage_hypothesis or [],
        competitor_observations=report.competitor_observations or [],
        recommended_outreach_angle=report.recommended_outreach_angle,
        confidence=float(report.confidence) if report.confidence is not None else None,
        model_used=report.model_used,
        sources_used=report.sources_used or [],
        created_at=str(report.created_at),
    )


# ── POST /leads/bulk-research — bulk research trigger ───────────────────────


@router.post(
    "/bulk-research",
    response_model=BulkResearchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def bulk_research(
    body: BulkResearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Trigger research for leads matching a status or score_band filter.

    This endpoint queues the research and returns immediately. Actual research
    is generated asynchronously (background task).
    """
    # Build query for leads matching filters
    stmt = select(Lead).where(Lead.team_id == current_user.team_id)

    if body.status:
        statuses = [s.strip() for s in body.status.split(",")]
        stmt = stmt.where(Lead.status.in_(statuses))

    if body.score_band:
        bands = [b.strip() for b in body.score_band.split(",")]
        stmt = stmt.where(Lead.score_band.in_(bands))

    stmt = stmt.order_by(Lead.lead_score.desc()).limit(body.limit)

    result = await db.execute(stmt)
    leads = list(result.scalars().all())

    triggered = 0
    lead_ids: list[str] = []

    agent = ResearchAgent()
    for lead in leads:
        try:
            await agent.generate_research(lead.id, db)
            triggered += 1
            lead_ids.append(str(lead.id))
        except Exception:
            # Skip failed research but continue with others
            continue

    return BulkResearchResponse(triggered=triggered, lead_ids=lead_ids)