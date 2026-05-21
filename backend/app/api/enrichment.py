"""Enrichment, signal detection, scoring, and website audit API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user_from_token
from app.models.lead import Lead
from app.models.company import Company
from app.models.signal import BuyingSignal
from app.models.score import LeadScore
from app.models.audit import WebsiteAudit
from app.services.enrichment.enrichment_service import EnrichmentService
from app.services.ai.signal_detector import SignalDetector
from app.services.ai.scoring_service import ScoringService
from app.services.ai.audit_service import AuditService
from app.services.ai.llm_service import LLMService

router = APIRouter(prefix="", tags=["enrichment"])


async def _get_current_user(authorization: str = Depends(lambda: None), db: AsyncSession = Depends(get_db)):
    """Extract token and resolve user — placeholder until auth middleware is wired."""
    # In production, this would extract the JWT from the Authorization header
    # and validate it.  For now, we allow direct access for development.
    from app.models.user import User
    result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    if user:
        return user
    raise HTTPException(status_code=401, detail="Authentication required")


# ── Enrich lead ───────────────────────────────────────────────────────────────


@router.post("/leads/{lead_id}/enrich", status_code=status.HTTP_202_ACCEPTED)
async def enrich_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Trigger the full enrichment pipeline for a lead.

    Runs: contact enrichment, company enrichment, tech stack detection, email verification.
    """
    # Verify lead exists
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    service = EnrichmentService(db)
    try:
        result = await service.enrich_lead(lead_id)
        return {"message": "Lead enrichment completed", "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Enrichment failed: {exc}")


# ── Detect signals ────────────────────────────────────────────────────────────


@router.post("/leads/{lead_id}/detect-signals", status_code=status.HTTP_202_ACCEPTED)
async def detect_signals(
    lead_id: uuid.UUID,
    method: str = "both",
    model: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger signal detection for a lead.

    Parameters
    ----------
    method : str
        Detection method: 'rule', 'llm', or 'both' (default).
    model : str | None
        LLM model to use (default: gpt-4o-mini).
    """
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    llm = LLMService() if method in ("llm", "both") else None
    detector = SignalDetector(llm_service=llm)
    try:
        signals = await detector.detect_signals(lead_id, db, method=method)
        return {
            "message": "Signal detection completed",
            "lead_id": str(lead_id),
            "signals_detected": len(signals),
            "categories": [s.category for s in signals],
            "signal_ids": [str(s.id) for s in signals],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Signal detection failed: {exc}")


# ── Calculate score ───────────────────────────────────────────────────────────


@router.post("/leads/{lead_id}/score", status_code=status.HTTP_202_ACCEPTED)
async def score_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Trigger lead scoring for a lead.

    Calculates a multi-dimensional score based on signals, enrichment data,
    website audit, and contact info.
    """
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    service = ScoringService(db)
    try:
        score = await service.calculate_score(lead_id)
        return {
            "message": "Lead scored successfully",
            "lead_id": str(lead_id),
            "total_score": score.total_score,
            "score_band": score.score_band,
            "dimensions": {
                "buying_intent": score.buying_intent_score,
                "urgency": score.urgency_score,
                "operational_pain": score.operational_pain_score,
                "scaling_pressure": score.scaling_pressure_score,
                "budget_probability": score.budget_probability_score,
                "website_weakness": score.website_weakness_score,
                "contactability": score.contactability_score,
                "recency": score.recency_score,
            },
            "explanation": score.explanation,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scoring failed: {exc}")


# ── Audit website ──────────────────────────────────────────────────────────────


@router.post("/companies/{company_id}/audit-website", status_code=status.HTTP_202_ACCEPTED)
async def audit_website(
    company_id: uuid.UUID,
    domain: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a website audit for a company.

    Parameters
    ----------
    company_id : UUID
        The company ID to audit.
    domain : str | None
        Override domain (uses company.domain if not provided).
    """
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Use provided domain or fall back to company domain
    audit_domain = domain or company.domain
    if not audit_domain:
        raise HTTPException(status_code=400, detail="No domain available for this company")

    service = AuditService(db)
    try:
        audit = await service.audit_website(company_id, audit_domain)
        return {
            "message": "Website audit completed",
            "company_id": str(company_id),
            "domain": audit_domain,
            "website_score": audit.website_score,
            "page_speed_score": audit.page_speed_score,
            "mobile_score": audit.mobile_score,
            "has_chatbot": audit.has_chatbot,
            "has_booking": audit.has_booking,
            "has_contact_form": audit.has_contact_form,
            "has_email_capture": audit.has_email_capture,
            "has_crm_form": audit.has_crm_form,
            "has_tracking_scripts": audit.has_tracking_scripts,
            "has_support_widget": audit.has_support_widget,
            "broken_forms": audit.broken_forms,
            "weak_cta": audit.weak_cta,
            "sales_angle": audit.sales_angle,
            "technical_findings": audit.technical_findings,
            "conversion_findings": audit.conversion_findings,
            "automation_findings": audit.automation_findings,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Website audit failed: {exc}")