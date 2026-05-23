"""Webhook endpoints for Resend email events."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Request, Response, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.email.event_tracker import EmailEventTracker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


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

    # Extract Resend message ID
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
