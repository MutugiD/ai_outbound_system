"""API endpoints for inbox replies and auto-response management."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.reply import Reply, ReplyClassification
from app.services.email.inbox_service import InboxService
from app.services.email.auto_responder import AutoResponder
from app.services.ai.reply_classifier import ReplyClassifier

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("/replies")
async def list_replies(
    lead_id: Optional[str] = None,
    classification: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all inbound replies, optionally filtered."""
    query = select(Reply).order_by(Reply.received_at.desc())

    if lead_id:
        query = query.where(Reply.lead_id == uuid.UUID(lead_id))

    result = await db.execute(query.offset(offset).limit(limit))
    replies = result.scalars().all()

    # Get classifications
    reply_ids = [r.id for r in replies]
    classifications = {}
    if reply_ids:
        cls_result = await db.execute(
            select(ReplyClassification).where(
                ReplyClassification.reply_id.in_(reply_ids)
            )
        )
        for cls in cls_result.scalars().all():
            classifications[cls.reply_id] = cls

    items = []
    for reply in replies:
        item = {
            "id": str(reply.id),
            "lead_id": str(reply.lead_id) if reply.lead_id else None,
            "message_id": str(reply.message_id) if reply.message_id else None,
            "channel": reply.channel,
            "subject": reply.subject,
            "body": reply.body[:500] if reply.body else None,
            "from_email": reply.from_email,
            "from_name": reply.from_name,
            "received_at": reply.received_at.isoformat() if reply.received_at else None,
            "classification": None,
        }
        cls = classifications.get(reply.id)
        if cls:
            item["classification"] = {
                "category": cls.classification,
                "subtype": cls.subtype,
                "confidence": float(cls.confidence),
                "summary": cls.summary,
                "recommended_action": cls.recommended_action,
                "draft_response": cls.draft_response[:200] if cls.draft_response else None,
            }
        items.append(item)

    return {"items": items, "total": len(items)}


@router.get("/replies/{reply_id}")
async def get_reply(
    reply_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific reply with its classification."""
    result = await db.execute(select(Reply).where(Reply.id == uuid.UUID(reply_id)))
    reply = result.scalar_one_or_none()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")

    # Get classification
    cls_result = await db.execute(
        select(ReplyClassification).where(ReplyClassification.reply_id == reply.id)
    )
    classification = cls_result.scalar_one_or_none()

    item = {
        "id": str(reply.id),
        "lead_id": str(reply.lead_id) if reply.lead_id else None,
        "message_id": str(reply.message_id) if reply.message_id else None,
        "channel": reply.channel,
        "subject": reply.subject,
        "body": reply.body,
        "from_email": reply.from_email,
        "from_name": reply.from_name,
        "received_at": reply.received_at.isoformat() if reply.received_at else None,
        "classification": None,
    }

    if classification:
        item["classification"] = {
            "category": classification.classification,
            "subtype": classification.subtype,
            "confidence": float(classification.confidence),
            "summary": classification.summary,
            "recommended_action": classification.recommended_action,
            "draft_response": classification.draft_response,
            "model_used": classification.model_used,
        }

    return item


@router.post("/replies/{reply_id}/classify")
async def classify_reply(
    reply_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Classify a reply and optionally auto-respond."""
    responder = AutoResponder(db)
    result = await responder.process_reply(uuid.UUID(reply_id))
    await db.commit()
    return result


@router.post("/check")
async def check_inbox_now(
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger an inbox check (poll Gmail for new replies)."""
    from app.config import settings

    if not settings.GMAIL_INBOX_EMAIL or not settings.GMAIL_INBOX_APP_PASSWORD:
        raise HTTPException(status_code=400, detail="Gmail inbox not configured")

    svc = InboxService(db)
    try:
        await svc.connect()
        replies = await svc.fetch_and_process_new_messages()

        # Classify each new reply
        results = []
        for reply in replies:
            try:
                responder = AutoResponder(db)
                result = await responder.process_reply(reply.id)
                results.append(result)
            except Exception as exc:
                results.append({
                    "reply_id": str(reply.id),
                    "error": str(exc),
                })

        await db.commit()
        return {
            "checked": True,
            "new_replies": len(replies),
            "results": results,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inbox check failed: {str(exc)}")
    finally:
        await svc.disconnect()


@router.get("/classifications")
async def list_classifications(
    category: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all reply classifications."""
    query = select(ReplyClassification).order_by(ReplyClassification.created_at.desc())

    if category:
        query = query.where(ReplyClassification.classification == category)

    result = await db.execute(query.offset(offset).limit(limit))
    classifications = result.scalars().all()

    return {
        "items": [
            {
                "id": str(cls.id),
                "reply_id": str(cls.reply_id),
                "lead_id": str(cls.lead_id) if cls.lead_id else None,
                "classification": cls.classification,
                "subtype": cls.subtype,
                "confidence": float(cls.confidence),
                "summary": cls.summary,
                "recommended_action": cls.recommended_action,
                "model_used": cls.model_used,
                "created_at": cls.created_at.isoformat() if cls.created_at else None,
            }
            for cls in classifications
        ],
        "total": len(classifications),
    }


@router.get("/stats")
async def inbox_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get inbox reply statistics."""
    # Total replies
    total_result = await db.execute(select(func.count(Reply.id)))
    total = total_result.scalar()

    # Replies by classification
    cls_result = await db.execute(
        select(ReplyClassification.classification, func.count(ReplyClassification.id))
        .group_by(ReplyClassification.classification)
    )
    by_category = {row[0]: row[1] for row in cls_result}

    # Unmatched replies (no lead)
    unmatched_result = await db.execute(
        select(func.count(Reply.id)).where(Reply.lead_id == uuid.UUID(int=0))
    )
    unmatched = unmatched_result.scalar()

    return {
        "total_replies": total,
        "by_classification": by_category,
        "unmatched_replies": unmatched,
    }
