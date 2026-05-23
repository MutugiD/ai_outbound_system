"""Email delivery service using Resend API."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.message import OutreachMessage
from app.models.email_account import EmailAccount
from app.models.suppression import SuppressionList

try:
    import resend

    RESEND_AVAILABLE = True
except ImportError:
    resend = None
    RESEND_AVAILABLE = False

logger = logging.getLogger(__name__)

# Status constants matching OutreachMessage.status string values
STATUS_APPROVED = "approved"
STATUS_QUEUED = "queued"
STATUS_SENT = "sent"
STATUS_DELIVERED = "delivered"
STATUS_OPENED = "opened"
STATUS_CLICKED = "clicked"
STATUS_BOUNCED = "bounced"
STATUS_FAILED = "failed"


class EmailService:
    """Send outreach emails via Resend and track delivery events."""

    def __init__(self, db: AsyncSession):
        self.db = db
        if RESEND_AVAILABLE and settings.RESEND_API_KEY:
            resend.api_key = settings.RESEND_API_KEY

    async def _check_suppression(self, email: str) -> bool:
        """Check if an email is on the suppression list."""
        result = await self.db.execute(select(SuppressionList).where(SuppressionList.email == email))
        return result.scalar_one_or_none() is not None

    async def _get_sending_account(self) -> Optional[EmailAccount]:
        """Get the primary sending account with remaining daily quota."""
        result = await self.db.execute(
            select(EmailAccount)
            .where(EmailAccount.is_sending_account == True)  # noqa: E712
            .where(EmailAccount.status == "active")
        )
        account = result.scalar_one_or_none()
        if account and (account.daily_send_limit is None or account.sends_today < account.daily_send_limit):
            return account
        return None

    async def send_message(self, message_id: UUID) -> OutreachMessage:
        """Send an approved outreach message via Resend.

        Transitions message through: approved -> queued -> sent/delivered/failed.
        Updates sends_today counter on the email account.
        """
        message = await self.db.get(OutreachMessage, message_id)
        if not message:
            raise ValueError(f"Message {message_id} not found")

        if message.status not in (STATUS_APPROVED, STATUS_QUEUED):
            raise ValueError(f"Message {message_id} has status {message.status}, cannot send")

        # Check suppression list
        recipient_email: Optional[str] = None
        if message.lead_id:
            from app.models.lead import Lead
            from app.models.contact import Contact

            lead = await self.db.get(Lead, message.lead_id)
            if lead and lead.contact_id:
                contact = await self.db.get(Contact, lead.contact_id)
                if contact and contact.email:
                    recipient_email = contact.email
                    if await self._check_suppression(recipient_email):
                        message.status = STATUS_FAILED
                        message.error_message = "Recipient on suppression list"
                        self.db.add(message)
                        await self.db.commit()
                        logger.info("Message %s blocked: recipient on suppression list", message_id)
                        return message

        if not recipient_email:
            message.status = STATUS_FAILED
            message.error_message = "No recipient email found"
            self.db.add(message)
            await self.db.commit()
            logger.error("Message %s: no recipient email", message_id)
            return message

        # Check email status (bounced, invalid)
        if message.lead_id:
            from app.models.lead import Lead
            from app.models.contact import Contact

            lead = await self.db.get(Lead, message.lead_id)
            if lead and lead.contact_id:
                contact = await self.db.get(Contact, lead.contact_id)
                if contact and contact.email_status in ("bounced", "invalid"):
                    message.status = STATUS_BOUNCED
                    message.error_message = f"Email status: {contact.email_status}"
                    self.db.add(message)
                    await self.db.commit()
                    return message

        # Get sending account
        account = await self._get_sending_account()
        from_email = account.email_address if account else settings.EMAIL_FROM_ADDRESS
        from_name = settings.EMAIL_FROM_NAME

        # Mark as queued
        message.status = STATUS_QUEUED
        self.db.add(message)
        await self.db.commit()

        # Send via Resend
        try:
            if not RESEND_AVAILABLE or not settings.RESEND_API_KEY:
                # Dry-run mode: mark as sent without actually sending
                logger.info("DRY RUN: Would send message %s to %s", message_id, recipient_email)
                message.status = STATUS_SENT
                message.sent_at = datetime.now(timezone.utc)
                self.db.add(message)
                await self.db.commit()
                return message

            params: resend.Emails.SendParams = {
                "from": f"{from_name} <{from_email}>",
                "to": [recipient_email],
                "subject": message.subject or "Following up",
                "html": message.body,
                "tags": [
                    {"name": "message_id", "value": str(message_id)},
                    {"name": "campaign_id", "value": str(message.campaign_id) if message.campaign_id else ""},
                    {"name": "lead_id", "value": str(message.lead_id)},
                ],
            }

            # Add reply-to if different from from
            if account and account.email_address != from_email:
                params["reply_to"] = account.email_address

            response = resend.Emails.send(params)
            message.resend_id = response["id"]
            message.status = STATUS_SENT
            message.sent_at = datetime.now(timezone.utc)

            # Update account send counter
            if account:
                account.sends_today = (account.sends_today or 0) + 1
                self.db.add(account)

            self.db.add(message)
            await self.db.commit()
            logger.info("Message %s sent to %s via Resend", message_id, recipient_email)

        except Exception as e:
            logger.error("Failed to send message %s: %s", message_id, e)
            message.status = STATUS_FAILED
            message.error_message = str(e)[:500]
            self.db.add(message)
            await self.db.commit()

        return message

    async def send_pending_messages(self, limit: int = 50) -> dict:
        """Send all approved messages that are due.

        Returns dict with sent/failed/skipped counts.
        """
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(OutreachMessage)
            .where(OutreachMessage.status == STATUS_APPROVED)
            .where(OutreachMessage.scheduled_at <= now)
            .limit(limit)
        )
        messages = list(result.scalars().all())

        sent = failed = skipped = 0
        for msg in messages:
            try:
                res = await self.send_message(msg.id)
                if res.status == STATUS_SENT:
                    sent += 1
                elif res.status == STATUS_FAILED:
                    failed += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error("Error sending message %s: %s", msg.id, e)
                failed += 1

        return {"sent": sent, "failed": failed, "skipped": skipped}
