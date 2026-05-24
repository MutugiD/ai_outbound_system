"""Webhook endpoints (provider callbacks).

These endpoints are intentionally *not* JWT-protected; they authenticate using
provider-specific webhook signing secrets.
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.message import OutreachMessage
from app.rate_limit import rate_limit
from app.services.webhooks.svix_verify import WebhookVerificationError, verify_svix_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _parse_iso8601(ts: str | None) -> datetime | None:
    if not ts:
        return None
    # Resend uses ISO-8601; handle trailing Z.
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


@router.post(
    "/resend",
    response_model=dict,
    dependencies=[Depends(rate_limit(limit=300, window_seconds=60, scope="webhooks:resend"))],
)
async def resend_events_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Resend (Svix-signed) email events and update OutreachMessage status."""
    if not settings.RESEND_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="RESEND_WEBHOOK_SECRET not configured")

    raw = await request.body()
    try:
        verify_svix_webhook(
            raw_body=raw,
            headers=request.headers,
            secret=settings.RESEND_WEBHOOK_SECRET,
            tolerance_seconds=settings.RESEND_WEBHOOK_TOLERANCE_SECONDS,
        )
    except WebhookVerificationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {exc}")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = payload.get("type")
    created_at = _parse_iso8601(payload.get("created_at"))
    data = payload.get("data") or {}

    provider_email_id = data.get("email_id") or data.get("id")
    if not provider_email_id:
        return {"status": "ignored", "reason": "missing_email_id"}

    result = await db.execute(
        select(OutreachMessage).where(
            OutreachMessage.provider == "resend",
            OutreachMessage.provider_message_id == str(provider_email_id),
        )
    )
    message = result.scalar_one_or_none()
    if not message:
        # Idempotent success: provider may send events for non-tracked emails.
        return {"status": "ok", "note": "message_not_found"}

    # Map Resend event types to message statuses/timestamps.
    # Note: events can arrive out-of-order.
    if event_type == "email.delivered":
        message.status = "delivered"
        message.delivered_at = created_at or datetime.utcnow()
    elif event_type == "email.opened":
        message.status = "opened"
        message.opened_at = created_at or datetime.utcnow()
    elif event_type == "email.clicked":
        message.status = "clicked"
        message.clicked_at = created_at or datetime.utcnow()
    elif event_type == "email.bounced":
        message.status = "bounced"
        bounce = data.get("bounce") or {}
        message.error = bounce.get("message") or message.error
    elif event_type == "email.failed":
        message.status = "failed"
        message.error = (data.get("error") or {}).get("message") or message.error
    elif event_type == "email.complained":
        message.status = "failed"
        message.error = "complained"
    elif event_type in ("email.sent", "email.scheduled"):
        # Informational; keep our status as-is unless still pending.
        if message.status in ("approved", "scheduled"):
            message.status = "sent"
            message.sent_at = created_at or message.sent_at or datetime.utcnow()
    else:
        # Unknown or unhandled event type.
        return {"status": "ignored", "type": event_type}

    db.add(message)
    await db.commit()
    return {"status": "ok"}

