"""Leads router: CRUD, import, filtering, pagination, and scraping endpoints."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import PaginationParams, get_current_user, paginated_response
from app.schemas.lead import (
    LeadCreate,
    LeadListResponse,
    LeadResponse,
    LeadUpdate,
)
from app.schemas.pipeline import PipelineTransitionDetailResponse, PipelineTransitionRequest
from app.models.pipeline import PipelineTransition
from app.models.note import LeadNote
from app.services.lead_service import LeadService
from app.services.scraping.csv_adapter import CSVAdapter
from app.services.scraping.reddit_adapter import RedditAdapter
from app.services.scraping.linkedin_adapter import LinkedInJobsAdapter
from app.services.scraping.website_adapter import WebsiteAdapter
from app.services.scraping.base_adapter import RawLead
from app.rate_limit import rate_limit
from services.crm_service.ingestion import ingest_raw_leads

router = APIRouter(prefix="/leads", tags=["leads"])

# ── Reusable adapters ──────────────────────────────────────────────────────

_csv_adapter = CSVAdapter()
_reddit_adapter = RedditAdapter()
_linkedin_adapter = LinkedInJobsAdapter()
_website_adapter = WebsiteAdapter()


# ── List leads ────────────────────────────────────────────────────────────


@router.get("", response_model=LeadListResponse)
async def list_leads(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    score_band: Optional[str] = Query(None),
    pipeline_stage: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None),
    max_score: Optional[int] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = LeadService(db)
    filters = {}
    if status:
        filters["status"] = status.split(",")
    if score_band:
        filters["score_band"] = score_band.split(",")
    if pipeline_stage:
        filters["pipeline_stage"] = pipeline_stage.split(",")
    if source:
        filters["source"] = source.split(",")
    if industry:
        filters["industry"] = industry.split(",")
    if search:
        filters["search"] = search
    if min_score is not None:
        filters["min_score"] = min_score
    if max_score is not None:
        filters["max_score"] = max_score

    items, total = await svc.list_leads(
        team_id=current_user.team_id,
        filters=filters,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    params = PaginationParams(page=page, per_page=per_page)
    return paginated_response(
        [LeadResponse.model_validate(l, from_attributes=True) for l in items],
        total,
        params,
    )


# ── Create lead ───────────────────────────────────────────────────────────


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    body: LeadCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = LeadService(db)
    lead = await svc.create_lead(team_id=current_user.team_id, user_id=current_user.id, data=body)
    return LeadResponse.model_validate(lead, from_attributes=True)


# ── Get lead ──────────────────────────────────────────────────────────────


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = LeadService(db)
    lead = await svc.get_lead(lead_id, team_id=current_user.team_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return LeadResponse.model_validate(lead, from_attributes=True)


# ── Update lead ──────────────────────────────────────────────────────────


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: uuid.UUID,
    body: LeadUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = LeadService(db)
    lead = await svc.update_lead(lead_id, team_id=current_user.team_id, user_id=current_user.id, data=body)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return LeadResponse.model_validate(lead, from_attributes=True)


# ── Delete lead (soft — sets status suppressed) ───────────────────────────


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = LeadService(db)
    await svc.delete_lead(lead_id, team_id=current_user.team_id, user_id=current_user.id)


# ── Pipeline transition ─────────────────────────────────────────────────


@router.post("/{lead_id}/transition", response_model=PipelineTransitionDetailResponse)
async def transition_lead(
    lead_id: uuid.UUID,
    body: PipelineTransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Transition a lead's pipeline stage, creating a PipelineTransition record and optional note."""
    from datetime import datetime

    svc = LeadService(db)
    lead = await svc.get_lead(lead_id, team_id=current_user.team_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    from_stage = lead.pipeline_stage

    # Create the transition record
    transition = PipelineTransition(
        lead_id=lead_id,
        from_stage=from_stage,
        to_stage=body.to_stage,
        reason=body.reason,
        transitioned_by=current_user.id,
    )
    db.add(transition)

    # Update the lead's pipeline stage
    lead.pipeline_stage = body.to_stage
    lead.updated_at = datetime.utcnow()
    db.add(lead)

    # Optionally create a note
    note_id = None
    if body.note_content:
        note = LeadNote(
            lead_id=lead_id,
            user_id=current_user.id,
            content=body.note_content,
            note_type=body.note_type or "update",
        )
        db.add(note)
        await db.flush()
        note_id = note.id

    await db.flush()
    await db.refresh(transition)

    # Log activity
    await svc._log_activity(
        team_id=current_user.team_id,
        user_id=current_user.id,
        lead_id=lead_id,
        action="lead.pipeline_transition",
        details={"from_stage": from_stage, "to_stage": body.to_stage, "reason": body.reason},
    )

    resp = PipelineTransitionDetailResponse.model_validate(transition, from_attributes=True)
    resp.note_id = note_id
    return resp


# ═══════════════════════════════════════════════════════════════════════════
# SCRAPING / IMPORT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════


async def _ingest_leads(
    raw_leads: list[RawLead],
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Common pipeline: normalize → deduplicate → persist a batch of raw leads."""
    return await ingest_raw_leads(raw_leads=raw_leads, team_id=team_id, user_id=user_id, db=db)


# ── Import CSV ─────────────────────────────────────────────────────────────


@router.post(
    "/import-csv",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(10, 60, "leads_import_csv"))],
)
async def import_csv(
    file: UploadFile = File(..., description="CSV file to import"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Upload a CSV file and import leads from it."""
    if not file.filename.endswith((".csv", ".txt")):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    try:
        raw_leads = await _csv_adapter.search({"file": file})
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"CSV parsing error: {exc}")

    result = await _ingest_leads(raw_leads, current_user.team_id, current_user.id, db)
    return {"message": "CSV import processed", **result}


# ── Scrape Reddit ──────────────────────────────────────────────────────────


@router.post(
    "/scrape-reddit",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(20, 60, "leads_scrape_reddit"))],
)
async def scrape_reddit(
    keywords: Optional[list[str]] = Query(None, description="Buying signal keywords to search for"),
    subreddits: Optional[list[str]] = Query(None, description="Subreddits to search"),
    limit: int = Query(25, ge=1, le=100, description="Max results per subreddit"),
    timeframe: str = Query("week", description="Time window: hour, day, week, month, year, all"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Search Reddit for buying-signal posts and import as leads."""
    query = {}
    if keywords:
        query["keywords"] = keywords
    if subreddits:
        query["subreddits"] = subreddits
    query["limit"] = limit
    query["timeframe"] = timeframe

    try:
        raw_leads = await _reddit_adapter.search(query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reddit scraping error: {exc}")
    finally:
        await _reddit_adapter.close()

    result = await _ingest_leads(raw_leads, current_user.team_id, current_user.id, db)
    return {"message": "Reddit scrape processed", **result}


# ── Scrape LinkedIn ────────────────────────────────────────────────────────


@router.post(
    "/scrape-linkedin",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(20, 60, "leads_scrape_linkedin"))],
)
async def scrape_linkedin(
    keywords: str = Query(..., description="Job search keywords"),
    location: str = Query("United States", description="Location filter"),
    time_window: str = Query("7d", description="Time window: 24h, 7d, 30d"),
    remote: bool = Query(True, description="Filter for remote jobs"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Scrape LinkedIn public job search (guest mode, no login) and import as leads."""
    query = {
        "keywords": keywords,
        "location": location,
        "time_window": time_window,
        "remote": remote,
        "limit": limit,
    }

    try:
        raw_leads = await _linkedin_adapter.search(query)
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"Playwright not installed: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LinkedIn scraping error: {exc}")
    finally:
        await _linkedin_adapter.close()

    result = await _ingest_leads(raw_leads, current_user.team_id, current_user.id, db)
    return {"message": "LinkedIn scrape processed", **result}


# ── Scrape Website ─────────────────────────────────────────────────────────


@router.post(
    "/scrape-website",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(20, 60, "leads_scrape_website"))],
)
async def scrape_website(
    domain: str = Query(..., description="Domain to crawl (e.g. acme.com)"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Crawl a company website for contact/industry info and import as leads."""
    query = {"domain": domain}

    try:
        raw_leads = await _website_adapter.search(query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Website crawling error: {exc}")
    finally:
        await _website_adapter.close()

    if not raw_leads:
        raise HTTPException(status_code=404, detail=f"No useful content found on {domain}")

    result = await _ingest_leads(raw_leads, current_user.team_id, current_user.id, db)
    return {"message": "Website crawl processed", **result}
