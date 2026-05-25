"""Enrichment, signal detection, scoring, and website audit API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.lead import Lead
from app.models.company import Company
from app.models.user import User
from app.rate_limit import rate_limit

router = APIRouter(prefix="", tags=["enrichment"])


# ── Enrich lead ───────────────────────────────────────────────────────────────


@router.post(
    "/leads/{lead_id}/enrich",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(20, 60, "enrich_lead"))],
)
async def enrich_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger the full enrichment pipeline for a lead.

    Runs: contact enrichment, company enrichment, tech stack detection, email verification.
    """
    # Verify lead exists
    result = await db.execute(select(Lead).where(Lead.id == lead_id, Lead.team_id == current_user.team_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    from app.workers.enrichment_tasks import enrich_lead as enrich_task

    async_result = enrich_task.delay(str(lead_id))
    return {"message": "Lead enrichment queued", "lead_id": str(lead_id), "task_id": async_result.id}


# ── Detect signals ────────────────────────────────────────────────────────────


@router.post(
    "/leads/{lead_id}/detect-signals",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(20, 60, "detect_signals"))],
)
async def detect_signals(
    lead_id: uuid.UUID,
    method: str = "both",
    model: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger signal detection for a lead.

    Parameters
    ----------
    method : str
        Detection method: 'rule', 'llm', or 'both' (default).
    model : str | None
        LLM model to use (default: configured LLM_MODEL).
    """
    result = await db.execute(select(Lead).where(Lead.id == lead_id, Lead.team_id == current_user.team_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    from app.workers.ai_tasks import detect_buying_signals as detect_task

    async_result = detect_task.delay(str(lead_id), method=method, model=model)
    return {"message": "Signal detection queued", "lead_id": str(lead_id), "task_id": async_result.id}


# ── Calculate score ───────────────────────────────────────────────────────────


@router.post(
    "/leads/{lead_id}/score",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(20, 60, "score_lead"))],
)
async def score_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger lead scoring for a lead.

    Calculates a multi-dimensional score based on signals, enrichment data,
    website audit, and contact info.
    """
    result = await db.execute(select(Lead).where(Lead.id == lead_id, Lead.team_id == current_user.team_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    from app.workers.ai_tasks import calculate_lead_score as score_task

    async_result = score_task.delay(str(lead_id))
    return {"message": "Lead scoring queued", "lead_id": str(lead_id), "task_id": async_result.id}


# ── Audit website ──────────────────────────────────────────────────────────────


@router.post(
    "/companies/{company_id}/audit-website",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(20, 60, "audit_website"))],
)
async def audit_website(
    company_id: uuid.UUID,
    domain: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger a website audit for a company.

    Parameters
    ----------
    company_id : UUID
        The company ID to audit.
    domain : str | None
        Override domain (uses company.domain if not provided).
    """
    result = await db.execute(select(Company).where(Company.id == company_id, Company.team_id == current_user.team_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Use provided domain or fall back to company domain
    audit_domain = domain or company.domain
    if not audit_domain:
        raise HTTPException(status_code=400, detail="No domain available for this company")

    from app.workers.ai_tasks import audit_company_website as audit_task

    async_result = audit_task.delay(str(company_id), domain=audit_domain)
    return {
        "message": "Website audit queued",
        "company_id": str(company_id),
        "domain": audit_domain,
        "task_id": async_result.id,
    }
