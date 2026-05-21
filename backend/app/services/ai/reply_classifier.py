"""Reply classification service — uses LLM to classify prospect replies.

Classifies replies into categories:
  - positive_interest: Prospect is interested, wants to learn more
  - meeting_request: Prospect wants to schedule a meeting/call
  - objection: Prospect raises an objection but is still in conversation
  - not_now: Prospect is not ready right now (timing)
  -not_interested: Prospect explicitly declines
  - out_of_office: Auto-responder / OOO
  - unsubscribe: Prospect wants to stop receiving emails
  - spam: Appears to be spam
  - referral: Prospect refers someone else
  - question: Prospect asks a question (indicating interest)
  - no_response: No meaningful content to classify

For each classification, generates:
  - Confidence score (0-1)
  - Subtype for more granular categorization
  - Summary of what the prospect said
  - Recommended next action
  - Draft response (when appropriate)
"""

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.contact import Contact
from app.models.company import Company
from app.models.message import OutreachMessage
from app.models.reply import Reply, ReplyClassification
from app.models.campaign import CampaignEnrollment
from app.services.ai.llm_service import LLMService
from app.services.activity_service import log_activity

logger = logging.getLogger(__name__)

# ── Classification categories ─────────────────────────────────────────────────


class ReplyCategory(str, Enum):
    POSITIVE_INTEREST = "positive_interest"
    MEETING_REQUEST = "meeting_request"
    OBJECTION = "objection"
    NOT_NOW = "not_now"
    NOT_INTERESTED = "not_interested"
    OUT_OF_OFFICE = "out_of_office"
    UNSUBSCRIBE = "unsubscribe"
    SPAM = "spam"
    REFERRAL = "referral"
    QUESTION = "question"
    NO_RESPONSE = "no_response"


VALID_CATEGORIES = [c.value for c in ReplyCategory]

CATEGORY_DESCRIPTIONS = {
    "positive_interest": "The prospect expresses interest in learning more, getting a demo, or continuing the conversation.",
    "meeting_request": "The prospect explicitly asks to schedule a meeting, call, or demo.",
    "objection": "The prospect raises a concern or objection (pricing, timing, priority) but doesn't completely close the door.",
    "not_now": "The prospect indicates bad timing — they're interested in principle but can't engage right now.",
    "not_interested": "The prospect explicitly says they're not interested or declines the offer.",
    "out_of_office": "An auto-responder or out-of-office message, possibly with an alternate contact.",
    "unsubscribe": "The prospect requests to be removed from future communications.",
    "spam": "The message appears to be spam, irrelevant, or automated.",
    "referral": "The prospect refers someone else who might be a better fit.",
    "question": "The prospect asks a question about your product, service, or offering.",
    "no_response": "The reply contains no meaningful content to classify.",
}


# ── LLM output schemas ───────────────────────────────────────────────────────


class ClassificationItem(BaseModel):
    """Single classification result."""

    classification: str = Field(description=f"Category: one of {VALID_CATEGORIES}")
    subtype: Optional[str] = Field(
        description="More specific subcategory, e.g. 'pricing_concern', 'timing', 'competitor_comparison'"
    )
    confidence: float = Field(description="Confidence score 0-1", ge=0.0, le=1.0)
    summary: str = Field(description="Brief summary of what the prospect said")
    recommended_action: str = Field(
        description="Recommended next action, e.g. 'send_follow_up', 'book_meeting', 'suppress_lead'"
    )
    draft_response: Optional[str] = Field(
        description="Draft response to send back, if appropriate. Null if no response recommended."
    )


class ReplyClassificationOutput(BaseModel):
    """Structured output for reply classification."""

    result: ClassificationItem


# ── Reply Classifier ──────────────────────────────────────────────────────────


