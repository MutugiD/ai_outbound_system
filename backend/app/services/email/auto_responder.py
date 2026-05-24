"""Auto-response service — classifies incoming replies and sends appropriate responses.

Orchestrates the full reply handling pipeline:
  1. Classify reply (using ReplyClassifier)
  2. Decide whether to auto-respond
  3. Generate + send response via EmailService
  4. Update lead pipeline stage
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead
from app.models.message import OutreachMessage
from app.models.reply import Reply, ReplyClassification
from app.services.ai.reply_classifier import ReplyClassifier
from app.services.email.email_service import EmailService

logger = logging.getLogger(__name__)

# Categories that trigger auto-response
AUTO_RESPOND_CATEGORIES = {
    "positive_interest",
    "meeting_request",
    "question",
    "objection",
}

# Categories that suppress the lead (no response)
SUPPRESSED_CATEGORIES = {
    "unsubscribe",
    "not_interested",
    "spam",
}

# Categories where we schedule a reminder but don't respond
REMINDER_ONLY_CATEGORIES = {
    "out_of_office",
    "not_now",
}


class AutoResponder:
    """Process incoming replies: classify, decide whether to auto-respond, and send."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.classifier = ReplyClassifier()
        self.email_service = EmailService(db)

    async def process_reply(self, reply_id: uuid.UUID) -> dict:
        """Process an incoming reply: classify and optionally auto-respond.

        Returns a dict with classification details and whether a response was sent.
        """
        # Load the reply
        result = await self.db.execute(select(Reply).where(Reply.id == reply_id))
        reply = result.scalar_one_or_none()
        if not reply:
            raise ValueError(f"Reply {reply_id} not found")

        # Check if auto-respond is enabled
        auto_send = settings.AUTO_RESPOND_ENABLED

        # Step 1: Classify the reply
        try:
            classification = await self.classifier.classify(reply_id, self.db)
        except Exception as exc:
            logger.error("Classification failed for reply %s: %s", reply_id, exc)
            return {
                "reply_id": str(reply_id),
                "classification": "error",
                "error": str(exc),
                "auto_responded": False,
            }

        category = classification.classification
        confidence = float(classification.confidence)
        draft_response = classification.draft_response
        recommended_action = classification.recommended_action

        logger.info(
            "Classified reply %s as '%s' (confidence=%.2f, action=%s)",
            reply_id, category, confidence, recommended_action,
        )

        # Step 2: Decide whether to auto-respond
        response_sent = False

        if category in SUPPRESSED_CATEGORIES:
            # Add to suppression list
            if reply.from_email and category in ("unsubscribe", "not_interested"):
                await self._add_suppression(reply)

            # Update lead status
            if reply.lead_id and reply.lead_id != uuid.UUID(int=0):
                lead = await self.db.get(Lead, reply.lead_id)
                if lead:
                    lead.status = "lost"
                    lead.pipeline_stage = "lost"
                    lead.next_action = "suppress_lead"
                    lead.updated_at = datetime.utcnow()
                    self.db.add(lead)

            await self.db.commit()
            return {
                "reply_id": str(reply_id),
                "classification": category,
                "confidence": confidence,
                "auto_responded": False,
                "reason": "suppressed_category",
            }

        elif category in REMINDER_ONLY_CATEGORIES:
            # Schedule a reminder but don't respond now
            if reply.lead_id and reply.lead_id != uuid.UUID(int=0):
                lead = await self.db.get(Lead, reply.lead_id)
                if lead:
                    lead.next_action = "schedule_reminder_after_ooo"
                    lead.updated_at = datetime.utcnow()
                    self.db.add(lead)

            await self.db.commit()
            return {
                "reply_id": str(reply_id),
                "classification": category,
                "confidence": confidence,
                "auto_responded": False,
                "reason": "reminder_scheduled",
            }

        elif category in AUTO_RESPOND_CATEGORIES and auto_send and draft_response:
            # Auto-send the draft response
            if not reply.lead_id or reply.lead_id == uuid.UUID(int=0):
                logger.info("Cannot auto-respond to reply %s — no matching lead", reply_id)
                await self.db.commit()
                return {
                    "reply_id": str(reply_id),
                    "classification": category,
                    "confidence": confidence,
                    "auto_responded": False,
                    "reason": "no_matching_lead",
                }

            # Create and send a response outreach message
            response_sent = await self._send_auto_response(
                reply=reply,
                classification=classification,
                draft_body=draft_response,
            )

            await self.db.commit()

            return {
                "reply_id": str(reply_id),
                "classification": category,
                "subtype": classification.subtype,
                "confidence": confidence,
                "recommended_action": recommended_action,
                "auto_responded": response_sent,
                "draft_response_preview": draft_response[:100] if draft_response else None,
            }

        else:
            # Category eligible for auto-respond but either auto-respond is disabled
            # or no draft response was generated — just save classification
            await self.db.commit()
            return {
                "reply_id": str(reply_id),
                "classification": category,
                "confidence": confidence,
                "auto_responded": False,
                "reason": "auto_respond_disabled" if not auto_send else "no_draft",
                "draft_response_preview": draft_response[:100] if draft_response else None,
            }

    async def _send_auto_response(
        self,
        reply: Reply,
        classification: ReplyClassification,
        draft_body: str,
    ) -> bool:
        """Create and send an auto-response outreach message."""
        # Load the lead and contact
        lead = await self.db.get(Lead, reply.lead_id)
        if not lead or not lead.contact_id:
            logger.warning("Lead %s has no contact, cannot auto-respond", reply.lead_id)
            return False

        from app.models.contact import Contact
        contact = await self.db.get(Contact, lead.contact_id)
        if not contact or not contact.email:
            logger.warning("Contact for lead %s has no email", reply.lead_id)
            return False

        # Build response subject (Re: original subject)
        original_subject = reply.subject or "Following up"
        if not original_subject.lower().startswith("re:"):
            response_subject = f"Re: {original_subject}"
        else:
            response_subject = original_subject

        # Create an outreach message for the response
        message = OutreachMessage(
            lead_id=lead.id,
            campaign_id=None,  # Auto-response, not part of a campaign
            channel="email",
            subject=response_subject,
            body=draft_body,
            status="approved",  # Auto-approved since classifier recommended it
            personalization_sources={
                "auto_response": True,
                "reply_classification": classification.classification,
                "original_reply_id": str(reply.id),
            },
        )
        self.db.add(message)
        await self.db.flush()
        await self.db.refresh(message)

        # Send the email
        try:
            sent = await self.email_service.send_message(message.id)
            logger.info(
                "Auto-response sent: message %s to %s (classification=%s)",
                message.id, contact.email, classification.classification,
            )
            return sent.status == "sent"
        except Exception as exc:
            logger.error("Failed to send auto-response %s: %s", message.id, exc)
            return False

    async def _add_suppression(self, reply: Reply) -> None:
        """Add the reply sender to the suppression list."""
        from app.models.suppression import SuppressionList

        result = await self.db.execute(
            select(SuppressionList).where(SuppressionList.email == reply.from_email)
        )
        existing = result.scalar_one_or_none()
        if not existing and reply.from_email:
            suppression = SuppressionList(
                email=reply.from_email,
                reason="unsubscribe" if reply.from_email else "auto_suppress",
                source="auto_responder",
                team_id=uuid.UUID(int=0),
            )
            self.db.add(suppression)