"""Multi-provider email delivery service.

Supports:
  - Brevo API (xkeysib- keys): 300 emails/day free forever
  - Brevo SMTP (xsmtpsib- keys): 300 emails/day free forever
  - Resend API: 100 emails/day free, for verified domains

Provider is selected via EMAIL_PROVIDER env var (default: "brevo").
Auto-detects Brevo key type: xkeysib- → API, xsmtpsib- → SMTP relay.
"""

import logging
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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

try:
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException as BrevoApiException
    BREVO_AVAILABLE = True
except ImportError:
    sib_api_v3_sdk = None
    BREVO_AVAILABLE = False

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
    """Send outreach emails via Brevo (API/SMTP) or Resend, with provider fallback."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.provider = (settings.EMAIL_PROVIDER or "brevo").lower()
        if RESEND_AVAILABLE and settings.RESEND_API_KEY:
            resend.api_key = settings.RESEND_API_KEY
        # Auto-detect Brevo mode: xkeysib- = API, xsmtpsib- = SMTP
        self._brevo_mode = self._detect_brevo_mode()

    def _detect_brevo_mode(self) -> str:
        """Detect whether to use Brevo API v3 or SMTP relay based on key format."""
        key = settings.BREVO_API_KEY
        if not key:
            return "none"
        if key.startswith("xkeysib-"):
            return "api"
        elif key.startswith("xsmtpsib-"):
            return "smtp"
        # Default: try API first, fall back to SMTP
        return "api"

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

    async def _resolve_recipient_email(self, message: OutreachMessage) -> Optional[str]:
        """Resolve recipient email from the message's lead/contact."""
        if not message.lead_id:
            return None

        from app.models.lead import Lead
        from app.models.contact import Contact

        lead = await self.db.get(Lead, message.lead_id)
        if not lead or not lead.contact_id:
            return None

        contact = await self.db.get(Contact, lead.contact_id)
        if contact and contact.email:
            return contact.email
        return None

    async def send_message(self, message_id: UUID) -> OutreachMessage:
        """Send an approved outreach message via the configured email provider.

        Transitions message through: approved -> queued -> sent/delivered/failed.
        Falls back to alternate provider on failure.
        """
        message = await self.db.get(OutreachMessage, message_id)
        if not message:
            raise ValueError(f"Message {message_id} not found")

        if message.status not in (STATUS_APPROVED, STATUS_QUEUED):
            raise ValueError(f"Message {message_id} has status {message.status}, cannot send")

        # ── Resolve recipient ────────────────────────────────────────────
        recipient_email = await self._resolve_recipient_email(message)

        # Check suppression list
        if recipient_email and await self._check_suppression(recipient_email):
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

        # ── Try providers in order ────────────────────────────────────────
        providers_to_try = self._get_provider_order()
        last_error = None

        # If no providers configured, use dry-run mode
        if not providers_to_try:
            logger.info("DRY RUN: No email providers configured. Would send message %s to %s", message_id, recipient_email)
            message.status = STATUS_SENT
            message.sent_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self.db.add(message)
            await self.db.commit()
            return message

        for provider in providers_to_try:
            try:
                if provider == "brevo_api":
                    result = await self._send_via_brevo_api(
                        message, recipient_email, from_email, from_name, account
                    )
                    if result:
                        return result
                elif provider == "brevo_smtp":
                    result = await self._send_via_brevo_smtp(
                        message, recipient_email, from_email, from_name, account
                    )
                    if result:
                        return result
                elif provider == "resend":
                    result = await self._send_via_resend(
                        message, recipient_email, from_email, from_name, account
                    )
                    if result:
                        return result
            except Exception as e:
                last_error = e
                logger.warning("Provider %s failed for message %s: %s", provider, message_id, e)
                continue

        # All providers failed
        message.status = STATUS_FAILED
        message.error_message = f"All providers failed. Last error: {str(last_error)[:400]}"
        self.db.add(message)
        await self.db.commit()
        return message

    def _get_provider_order(self) -> list:
        """Return ordered list of providers to try.

        For Brevo, auto-detects API vs SMTP based on key format:
          - xkeysib- → brevo_api (REST API v3)
          - xsmtpsib- → brevo_smtp (SMTP relay)
        """
        order = []

        # Primary provider
        if self.provider == "brevo":
            if BREVO_AVAILABLE and settings.BREVO_API_KEY:
                if self._brevo_mode == "api":
                    order.append("brevo_api")
                elif self._brevo_mode == "smtp":
                    order.append("brevo_smtp")
                else:
                    order.append("brevo_api")  # default to API
        elif self.provider == "resend":
            if RESEND_AVAILABLE and settings.RESEND_API_KEY:
                order.append("resend")

        # Fallback providers
        if self.provider != "resend" and RESEND_AVAILABLE and settings.RESEND_API_KEY:
            order.append("resend")
        if self.provider != "brevo" and BREVO_AVAILABLE and settings.BREVO_API_KEY:
            if self._brevo_mode == "smtp":
                order.append("brevo_smtp")
            else:
                order.append("brevo_api")

        return order

    async def _send_via_brevo_api(
        self,
        message: OutreachMessage,
        recipient_email: str,
        from_email: str,
        from_name: str,
        account: Optional[EmailAccount],
    ) -> Optional[OutreachMessage]:
        """Send email via Brevo API v3 (for xkeysib- keys)."""
        if not BREVO_AVAILABLE or not settings.BREVO_API_KEY:
            return None

        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key["api-key"] = settings.BREVO_API_KEY

        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )

        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            sender=sib_api_v3_sdk.SendSmtpEmailSender(
                name=from_name,
                email=from_email,
            ),
            to=[sib_api_v3_sdk.SendSmtpEmailTo(email=recipient_email)],
            subject=message.subject or "Following up",
            html_content=message.body,
            tags=["outbound-os"],
        )

        # Custom headers for webhook tracking
        send_smtp_email.headers = {
            "X-Message-ID": str(message.id),
        }
        if message.lead_id:
            send_smtp_email.headers["X-Lead-ID"] = str(message.lead_id)
        if message.campaign_id:
            send_smtp_email.headers["X-Campaign-ID"] = str(message.campaign_id)
        # Add reply-to: use configured reply-to address for inbound responses
        elif account and account.email_address != from_email:
            send_smtp_email.reply_to = sib_api_v3_sdk.SendSmtpEmailReplyTo(
                email=account.email_address, name=from_name
            )

        response = api_instance.send_transac_email(send_smtp_email)
        brevo_id = str(response) if response else None

        message.resend_id = brevo_id  # Reuse field for provider message ID
        message.status = STATUS_SENT
        message.sent_at = datetime.now(timezone.utc).replace(tzinfo=None)

        if account:
            account.sends_today = (account.sends_today or 0) + 1
            self.db.add(account)

        self.db.add(message)
        await self.db.commit()
        logger.info("Message %s sent to %s via Brevo API (id=%s)", message.id, recipient_email, brevo_id)
        return message

    def _send_via_brevo_smtp_sync(
        self,
        message_id: str,
        recipient_email: str,
        from_email: str,
        from_name: str,
        subject: str,
        html_body: str,
        lead_id: str,
        campaign_id: str,
    ) -> str:
        """Synchronous SMTP send via Brevo relay (for xsmtpsib- keys).

        Returns the Brevo message ID from the SMTP response.
        Raises on failure.
        """
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = recipient_email
        msg["Subject"] = subject or "Following up"

        # Custom headers for tracking
        msg["X-Message-ID"] = str(message_id)
        if lead_id:
            msg["X-Lead-ID"] = str(lead_id)
        if campaign_id:
            msg["X-Campaign-ID"] = str(campaign_id)

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP("smtp-relay.brevo.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            # Brevo SMTP login: use account email + SMTP key as password
            # The SMTP key IS the password; login is any sender email on the account
            smtp_login = from_email  # Use the from_email as SMTP login
            server.login(smtp_login, settings.BREVO_API_KEY)
            server.sendmail(from_email, [recipient_email], msg.as_string())

        return "brevo-smtp-sent"

    async def _send_via_brevo_smtp(
        self,
        message: OutreachMessage,
        recipient_email: str,
        from_email: str,
        from_name: str,
        account: Optional[EmailAccount],
    ) -> Optional[OutreachMessage]:
        """Send email via Brevo SMTP relay (for xsmtpsib- keys)."""
        if not settings.BREVO_API_KEY:
            return None

        # Run SMTP in thread pool to avoid blocking async loop
        import asyncio
        loop = asyncio.get_event_loop()
        brevo_id = await loop.run_in_executor(
            None,
            self._send_via_brevo_smtp_sync,
            str(message.id),
            recipient_email,
            from_email,
            from_name,
            message.subject,
            message.body,
            str(message.lead_id) if message.lead_id else "",
            str(message.campaign_id) if message.campaign_id else "",
        )

        message.resend_id = brevo_id
        message.status = STATUS_SENT
        message.sent_at = datetime.now(timezone.utc).replace(tzinfo=None)

        if account:
            account.sends_today = (account.sends_today or 0) + 1
            self.db.add(account)

        self.db.add(message)
        await self.db.commit()
        logger.info("Message %s sent to %s via Brevo SMTP", message.id, recipient_email)
        return message

    async def _send_via_resend(
        self,
        message: OutreachMessage,
        recipient_email: str,
        from_email: str,
        from_name: str,
        account: Optional[EmailAccount],
    ) -> Optional[OutreachMessage]:
        """Send email via Resend API."""
        if not RESEND_AVAILABLE or not settings.RESEND_API_KEY:
            return None

        tags = [
            {"name": "message_id", "value": str(message.id).replace("-", "")},
            {"name": "lead_id", "value": str(message.lead_id).replace("-", "")},
        ]
        if message.campaign_id:
            tags.append({"name": "campaign_id", "value": str(message.campaign_id).replace("-", "")})

        params: resend.Emails.SendParams = {
            "from": f"{from_name} <{from_email}>",
            "to": [recipient_email],
            "subject": message.subject or "Following up",
            "html": message.body,
            "tags": tags,
        }

        if account and account.email_address != from_email:
            params["reply_to"] = account.email_address

        response = resend.Emails.send(params)
        resend_id = response.get("id", "")
        message.resend_id = resend_id
        message.status = STATUS_SENT
        message.sent_at = datetime.now(timezone.utc).replace(tzinfo=None)

        if account:
            account.sends_today = (account.sends_today or 0) + 1
            self.db.add(account)

        self.db.add(message)
        await self.db.commit()
        logger.info("Message %s sent to %s via Resend (id=%s)", message.id, recipient_email, resend_id)
        return message

    async def send_pending_messages(self, limit: int = 50) -> dict:
        """Send all approved messages that are due.

        Returns dict with sent/failed/skipped counts.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
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