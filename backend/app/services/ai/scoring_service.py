"""Lead scoring engine — weighted multi-dimensional scoring.

Scoring formula:
  total = buying_intent(20%) + urgency(15%) + operational_pain(15%)
        + scaling_pressure(15%) + budget_probability(10%)
        + website_weakness(10%) + contactability(10%) + recency(5%)

Each dimension is scored 0-100, then the weighted sum produces the final
lead_score.  Score bands are:
  very_hot: 85-100
  hot:      70-84
  warm:     55-69
  weak:     40-54
  low:      0-39
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.company import Company
from app.models.contact import Contact
from app.models.signal import BuyingSignal
from app.models.score import LeadScore
from app.models.audit import WebsiteAudit
from app.models.enrichment import EnrichmentRecord
from app.services.activity_service import log_activity

logger = logging.getLogger(__name__)

# ── Scoring weights ────────────────────────────────────────────────────────────

WEIGHTS = {
    "buying_intent": 0.20,
    "urgency": 0.15,
    "operational_pain": 0.15,
    "scaling_pressure": 0.15,
    "budget_probability": 0.10,
    "website_weakness": 0.10,
    "contactability": 0.10,
    "recency": 0.05,
}

# ── Score bands ───────────────────────────────────────────────────────────────

SCORE_BANDS = [
    (85, "very_hot"),
    (70, "hot"),
    (55, "warm"),
    (40, "weak"),
    (0, "low"),
]


def _band(score: int) -> str:
    """Map a numeric score to a score band string."""
    for threshold, band in SCORE_BANDS:
        if score >= threshold:
            return band
    return "low"


# ── Scoring service ───────────────────────────────────────────────────────────


class ScoringService:
    """Calculate multi-dimensional lead scores based on signals, enrichment data,
    website audits, and contact info."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Public API ──────────────────────────────────────────────────────────

    async def calculate_score(self, lead_id: uuid.UUID) -> LeadScore:
        """Calculate and persist a lead score.

        Returns
        -------
        LeadScore
            The persisted score record.
        """
        # Fetch lead with related data
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Fetch related data
        company: Optional[Company] = None
        contact: Optional[Contact] = None
        signals: list[BuyingSignal] = []
        audits: list[WebsiteAudit] = []
        enrichments: list[EnrichmentRecord] = []

        if lead.company_id:
            result = await self.db.execute(select(Company).where(Company.id == lead.company_id))
            company = result.scalar_one_or_none()

        if lead.contact_id:
            result = await self.db.execute(select(Contact).where(Contact.id == lead.contact_id))
            contact = result.scalar_one_or_none()

        # Fetch signals for this lead
        result = await self.db.execute(
            select(BuyingSignal).where(BuyingSignal.lead_id == lead_id)
        )
        signals = list(result.scalars().all())

        # Fetch latest website audit for the company
        if lead.company_id:
            result = await self.db.execute(
                select(WebsiteAudit)
                .where(WebsiteAudit.company_id == lead.company_id)
                .order_by(WebsiteAudit.created_at.desc())
                .limit(1)
            )
            audit_row = result.scalar_one_or_none()
            if audit_row:
                audits = [audit_row]

        # Fetch enrichment records
        result = await self.db.execute(
            select(EnrichmentRecord).where(EnrichmentRecord.lead_id == lead_id)
        )
        enrichments = list(result.scalars().all())

        # ── Calculate each dimension ───────────────────────────────────
        buying_intent = self._score_buying_intent(signals)
        urgency = self._score_urgency(signals, enrichments)
        operational_pain = self._score_operational_pain(signals)
        scaling_pressure = self._score_scaling_pressure(signals, company, enrichments)
        budget_probability = self._score_budget_probability(company, enrichments)
        website_weakness = self._score_website_weakness(audits)
        contactability = self._score_contactability(contact, enrichments)
        recency = self._score_recency(signals)

        # ── Weighted total ──────────────────────────────────────────────
        total = int(round(
            buying_intent * WEIGHTS["buying_intent"]
            + urgency * WEIGHTS["urgency"]
            + operational_pain * WEIGHTS["operational_pain"]
            + scaling_pressure * WEIGHTS["scaling_pressure"]
            + budget_probability * WEIGHTS["budget_probability"]
            + website_weakness * WEIGHTS["website_weakness"]
            + contactability * WEIGHTS["contactability"]
            + recency * WEIGHTS["recency"]
        ))
        total = max(0, min(100, total))  # clamp to 0-100
        band = _band(total)

        # ── Generate explanation ─────────────────────────────────────────
        explanation = self._generate_explanation(
            lead_id=lead_id,
            total=total,
            band=band,
            buying_intent=buying_intent,
            urgency=urgency,
            operational_pain=operational_pain,
            scaling_pressure=scaling_pressure,
            budget_probability=budget_probability,
            website_weakness=website_weakness,
            contactability=contactability,
            recency=recency,
            signals=signals,
        )

        # ── Persist score ────────────────────────────────────────────────
        score = LeadScore(
            lead_id=lead_id,
            total_score=total,
            score_band=band,
            buying_intent_score=buying_intent,
            urgency_score=urgency,
            operational_pain_score=operational_pain,
            scaling_pressure_score=scaling_pressure,
            budget_probability_score=budget_probability,
            website_weakness_score=website_weakness,
            contactability_score=contactability,
            recency_score=recency,
            explanation=explanation,
        )
        self.db.add(score)

        # Update lead
        lead.lead_score = total
        lead.score_band = band
        lead.updated_at = datetime.utcnow()
        self.db.add(lead)

        await self.db.flush()
        await self.db.refresh(score)

        # Log activity
        await log_activity(
            self.db,
            team_id=lead.team_id,
            user_id=None,
            lead_id=lead_id,
            action="score_calculated",
            details={"total": total, "band": band},
        )

        return score

    # ── Dimension scorers (each returns 0-100) ─────────────────────────────

    @staticmethod
    def _score_buying_intent(signals: list[BuyingSignal]) -> int:
        """Score buying intent: based on count and confidence of signals.

        More signals and higher confidence = higher score.
        """
        if not signals:
            return 10  # baseline — no signals doesn't mean zero

        # Weight by confidence
        total_weight = sum(float(s.confidence) for s in signals)
        count = len(signals)

        # High-signal categories that strongly indicate buying intent
        strong_categories = {
            "funding_event", "rapid_hiring", "scaling_issues",
            "crm_pain", "manual_processes", "workflow_inefficiency",
        }
        strong_count = sum(1 for s in signals if s.category in strong_categories)

        # Score formula: base from count, boost from strong signals and total confidence
        base = min(count * 12, 50)
        strong_boost = min(strong_count * 10, 25)
        conf_boost = min(int(total_weight * 8), 25)

        return min(base + strong_boost + conf_boost, 100)

    @staticmethod
    def _score_urgency(signals: list[BuyingSignal], enrichments: list[EnrichmentRecord]) -> int:
        """Score urgency: recency of signals and funding events.

        Recent signals and funding events indicate urgency.
        """
        if not signals:
            return 10

        now = datetime.utcnow()

        # Check for funding events (high urgency)
        funding_signals = [s for s in signals if s.category == "funding_event"]
        if funding_signals:
            # Funding event = high urgency
            base = 60
            # Boost if recent (within 90 days)
            for sig in funding_signals:
                days_ago = (now - sig.detected_at.replace(tzinfo=None)).days if sig.detected_at else 999
                if days_ago <= 30:
                    base += 25
                elif days_ago <= 90:
                    base += 15
                elif days_ago <= 180:
                    base += 5
            return min(base, 100)

        # Check for rapid hiring (urgency indicator)
        hiring_signals = [s for s in signals if s.category in ("rapid_hiring", "hiring_ops_role")]
        if hiring_signals:
            base = 50
            for sig in hiring_signals:
                days_ago = (now - sig.detected_at.replace(tzinfo=None)).days if sig.detected_at else 999
                if days_ago <= 30:
                    base += 20
                elif days_ago <= 90:
                    base += 10
            return min(base, 100)

        # General signal recency
        avg_recency_days = 0
        valid_count = 0
        for sig in signals:
            if sig.detected_at:
                days_ago = (now - sig.detected_at.replace(tzinfo=None)).days
                avg_recency_days += days_ago
                valid_count += 1

        if valid_count > 0:
            avg_recency_days /= valid_count
        else:
            return 20

        if avg_recency_days <= 7:
            return 55
        elif avg_recency_days <= 30:
            return 45
        elif avg_recency_days <= 90:
            return 30
        else:
            return 15

    @staticmethod
    def _score_operational_pain(signals: list[BuyingSignal]) -> int:
        """Score operational pain: based on signal categories indicating pain."""
        if not signals:
            return 10

        pain_categories = {
            "crm_pain": 20,
            "workflow_inefficiency": 18,
            "support_overload": 16,
            "manual_processes": 18,
            "onboarding_complaints": 14,
            "founder_burnout": 16,
            "heavy_support_requests": 15,
            "fragmented_tools": 12,
            "tool_stack_overload": 12,
        }

        score = 0
        for sig in signals:
            weight = pain_categories.get(sig.category, 5)
            # Scale by confidence
            score += int(weight * float(sig.confidence))

        return min(max(score, 10), 100)

    @staticmethod
    def _score_scaling_pressure(
        signals: list[BuyingSignal],
        company: Optional[Company],
        enrichments: list[EnrichmentRecord],
    ) -> int:
        """Score scaling pressure: employee growth, job volume, funding."""
        score = 10  # baseline

        # From signals
        scaling_categories = {
            "rapid_hiring": 25,
            "scaling_issues": 20,
            "funding_event": 15,
            "hiring_ops_role": 10,
        }
        for sig in signals:
            weight = scaling_categories.get(sig.category, 0)
            score += int(weight * float(sig.confidence))

        # From company data
        if company and company.employee_count:
            if company.employee_count >= 50:
                score += 10
            elif company.employee_count >= 20:
                score += 5

        # From enrichment - funding data
        for enr in enrichments:
            if enr.enrichment_type == "company" and enr.data:
                data = enr.data if isinstance(enr.data, dict) else {}
                if data.get("funding_total") or data.get("funding_status"):
                    score += 10
                if data.get("company_size"):
                    size = data["company_size"]
                    if size >= 50:
                        score += 5
                    elif size >= 20:
                        score += 3

        return min(max(score, 10), 100)

    @staticmethod
    def _score_budget_probability(
        company: Optional[Company],
        enrichments: list[EnrichmentRecord],
    ) -> int:
        """Score budget probability: based on company size, revenue, industry."""
        score = 20  # baseline

        if company:
            # Employee count is a proxy for budget
            if company.employee_count:
                if company.employee_count >= 500:
                    score += 30
                elif company.employee_count >= 100:
                    score += 25
                elif company.employee_count >= 50:
                    score += 20
                elif company.employee_count >= 20:
                    score += 15
                elif company.employee_count >= 10:
                    score += 10
                else:
                    score += 5

            # Revenue estimate
            if company.revenue_estimate:
                rev = float(company.revenue_estimate)
                if rev >= 10_000_000:
                    score += 20
                elif rev >= 1_000_000:
                    score += 15
                elif rev >= 100_000:
                    score += 10

            # Industry signal (some industries spend more on ops tools)
            high_budget_industries = {
                "technology", "software", "saas", "fintech", "healthtech",
                "e-commerce", "financial services", "healthcare", "real estate",
            }
            if company.industry and company.industry.lower() in high_budget_industries:
                score += 10

        # From enrichment data
        for enr in enrichments:
            if enr.enrichment_type == "company" and enr.data:
                data = enr.data if isinstance(enr.data, dict) else {}
                if data.get("company_revenue"):
                    score += 5
                if data.get("company_size") and data["company_size"] >= 10:
                    score += 5

        return min(max(score, 10), 100)

    @staticmethod
    def _score_website_weakness(audits: list[WebsiteAudit]) -> int:
        """Score website weakness: based on audit results (inverted — worse site = higher score).

        No audit = 50 (neutral).
        """
        if not audits:
            return 50

        audit = audits[0]
        score = 50  # start neutral

        # Low website score = high weakness (our angle)
        if audit.website_score is not None:
            # Invert: 0 website score = 100 weakness, 100 website score = 0 weakness
            score = 100 - audit.website_score

        # Individual weakness indicators
        if audit.has_chatbot is False:
            score = min(score + 10, 100)
        if audit.has_booking is False:
            score = min(score + 10, 100)
        if audit.has_contact_form is False:
            score = min(score + 8, 100)
        if audit.has_email_capture is False:
            score = min(score + 5, 100)
        if audit.weak_cta is True:
            score = min(score + 8, 100)
        if audit.broken_forms is True:
            score = min(score + 10, 100)
        if audit.has_tracking_scripts is False:
            score = min(score + 5, 100)

        return min(max(score, 10), 100)

    @staticmethod
    def _score_contactability(
        contact: Optional[Contact],
        enrichments: list[EnrichmentRecord],
    ) -> int:
        """Score contactability: email verified, phone available, LinkedIn found."""
        score = 20  # baseline

        if contact:
            # Email
            if contact.email:
                score += 15
                if contact.email_status == "verified":
                    score += 20
                elif contact.email_status in ("deliverable", "likely"):
                    score += 15
                elif contact.email_status in ("risky", "unverified"):
                    score += 5

            # Phone
            if contact.phone:
                score += 15

            # LinkedIn
            if contact.linkedin_url:
                score += 15

            # Title / seniority (decision maker)
            if contact.seniority in ("c_suite", "vp", "director"):
                score += 10
            elif contact.seniority == "manager":
                score += 5

        # From enrichment data
        for enr in enrichments:
            if enr.enrichment_type == "contact" and enr.data:
                data = enr.data if isinstance(enr.data, dict) else {}
                if data.get("email"):
                    score += 5
                if data.get("phone"):
                    score += 5
                if data.get("linkedin_url"):
                    score += 5

        return min(max(score, 10), 100)

    @staticmethod
    def _score_recency(signals: list[BuyingSignal]) -> int:
        """Score recency: days since the strongest/most recent signal.

        Recent = high score.
        """
        if not signals:
            return 10

        now = datetime.utcnow()

        # Find most recent signal
        most_recent: Optional[datetime] = None
        for sig in signals:
            if sig.detected_at:
                dt = sig.detected_at.replace(tzinfo=None)
                if most_recent is None or dt > most_recent:
                    most_recent = dt

        if most_recent is None:
            return 20

        days_ago = (now - most_recent).days

        if days_ago <= 1:
            return 95
        elif days_ago <= 3:
            return 85
        elif days_ago <= 7:
            return 75
        elif days_ago <= 14:
            return 60
        elif days_ago <= 30:
            return 45
        elif days_ago <= 90:
            return 30
        else:
            return 15

    # ── Explanation generation ──────────────────────────────────────────────

    @staticmethod
    def _generate_explanation(
        lead_id: uuid.UUID,
        total: int,
        band: str,
        buying_intent: int,
        urgency: int,
        operational_pain: int,
        scaling_pressure: int,
        budget_probability: int,
        website_weakness: int,
        contactability: int,
        recency: int,
        signals: list[BuyingSignal],
    ) -> str:
        """Generate a human-readable explanation of the score."""
        lines = []
        lines.append(f"Lead score: {total}/100 ({band})")

        # Top dimensions
        dims = [
            ("Buying intent", buying_intent, WEIGHTS["buying_intent"]),
            ("Urgency", urgency, WEIGHTS["urgency"]),
            ("Operational pain", operational_pain, WEIGHTS["operational_pain"]),
            ("Scaling pressure", scaling_pressure, WEIGHTS["scaling_pressure"]),
            ("Budget probability", budget_probability, WEIGHTS["budget_probability"]),
            ("Website weakness", website_weakness, WEIGHTS["website_weakness"]),
            ("Contactability", contactability, WEIGHTS["contactability"]),
            ("Recency", recency, WEIGHTS["recency"]),
        ]
        dims.sort(key=lambda x: x[1] * x[2], reverse=True)

        lines.append("Top scoring dimensions:")
        for name, score, weight in dims[:3]:
            lines.append(f"  - {name}: {score}/100 (weight: {int(weight*100)}%)")

        # Key signals
        if signals:
            categories = [s.category for s in signals[:5]]
            lines.append(f"Detected signals: {', '.join(categories)}")

        # Band interpretation
        interpretations = {
            "very_hot": "Strong buying intent detected — prioritize immediately",
            "hot": "High likelihood of conversion — fast-track outreach",
            "warm": "Showing interest signals — nurture with targeted messaging",
            "weak": "Some signals present — add to drip campaign",
            "low": "Minimal signals detected — monitor and re-evaluate later",
        }
        lines.append(interpretations.get(band, "Requires further research"))

        return "\n".join(lines)