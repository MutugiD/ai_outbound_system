"""Personalization Engine — generates personalized outreach messages using lead context.

Gathers data from multiple sources (company, contact, signals, enrichment, audits)
and uses the LLM to produce highly personalized message variants that reference
specific pain points, signals, and company context.

Supports:
  - Email (subject + body) generation
  - LinkedIn DM generation
  - Multiple personalization strategies (pain-point, compliment, question, insight)
  - Template variable interpolation
  - A/B variant generation for testing
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.company import Company
from app.models.contact import Contact
from app.models.signal import BuyingSignal
from app.models.audit import WebsiteAudit
from app.models.enrichment import EnrichmentRecord
from app.models.campaign import Campaign, CampaignStep
from app.models.message import OutreachMessage
from app.services.ai.llm_service import LLMService
from app.services.activity_service import log_activity

logger = logging.getLogger(__name__)

# ── Personalization strategies ────────────────────────────────────────────────

STRATEGIES = [
    "pain_point",  # Lead with the prospect's pain / signal
    "compliment",  # Lead with genuine compliment about their work/company
    "question",  # Lead with a thought-provoking question
    "insight",  # Lead with a valuable insight or datapoint
    "direct",  # Short, direct value proposition
]

STRATEGY_DESCRIPTIONS = {
    "pain_point": "Start by acknowledging a specific pain point or challenge the prospect faces, then position your solution as the answer.",
    "compliment": "Start with a genuine compliment about their company, product, or recent achievement, then transition to how you can help.",
    "question": "Start with a thought-provoking question related to their role or industry, then offer value.",
    "insight": "Start with an interesting data point, trend, or insight relevant to their business, then connect it to your offering.",
    "direct": "Get straight to the point — state who you are, what you do, and why it matters to them in 2-3 sentences.",
}

# ── Tone guidelines ──────────────────────────────────────────────────────────

TONE_GUIDELINES = {
    "professional": "Use formal, business-appropriate language. Avoid slang. Be respectful and concise.",
    "casual": "Use friendly, approachable language. Write like you're talking to a peer. It's OK to be a bit informal.",
    "direct": "Be brief and to the point. No fluff, no lengthy introductions. Every sentence should earn its place.",
    "consultative": "Position yourself as an advisor. Ask questions, offer insights. Build trust through expertise.",
}

# ── LLM output schemas ───────────────────────────────────────────────────────


class MessageVariant(BaseModel):
    """A single personalized message variant."""

    subject: str = Field(description="Email subject line (empty for LinkedIn/SMS)")
    body: str = Field(description="The full message body, personalized for this lead")
    strategy: str = Field(description="The personalization strategy used")
    personalization_points: list[str] = Field(description="Specific data points used for personalization")
    confidence: float = Field(description="Confidence that this message will resonate (0-1)", ge=0.0, le=1.0)


class PersonalizationOutput(BaseModel):
    """Structured output from the personalization engine."""

    variants: list[MessageVariant] = Field(description="Generated message variants")


# ── Personalization context builder ──────────────────────────────────────────


class PersonalizationContext:
    """Gathers and formats all relevant lead context for personalization."""

    def __init__(
        self,
        lead: Lead,
        company: Optional[Company] = None,
        contact: Optional[Contact] = None,
        signals: Optional[list[BuyingSignal]] = None,
        audit: Optional[WebsiteAudit] = None,
        enrichments: Optional[list[EnrichmentRecord]] = None,
    ):
        self.lead = lead
        self.company = company
        self.contact = contact
        self.signals = signals or []
        self.audit = audit
        self.enrichments = enrichments or []

    def build_prompt_context(self) -> str:
        """Build a structured context string for the LLM prompt."""
        parts = []

        # Contact info
        if self.contact:
            contact_parts = []
            if self.contact.full_name:
                contact_parts.append(f"Name: {self.contact.full_name}")
            elif self.contact.first_name or self.contact.last_name:
                contact_parts.append(f"Name: {self.contact.first_name or ''} {self.contact.last_name or ''}".strip())
            if self.contact.title:
                contact_parts.append(f"Title: {self.contact.title}")
            if self.contact.seniority:
                contact_parts.append(f"Seniority: {self.contact.seniority}")
            if self.contact.department:
                contact_parts.append(f"Department: {self.contact.department}")
            if self.contact.email:
                contact_parts.append(f"Email: {self.contact.email}")
            if self.contact.location:
                contact_parts.append(f"Location: {self.contact.location}")
            if contact_parts:
                parts.append("## Contact Information\n" + "\n".join(contact_parts))

        # Company info
        if self.company:
            company_parts = []
            if self.company.name:
                company_parts.append(f"Company: {self.company.name}")
            if self.company.domain:
                company_parts.append(f"Website: {self.company.domain}")
            if self.company.industry:
                company_parts.append(f"Industry: {self.company.industry}")
            if self.company.sub_industry:
                company_parts.append(f"Sub-industry: {self.company.sub_industry}")
            if self.company.employee_count:
                company_parts.append(f"Employees: {self.company.employee_count}")
            if self.company.revenue_estimate:
                company_parts.append(f"Revenue: ${self.company.revenue_estimate:,.0f}")
            if self.company.funding_status:
                company_parts.append(f"Funding: {self.company.funding_status}")
            if self.company.description:
                company_parts.append(f"Description: {self.company.description[:500]}")
            if self.company.location:
                company_parts.append(f"HQ Location: {self.company.location}")
            if company_parts:
                parts.append("## Company Information\n" + "\n".join(company_parts))

        # Buying signals
        if self.signals:
            signal_lines = []
            for sig in self.signals[:10]:  # cap at 10 most relevant
                signal_lines.append(f"- [{sig.category}] (confidence: {sig.confidence}) {sig.evidence[:200]}")
            if signal_lines:
                parts.append("## Buying Signals\n" + "\n".join(signal_lines))

        # Website audit insights
        if self.audit:
            audit_parts = []
            if self.audit.website_score is not None:
                audit_parts.append(f"Website Score: {self.audit.website_score}/100")
            if not self.audit.has_chatbot:
                audit_parts.append("No chatbot detected")
            if not self.audit.has_booking:
                audit_parts.append("No online booking system detected")
            if not self.audit.has_contact_form:
                audit_parts.append("No contact form detected")
            if self.audit.weak_cta:
                audit_parts.append("Weak call-to-action detected")
            if self.audit.broken_forms:
                audit_parts.append("Broken forms detected")
            if self.audit.ai_summary:
                audit_parts.append(f"AI Summary: {self.audit.ai_summary[:500]}")
            if audit_parts:
                parts.append("## Website Audit\n" + "\n".join(audit_parts))

        # Enrichment highlights
        if self.enrichments:
            enrich_parts = []
            for enr in self.enrichments[:5]:
                if enr.data and isinstance(enr.data, dict):
                    data_str = ", ".join(f"{k}: {v}" for k, v in list(enr.data.items())[:5])
                    enrich_parts.append(f"- [{enr.enrichment_type}] {data_str}")
            if enrich_parts:
                parts.append("## Enrichment Data\n" + "\n".join(enrich_parts))

        return "\n\n".join(parts) if parts else "Limited information available about this lead."

    def get_top_signals(self, limit: int = 3) -> list[BuyingSignal]:
        """Return the top N signals by confidence."""
        sorted_signals = sorted(self.signals, key=lambda s: float(s.confidence), reverse=True)
        return sorted_signals[:limit]

    def get_contact_first_name(self) -> str:
        """Get the best available first name for personalization."""
        if self.contact:
            if self.contact.first_name:
                return self.contact.first_name
            if self.contact.full_name:
                parts = self.contact.full_name.split()
                if parts:
                    return parts[0]
        return "there"


# ── Personalization Engine ────────────────────────────────────────────────────


class PersonalizationEngine:
    """Generates personalized outreach messages using LLM and lead context.

    Usage::

        engine = PersonalizationEngine()
        messages = await engine.generate_messages(
            lead_id=lead_id,
            db=db,
            channel="email",
            strategies=["pain_point", "question"],
            tone="professional",
        )
    """

    def __init__(self, llm_service: Optional[LLMService] = None):
        self._llm = llm_service or LLMService()

    async def _load_context(self, lead_id: uuid.UUID, db: AsyncSession) -> PersonalizationContext:
        """Load all relevant data for personalizing messages for a lead."""
        # Fetch lead
        result = await db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Fetch company
        company = None
        if lead.company_id:
            result = await db.execute(select(Company).where(Company.id == lead.company_id))
            company = result.scalar_one_or_none()

        # Fetch contact
        contact = None
        if lead.contact_id:
            result = await db.execute(select(Contact).where(Contact.id == lead.contact_id))
            contact = result.scalar_one_or_none()

        # Fetch signals
        result = await db.execute(
            select(BuyingSignal).where(BuyingSignal.lead_id == lead_id).order_by(BuyingSignal.confidence.desc())
        )
        signals = list(result.scalars().all())

        # Fetch audit
        audit = None
        if lead.company_id:
            result = await db.execute(
                select(WebsiteAudit)
                .where(WebsiteAudit.company_id == lead.company_id)
                .order_by(WebsiteAudit.created_at.desc())
                .limit(1)
            )
            audit = result.scalar_one_or_none()

        # Fetch enrichment
        result = await db.execute(select(EnrichmentRecord).where(EnrichmentRecord.lead_id == lead_id))
        enrichments = list(result.scalars().all())

        return PersonalizationContext(
            lead=lead,
            company=company,
            contact=contact,
            signals=signals,
            audit=audit,
            enrichments=enrichments,
        )

    async def generate_messages(
        self,
        lead_id: uuid.UUID,
        db: AsyncSession,
        channel: str = "email",
        strategies: Optional[list[str]] = None,
        tone: str = "professional",
        goal: str = "generate_interest",
        custom_instructions: Optional[str] = None,
        num_variants: int = 2,
        model: Optional[str] = None,
    ) -> list[OutreachMessage]:
        """Generate personalized outreach messages for a lead.

        Parameters
        ----------
        lead_id : UUID
            The lead to generate messages for.
        db : AsyncSession
            Database session.
        channel : str
            Output channel: email, linkedin, sms.
        strategies : list[str] | None
            Personalization strategies to use. Defaults to ["pain_point", "question"].
        tone : str
            Message tone: professional, casual, direct, consultative.
        goal : str
            Campaign goal: book_meeting, generate_interest, nurture.
        custom_instructions : str | None
            Additional instructions to inject into the prompt.
        num_variants : int
            How many message variants to generate (1-5).
        model : str | None
            LLM model override.

        Returns
        -------
        list[OutreachMessage]
            Persisted OutreachMessage records (in draft status).
        """
        strategies = strategies or ["pain_point", "question"]
        num_variants = max(1, min(num_variants, 5))
        tone_guideline = TONE_GUIDELINES.get(tone, TONE_GUIDELINES["professional"])

        # Load context
        ctx = await self._load_context(lead_id, db)
        context_text = ctx.build_prompt_context()
        top_signals = ctx.get_top_signals(3)
        first_name = ctx.get_contact_first_name()

        # Build strategy descriptions for the prompt
        strategy_descs = []
        for s in strategies:
            desc = STRATEGY_DESCRIPTIONS.get(s, STRATEGY_DESCRIPTIONS["direct"])
            strategy_descs.append(f"- {s}: {desc}")
        strategy_list = "\n".join(strategy_descs)

        # Build signal summary for focus
        signal_summary = ""
        if top_signals:
            signal_lines = [f"  * {s.category}: {s.evidence[:150]}" for s in top_signals]
            signal_summary = "Key signals to reference:\n" + "\n".join(signal_lines)

        # Channel-specific instructions
        channel_instructions = {
            "email": (
                "Generate an email with a subject line and body. "
                "The subject should be short (3-6 words), curiosity-inducing, and personal. "
                "The body should be 50-150 words. Include a clear call-to-action."
            ),
            "linkedin": (
                "Generate a LinkedIn DM. No subject line needed. "
                "Keep it under 300 characters for the connection request note, "
                "or under 500 characters for a follow-up DM. Be conversational."
            ),
            "sms": ("Generate an SMS message. No subject line. Keep it under 160 characters. Be extremely concise."),
        }

        channel_instruction = channel_instructions.get(channel, channel_instructions["email"])

        # Goal-specific guidance
        goal_guidance = {
            "book_meeting": "The goal is to book a call/meeting. Include a specific, low-friction meeting ask.",
            "generate_interest": "The goal is to generate initial interest. Focus on value and curiosity, don't push too hard for a meeting.",
            "nurture": "The goal is to nurture the relationship over time. Be helpful, share an insight, don't ask for anything yet.",
        }
        goal_text = goal_guidance.get(goal, goal_guidance["generate_interest"])

        # Construct prompt
        prompt = (
            f"You are an expert outbound sales copywriter generating personalized {channel} messages.\n\n"
            f"## Context about the lead\n{context_text}\n\n"
            f"## Personalization Strategy\nChoose from these strategies:\n{strategy_list}\n\n"
            f"## Signal Insights\n{signal_summary}\n\n"
            f"## Instructions\n"
            f"- Channel: {channel}\n"
            f"- Tone: {tone_guideline}\n"
            f"- Goal: {goal_text}\n"
            f"- {channel_instruction}\n"
            f"- Address the contact by first name ({first_name}) when appropriate for the channel.\n"
            f"- Reference specific signals, company details, or pain points found in the context above.\n"
            f"- Do NOT make up facts not present in the context. If context is limited, use general but relevant messaging.\n"
            f"- Generate exactly {num_variants} message variant(s), each using a DIFFERENT strategy from the list.\n"
            f"- For each variant, list the specific data points you used for personalization.\n"
        )

        if custom_instructions:
            prompt += f"\n- Additional instructions: {custom_instructions}\n"

        # System prompt
        system_prompt = (
            "You are a world-class outbound copywriter who crafts personalized messages "
            "that get replies. You always ground your messages in real data about the lead "
            "and their company. You never use spammy or generic language. Every message "
            "must feel like it was written specifically for this one person."
        )

        try:
            result = await self._llm.call(
                prompt=prompt,
                schema=PersonalizationOutput,
                model=model or "gpt-4o",
                task_name="personalization",
                system_prompt=system_prompt,
                temperature=0.8,
                max_tokens=3000,
            )
        except Exception as exc:
            logger.error("Personalization engine LLM call failed: %s", exc)
            # Fallback: generate a simple template-based message
            return await self._generate_fallback_messages(
                ctx=ctx,
                channel=channel,
                tone=tone,
                db=db,
            )

        # Persist messages
        messages = []
        for variant in result.variants[:num_variants]:
            personalization_sources = []
            if ctx.company and ctx.company.name:
                personalization_sources.append(f"company:{ctx.company.name}")
            if ctx.contact and ctx.contact.title:
                personalization_sources.append(f"title:{ctx.contact.title}")
            for sig in top_signals:
                personalization_sources.append(f"signal:{sig.category}")

            msg = OutreachMessage(
                lead_id=lead_id,
                channel=channel,
                subject=variant.subject if channel == "email" else None,
                body=variant.body,
                personalization_sources=personalization_sources,
                status="draft",
            )
            db.add(msg)
            messages.append(msg)

        await db.flush()

        # Refresh to get IDs
        for msg in messages:
            await db.refresh(msg)

        # Log activity
        await log_activity(
            db,
            team_id=ctx.lead.team_id,
            user_id=None,
            lead_id=lead_id,
            action="message_generated",
            details={
                "channel": channel,
                "num_variants": len(messages),
                "strategies": strategies,
                "tone": tone,
            },
        )

        return messages

    async def _generate_fallback_messages(
        self,
        ctx: PersonalizationContext,
        channel: str,
        tone: str,
        db: AsyncSession,
    ) -> list[OutreachMessage]:
        """Generate simple template-based messages as fallback when LLM fails."""
        first_name = ctx.get_contact_first_name()
        company_name = ctx.company.name if ctx.company else "your company"

        if channel == "email":
            subject = f"Quick question about {company_name}"
            body = (
                f"Hi {first_name},\n\n"
                f"I came across {company_name} and thought there might be a fit "
                f"with what we're doing. Would love to share some ideas.\n\n"
                f"Are you open to a quick chat this week?\n\n"
                f"Best,\n[Your Name]"
            )
        elif channel == "linkedin":
            body = (
                f"Hi {first_name}, I saw your work at {company_name} and think "
                f"there could be some interesting synergies. Would love to connect."
            )
            subject = None
        else:  # sms
            body = f"Hi {first_name}, quick question about {company_name} — open to chatting?"
            subject = None

        msg = OutreachMessage(
            lead_id=ctx.lead.id,
            channel=channel,
            subject=subject,
            body=body,
            personalization_sources=["fallback_template"],
            status="draft",
        )
        db.add(msg)
        await db.flush()
        await db.refresh(msg)
        return [msg]

    async def generate_for_campaign_step(
        self,
        lead_id: uuid.UUID,
        campaign_step_id: uuid.UUID,
        db: AsyncSession,
        tone: str = "professional",
        goal: str = "generate_interest",
        model: Optional[str] = None,
    ) -> list[OutreachMessage]:
        """Generate messages using a campaign step's template as a starting point.

        Merges the template structure with personalized content.
        """
        # Load campaign step
        result = await db.execute(select(CampaignStep).where(CampaignStep.id == campaign_step_id))
        step = result.scalar_one_or_none()
        if not step:
            raise ValueError(f"CampaignStep {campaign_step_id} not found")

        # Determine channel
        channel = step.channel or "email"

        # If step has templates, use them as additional context
        custom_instructions = ""
        if step.template_type:
            custom_instructions += f"Message type: {step.template_type}. "
        if step.body_template:
            custom_instructions += (
                f"Consider this template structure (adapt and personalize it): {step.body_template[:500]} "
            )

        messages = await self.generate_messages(
            lead_id=lead_id,
            db=db,
            channel=channel,
            strategies=["pain_point", "compliment"],
            tone=tone,
            goal=goal,
            custom_instructions=custom_instructions if custom_instructions.strip() else None,
            num_variants=1,
            model=model,
        )

        # Attach campaign context
        for msg in messages:
            msg.campaign_step_id = campaign_step_id
            msg.campaign_id = step.campaign_id

        await db.flush()
        return messages
