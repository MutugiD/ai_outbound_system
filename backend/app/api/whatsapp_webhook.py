"""WhatsApp webhook handler for Evolution API callbacks.

These endpoints are called BY Evolution API, not JWT-protected.
They authenticate via the Evolution API webhook configuration.
"""

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.contact import Contact
from app.models.lead import Lead
from app.models.message import OutreachMessage
from app.models.reply import Reply
from app.models.whatsapp_session import WhatsAppSession
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/whatsapp", tags=["webhooks"])


def _normalize_phone(raw: str) -> str:
    """Normalize a WhatsApp JID to a phone number string.

    Evolution API sends numbers like '254712345678@s.whatsapp.net'.
    We strip the @s.whatsapp.net suffix.
    """
    if not raw:
        return ""
    return raw.split("@")[0].strip()


@router.post("")
async def evolution_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive webhook events from Evolution API.

    Evolution API posts events here when:
    - A new message is received (messages.upsert)
    - A message status changes (messages.upsert with update)
    - Connection state changes (connection.update)
    - QR code is ready (qrcode.updated)
    """
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        logger.warning("Invalid webhook payload from Evolution API")
        return {"status": "ignored"}

    event = payload.get("event")
    instance_name = payload.get("instance")

    logger.info("WhatsApp webhook: event=%s instance=%s", event, instance_name)

    # ── Connection state updates ────────────────────────────────────
    if event == "connection.update":
        state = payload.get("state", "")
        session_result = await db.execute(select(WhatsAppSession).where(WhatsAppSession.instance_name == instance_name))
        session = session_result.scalar_one_or_none()
        if session:
            state_map = {
                "open": "connected",
                "connecting": "connecting",
                "close": "disconnected",
                "disconnected": "disconnected",
                "logged-out": "disconnected",
            }
            session.status = state_map.get(state, state)
            session.updated_at = datetime.utcnow()
            if session.status == "connected":
                session.paired_at = datetime.utcnow()
            db.add(session)
            await db.flush()
            await db.commit()
        return {"status": "ok"}

    # ── QR code ready ───────────────────────────────────────────────
    if event == "qrcode.updated":
        # QR code can be a plain base64 string or an object with "base64" key
        raw_qr = payload.get("qrcode", "")
        if isinstance(raw_qr, dict):
            qr_code = raw_qr.get("base64", "")
        else:
            qr_code = str(raw_qr)
        session_result = await db.execute(select(WhatsAppSession).where(WhatsAppSession.instance_name == instance_name))
        session = session_result.scalar_one_or_none()
        if session:
            session.qr_code = qr_code
            session.status = "connecting"
            session.updated_at = datetime.utcnow()
            db.add(session)
            await db.flush()
            await db.commit()
        return {"status": "ok"}

    # ── Inbound messages ─────────────────────────────────────────────
    if event == "messages.upsert":
        data = payload.get("data", {})
        key = data.get("key", {})

        # Only process incoming messages (from others, not from us)
        from_me = key.get("fromMe", False)
        if from_me:
            return {"status": "ignored", "reason": "fromMe"}

        remote_jid = key.get("remoteJid", "")
        sender_phone = _normalize_phone(remote_jid)

        # If it's a group message, the participant field has the actual sender
        participant = key.get("participant") or data.get("participant", "")
        if participant and "@s.whatsapp.net" in participant:
            sender_phone = _normalize_phone(participant)

        message_data = data.get("message", {})
        message_text = ""
        if "conversation" in message_data:
            message_text = message_data["conversation"]
        elif "extendedTextMessage" in message_data:
            message_text = message_data["extendedTextMessage"].get("text", "")

        push_name = data.get("pushName", "")

        if not sender_phone or not message_text:
            return {"status": "ignored", "reason": "missing_phone_or_text"}

        # Find contact by whatsapp_phone
        contact_result = await db.execute(select(Contact).where(Contact.whatsapp_phone == sender_phone))
        contact = contact_result.scalar_one_or_none()

        # Find lead associated with this contact (via company -> lead or direct)
        lead_id = None
        message_id = None
        if contact and contact.company_id:
            lead_result = await db.execute(select(Lead).where(Lead.company_id == contact.company_id))
            lead = lead_result.scalar_one_or_none()
            if lead:
                lead_id = lead.id

        if not lead_id:
            # Try matching via the contact's normalized_phone or whatsapp_phone
            phone_contact = await db.execute(
                select(Contact).where(
                    or_(Contact.normalized_phone == sender_phone, Contact.whatsapp_phone == sender_phone)
                )
            )
            phone_contact_obj = phone_contact.scalar_one_or_none()
            if phone_contact_obj and phone_contact_obj.company_id:
                lead_result = await db.execute(select(Lead).where(Lead.company_id == phone_contact_obj.company_id))
                lead = lead_result.scalar_one_or_none()
                if lead:
                    lead_id = lead.id

        # Create Reply record only if we matched a lead or found a contact
        # WhatsApp inbound from unknown numbers can't create a Reply without a lead (FK constraint)
        if not lead_id and not contact:
            logger.info(
                "WhatsApp inbound from unknown number: phone=%s text=%.50s — no matching lead or contact, skipping reply creation",
                sender_phone,
                message_text,
            )
            return {"status": "ok", "reason": "unknown_sender"}

        # If we found a contact but not a lead, try to create a lead from it
        if not lead_id and contact:
            if contact.company_id:
                lead_result = await db.execute(select(Lead).where(Lead.company_id == contact.company_id))
                lead = lead_result.scalar_one_or_none()
                if lead:
                    lead_id = lead.id
            if not lead_id and contact.id:
                # Check if contact has an associated lead via contact_id
                lead_result = await db.execute(select(Lead).where(Lead.contact_id == contact.id))
                lead = lead_result.scalar_one_or_none()
                if lead:
                    lead_id = lead.id

        if not lead_id:
            logger.info(
                "WhatsApp inbound: phone=%s has contact but no lead — skipping reply creation",
                sender_phone,
            )
            return {"status": "ok", "reason": "no_lead_for_contact"}

        # Try to correlate with an existing outbound message
        # Look for the most recent outreach message sent to this phone
        if lead_id:
            msg_result = await db.execute(
                select(OutreachMessage)
                .where(
                    OutreachMessage.lead_id == lead_id,
                    OutreachMessage.channel == "whatsapp",
                    OutreachMessage.status.in_(["sent", "delivered", "opened"]),
                )
                .order_by(OutreachMessage.sent_at.desc())
                .limit(1)
            )
            existing_msg = msg_result.scalar_one_or_none()
            if existing_msg:
                message_id = existing_msg.id

        # Create Reply record
        reply = Reply(
            lead_id=lead_id,
            message_id=message_id,
            channel="whatsapp",
            subject=None,
            body=message_text[:5000],
            from_email=None,
            from_name=push_name or sender_phone,
            provider="evolution-api",
            provider_inbound_id=key.get("id"),
        )

        # Override: WhatsApp replies come from phone, store in from_email field as phone
        reply.from_email = sender_phone

        db.add(reply)
        await db.flush()
        await db.refresh(reply)

        # Enqueue classification task
        try:
            from app.workers.inbox_tasks import process_new_reply

            process_new_reply.delay(str(reply.id))
        except Exception as e:
            logger.warning("Failed to enqueue reply classification: %s", e)

        await db.commit()

        logger.info("WhatsApp inbound: phone=%s text=%.50s reply_id=%s", sender_phone, message_text, reply.id)
        return {"status": "ok", "reply_id": str(reply.id)}

    # ── Message delivery receipts (from send.message event) ────────
    if event == "send.message":
        data = payload.get("data", {})
        provider_msg_id = data.get("key", {}).get("id", "")
        status_val = data.get("status", "")

        if provider_msg_id:
            msg_result = await db.execute(
                select(OutreachMessage).where(
                    OutreachMessage.provider == "evolution-api",
                    OutreachMessage.provider_message_id == provider_msg_id,
                )
            )
            message = msg_result.scalar_one_or_none()
            if message:
                status_map = {
                    "pending": "sent",
                    "delivered": "delivered",
                    "read": "opened",
                    "played": "opened",
                }
                new_status = status_map.get(status_val, message.status)
                if new_status != message.status:
                    message.status = new_status
                    if new_status == "delivered":
                        message.delivered_at = datetime.utcnow()
                    elif new_status == "opened":
                        message.opened_at = datetime.utcnow()
                    db.add(message)
                    await db.commit()

        return {"status": "ok"}

    return {"status": "ignored", "event": event}
