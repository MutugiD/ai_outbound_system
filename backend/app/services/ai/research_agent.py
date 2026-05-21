"""Business research agent — generates comprehensive research briefs for companies.

Uses LLMService for structured output. Produces an AIResearchReport record
that a sales team can use to understand a prospect's pain points, competitive
landscape, revenue leakage hypotheses, and recommended outreach angle.
"""

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.company import Company
from app.models.contact import Contact
from app.models.enrichment import EnrichmentRecord
from app.models.signal import BuyingSignal
from app.models.audit import WebsiteAudit
from app.models.lead_source import LeadSource
from app.models.research import AIResearchReport
from app.services.ai.llm_service import LLMService
from app.services.activity_service import log_activity

logger = logging.getLogger(__name__)

# ── Pydantic output schema ──────────────────────────────────────────────────


class ResearchBriefSchema(BaseModel):
    """Structured output schema for the research brief LLM call."""

    company_summary: str = Field(
        description="Concise summary of the company: what they do, size, industry, market position."
    )
    target_customer: str = Field(
        description="Who this company sells to — ICP description with role/industry clues."
    )
    likely_operational_pain: list[str] = Field(
        default_factory=list,
        description="List of identified or hypothesised operational pain points, grounded in evidence."
    )
    revenue_leakage_hypothesis: list[str] = Field(
        default_factory=list,
        description="Hypotheses on where the company may be losing revenue, with reasoning."
    )
    competitor_observations: list[str] = Field(
        default_factory=list,
        description="Competitive landscape observations relevant to the outreach angle."
    )
    recommended_outreach_angle: str = Field(
        description="Specific positioning and value proposition to lead with in outbound messaging."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence in the brief based on data completeness (0-1).",
    )
    sources_used: list[str] = Field(
        default_factory=list,
        description="List of source identifiers that contributed evidence to this brief."
    )


# ── System prompt ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are an expert business analyst. Analyze this company and generate a "
    "research brief for a sales team. Base ALL observations on the provided "
    "evidence. If evidence is thin for an area, say so rather than fabricating. "
    "Be specific — avoid generic statements that could apply to any company. "
    "Prioritise actionable insights that a sales rep can use to craft a "
    "personalised outreach message."
)

# ── User prompt template ──────────────────────────────────────────────────

PROMPT_TEMPLATE = """\
## COMPANY INFORMATION
{company_section}

## CONTACT INFORMATION
{contact_section}

## ENRICHMENT DATA
{enrichment_section}

## BUYING SIGNALS
{signals_section}

## WEBSITE AUDIT
{audit_section}

## SOURCE TEXT EVIDENCE
{sources_section}

---

Based on ALL the evidence above, generate a research brief with the following:

1. **company_summary**: Concise summary of the company — what they do, size, industry, market position. Only state what is supported by evidence.

2. **target_customer**: Who this company likely sells to — describe the ideal customer profile with role/industry clues from the data.

3. **likely_operational_pain**: List specific operational pain points you can identify or hypothesise from the evidence. For each point, explain the reasoning. If evidence is thin, say "Limited evidence — hypothesis based on industry patterns".

4. **revenue_leakage_hypothesis**: List hypotheses about where the company may be losing revenue — inefficient processes, poor conversion, manual overhead, etc. Include reasoning for each.

5. **competitor_observations**: Observations about the competitive landscape relevant to this company. What alternatives might their prospects use? What differentiators matter?

6. **recommended_outreach_angle**: A specific positioning and value proposition to lead with. Be concrete — reference the company's situation, not generic benefits.

7. **confidence**: A number 0-1 reflecting how complete and reliable the data is. Low data = low confidence. State what is missing that would improve confidence.

8. **sources_used**: List the specific sources that contributed evidence to this brief (e.g. "enrichment_apollo", "signal_crm_pain", "audit_website", "source_reddit").
"""


# ── Research Agent ──────────────────────────────────────────────────────────


