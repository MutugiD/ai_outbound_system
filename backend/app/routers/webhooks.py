"""Webhook endpoints for email delivery events and inbound email parsing.

Supports:
  - Brevo: /webhooks/brevo (delivery events + inbound email)
  - Resend: /webhooks/resend (delivery events)
  - Inbound: /webhooks/inbound (generic inbound email processing)
"""

import hashlib
import hmac
import json
import logging
import uuid

from fastapi import APIRouter, Request, Response, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.email.event_tracker import EmailEventTracker
from app.services.email.inbound_processor import InboundEmailProcessor
from app.services.email.auto_responder import AutoResponder

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ── Brevo webhook (delivery events + inbound) ──────────────────────────────

@router.post("/brevo")
async def brevo_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """Handle Brevo webhook events for email tracking and inbound parsing.

    Brevo sends events for: delivered, opened, clicked, bounced,
    complaint, blocked, error, soft_bounced.
    Brevo also sends inbound emails when configured with inbound parsing.

    Brevo verifies webhook signature via a secret in the X-Brevo-Signature header.
    """
    body = await request.body()
    signature = request.headers.get("X-Brevo-Signature", "")

    if settings.BREVO_WEBHOOK_SECRET and not _verify_brevo_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Brevo can send single events or arrays
    events = payload if isinstance(payload, list) else [payload]

    for event in events:
        event_type = event.get("event", "")

        # ── Inbound email (reply) ──────────────────────────────────────
        # Brevo inbound parse sends: from, to, subject, headers, raw-body, html, text
        if event_type in ("inbound", "inbound_email") or "from" in event and "subject" in event and not event_type:
            # Check if this looks like an inbound email (has 'from' and 'subject' but no 'event' delivery type)
            if event.get("from") and event.get("subject") and not event_type.startswith("email."):
                try:
                    processor = InboundEmailProcessor(db)
                    reply = await processor.process_brevo_inbound(event)
                    if reply:
                        # Trigger auto-response
                        try:
                            responder = AutoResponder(db)
                            result = await responder.process_reply(reply.id)
                            await db.commit()
                            logger.info("Inbound email processed: %s → %s", reply.from_email, result.get("classification"))
                        except Exception as e:
                            logger.error("Auto-respond failed for reply %s: %s", reply.id, e)
                            await db.commit()
                except Exception as e:
                    logger.error("Error processing Brevo inbound email: %s", e)
                continue

        # ── Delivery event tracking ─────────────────────────────────────
        # Map Brevo event names to our internal format
        brevo_to_internal = {
            "delivered": "email.delivered",
            "opened": "email.opened",
            "click": "email.clicked",
            "clicked": "email.clicked",
            "bounce": "email.bounced",
            "soft_bounced": "email.bounced",
            "blocked": "email.bounced",
            "error": "email.bounced",
            "complaint": "email.complained",
            "spam": "email.complained",
            "invalid_email": "email.bounced",
            "deferred": "email.deferred",
            "unsubscribed": "email.unsubscribed",
        }

        internal_type = brevo_to_internal.get(event_type, event_type)

        message_id = event.get("message-id") or event.get("message_id", "")

        if not message_id:
            # Try X-Message-ID custom header we set when sending
            headers = event.get("headers", {})
            if isinstance(headers, dict):
                message_id = headers.get("X-Message-ID", "")

        if not message_id:
            logger.warning("Brevo webhook missing message-id: %s", event_type)
            continue

        try:
            tracker = EmailEventTracker(db)
            await tracker.process_event(internal_type, message_id, event)
        except Exception as e:
            logger.error("Error processing Brevo webhook: %s", e)

    return Response(status_code=200)


def _verify_brevo_signature(payload: bytes, signature: str) -> bool:
    """Verify Brevo webhook signature."""
    if not settings.BREVO_WEBHOOK_SECRET:
        return True
    computed = hmac.new(
        settings.BREVO_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, signature)


# ── Resend webhook ────────────────────────────────────────────────────────

def _verify_resend_signature(payload: bytes, signature: str) -> bool:
    """Verify Resend webhook signature."""
    if not settings.RESEND_WEBHOOK_SECRET:
        return True  # Skip verification if no secret configured

    computed = hmac.new(
        settings.RESEND_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, signature)


@router.post("/resend")
async def resend_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """Handle Resend webhook events for email tracking.

    Events: email.sent, email.delivered, email.opened, email.clicked,
    email.bounced, email.complained
    """
    body = await request.body()
    signature = request.headers.get("resend-signature", "")

    if not _verify_resend_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("type", "")
    data = payload.get("data", {})

    # ── Inbound email (reply) ──────────────────────────────────────
    if event_type == "email.inbound":
        try:
            processor = InboundEmailProcessor(db)
            reply = await processor.process_brevo_inbound(data)
            if reply:
                try:
                    responder = AutoResponder(db)
                    result = await responder.process_reply(reply.id)
                    await db.commit()
                    logger.info("Resend inbound email processed: %s → %s", reply.from_email, result.get("classification"))
                except Exception as e:
                    logger.error("Auto-respond failed for reply %s: %s", reply.id, e)
                    await db.commit()
        except Exception as e:
            logger.error("Error processing Resend inbound email: %s", e)
        return Response(status_code=200)

    # ── Delivery event tracking ─────────────────────────────────────
    message_id = data.get("email_id", "")

    if not message_id:
        logger.warning("Resend webhook missing email_id: %s", event_type)
        return Response(status_code=200)

    try:
        tracker = EmailEventTracker(db)
        await tracker.process_event(event_type, message_id, data)
    except Exception as e:
        logger.error("Error processing Resend webhook: %s", e)

    return Response(status_code=200)


# ── Generic inbound webhook ────────────────────────────────────────────────

@router.post("/inbound")
async def inbound_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """Handle inbound emails from any source (Brevo, custom SMTP, etc.).

    Accepts JSON payloads with: from, subject, body/html/text, headers dict.
    Also accepts raw RFC822 email via Content-Type: message/rfc822.
    """
    content_type = request.headers.get("content-type", "")

    processor = InboundEmailProcessor(db)

    if "message/rfc822" in content_type or "message/rfc822" in content_type.lower():
        # Raw email format
        body = await request.body()
        try:
            reply = await processor.process_raw_email(body)
        except Exception as e:
            logger.error("Error processing raw inbound email: %s", e)
            raise HTTPException(status_code=400, detail=f"Failed to parse email: {str(e)}")
    else:
        # JSON format
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        try:
            reply = await processor.process_brevo_inbound(payload)
        except Exception as e:
            logger.error("Error processing inbound JSON: %s", e)
            raise HTTPException(status_code=400, detail=f"Failed to process inbound email: {str(e)}")

    if not reply:
        return Response(status_code=200, content=json.dumps({"status": "skipped"}).encode())

    # Trigger auto-response
    try:
        responder = AutoResponder(db)
        result = await responder.process_reply(reply.id)
        await db.commit()
        return Response(
            status_code=200,
            content=json.dumps({
                "status": "processed",
                "reply_id": str(reply.id),
                "classification": result.get("classification"),
                "auto_responded": result.get("auto_responded", False),
            }).encode(),
        )
    except Exception as e:
        logger.error("Auto-respond failed for reply %s: %s", reply.id, e)
        await db.commit()
        return Response(
            status_code=200,
            content=json.dumps({"status": "processed", "reply_id": str(reply.id), "auto_response_error": str(e)}).encode(),
        )