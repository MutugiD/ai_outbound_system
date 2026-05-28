"""Buying signal detection engine — rule-based and LLM-based classification.

Detects buying signals from lead source data using two complementary approaches:
  1. **Rule-based** (fast, deterministic): regex/keyword patterns for each signal category
  2. **LLM-based** (contextual, nuanced): structured prompt asking a language model
     to classify source text into signal categories with evidence and confidence

Both modes return BuyingSignal-compatible dicts that can be persisted to the DB.
"""

import logging
import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.company import Company
from app.models.contact import Contact
from app.models.signal import BuyingSignal
from app.models.lead_source import LeadSource
from app.config import settings
from app.services.ai.llm_service import LLMService

logger = logging.getLogger(__name__)

# ── Signal categories (20 from FEATURES.md) ──────────────────────────────────

SIGNAL_CATEGORIES = [
    "hiring_ops_role",
    "crm_pain",
    "founder_burnout",
    "onboarding_complaints",
    "workflow_inefficiency",
    "support_overload",
    "scaling_issues",
    "slow_lead_response",
    "rapid_hiring",
    "funding_event",
    "tool_stack_overload",
    "manual_processes",
    "poor_website_conversion",
    "poor_booking_flow",
    "no_automation_layer",
    "no_chatbot",
    "heavy_support_requests",
    "negative_reviews",
    "high_response_latency",
    "fragmented_tools",
]

# ── Rule-based patterns ──────────────────────────────────────────────────────

