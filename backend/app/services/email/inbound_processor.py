"""Inbound email processing — receives replies via Brevo/Resend webhooks and processes them.

Brevo inbound parse: https://developers.brevo.com/docs/inbound-parse-webhooks
Resend inbound routing: not supported (use Brevo for inbound)

When someone replies to an outreach email, Brevo forwards the raw email to our
webhook endpoint. We parse it, match to the original outreach message, create
a Reply record, and trigger classification + auto-respond.
"""

import email
import logging
import uuid
from datetime import datetime
from email.header import decode_header
from email.utils import parseaddr
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.contact import Contact
from app.models.message import OutreachMessage
from app.models.reply import Reply

logger = logging.getLogger(__name__)


def _decode_header(header_value: str) -> str:
    """Decode an email header value, handling encoded words."""
    if not header_value:
        return ""
    decoded_parts = decode_header(header_value)
    parts = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(part)
    return " ".join(parts)


def _get_text_body(msg: email.message.Message) -> str:
    """Extract the plain text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
                except Exception:
                    continue
        # Fall back to HTML
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        except Exception:
            pass
    return ""


class InboundEmailProcessor:
    """Process inbound emails received via Brevo/Resend webhooks."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_brevo_inbound(self, payload: dict) -> Optional[Reply]:
        """Process an inbound email from Brevo webhook payload.

        Brevo sends: https://developers.brevo.com/docs/inbound-parse-webhooks
        Payload fields: from, to, subject, raw-body, headers, etc.
        """
        # Extract email content from Brevo payload
        from_header = payload.get("from", "")
        from_name, from_email = parseaddr(from_header)
        from_name = _decode_header(from_name) if from_name else from_email.split("@")[0]

        subject = payload.get("subject", "")
        body = payload.get("raw-body", payload.get("html", payload.get("text", "")))

        # Brevo provides headers as a dict
        headers = payload.get("headers", {})
        in_reply_to = headers.get("In-Reply-To", "") or headers.get("in-reply-to", "")
        message_id_header = headers.get("Message-ID", "") or headers.get("message-id", "")

        # Clean up in_reply_to
        if in_reply_to:
            in_reply_to = in_reply_to.strip().strip("<>")

        return await self._process_reply(
            from_email=from_email,
            from_name=from_name,
            subject=subject,
            body=body,
            in_reply_to=in_reply_to,
            message_id_header=message_id_header.strip("<>") if message_id_header else "",
        )

    async def process_raw_email(self, raw_email_bytes: bytes) -> Optional[Reply]:
        """Process a raw RFC822 email message (from IMAP or raw webhook).

        Parses the raw email bytes into an email.message.Message object,
        extracts headers and body, then processes the reply.
        """
        msg = email.message_from_bytes(raw_email_bytes)

        from_header = msg.get("From", "")
        from_name, from_email = parseaddr(from_header)
        from_name = _decode_header(from_name) if from_name else from_email.split("@")[0]

        subject = _decode_header(msg.get("Subject", ""))
        body = _get_text_body(msg)

        in_reply_to = (msg.get("In-Reply-To", "") or "").strip().strip("<>")
        message_id_header = (msg.get("Message-ID", "") or "").strip().strip("<>")

        return await self._process_reply(
            from_email=from_email,
            from_name=from_name,
            subject=subject,
            body=body,
            in_reply_to=in_reply_to,
            message_id_header=message_id_header,
        )

    async def _process_reply(
        self,
        from_email: str,
        from_name: str,
        subject: str,
        body: str,
        in_reply_to: str,
        message_id_header: str,
    ) -> Optional[Reply]:
        """Core reply processing: match to outreach, create Reply record."""
        # Skip if no content at all
        if not body.strip() and not subject.strip():
            logger.debug("Skipping empty message from %s", from_email)
            return None

        # Match to a sent outreach message
        matched_message_id = await self._find_matching_message(
            in_reply_to=in_reply_to,
            subject=subject,
            from_email=from_email,
        )

        # Find lead by sender email
        lead_id = await self._find_lead_by_email(from_email)

        # Dedup — check if we already have a reply from this sender about this message
        if lead_id and lead_id != uuid.UUID(int=0) and matched_message_id:
            existing = await self.db.execute(
                select(Reply).where(
                    Reply.lead_id == lead_id,
                    Reply.message_id == matched_message_id,
                    Reply.from_email == from_email,
                )
            )
            if existing.scalar_one_or_none():
                logger.debug("Duplicate reply from %s for message %s, skipping", from_email, matched_message_id)
                return None

        # Create Reply record
        reply = Reply(
            lead_id=lead_id or uuid.UUID(int=0),
            message_id=matched_message_id,
            channel="email",
            subject=subject[:500] if subject else "(no subject)",
            body=body[:10000] if body else "(no body)",
            from_email=from_email,
            from_name=from_name[:255] if from_name else from_email.split("@")[0],
            received_at=datetime.utcnow(),
        )

        self.db.add(reply)
        await db_flush_safe(self.db)
        await self.db.refresh(reply)

        if not lead_id or lead_id == uuid.UUID(int=0):
            logger.info("Unmatched reply from %s: %s", from_email, subject[:50])
        else:
            logger.info("Matched reply from %s to message %s: %s", from_email, matched_message_id, subject[:50])

        return reply

    async def _find_matching_message(
        self,
        in_reply_to: Optional[str],
        subject: str,
        from_email: str,
    ) -> Optional[uuid.UUID]:
        """Match an incoming reply to a sent outreach message."""
        # 1. Match by In-Reply-To header against provider message ID
        if in_reply_to:
            clean_id = in_reply_to.strip()

            # Try matching against resend_id (provider message ID)
            result = await self.db.execute(
                select(OutreachMessage).where(OutreachMessage.resend_id == clean_id)
            )
            msg = result.scalar_one_or_none()
            if msg:
                return msg.id

            # Try matching UUID (X-Message-ID custom header)
            try:
                msg_uuid = uuid.UUID(clean_id)
                msg = await self.db.get(OutreachMessage, msg_uuid)
                if msg:
                    return msg.id
            except (ValueError, AttributeError):
                pass

            # Partial match for Brevo message IDs (long format)
            if len(clean_id) > 20:
                result = await self.db.execute(
                    select(OutreachMessage).where(OutreachMessage.resend_id.contains(clean_id[:30]))
                )
                msg = result.scalar_one_or_none()
                if msg:
                    return msg.id

        # 2. Match by from_email to a lead's contact + most recent sent message
        if from_email:
            result = await self.db.execute(
                select(Contact).where(Contact.email == from_email).limit(1)
            )
            contact = result.scalar_one_or_none()
            if contact:
                result = await self.db.execute(
                    select(Lead).where(Lead.contact_id == contact.id).limit(1)
                )
                lead = result.scalar_one_or_none()
                if lead:
                    result = await self.db.execute(
                        select(OutreachMessage)
                        .where(OutreachMessage.lead_id == lead.id)
                        .where(OutreachMessage.status.in_(["sent", "delivered", "opened", "approved"]))
                        .order_by(OutreachMessage.created_at.desc())
                        .limit(1)
                    )
                    msg = result.scalar_one_or_none()
                    if msg:
                        return msg.id

        return None

    async def _find_lead_by_email(self, from_email: str) -> Optional[uuid.UUID]:
        """Find a lead ID by the sender's email address."""
        result = await self.db.execute(
            select(Contact).where(Contact.email == from_email).limit(1)
        )
        contact = result.scalar_one_or_none()
        if contact:
            result = await self.db.execute(
                select(Lead).where(Lead.contact_id == contact.id).limit(1)
            )
            lead = result.scalar_one_or_none()
            if lead:
                return lead.id
        return None


async def db_flush_safe(db: AsyncSession) -> None:
    """Flush the DB session, handling integrity errors."""
    try:
        await db.flush()
    except Exception as exc:
        logger.warning("DB flush error (possible duplicate): %s", exc)
        await db.rollback()
        raise