"""Leads router: CRUD, import, filtering, pagination, and scraping endpoints."""

import io
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import PaginationParams, get_current_user_from_token, paginated_response
from app.models.lead import Lead
from app.models.company import Company
from app.models.contact import Contact
from app.models.lead_source import LeadSource
from app.models.activity import ActivityLog
from app.schemas.lead import (
    LeadCreate,
    LeadUpdate,
    LeadResponse,
    LeadListResponse,
)
from app.schemas.pipeline import PipelineTransitionRequest, PipelineTransitionResponse, PipelineTransitionDetailResponse
from app.models.pipeline import PipelineTransition
from app.models.note import LeadNote
from app.services.lead_service import LeadService
from app.services.scraping.csv_adapter import CSVAdapter
from app.services.scraping.reddit_adapter import RedditAdapter
from app.services.scraping.linkedin_adapter import LinkedInJobsAdapter
from app.services.scraping.website_adapter import WebsiteAdapter
from app.services.scraping.normalizer import LeadNormalizer
from app.services.scraping.deduplicator import LeadDeduplicator
from app.services.scraping.base_adapter import RawLead, NormalizedLead

router = APIRouter(prefix="/leads", tags=["leads"])

# ── Reusable adapters ──────────────────────────────────────────────────────

_csv_adapter = CSVAdapter()
_reddit_adapter = RedditAdapter()
_linkedin_adapter = LinkedInJobsAdapter()
_website_adapter = WebsiteAdapter()
_normalizer = LeadNormalizer()


async def _get_current_user(authorization: str = Query(..., alias="Authorization"), db: AsyncSession = Depends(get_db)):
    """Extract token from header and resolve user."""
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    return await get_current_user_from_token(token, db)


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
    current_user=Depends(_get_current_user),
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
    current_user=Depends(_get_current_user),
):
    svc = LeadService(db)
    lead = await svc.create_lead(team_id=current_user.team_id, user_id=current_user.id, data=body)
    return LeadResponse.model_validate(lead, from_attributes=True)


# ── Get lead ──────────────────────────────────────────────────────────────


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_get_current_user),
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
    current_user=Depends(_get_current_user),
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
    current_user=Depends(_get_current_user),
):
    svc = LeadService(db)
    await svc.delete_lead(lead_id, team_id=current_user.team_id, user_id=current_user.id)


# ── Pipeline transition ─────────────────────────────────────────────────


@router.post("/{lead_id}/transition", response_model=PipelineTransitionDetailResponse)
async def transition_lead(
    lead_id: uuid.UUID,
    body: PipelineTransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_get_current_user),
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
    """Common pipeline: normalize → deduplicate → persist a batch of raw leads.

    Returns a summary dict with counts.
    """
    dedup = LeadDeduplicator(db)
    created = 0
    merged = 0
    skipped = 0
    errors = 0
    sources_created = 0

    for raw in raw_leads:
        try:
            normalized = _normalizer.normalize(raw)

            # Validate
            if (
                not normalized.company_name
                and not normalized.company_domain
                and not normalized.email
                and not normalized.linkedin_url
            ):
                skipped += 1
                continue

            # Deduplicate and persist
            lead = await dedup.merge_or_create(normalized, team_id, user_id)
            if lead:
                # Create lead_source record
                source = LeadSource(
                    lead_id=lead.id,
                    source_type=raw.source_type,
                    source_url=raw.source_url,
                    source_name=raw.raw_data.get("title") or raw.raw_data.get("subreddit") or raw.source_type,
                    raw_text=raw.raw_text[:4000] if raw.raw_text else None,
                    detected_signal_text=",".join(raw.raw_data.get("buying_signals", []))
                    if raw.raw_data.get("buying_signals")
                    else None,
                )
                db.add(source)
                sources_created += 1

                # Check if this was a merge
                existing_check = await dedup.check_duplicate(normalized, team_id)
                if existing_check.is_duplicate:
                    merged += 1
                else:
                    created += 1
            else:
                errors += 1

        except Exception as exc:
            errors += 1
            import logging

            logging.getLogger(__name__).warning("Error ingesting lead: %s", exc)
            continue

    await db.flush()
    return {
        "total": len(raw_leads),
        "created": created,
        "merged": merged,
        "skipped": skipped,
        "errors": errors,
        "sources_created": sources_created,
    }


# ── Import CSV ─────────────────────────────────────────────────────────────


@router.post("/import-csv", status_code=status.HTTP_202_ACCEPTED)
async def import_csv(
    file: UploadFile = File(..., description="CSV file to import"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_get_current_user),
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


@router.post("/scrape-reddit", status_code=status.HTTP_202_ACCEPTED)
async def scrape_reddit(
    keywords: Optional[list[str]] = Query(None, description="Buying signal keywords to search for"),
    subreddits: Optional[list[str]] = Query(None, description="Subreddits to search"),
    limit: int = Query(25, ge=1, le=100, description="Max results per subreddit"),
    timeframe: str = Query("week", description="Time window: hour, day, week, month, year, all"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_get_current_user),
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


@router.post("/scrape-linkedin", status_code=status.HTTP_202_ACCEPTED)
async def scrape_linkedin(
    keywords: str = Query(..., description="Job search keywords"),
    location: str = Query("United States", description="Location filter"),
    time_window: str = Query("7d", description="Time window: 24h, 7d, 30d"),
    remote: bool = Query(True, description="Filter for remote jobs"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_get_current_user),
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


@router.post("/scrape-website", status_code=status.HTTP_202_ACCEPTED)
async def scrape_website(
    domain: str = Query(..., description="Domain to crawl (e.g. acme.com)"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_get_current_user),
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