RULE_PATTERNS: dict[str, list[dict[str, str | float]]] = {
    "hiring_ops_role": [
        {"pattern": r"(?i)hiring.*(ops|operations|coordinator|admin)", "confidence": 0.8},
        {"pattern": r"(?i)operations.*(manager|lead|director)", "confidence": 0.7},
        {"pattern": r"(?i)looking for.*operations", "confidence": 0.6},
        {"pattern": r"(?i)job opening.*operations", "confidence": 0.7},
    ],
    "crm_pain": [
        {"pattern": r"(?i)CRM.*(pain|problem|issue|frustrat|struggl)", "confidence": 0.85},
        {"pattern": r"(?i)HubSpot.*(expensive|cost|switch|alternativ)", "confidence": 0.7},
        {"pattern": r"(?i)Salesforce.*(compli|expensive|overkill)", "confidence": 0.7},
        {"pattern": r"(?i)data.*(silos|scattered|fragment)", "confidence": 0.65},
        {"pattern": r"(?i)customer data.*(mess|disorganiz|spread)", "confidence": 0.6},
    ],
    "founder_burnout": [
        {"pattern": r"(?i)(founder|ceo|owner).*(burnout|exhausted|overwhelm)", "confidence": 0.85},
        {"pattern": r"(?i)wearing.*(too many hats|all hats|multiple hats)", "confidence": 0.75},
        {"pattern": r"(?i)doing everything.*(myself|alone)", "confidence": 0.7},
        {"pattern": r"(?i)can'?t keep up.*(growth|demand|orders)", "confidence": 0.65},
    ],
    "onboarding_complaints": [
        {"pattern": r"(?i)onboarding.*(slow|pain|terribl|frustrat|difficult)", "confidence": 0.85},
        {"pattern": r"(?i)onboard.*(new hire|employee).*(take|long|slow)", "confidence": 0.7},
        {"pattern": r"(?i)training.*(materials|process).*(disorganiz|lack|missing)", "confidence": 0.6},
    ],
    "workflow_inefficiency": [
        {"pattern": r"(?i)(workflow|process).*(inefficient|manual|bottleneck|slow)", "confidence": 0.85},
        {"pattern": r"(?i)manual.*(data entry|process|work|task)", "confidence": 0.8},
        {"pattern": r"(?i)spreadsheets.*(run|track|manag|everything)", "confidence": 0.7},
        {"pattern": r"(?i)copy.*paste.*(data|info|spreadsheet)", "confidence": 0.75},
    ],
    "support_overload": [
        {"pattern": r"(?i)(support|help desk).*(overwhelm|overflow|too many|can'?t handle)", "confidence": 0.85},
        {"pattern": r"(?i)ticket.*(backlog|pile up|too many)", "confidence": 0.75},
        {"pattern": r"(?i)customer support.*(struggl|drown|overload)", "confidence": 0.7},
    ],
    "scaling_issues": [
        {"pattern": r"(?i)scal(e|ing).*(problem|issue|challenge|difficult)", "confidence": 0.8},
        {"pattern": r"(?i)(growing|growth).*(pain|too fast|can'?t keep)", "confidence": 0.75},
        {"pattern": r"(?i)outgrown.*(system|tool|process|spreadsheet)", "confidence": 0.8},
    ],
    "slow_lead_response": [
        {"pattern": r"(?i)(lead|inquir|contact).*(slow|response|follow.up|reply)", "confidence": 0.8},
        {"pattern": r"(?i)response time.*(slow|too long|hour|days)", "confidence": 0.75},
        {"pattern": r"(?i)(taking|take).*(too long|long).*(respond|reply|follow up)", "confidence": 0.7},
    ],
    "rapid_hiring": [
        {"pattern": r"(?i)hiring.*(5|10|20|50|multiple|several).*(people|role|position)", "confidence": 0.85},
        {"pattern": r"(?i)doubling.*(team|headcount|staff)", "confidence": 0.8},
        {"pattern": r"(?i)rapid.*(hiring|growth| expans)", "confidence": 0.75},
        {"pattern": r"(?i)(series A|series B|funding).*(hire|hiring|grow|expand)", "confidence": 0.7},
    ],
    "funding_event": [
        {"pattern": r"(?i)(raised|announced|closed).*(\$|funding|round|series)", "confidence": 0.9},
        {"pattern": r"(?i)(series [A-F]|seed round|pre-seed).*(funding|raised|investment)", "confidence": 0.85},
        {"pattern": r"(?i)(venture|VC|investor).*(investment|funded|backed)", "confidence": 0.7},
    ],
    "tool_stack_overload": [
        {"pattern": r"(?i)(too many|10|12|15|dozens of).*(tool|app|platform|software)", "confidence": 0.85},
        {"pattern": r"(?i)(tool|app|software).*(overload|fragment|disconnec|integrat)", "confidence": 0.75},
        {"pattern": r"(?i)(Zapier|Make|IFTTT).*(connect|integrate|sync)", "confidence": 0.65},
    ],
    "manual_processes": [
        {"pattern": r"(?i)manually.*(process|enter|copy|handle|manage)", "confidence": 0.85},
        {"pattern": r"(?i)hours.*(week|month).*(manual|data entry|spreadsheet)", "confidence": 0.8},
        {"pattern": r"(?i)still.*(manually|by hand|spreadsheet|excel)", "confidence": 0.75},
    ],
    "poor_website_conversion": [
        {"pattern": r"(?i)(website|site).*(conver|bounce|low conver|poor conver)", "confidence": 0.85},
        {"pattern": r"(?i)(CTR|click.through).*(low|poor|terrible|bad)", "confidence": 0.75},
        {"pattern": r"(?i)landing page.*(not conver|poor|bad|low)", "confidence": 0.7},
    ],
    "poor_booking_flow": [
        {"pattern": r"(?i)(book|schedule|appointment).*(confus|difficult|hard|frustrat)", "confidence": 0.85},
        {"pattern": r"(?i)(no.*book|can'?t book|booking.*issue)", "confidence": 0.8},
        {"pattern": r"(?i)booking.*(broken|not work|error|slow)", "confidence": 0.75},
    ],
    "no_automation_layer": [
        {"pattern": r"(?i)(no|without|lack).*(automation|automat|auto)", "confidence": 0.8},
        {"pattern": r"(?i)everything.*(manual|by hand|no automation)", "confidence": 0.75},
        {"pattern": r"(?i)should.*(automat|streamline)", "confidence": 0.6},
    ],
    "no_chatbot": [
        {"pattern": r"(?i)(no|without|need).*(chatbot|chat bot|live chat|widget)", "confidence": 0.75},
        {"pattern": r"(?i)(add|implement|get).*(chatbot|chat support|AI chat)", "confidence": 0.7},
    ],
    "heavy_support_requests": [
        {"pattern": r"(?i)(support|help).*(request|ticket|volume).*(high|heavy|overwhelm)", "confidence": 0.85},
        {"pattern": r"(?i)(customer|user).*(question|inquir|issue).*(too many|overwhelm)", "confidence": 0.75},
    ],
    "negative_reviews": [
        {"pattern": r"(?i)(review|rating).*(1.star|terribl|awful|worst|bad experience)", "confidence": 0.85},
        {"pattern": r"(?i)(G2|Capterra|Glassdoor).*(bad review|poor rating|complaint)", "confidence": 0.7},
        {"pattern": r"(?i)(complaint|dissatisf|disappoint).*(product|service|experience)", "confidence": 0.65},
    ],
    "high_response_latency": [
        {"pattern": r"(?i)(response|reply).*(time|latency).*(slow|hour|day|long)", "confidence": 0.85},
        {"pattern": r"(?i)(take|takes).*(hour|day|days|long).*(respond|reply|get back)", "confidence": 0.7},
    ],
    "fragmented_tools": [
        {"pattern": r"(?i)(fragment|disconnec|disjoint).*(tool|system|stack|platform)", "confidence": 0.85},
        {"pattern": r"(?i)data.*(silo|spread|scatter).*(across|between|tool|app)", "confidence": 0.8},
        {"pattern": r"(?i)(switch|jump|toggl).*(between|across).*(tool|app|platform)", "confidence": 0.7},
    ],
}