class ResearchAgent:
    """Generates comprehensive research briefs for companies using LLM + DB data."""

    def __init__(self, llm_service: Optional[LLMService] = None) -> None:
        self._llm = llm_service

    # ── Full pipeline (from DB) ────────────────────────────────────────────

    async def generate_research(
        self,
        lead_id: uuid.UUID,
        db: AsyncSession,
        model: Optional[str] = None,
    ) -> AIResearchReport:
        """Generate a research brief for a lead by loading all related data from the DB.

        Steps:
        1. Load lead + company + contact
        2. Load enrichment records
        3. Load buying signals
        4. Load website audits
        5. Load lead sources (raw text evidence)
        6. Compile context into structured prompt
        7. Call LLM with ResearchBriefSchema
        8. Persist AIResearchReport
        9. Log activity
        10. Return report
        """
        # ── a. Load lead ────────────────────────────────────────────────
        result = await db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # ── Load company ────────────────────────────────────────────────
        company: Optional[Company] = None
        if lead.company_id:
            result = await db.execute(select(Company).where(Company.id == lead.company_id))
            company = result.scalar_one_or_none()

        # ── Load contact ─────────────────────────────────────────────────
        contact: Optional[Contact] = None
        if lead.contact_id:
            result = await db.execute(select(Contact).where(Contact.id == lead.contact_id))
            contact = result.scalar_one_or_none()

        # ── b. Load enrichment records ───────────────────────────────────
        result = await db.execute(
            select(EnrichmentRecord).where(EnrichmentRecord.lead_id == lead_id)
        )
        enrichment_records = list(result.scalars().all())

        # ── c. Load buying signals ───────────────────────────────────────
        result = await db.execute(
            select(BuyingSignal).where(BuyingSignal.lead_id == lead_id)
        )
        buying_signals = list(result.scalars().all())

        # ── d. Load website audits ───────────────────────────────────────
        audits: list[WebsiteAudit] = []
        if lead.company_id:
            result = await db.execute(
                select(WebsiteAudit)
                .where(WebsiteAudit.company_id == lead.company_id)
                .order_by(WebsiteAudit.created_at.desc())
                .limit(5)
            )
            audits = list(result.scalars().all())

        # ── e. Load lead sources ─────────────────────────────────────────
        result = await db.execute(
            select(LeadSource).where(LeadSource.lead_id == lead_id)
        )
        lead_sources = list(result.scalars().all())

        # ── f. Compile context into prompt ──────────────────────────────
        prompt = self._build_prompt(
            company=company,
            contact=contact,
            enrichment_records=enrichment_records,
            buying_signals=buying_signals,
            audits=audits,
            lead_sources=lead_sources,
        )

        # ── g+h. Call LLM ────────────────────────────────────────────────
        llm = self._llm or LLMService()
        brief: ResearchBriefSchema = await llm.call(
            prompt=prompt,
            schema=ResearchBriefSchema,
            model=model or "gpt-4o",
            task_name="research_brief",
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=3000,
        )

        # Get model info from LLM usage metadata
        model_used = getattr(brief, "_llm_usage", {}).get("model", model or "gpt-4o")

        # ── i. Store AIResearchReport ─────────────────────────────────────
        report = AIResearchReport(
            lead_id=lead_id,
            version=1,
            company_summary=brief.company_summary,
            target_customer=brief.target_customer,
            likely_operational_pain=brief.likely_operational_pain,
            revenue_leakage_hypothesis=brief.revenue_leakage_hypothesis,
            competitor_observations=brief.competitor_observations,
            recommended_outreach_angle=brief.recommended_outreach_angle,
            confidence=Decimal(str(round(brief.confidence, 4))),
            model_used=model_used,
            sources_used=brief.sources_used,
        )
        db.add(report)

        # Update lead status
        lead.status = "researched"
        lead.pipeline_stage = "researched"
        lead.updated_at = datetime.utcnow()
        db.add(lead)

        await db.flush()
        await db.refresh(report)

        # ── j. Log activity ───────────────────────────────────────────────
        await log_activity(
            db,
            team_id=lead.team_id,
            user_id=None,
            lead_id=lead_id,
            action="research_completed",
            details={
                "report_id": str(report.id),
                "confidence": float(brief.confidence),
                "sources_count": len(brief.sources_used),
                "pain_points": len(brief.likely_operational_pain),
                "model_used": model_used,
            },
        )

        # ── k. Return report ─────────────────────────────────────────────
        return report

    # ── Standalone version (no DB) ────────────────────────────────────────

    async def generate_from_context(
        self,
        company_name: str,
        domain: Optional[str] = None,
        website_text: Optional[str] = None,
        signals: Optional[list[dict]] = None,
        audit_data: Optional[dict] = None,
        enrichment_data: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> ResearchBriefSchema:
        """Generate a research brief from provided context (no DB required).

        Useful for testing or ad-hoc research without persisting to the database.

        Parameters
        ----------
        company_name : str
            Name of the company to research.
        domain : str | None
            Company domain/website URL.
        website_text : str | None
            Text scraped from the company website.
        signals : list[dict] | None
            Buying signal dicts with category, evidence, confidence keys.
        audit_data : dict | None
            Website audit findings (has_chatbot, has_booking, website_score, etc.)
        enrichment_data : list[dict] | None
            Enrichment records with enrichment_type and data keys.
        model : str | None
            LLM model to use.

        Returns
        -------
        ResearchBriefSchema
            The validated research brief.
        """
        # Build sections
        company_section = f"Name: {company_name}"
        if domain:
            company_section += f"\nDomain: {domain}"

        contact_section = "No contact data provided for this context-only analysis."

        enrichment_section = "No enrichment data provided."
        if enrichment_data:
            lines = []
            for enr in enrichment_data:
                enr_type = enr.get("enrichment_type", "unknown")
                enr_data = enr.get("data", {})
                lines.append(f"[{enr_type}] {enr_data}")
            enrichment_section = "\n".join(lines)

        signals_section = "No buying signals detected."
        if signals:
            lines = []
            for sig in signals:
                cat = sig.get("category", "unknown")
                evidence = sig.get("evidence", "")
                conf = sig.get("confidence", 0)
                lines.append(f"- [{cat}] (confidence: {conf}) {evidence}")
            signals_section = "\n".join(lines)

        audit_section = "No website audit available."
        if audit_data:
            lines = []
            for key, value in audit_data.items():
                lines.append(f"- {key}: {value}")
            audit_section = "\n".join(lines)

        sources_section = "No raw source text available."
        if website_text:
            sources_section = website_text[:4000]

        prompt = PROMPT_TEMPLATE.format(
            company_section=company_section,
            contact_section=contact_section,
            enrichment_section=enrichment_section,
            signals_section=signals_section,
            audit_section=audit_section,
            sources_section=sources_section,
        )

        llm = self._llm or LLMService()
        brief: ResearchBriefSchema = await llm.call(
            prompt=prompt,
            schema=ResearchBriefSchema,
            model=model or "gpt-4o",
            task_name="research_brief_context",
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=3000,
        )

        return brief

    # ── Prompt builder ────────────────────────────────────────────────────

    @staticmethod
    def _build_prompt(
        company: Optional[Company],
        contact: Optional[Contact],
        enrichment_records: list[EnrichmentRecord],
        buying_signals: list[BuyingSignal],
        audits: list[WebsiteAudit],
        lead_sources: list[LeadSource],
    ) -> str:
        """Compile all available data into a structured prompt string."""

        # ── Company section ────────────────────────────────────────────
        if company:
            company_lines = [f"Name: {company.name}"]
            if company.domain:
                company_lines.append(f"Domain: {company.domain}")
            if company.industry:
                company_lines.append(f"Industry: {company.industry}")
            if company.sub_industry:
                company_lines.append(f"Sub-industry: {company.sub_industry}")
            if company.description:
                company_lines.append(f"Description: {company.description}")
            if company.employee_count:
                company_lines.append(f"Employees: {company.employee_count}")
            if company.employee_count_range:
                company_lines.append(f"Employee range: {company.employee_count_range}")
            if company.revenue_estimate:
                company_lines.append(f"Revenue estimate: {company.revenue_estimate}")
            if company.revenue_range:
                company_lines.append(f"Revenue range: {company.revenue_range}")
            if company.funding_status:
                company_lines.append(f"Funding status: {company.funding_status}")
            if company.funding_total:
                company_lines.append(f"Funding total: {company.funding_total}")
            if company.location:
                company_lines.append(f"Location: {company.location}")
            if company.linkedin_url:
                company_lines.append(f"LinkedIn: {company.linkedin_url}")
            company_section = "\n".join(company_lines)
        else:
            company_section = "No company data available."

        # ── Contact section ────────────────────────────────────────────
        if contact:
            contact_lines = []
            if contact.full_name:
                contact_lines.append(f"Name: {contact.full_name}")
            if contact.title:
                contact_lines.append(f"Title: {contact.title}")
            if contact.seniority:
                contact_lines.append(f"Seniority: {contact.seniority}")
            if contact.department:
                contact_lines.append(f"Department: {contact.department}")
            if contact.email:
                contact_lines.append(f"Email: {contact.email} (status: {contact.email_status})")
            if contact.phone:
                contact_lines.append(f"Phone: {contact.phone}")
            if contact.linkedin_url:
                contact_lines.append(f"LinkedIn: {contact.linkedin_url}")
            contact_section = "\n".join(contact_lines) if contact_lines else "Contact exists but no details."
        else:
            contact_section = "No contact data available."

        # ── Enrichment section ─────────────────────────────────────────
        if enrichment_records:
            enrichment_lines = []
            for enr in enrichment_records:
                enr_type = enr.enrichment_type or "unknown"
                provider = enr.provider or "unknown"
                data = enr.data if isinstance(enr.data, dict) else {}
                enrichment_lines.append(f"[{provider}/{enr_type}] {data}")
            enrichment_section = "\n".join(enrichment_lines)
        else:
            enrichment_section = "No enrichment data available."

        # ── Buying signals section ──────────────────────────────────────
        if buying_signals:
            signal_lines = []
            for sig in buying_signals:
                cat = sig.category
                evidence = sig.evidence[:500] if sig.evidence else ""
                conf = float(sig.confidence) if sig.confidence else 0.0
                source = sig.source or "unknown"
                method = sig.detection_method or "rule"
                signal_lines.append(
                    f"- [{cat}] (confidence: {conf:.2f}, source: {source}, method: {method}) "
                    f"Evidence: {evidence}"
                )
            signals_section = "\n".join(signal_lines)
        else:
            signals_section = "No buying signals detected."

        # ── Website audit section ──────────────────────────────────────
        if audits:
            audit_lines = []
            for audit in audits:
                audit_lines.append(f"Website score: {audit.website_score}")
                audit_lines.append(f"Page speed: {audit.page_speed_score}")
                audit_lines.append(f"Mobile score: {audit.mobile_score}")
                audit_lines.append(f"Has chatbot: {audit.has_chatbot}")
                audit_lines.append(f"Has booking tool: {audit.has_booking}")
                audit_lines.append(f"Has contact form: {audit.has_contact_form}")
                audit_lines.append(f"Has email capture: {audit.has_email_capture}")
                audit_lines.append(f"Has CRM form: {audit.has_crm_form}")
                audit_lines.append(f"Has tracking scripts: {audit.has_tracking_scripts}")
                audit_lines.append(f"Has support widget: {audit.has_support_widget}")
                audit_lines.append(f"Weak CTA: {audit.weak_cta}")
                audit_lines.append(f"Broken forms: {audit.broken_forms}")
                if audit.sales_angle:
                    audit_lines.append(f"Sales angle: {audit.sales_angle}")
                if audit.technical_findings:
                    audit_lines.append(f"Technical findings: {audit.technical_findings}")
                if audit.conversion_findings:
                    audit_lines.append(f"Conversion findings: {audit.conversion_findings}")
                if audit.automation_findings:
                    audit_lines.append(f"Automation findings: {audit.automation_findings}")
            audit_section = "\n".join(audit_lines)
        else:
            audit_section = "No website audit available."

        # ── Source text section ─────────────────────────────────────────
        if lead_sources:
            source_lines = []
            for src in lead_sources:
                src_type = src.source_type or "unknown"
                src_name = src.source_name or ""
                raw_text = (src.raw_text or "")[:2000]
                detected = src.detected_signal_text or ""
                header = f"--- [{src_type}] {src_name} ---"
                if src.source_url:
                    header += f" ({src.source_url})"
                text = raw_text
                if detected:
                    text += f"\nDetected signals: {detected}"
                source_lines.append(f"{header}\n{text}")
            sources_section = "\n\n".join(source_lines)[:8000]
        else:
            sources_section = "No raw source text available."

        return PROMPT_TEMPLATE.format(
            company_section=company_section,
            contact_section=contact_section,
            enrichment_section=enrichment_section,
            signals_section=signals_section,
            audit_section=audit_section,
            sources_section=sources_section,
        )