"""Campaigns router: CRUD, enrollment, lifecycle, and analytics endpoints."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import PaginationParams, get_current_user, paginated_response
from app.models.user import User
from app.schemas.outreach import (
    CampaignCreate,
    CampaignUpdate,
    CampaignResponse,
    CampaignDetailResponse,
    CampaignListResponse,
    CampaignStepCreate,
    CampaignStepUpdate,
    CampaignStepResponse,
    CampaignEnrollmentResponse,
    EnrollLeadsRequest,
    CampaignStatsResponse,
)
from app.services.campaign_service import CampaignService

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


# ── List campaigns ────────────────────────────────────────────────────────


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all campaigns for the current team."""
    svc = CampaignService(db)
    campaigns, total = await svc.list_campaigns(
        team_id=current_user.team_id,
        status=status_filter,
        page=page,
        per_page=per_page,
    )
    params = PaginationParams(page=page, per_page=per_page)
    return paginated_response(
        [CampaignResponse.model_validate(c, from_attributes=True) for c in campaigns],
        total,
        params,
    )


# ── Create campaign ───────────────────────────────────────────────────────


@router.post("", response_model=CampaignDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new campaign with optional steps."""
    svc = CampaignService(db)
    steps_data = None
    if body.steps:
        steps_data = [s.model_dump() for s in body.steps]

    campaign = await svc.create_campaign(
        team_id=current_user.team_id,
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        goal=body.goal,
        tone=body.tone,
        approval_mode=body.approval_mode,
        send_limits=body.send_limits,
        steps=steps_data,
    )

    # Load steps for response
    steps = await svc.get_steps(campaign.id)
    steps_response = [CampaignStepResponse.model_validate(s, from_attributes=True) for s in steps]

    response = CampaignDetailResponse.model_validate(campaign, from_attributes=True)
    response.steps = steps_response
    return response


# ── Get campaign ──────────────────────────────────────────────────────────


@router.get("/{campaign_id}", response_model=CampaignDetailResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a campaign by ID, including its steps."""
    svc = CampaignService(db)
    campaign = await svc.get_campaign(campaign_id, current_user.team_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    steps = await svc.get_steps(campaign.id)
    steps_response = [CampaignStepResponse.model_validate(s, from_attributes=True) for s in steps]

    response = CampaignDetailResponse.model_validate(campaign, from_attributes=True)
    response.steps = steps_response
    return response


# ── Update campaign ───────────────────────────────────────────────────────


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update campaign fields."""
    svc = CampaignService(db)
    updates = body.model_dump(exclude_unset=True)
    campaign = await svc.update_campaign(
        campaign_id,
        current_user.team_id,
        current_user.id,
        **updates,
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignResponse.model_validate(campaign, from_attributes=True)


# ── Delete (archive) campaign ──────────────────────────────────────────────


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Archive a campaign."""
    svc = CampaignService(db)
    deleted = await svc.delete_campaign(campaign_id, current_user.team_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Campaign not found")


# ── Campaign Steps ────────────────────────────────────────────────────────


@router.post("/{campaign_id}/steps", response_model=CampaignStepResponse, status_code=status.HTTP_201_CREATED)
async def add_campaign_step(
    campaign_id: uuid.UUID,
    body: CampaignStepCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a step to a campaign."""
    svc = CampaignService(db)
    # Verify campaign exists and belongs to team
    campaign = await svc.get_campaign(campaign_id, current_user.team_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    step = await svc.add_step(
        campaign_id=campaign_id,
        step_order=body.step_order,
        channel=body.channel,
        delay_days=body.delay_days,
        template_type=body.template_type,
        subject_template=body.subject_template,
        body_template=body.body_template,
    )
    return CampaignStepResponse.model_validate(step, from_attributes=True)


@router.get("/{campaign_id}/steps", response_model=list[CampaignStepResponse])
async def list_campaign_steps(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all steps for a campaign."""
    svc = CampaignService(db)
    campaign = await svc.get_campaign(campaign_id, current_user.team_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    steps = await svc.get_steps(campaign_id)
    return [CampaignStepResponse.model_validate(s, from_attributes=True) for s in steps]


@router.patch("/{campaign_id}/steps/{step_id}", response_model=CampaignStepResponse)
async def update_campaign_step(
    campaign_id: uuid.UUID,
    step_id: uuid.UUID,
    body: CampaignStepUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a campaign step."""
    svc = CampaignService(db)
    campaign = await svc.get_campaign(campaign_id, current_user.team_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    updates = body.model_dump(exclude_unset=True)
    step = await svc.update_step(step_id, **updates)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    return CampaignStepResponse.model_validate(step, from_attributes=True)


@router.delete("/{campaign_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign_step(
    campaign_id: uuid.UUID,
    step_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a campaign step."""
    svc = CampaignService(db)
    campaign = await svc.get_campaign(campaign_id, current_user.team_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    deleted = await svc.delete_step(step_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Step not found")


# ── Enrollment ────────────────────────────────────────────────────────────


@router.post("/{campaign_id}/enroll", response_model=list[CampaignEnrollmentResponse])
async def enroll_leads(
    campaign_id: uuid.UUID,
    body: EnrollLeadsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enroll leads into a campaign."""
    svc = CampaignService(db)
    try:
        enrollments = await svc.enroll_leads(
            campaign_id=campaign_id,
            lead_ids=body.lead_ids,
            team_id=current_user.team_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return [CampaignEnrollmentResponse.model_validate(e, from_attributes=True) for e in enrollments]


@router.get("/{campaign_id}/enrollments", response_model=dict)
async def list_enrollments(
    campaign_id: uuid.UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List enrollments for a campaign."""
    svc = CampaignService(db)
    campaign = await svc.get_campaign(campaign_id, current_user.team_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    enrollments, total = await svc.get_enrollments(
        campaign_id=campaign_id,
        status=status_filter,
        page=page,
        per_page=per_page,
    )
    params = PaginationParams(page=page, per_page=per_page)
    return paginated_response(
        [CampaignEnrollmentResponse.model_validate(e, from_attributes=True) for e in enrollments],
        total,
        params,
    )


# ── Lifecycle ────────────────────────────────────────────────────────────


@router.post("/{campaign_id}/start", response_model=CampaignResponse)
async def start_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start (activate) a campaign."""
    svc = CampaignService(db)
    try:
        campaign = await svc.start_campaign(campaign_id, current_user.team_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignResponse.model_validate(campaign, from_attributes=True)


@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
async def pause_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pause an active campaign."""
    svc = CampaignService(db)
    campaign = await svc.pause_campaign(campaign_id, current_user.team_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or not active")
    return CampaignResponse.model_validate(campaign, from_attributes=True)


@router.post("/{campaign_id}/complete", response_model=CampaignResponse)
async def complete_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a campaign as completed."""
    svc = CampaignService(db)
    campaign = await svc.complete_campaign(campaign_id, current_user.team_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignResponse.model_validate(campaign, from_attributes=True)


# ── Analytics ─────────────────────────────────────────────────────────────


@router.get("/{campaign_id}/stats", response_model=CampaignStatsResponse)
async def get_campaign_stats(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get analytics/statistics for a campaign."""
    svc = CampaignService(db)
    stats = await svc.get_campaign_stats(campaign_id, current_user.team_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return stats