# ── LLM signal detection schemas ──────────────────────────────────────────────


class LLMSignalResult(BaseModel):
    """Structured output schema for LLM-based signal detection."""

    signals: list[dict[str, Any]] = Field(
        description="List of detected signals with category, evidence, and confidence"
    )


class _SignalItem(BaseModel):
    """Single signal item for LLM output."""

    category: str = Field(description="Signal category")
    evidence: str = Field(description="Exact text evidence from the source")
    confidence: float = Field(description="Confidence score 0-1", ge=0.0, le=1.0)


class _SignalDetectionOutput(BaseModel):
    """Structured output for LLM signal detection."""

    signals: list[_SignalItem] = Field(default_factory=list)


# ── Signal Detector ────────────────────────────────────────────────────────


class SignalDetector:
    """Detects buying signals from lead source data.

    Supports two modes:
      - **rule** (default, fast): regex/keyword matching
      - **llm** (contextual, nuanced): language model classification

    Usage::

        detector = SignalDetector()
        # Rule-based
        signals = await detector.detect_from_text(text, company_name, source)
        # LLM-based
        signals = await detector.detect_from_text(text, company_name, source, method="llm")
        # Full pipeline (queries DB for source data)
        signals = await detector.detect_signals(lead_id, db)
    """

    def __init__(self, llm_service: Optional[LLMService] = None) -> None:
        self._llm = llm_service

    # ── Rule-based detection ────────────────────────────────────────────────

    def detect_rules(self, text: str, company: str = "", source: str = "unknown") -> list[dict]:
        """Run rule-based signal detection on text.

        Returns a list of signal dicts ready for DB persistence.
        """
        signals: list[dict] = []

        for category, patterns in RULE_PATTERNS.items():
            for pat_info in patterns:
                pattern = pat_info["pattern"]
                confidence = float(pat_info["confidence"])
                match = re.search(pattern, text)
                if match:
                    # Extract surrounding context as evidence
                    start = max(0, match.start() - 40)
                    end = min(len(text), match.end() + 40)
                    evidence = text[start:end].strip()

                    signals.append(
                        {
                            "category": category,
                            "evidence": evidence,
                            "source": source,
                            "confidence": min(confidence + 0.05, 1.0) if company else confidence,
                            "detection_method": "rule",
                        }
                    )

        # Deduplicate signals of same category (keep highest confidence)
        seen: dict[str, dict] = {}
        for sig in signals:
            key = sig["category"]
            if key not in seen or sig["confidence"] > seen[key]["confidence"]:
                seen[key] = sig

        return list(seen.values())

    # ── LLM-based detection ─────────────────────────────────────────────────

    async def detect_llm(
        self,
        text: str,
        company: str = "",
        source: str = "unknown",
        model: Optional[str] = None,
    ) -> list[dict]:
        """Run LLM-based signal detection on text.

        Falls back to rule-based detection if LLM is unavailable.
        """
        llm = self._llm or LLMService()

        prompt = (
            f"Analyze the following text for buying signals related to a company"
            f"{' (' + company + ')' if company else ''}.\n\n"
            f"Source: {source}\n\n"
            f'Text:\n"""\n{text[:3000]}\n"""\n\n'
            f"Ident which of these signal categories are present:\n"
            f"{', '.join(SIGNAL_CATEGORIES)}\n\n"
            f"For each detected signal, provide:\n"
            f"- category: one of the categories above\n"
            f"- evidence: the exact text that indicates this signal\n"
            f"- confidence: a score from 0.0 to 1.0\n\n"
            f"Only include signals you are confident about (confidence >= 0.5)."
        )

        try:
            result = await llm.call(
                prompt=prompt,
                schema=_SignalDetectionOutput,
                model=model or settings.LLM_MODEL,
                task_name="signal_detection",
                system_prompt=(
                    "You are a buying signal detection expert. "
                    "Analyze text for signals that a company might benefit from "
                    "operations automation, CRM, chatbots, booking systems, or "
                    "similar business solutions. Be precise and only report signals "
                    "with clear evidence."
                ),
            )
            signals: list[dict] = []
            for item in result.signals:
                if item.category in SIGNAL_CATEGORIES and item.confidence >= 0.5:
                    signals.append(
                        {
                            "category": item.category,
                            "evidence": item.evidence,
                            "source": source,
                            "confidence": item.confidence,
                            "detection_method": "llm",
                        }
                    )
            return signals
        except Exception as exc:
            logger.warning("LLM signal detection failed, falling back to rules: %s", exc)
            return self.detect_rules(text, company, source)

    # ── Combined detection from text ────────────────────────────────────────

    async def detect_from_text(
        self,
        text: str,
        company: str = "",
        source: str = "unknown",
        method: str = "rule",
        model: Optional[str] = None,
    ) -> list[dict]:
        """Detect signals from raw text.

        Parameters
        ----------
        text : str
            The source text to analyze.
        company : str
            Company name for context.
        source : str
            Source identifier (reddit, job_board, review, website, etc.)
        method : str
            Detection method: 'rule', 'llm', or 'both'.
        model : str | None
            LLM model to use (defaults to configured LLM_MODEL).

        Returns
        -------
        list[dict]
            List of signal dicts with keys: category, evidence, source,
            confidence, detection_method.
        """
        signals: list[dict] = []

        if method in ("rule", "both"):
            signals.extend(self.detect_rules(text, company, source))

        if method in ("llm", "both"):
            llm_signals = await self.detect_llm(text, company, source, model)
            signals.extend(llm_signals)

        # Deduplicate by category, keeping highest confidence
        seen: dict[str, dict] = {}
        for sig in signals:
            key = (sig["category"], sig["detection_method"])
            if key not in seen or sig["confidence"] > seen[key]["confidence"]:
                seen[key] = sig

        return list(seen.values())

    # ── Full pipeline (from DB) ────────────────────────────────────────────

    async def detect_signals(
        self,
        lead_id: uuid.UUID,
        db: AsyncSession,
        method: str = "both",
    ) -> list[BuyingSignal]:
        """Run signal detection for a lead using its associated source data.

        Queries the DB for lead source text and runs detection.

        Returns
        -------
        list[BuyingSignal]
            Persisted BuyingSignal records.
        """
        # Fetch lead
        result = await db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Fetch company
        company_name = ""
        if lead.company_id:
            result = await db.execute(select(Company).where(Company.id == lead.company_id))
            company = result.scalar_one_or_none()
            company_name = company.name if company else ""

        # Collect text from lead sources
        result = await db.execute(select(LeadSource).where(LeadSource.lead_id == lead_id))
        lead_sources = list(result.scalars().all())

        all_signals: list[dict] = []

        for source in lead_sources:
            text = f"{source.raw_text or ''}"
            if source.detected_signal_text:
                text += f" {source.detected_signal_text}"

            if not text.strip():
                continue

            source_name = source.source_type or source.source_name or "unknown"
            detected = await self.detect_from_text(
                text=text,
                company=company_name,
                source=source_name,
                method=method,
            )
            for sig in detected:
                sig["source_url"] = source.source_url
            all_signals.extend(detected)

        # Deduplicate across sources (same category, keep highest confidence)
        seen: dict[str, dict] = {}
        for sig in all_signals:
            key = sig["category"]
            if key not in seen or sig["confidence"] > seen[key]["confidence"]:
                seen[key] = sig

        # Persist signals
        persisted: list[BuyingSignal] = []
        for sig in seen.values():
            signal = BuyingSignal(
                lead_id=lead_id,
                category=sig["category"],
                evidence=sig["evidence"][:5000] if sig["evidence"] else "",
                source=sig["source"],
                source_url=sig.get("source_url"),
                confidence=Decimal(str(round(sig["confidence"], 4))),
                detection_method=sig["detection_method"],
                detected_at=datetime.utcnow(),
            )
            db.add(signal)
            persisted.append(signal)

        await db.flush()

        # Log activity
        from app.services.activity_service import log_activity

        await log_activity(
            db,
            team_id=lead.team_id,
            user_id=None,
            lead_id=lead_id,
            action="signal_detected",
            details={"count": len(persisted), "method": method, "categories": [s.category for s in persisted]},
        )

        return persisted
