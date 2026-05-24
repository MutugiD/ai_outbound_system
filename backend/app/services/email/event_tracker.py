"""Track email events (opens, clicks, bounces) from webhook payloads."""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.message import OutreachMessage
from app.models.lead import Lead
from app.models.suppression import SuppressionList

logger = logging.getLogger(__name__)

# Status constants
STATUS_DELIVERED = "delivered"
STATUS_OPENED = "opened"
STATUS_CLICKED = "clicked"
STATUS_BOUNCED = "bounced"
STATUS_FAILED = "failed"


class EmailEventTracker:
    """Process email delivery events from Resend webhooks."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _resolve_team_id(self, message: OutreachMessage) -> uuid.UUID:
        """Resolve team_id from the message's campaign context."""
        if message.campaign_id:
            campaign = await self.db.get(Campaign, message.campaign_id)
            if campaign:
                return campaign.team_id
        # Fallback: use a nil UUID (should not normally happen)
        logger.warning("Could not resolve team_id for message %s", message.id)
        return uuid.UUID(int=0)

    async def process_event(self, event_type: str, message_id: str, data: dict) -> None:
        """Process a single email event.

        event_type: email.delivered, email.opened, email.clicked, email.bounced, email.complained
        message_id: Provider message ID (stored as resend_id on OutreachMessage)
        data: event payload from webhook
        """
        # Try to find message by provider message ID (stored in resend_id field)
        result = await self.db.execute(select(OutreachMessage).where(OutreachMessage.resend_id == message_id))
        message = result.scalar_one_or_none()

        # Also try by UUID if the message_id looks like a UUID (custom X-Message-ID header)
        if not message and "-" in message_id:
            try:
                msg_uuid = uuid.UUID(message_id)
                message = await self.db.get(OutreachMessage, msg_uuid)
            except (ValueError, AttributeError):
                pass

        if not message:
            logger.warning("No message found for resend_id=%s", message_id)
            return

        team_id = await self._resolve_team_id(message)
        now = datetime.now(timezone.utc)

        if event_type == "email.delivered":
            message.status = STATUS_DELIVERED
            message.delivered_at = now

        elif event_type == "email.opened":
            if message.status not in (STATUS_BOUNCED, STATUS_FAILED):
                message.status = STATUS_OPENED
                message.opened_at = message.opened_at or now

        elif event_type == "email.clicked":
            if message.status not in (STATUS_BOUNCED, STATUS_FAILED):
                message.status = STATUS_CLICKED
                message.clicked_at = now

        elif event_type == "email.bounced":
            message.status = STATUS_BOUNCED
            message.error_message = data.get("bounce", {}).get("message", "Bounced")[:500]
            # Add to suppression list
            recipient = data.get("email", {}).get("to", "")
            if recipient:
                await self._add_suppression(recipient, "bounce", "Email bounced", team_id)

        elif event_type == "email.complained":
            # Spam complaint — suppress immediately
            recipient = data.get("email", {}).get("to", "")
            if recipient:
                await self._add_suppression(recipient, "complaint", "Spam complaint", team_id)
            # Also mark lead as unreachable
            if message.lead_id:
                lead = await self.db.get(Lead, message.lead_id)
                if lead:
                    lead.status = "suppressed"

        self.db.add(message)
        await self.db.commit()
        logger.info("Processed %s for message %s", event_type, message.id)

    async def _add_suppression(self, email: str, reason: str, source: str, team_id: uuid.UUID) -> None:
        """Add an email to the suppression list."""
        result = await self.db.execute(select(SuppressionList).where(SuppressionList.email == email))
        existing = result.scalar_one_or_none()
        if not existing:
            suppression = SuppressionList(email=email, reason=reason, source=source, team_id=team_id)
            self.db.add(suppression)
            await self.db.commit()
