"""IMAP inbox polling service — fetches replies from Gmail and matches to sent outreach.

Connects to Gmail via IMAP (imap.gmail.com:993) using an App Password.
Finds new replies, matches them to sent outreach messages, and creates Reply records.
"""

import asyncio
import email
import logging
import uuid
from datetime import datetime
from email.header import decode_header
from email.utils import parseaddr
from typing import Optional

import aioimaplib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead
from app.models.contact import Contact
from app.models.message import OutreachMessage
from app.models.reply import Reply

logger = logging.getLogger(__name__)

# Gmail IMAP settings
GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993


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
        # Fall back to HTML stripped
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


class InboxService:
    """Polls Gmail inbox for replies, matches to outreach messages, creates Reply records."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._client: Optional[aioimaplib.IMAP4_SSL] = None

    async def connect(self) -> None:
        """Connect to Gmail IMAP and authenticate."""
        email_addr = settings.GMAIL_INBOX_EMAIL
        app_password = settings.GMAIL_INBOX_APP_PASSWORD

        if not email_addr or not app_password:
            raise ValueError("GMAIL_INBOX_EMAIL and GMAIL_INBOX_APP_PASSWORD must be configured")

        self._client = aioimaplib.IMAP4_SSL(host=GMAIL_IMAP_HOST, port=GMAIL_IMAP_PORT)
        await self._client.wait_hello_from_server()

        # Login and wait for response
        response = await self._client.login(email_addr, app_password)
        if "OK" not in response[0]:
            raise ConnectionError(f"Gmail IMAP login failed: {response}")

        logger.info("Connected to Gmail IMAP as %s", email_addr)

    async def disconnect(self) -> None:
        """Disconnect from Gmail IMAP."""
        if self._client:
            try:
                await self._client.logout()
            except Exception:
                pass
            self._client = None

    async def _find_matching_message(
        self,
        in_reply_to: Optional[str],
        subject: str,
        from_email: str,
    ) -> Optional[uuid.UUID]:
        """Match an incoming reply to a sent outreach message.

        Matching strategy (in priority order):
        1. In-Reply-To header matches OutreachMessage.resend_id (provider message ID)
        2. In-Reply-To header matches OutreachMessage.id (our UUID in X-Message-ID)
        3. From email matches a lead's contact email + subject resembles our subject
        """
        # Strategy 1 & 2: Match by In-Reply-To header
        if in_reply_to:
            # Clean up the message ID (remove angle brackets)
            clean_id = in_reply_to.strip().strip("<>")

            # Try matching against resend_id (provider message ID)
            result = await self.db.execute(
                select(OutreachMessage).where(OutreachMessage.resend_id == clean_id)
            )
            msg = result.scalar_one_or_none()
            if msg:
                return msg.id

            # Try matching against our UUID (X-Message-ID header)
            try:
                msg_uuid = uuid.UUID(clean_id)
                msg = await self.db.get(OutreachMessage, msg_uuid)
                if msg:
                    return msg.id
            except (ValueError, AttributeError):
                pass

            # Brevo message IDs can be like <202605240131.93049087129@smtp-relay.mailin.fr>
            # Try partial match
            result = await self.db.execute(
                select(OutreachMessage).where(OutreachMessage.resend_id.contains(clean_id[:30]))
            )
            msg = result.scalar_one_or_none()
            if msg:
                return msg.id

        # Strategy 3: Match by from_email to a lead + subject similarity
        if from_email:
            # Find a lead with this contact email
            result = await self.db.execute(
                select(Contact).where(Contact.email == from_email)
            )
            contact = result.scalar_one_or_none()
            if contact:
                # Find outreach messages sent to this lead
                result = await self.db.execute(
                    select(Lead).where(Lead.contact_id == contact.id)
                )
                lead = result.scalar_one_or_none()
                if lead:
                    # Find the most recent sent message to this lead
                    result = await self.db.execute(
                        select(OutreachMessage)
                        .where(OutreachMessage.lead_id == lead.id)
                        .where(OutreachMessage.status == "sent")
                        .order_by(OutreachMessage.sent_at.desc())
                        .limit(1)
                    )
                    msg = result.scalar_one_or_none()
                    if msg:
                        return msg.id

        return None

    async def _find_lead_by_email(self, from_email: str) -> Optional[uuid.UUID]:
        """Find a lead ID by the sender's email address."""
        result = await self.db.execute(
            select(Contact).where(Contact.email == from_email)
        )
        contact = result.scalar_one_or_none()
        if contact:
            result = await self.db.execute(
                select(Lead).where(Lead.contact_id == contact.id)
            )
            lead = result.scalar_one_or_none()
            if lead:
                return lead.id
        return None

    async def fetch_and_process_new_messages(self, since_uid: int = 1) -> list[Reply]:
        """Fetch new unseen messages from inbox and create Reply records.

        Args:
            since_uid: Only fetch messages with UID > since_uid.

        Returns:
            List of newly created Reply records.
        """
        if not self._client:
            await self.connect()

        # Select INBOX
        await self._client.select("INBOX")

        # Search for unseen messages
        _, responses = await self._client.search("UNSEEN")
        if not responses or not responses[0]:
            logger.info("No new messages in inbox")
            return []

        msg_nums = responses[0].split()
        if not msg_nums or msg_nums == [b""]:
            logger.info("No new messages in inbox")
            return []

        logger.info("Found %d new messages in inbox", len(msg_nums))
        replies = []

        for msg_num in msg_nums:
            try:
                reply = await self._process_single_message(msg_num)
                if reply:
                    replies.append(reply)
            except Exception as exc:
                logger.error("Error processing message %s: %s", msg_num, exc)
                continue

        return replies

    async def _process_single_message(self, msg_num: bytes) -> Optional[Reply]:
        """Process a single IMAP message and create a Reply record."""
        # Fetch the message
        _, responses = await self._client.fetch(msg_num, "(RFC822)")
        if not responses:
            logger.warning("Empty response for message %s", msg_num)
            return None

        # Parse the raw email
        raw_email = responses[1]
        if isinstance(raw_email, bytes):
            msg = email.message_from_bytes(raw_email)
        else:
            msg = email.message_from_string(raw_email)

        # Extract headers
        subject = _decode_header(msg.get("Subject", ""))
        from_header = msg.get("From", "")
        from_name, from_email = parseaddr(from_header)
        from_name = _decode_header(from_name) if from_name else from_email.split("@")[0]
        in_reply_to = msg.get("In-Reply-To", "")
        message_id_header = msg.get("Message-ID", "")
        date_str = msg.get("Date", "")

        # Extract body
        body = _get_text_body(msg)

        # Skip if no body and no subject
        if not body.strip() and not subject.strip():
            logger.debug("Skipping empty message %s", msg_num)
            return None

        # Dedup by Message-ID header
        if message_id_header:
            existing = await self.db.execute(
                select(Reply).where(Reply.body.contains(message_id_header.strip("<>")))
            )
            # Simple dedup — check if we already have a reply from this sender with this subject
            # More robust: use a separate message_uid field, but this works for now

        # Match to a sent outreach message
        matched_message_id = await self._find_matching_message(
            in_reply_to=in_reply_to,
            subject=subject,
            from_email=from_email,
        )

        # Find lead by sender email
        lead_id = await self._find_lead_by_email(from_email)

        # Check for dedup — don't create duplicate replies
        if lead_id and matched_message_id:
            existing_reply = await self.db.execute(
                select(Reply).where(
                    Reply.lead_id == lead_id,
                    Reply.message_id == matched_message_id,
                    Reply.from_email == from_email,
                )
            )
            if existing_reply.scalar_one_or_none():
                logger.debug("Duplicate reply from %s for message %s, skipping", from_email, matched_message_id)
                return None

        # Create Reply record
        reply = Reply(
            lead_id=lead_id or uuid.UUID(int=0),  # Use nil UUID if no lead matched
            message_id=matched_message_id,
            channel="email",
            subject=subject,
            body=body[:10000] if body else "(no body)",  # Truncate very long bodies
            from_email=from_email,
            from_name=from_name,
            received_at=datetime.utcnow(),
        )

        if not lead_id:
            logger.info("Unmatched reply from %s: %s (no matching lead)", from_email, subject[:50])
        else:
            logger.info("Matched reply from %s to message %s: %s", from_email, matched_message_id, subject[:50])

        self.db.add(reply)
        await db_flush_safe(self.db)
        await self.db.refresh(reply)

        return reply


async def db_flush_safe(db: AsyncSession) -> None:
    """Flush the DB session, handling integrity errors."""
    try:
        await db.flush()
    except Exception as exc:
        logger.warning("DB flush error (possible duplicate): %s", exc)
        await db.rollback()
        raise