"""Webhook endpoints (provider callbacks).

These endpoints are intentionally *not* JWT-protected; they authenticate using
provider-specific webhook signing secrets.
"""

from __future__ import annotations

import json
from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.message import OutreachMessage
from app.models.reply import Reply
from app.rate_limit import rate_limit
from app.services.email.resend_service import retrieve_received_email
from app.services.webhooks.svix_verify import WebhookVerificationError, verify_svix_webhook
from app.workers.inbox_tasks import process_new_reply as process_new_reply_task

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _parse_iso8601(ts: str | None) -> datetime | None:
    if not ts:
        return None
    # Resend uses ISO-8601; handle trailing Z.
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _extract_uuid_from_to(to_list: list[str]) -> uuid.UUID | None:
    for addr in to_list:
        local = (addr or "").split("@", 1)[0]
        if "+" not in local:
            continue
        candidate = local.split("+", 1)[1]
        try:
            return uuid.UUID(candidate)
        except Exception:
            continue
    return None


def _parse_from_header(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    v = value.strip()
    if "<" in v and ">" in v:
        name = v.split("<", 1)[0].strip().strip('"') or None
        email = v.split("<", 1)[1].split(">", 1)[0].strip() or None
        return email, name
    return v, None


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

    # Inbound replies: fetch body via Receiving API, map to an OutreachMessage via plus-addressing,
    # then enqueue classification/follow-ups.
    if event_type == "email.received":
        inbound_to = list(data.get("to") or [])
        correlated_message_id = _extract_uuid_from_to(inbound_to)
        if not correlated_message_id:
            return {"status": "ignored", "reason": "unmapped_inbound_to"}

        msg_result = await db.execute(select(OutreachMessage).where(OutreachMessage.id == correlated_message_id))
        correlated_message = msg_result.scalar_one_or_none()
        if not correlated_message:
            return {"status": "ok", "note": "message_not_found"}

        # Dedup: Resend retries webhooks; don't ingest the same inbound email twice.
        existing_reply = (
            await db.execute(
                select(Reply).where(
                    Reply.provider == "resend",
                    Reply.provider_inbound_id == str(provider_email_id),
                )
            )
        ).scalar_one_or_none()
        if existing_reply:
            return {"status": "ok", "note": "duplicate"}

        received = await retrieve_received_email(email_id=str(provider_email_id))
        body = received.text or received.html or ""
        from_email, from_name = _parse_from_header(received.headers.get("from"))  # type: ignore[arg-type]

        reply = Reply(
            lead_id=correlated_message.lead_id,
            message_id=correlated_message.id,
            provider="resend",
            provider_inbound_id=str(provider_email_id),
            channel="email",
            subject=received.subject or data.get("subject"),
            body=body,
            from_email=from_email or data.get("from"),
            from_name=from_name,
            received_at=created_at or datetime.utcnow(),
        )
        db.add(reply)
        await db.flush()
        await db.refresh(reply)
        await db.commit()

        process_new_reply_task.delay(str(reply.id))
        return {"status": "ok", "reply_id": str(reply.id)}

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
