"""Outreach router: message generation, approval, reply ingestion, classification, and follow-up endpoints."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import PaginationParams, get_current_user, paginated_response
from app.models.user import User
from app.models.message import OutreachMessage
from app.models.reply import Reply, ReplyClassification
from app.models.follow_up import FollowUpTask
from app.models.campaign import CampaignEnrollment
from app.schemas.outreach import (
    MessageResponse,
    MessageListResponse,
    MessageApprovalRequest,
    GenerateMessagesRequest,
    ReplyCreate,
    ReplyResponse,
    ReplyClassificationResponse,
    ClassifyReplyRequest,
    ClassifyTextRequest,
    ClassifyTextResponse,
    FollowUpTaskResponse,
    FollowUpTaskListResponse,
    RescheduleTaskRequest,
    ProcessClassificationRequest,
)
from app.services.ai.personalization_engine import PersonalizationEngine
from app.services.ai.reply_classifier import ReplyClassifier
from app.services.campaign_service import CampaignService
from app.services.follow_up_service import FollowUpAutomation
from app.workers.outreach_tasks import send_message as send_message_task

router = APIRouter(prefix="/outreach", tags=["outreach"])


# ═══════════════════════════════════════════════════════════════════════════════
# MESSAGE GENERATION & MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/generate", response_model=list[MessageResponse], status_code=status.HTTP_201_CREATED)
async def generate_messages(
    body: GenerateMessagesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate personalized outreach messages for a lead using the Personalization Engine."""
    engine = PersonalizationEngine()
    try:
        messages = await engine.generate_messages(
            lead_id=body.lead_id,
            db=db,
            channel=body.channel,
            strategies=body.strategies,
            tone=body.tone,
            goal=body.goal,
            custom_instructions=body.custom_instructions,
            num_variants=body.num_variants,
            model=body.model,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Message generation failed: {e}")

    return [MessageResponse.model_validate(m, from_attributes=True) for m in messages]


@router.post(
    "/generate-for-step/{enrollment_id}", response_model=list[MessageResponse], status_code=status.HTTP_201_CREATED
)
async def generate_for_campaign_step(
    enrollment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate personalized messages for a lead in a campaign enrollment, using the current step's context."""
    # Get enrollment
    result = await db.execute(select(CampaignEnrollment).where(CampaignEnrollment.id == enrollment_id))
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    # Get campaign and steps
    svc = CampaignService(db)
    steps = await svc.get_steps(enrollment.campaign_id)
    if not steps:
        raise HTTPException(status_code=400, detail="Campaign has no steps")

    # Get current step
    current_step_index = min(enrollment.current_step, len(steps) - 1)
    step = steps[current_step_index]

    # Get campaign for tone
    campaign = await svc.get_campaign(enrollment.campaign_id, current_user.team_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    engine = PersonalizationEngine()
    try:
        messages = await engine.generate_for_campaign_step(
            lead_id=enrollment.lead_id,
            campaign_step_id=step.id,
            db=db,
            tone=campaign.tone,
            goal=campaign.goal or "generate_interest",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Message generation failed: {e}")

    return [MessageResponse.model_validate(m, from_attributes=True) for m in messages]


@router.get("/messages", response_model=MessageListResponse)
async def list_messages(
    lead_id: Optional[uuid.UUID] = Query(None),
    campaign_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List outreach messages with optional filters."""
    query = select(OutreachMessage)

    if lead_id:
        query = query.where(OutreachMessage.lead_id == lead_id)
    if campaign_id:
        query = query.where(OutreachMessage.campaign_id == campaign_id)
    if status_filter:
        statuses = status_filter.split(",")
        query = query.where(OutreachMessage.status.in_(statuses))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(OutreachMessage.created_at.desc())
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    messages = list(result.scalars().all())

    params = PaginationParams(page=page, per_page=per_page)
    return paginated_response(
        [MessageResponse.model_validate(m, from_attributes=True) for m in messages],
        total,
        params,
    )


@router.get("/messages/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific outreach message."""
    result = await db.execute(select(OutreachMessage).where(OutreachMessage.id == message_id))
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return MessageResponse.model_validate(message, from_attributes=True)


@router.patch("/messages/{message_id}/approve", response_model=MessageResponse)
async def approve_message(
    message_id: uuid.UUID,
    body: MessageApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve or reject a draft outreach message."""
    result = await db.execute(select(OutreachMessage).where(OutreachMessage.id == message_id))
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if body.action == "approve":
        message.status = "approved"
        message.approved_by = current_user.id
        from datetime import datetime

        message.approved_at = datetime.utcnow()
    elif body.action == "reject":
        message.status = "rejected"
    else:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

    await db.flush()
    await db.refresh(message)
    return MessageResponse.model_validate(message, from_attributes=True)


@router.post("/messages/{message_id}/send", response_model=dict)
async def send_outreach_message(
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue a message send via the outbound provider (Resend)."""
    from app.models.lead import Lead

    result = await db.execute(select(OutreachMessage).where(OutreachMessage.id == message_id))
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    lead = (await db.execute(select(Lead).where(Lead.id == message.lead_id))).scalar_one_or_none()
    if not lead or lead.team_id != current_user.team_id:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.status not in ("approved", "scheduled"):
        raise HTTPException(status_code=400, detail=f"Message not sendable (status={message.status})")

    task = send_message_task.delay(str(message_id))
    return {"task_id": task.id, "message_id": str(message_id)}


# ═══════════════════════════════════════════════════════════════════════════════
# REPLY INGESTION & CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/replies", response_model=ReplyResponse, status_code=status.HTTP_201_CREATED)
async def create_reply(
    body: ReplyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ingest a new reply from a prospect."""
    reply = Reply(
        lead_id=body.lead_id,
        message_id=body.message_id,
        channel=body.channel,
        subject=body.subject,
        body=body.body,
        from_email=body.from_email,
        from_name=body.from_name,
    )
    db.add(reply)
    await db.flush()
    await db.refresh(reply)
    return ReplyResponse.model_validate(reply, from_attributes=True)


@router.get("/replies", response_model=dict)
async def list_replies(
    lead_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List replies with optional filters."""
    query = select(Reply)
    if lead_id:
        query = query.where(Reply.lead_id == lead_id)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(Reply.received_at.desc())
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    replies = list(result.scalars().all())

    params = PaginationParams(page=page, per_page=per_page)
    return paginated_response(
        [ReplyResponse.model_validate(r, from_attributes=True) for r in replies],
        total,
        params,
    )


@router.post("/replies/classify", response_model=ReplyClassificationResponse, status_code=status.HTTP_201_CREATED)
async def classify_reply(
    body: ClassifyReplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Classify a persisted reply using the Reply Classifier."""
    classifier = ReplyClassifier()
    try:
        classification = await classifier.classify(
            reply_id=body.reply_id,
            db=db,
            model=body.model,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {e}")

    return ReplyClassificationResponse.model_validate(classification, from_attributes=True)


@router.post("/replies/classify-text", response_model=ClassifyTextResponse)
async def classify_text(
    body: ClassifyTextRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Classify raw reply text without persisting (preview)."""
    classifier = ReplyClassifier()
    try:
        result = await classifier.classify_text(
            reply_text=body.reply_text,
            original_subject=body.original_subject,
            original_body=body.original_body,
            contact_context=body.contact_context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {e}")

    return ClassifyTextResponse(
        classification=result.classification,
        subtype=result.subtype,
        confidence=result.confidence,
        summary=result.summary,
        recommended_action=result.recommended_action,
        draft_response=result.draft_response,
    )


@router.get("/replies/{reply_id}", response_model=ReplyResponse)
async def get_reply(
    reply_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific reply."""
    result = await db.execute(select(Reply).where(Reply.id == reply_id))
    reply = result.scalar_one_or_none()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    return ReplyResponse.model_validate(reply, from_attributes=True)


@router.get("/replies/{reply_id}/classification", response_model=list[ReplyClassificationResponse])
async def get_reply_classifications(
    reply_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get classification(s) for a reply."""
    result = await db.execute(select(ReplyClassification).where(ReplyClassification.reply_id == reply_id))
    classifications = list(result.scalars().all())
    return [ReplyClassificationResponse.model_validate(c, from_attributes=True) for c in classifications]


# ═══════════════════════════════════════════════════════════════════════════════
# FOLLOW-UP AUTOMATION
# ═══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/follow-ups/process-classification", response_model=list[FollowUpTaskResponse], status_code=status.HTTP_201_CREATED
)
async def process_classification(
    body: ProcessClassificationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create follow-up tasks from a reply classification."""
    automation = FollowUpAutomation(db)
    try:
        tasks = await automation.process_classification(body.classification_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return [FollowUpTaskResponse.model_validate(t, from_attributes=True) for t in tasks]


@router.post("/follow-ups/process-due", response_model=list[FollowUpTaskResponse])
async def process_due_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Process all follow-up tasks that are due right now."""
    automation = FollowUpAutomation(db)
    processed = await automation.process_due_tasks(team_id=current_user.team_id)
    return [FollowUpTaskResponse.model_validate(t, from_attributes=True) for t in processed]


@router.get("/follow-ups", response_model=FollowUpTaskListResponse)
async def list_follow_up_tasks(
    lead_id: Optional[uuid.UUID] = Query(None),
    task_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List follow-up tasks with optional filters."""
    automation = FollowUpAutomation(db)
    tasks, total = await automation.get_pending_tasks(
        lead_id=lead_id,
        task_type=task_type,
        page=page,
        per_page=per_page,
    )
    params = PaginationParams(page=page, per_page=per_page)
    return paginated_response(
        [FollowUpTaskResponse.model_validate(t, from_attributes=True) for t in tasks],
        total,
        params,
    )


@router.patch("/follow-ups/{task_id}/reschedule", response_model=FollowUpTaskResponse)
async def reschedule_task(
    task_id: uuid.UUID,
    body: RescheduleTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reschedule a pending follow-up task."""
    automation = FollowUpAutomation(db)
    task = await automation.reschedule_task(task_id, body.new_due_at)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or not pending")
    return FollowUpTaskResponse.model_validate(task, from_attributes=True)


@router.delete("/follow-ups/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a pending follow-up task."""
    automation = FollowUpAutomation(db)
    cancelled = await automation.cancel_task(task_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Task not found or not pending")