class ReplyClassifier:
    """Classifies prospect replies using LLM and rule-based heuristics.

    Usage::

        classifier = ReplyClassifier()
        classification = await classifier.classify(reply_id=reply_id, db=db)
        # Or classify directly from text:
        result = await classifier.classify_text(
            reply_text="...",
            original_subject="...",
            original_body="...",
        )
    """

    def __init__(self, llm_service: Optional[LLMService] = None):
        self._llm = llm_service or LLMService()

    # ── Rule-based quick checks ─────────────────────────────────────────────

    def _quick_classify(self, text: str) -> Optional[ClassificationItem]:
        """Fast rule-based classification for obvious categories.

        Returns None if no clear category is detected (needs LLM).
        """
        text_lower = text.lower().strip()

        # Unsubscribe patterns
        unsubscribe_patterns = [
            "unsubscribe",
            "remove me",
            "stop sending",
            "don't email",
            "opt out",
            "no longer interested",
            "take me off",
        ]
        for pattern in unsubscribe_patterns:
            if pattern in text_lower:
                return ClassificationItem(
                    classification="unsubscribe",
                    subtype="explicit_unsubscribe",
                    confidence=0.95,
                    summary="Prospect requested to be removed from communications.",
                    recommended_action="suppress_lead",
                    draft_response=None,
                )

        # Out-of-office patterns
        ooo_patterns = [
            "out of office",
            "out of the office",
            "i am currently away",
            "auto-reply",
            "auto reply",
            "automatic reply",
            "i will be out",
            "on leave",
            "on vacation",
            "maternity leave",
            "paternity leave",
        ]
        for pattern in ooo_patterns:
            if pattern in text_lower:
                return ClassificationItem(
                    classification="out_of_office",
                    subtype="auto_responder",
                    confidence=0.9,
                    summary="Auto-responder / out of office message.",
                    recommended_action="schedule_reminder",
                    draft_response=None,
                )

        # Spam patterns
        spam_patterns = [
            "buy cheap",
            "viagra",
            "lottery",
            "you won",
            "nigerian",
            "prince",
            "click here to claim",
            "free money",
        ]
        for pattern in spam_patterns:
            if pattern in text_lower:
                return ClassificationItem(
                    classification="spam",
                    subtype="spam_content",
                    confidence=0.9,
                    summary="Message appears to be spam.",
                    recommended_action="ignore",
                    draft_response=None,
                )

        # Very short / empty responses
        if len(text_lower) < 10:
            return ClassificationItem(
                classification="no_response",
                subtype="too_short",
                confidence=0.8,
                summary="Reply is too short to contain meaningful content.",
                recommended_action="send_follow_up",
                draft_response=None,
            )

        return None

    # ── LLM classification ──────────────────────────────────────────────────

    async def _classify_llm(
        self,
        reply_text: str,
        original_subject: Optional[str] = None,
        original_body: Optional[str] = None,
        contact_context: Optional[str] = None,
    ) -> ClassificationItem:
        """Classify a reply using the LLM."""
        # Build prompt
        category_list = "\n".join(f"  - {cat}: {desc}" for cat, desc in CATEGORY_DESCRIPTIONS.items())

        prompt = (
            f"Classify the following prospect reply into exactly one category.\n\n"
            f"## Original message sent to prospect\n"
        )

        if original_subject:
            prompt += f"Subject: {original_subject}\n"
        if original_body:
            prompt += f"Body:\n{original_body[:2000]}\n"

        prompt += f"\n## Prospect's reply\n{reply_text[:3000]}\n\n"

        if contact_context:
            prompt += f"## Additional context about the prospect\n{contact_context}\n\n"

        prompt += (
            f"## Categories\n{category_list}\n\n"
            f"Classify the reply into the most fitting category. "
            f"Provide a confidence score, summary, recommended next action, "
            f"and a draft response (if appropriate — set to null if no response "
            f"should be sent, e.g. for 'unsubscribe' or 'not_interested')."
        )

        system_prompt = (
            "You are an expert sales assistant who classifies prospect replies. "
            "You are precise, objective, and never over-interpret. "
            "If a message is ambiguous, prefer categories like 'question' or 'not_now' "
            "over 'positive_interest'. When in doubt, err on the side of caution."
        )

        result = await self._llm.call(
            prompt=prompt,
            schema=ReplyClassificationOutput,
            model="gpt-4o-mini",
            task_name="reply_classification",
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=1500,
        )

        # Validate classification
        classification = result.result.classification
        if classification not in VALID_CATEGORIES:
            logger.warning("LLM returned invalid classification '%s', defaulting to 'question'", classification)
            result.result.classification = "question"
            result.result.confidence = min(result.result.confidence, 0.5)

        return result.result

    # ── Context loader ──────────────────────────────────────────────────────

    async def _load_reply_context(
        self, reply_id: uuid.UUID, db: AsyncSession
    ) -> tuple[Reply, Optional[OutreachMessage], Optional[Lead]]:
        """Load a reply and its related original message and lead."""
        result = await db.execute(select(Reply).where(Reply.id == reply_id))
        reply = result.scalar_one_or_none()
        if not reply:
            raise ValueError(f"Reply {reply_id} not found")

        original_message = None
        if reply.message_id:
            result = await db.execute(select(OutreachMessage).where(OutreachMessage.id == reply.message_id))
            original_message = result.scalar_one_or_none()

        lead = None
        result = await db.execute(select(Lead).where(Lead.id == reply.lead_id))
        lead = result.scalar_one_or_none()

        return reply, original_message, lead

    def _build_contact_context(self, lead: Optional[Lead], db: AsyncSession) -> str:
        """Build a brief context string about the contact/company."""
        # Synchronous helper — returns a static string; async version below
        if not lead:
            return ""
        parts = []
        if lead.pipeline_stage:
            parts.append(f"Pipeline stage: {lead.pipeline_stage}")
        if lead.lead_score:
            parts.append(f"Lead score: {lead.lead_score} ({lead.score_band})")
        return "\n".join(parts) if parts else ""

    # ── Public API ────────────────────────────────────────────────────────────

    async def classify_text(
        self,
        reply_text: str,
        original_subject: Optional[str] = None,
        original_body: Optional[str] = None,
        contact_context: Optional[str] = None,
    ) -> ClassificationItem:
        """Classify a reply from raw text.

        Tries rule-based first, then falls back to LLM.

        Parameters
        ----------
        reply_text : str
            The text of the prospect's reply.
        original_subject : str | None
            Subject line of the original outreach message.
        original_body : str | None
            Body of the original outreach message.
        contact_context : str | None
            Additional context about the prospect.

        Returns
        -------
        ClassificationItem
            The classification result.
        """
        # Try quick rule-based classification first
        quick = self._quick_classify(reply_text)
        if quick and quick.confidence >= 0.9:
            return quick

        # Use LLM for nuanced classification
        try:
            result = await self._classify_llm(
                reply_text=reply_text,
                original_subject=original_subject,
                original_body=original_body,
                contact_context=contact_context,
            )
            return result
        except Exception as exc:
            logger.warning("LLM classification failed: %s, using rule-based fallback", exc)
            if quick:
                return quick
            # Ultimate fallback
            return ClassificationItem(
                classification="question",
                subtype="uncertain",
                confidence=0.3,
                summary="Could not classify — defaulting to question.",
                recommended_action="manual_review",
                draft_response=None,
            )

    async def classify(
        self,
        reply_id: uuid.UUID,
        db: AsyncSession,
        model: Optional[str] = None,
    ) -> ReplyClassification:
        """Classify a persisted reply and save the classification.

        Parameters
        ----------
        reply_id : UUID
            The reply to classify.
        db : AsyncSession
            Database session.
        model : str | None
            Optional LLM model override.

        Returns
        -------
        ReplyClassification
            The persisted classification record.
        """
        reply, original_message, lead = await self._load_reply_context(reply_id, db)

        # Build context
        contact_context = self._build_contact_context(lead, db)

        original_subject = original_message.subject if original_message else None
        original_body = original_message.body if original_message else reply.subject or None

        # Classify
        result = await self.classify_text(
            reply_text=reply.body,
            original_subject=original_subject,
            original_body=original_body,
            contact_context=contact_context,
        )

        # Persist classification
        classification = ReplyClassification(
            reply_id=reply.id,
            lead_id=reply.lead_id,
            classification=result.classification,
            subtype=result.subtype,
            confidence=Decimal(str(round(result.confidence, 4))),
            summary=result.summary,
            recommended_action=result.recommended_action,
            draft_response=result.draft_response,
            model_used=model or "gpt-4o-mini",
        )
        db.add(classification)
        await db.flush()
        await db.refresh(classification)

        # Update lead status based on classification
        if lead and result.classification in ("positive_interest", "meeting_request"):
            lead.pipeline_stage = "replied"
            lead.status = "contacting"
            lead.next_action = "follow_up_positive_reply"
            lead.next_action_at = datetime.utcnow()
            lead.updated_at = datetime.utcnow()
            db.add(lead)
        elif lead and result.classification == "objection":
            lead.pipeline_stage = "replied"
            lead.status = "contacting"
            lead.next_action = "draft_objection_response"
            lead.updated_at = datetime.utcnow()
            db.add(lead)
        elif lead and result.classification in ("not_interested", "unsubscribe"):
            lead.pipeline_stage = "lost"
            lead.status = "lost"
            lead.next_action = "suppress_lead"
            lead.updated_at = datetime.utcnow()
            db.add(lead)
        elif lead and result.classification == "not_now":
            lead.pipeline_stage = "replied"
            lead.status = "contacting"
            lead.next_action = "schedule_nurture_follow_up"
            lead.updated_at = datetime.utcnow()
            db.add(lead)
        elif lead and result.classification == "out_of_office":
            lead.next_action = "schedule_reminder_after_ooo"
            lead.updated_at = datetime.utcnow()
            db.add(lead)

        await db.flush()

        # Log activity
        team_id = lead.team_id if lead else None
        await log_activity(
            db,
            team_id=team_id or uuid.UUID(int=0),
            user_id=None,
            lead_id=reply.lead_id,
            action="reply_classified",
            details={
                "classification": result.classification,
                "subtype": result.subtype,
                "confidence": float(result.confidence),
            },
        )

        return classification

    async def batch_classify(
        self,
        reply_ids: list[uuid.UUID],
        db: AsyncSession,
        model: Optional[str] = None,
    ) -> list[ReplyClassification]:
        """Classify multiple replies in sequence.

        Parameters
        ----------
        reply_ids : list[UUID]
            List of reply IDs to classify.
        db : AsyncSession
            Database session.
        model : str | None
            Optional LLM model override.

        Returns
        -------
        list[ReplyClassification]
            List of classification records.
        """
        results = []
        for reply_id in reply_ids:
            try:
                classification = await self.classify(reply_id, db, model=model)
                results.append(classification)
            except Exception as exc:
                logger.error("Failed to classify reply %s: %s", reply_id, exc)
        return results
