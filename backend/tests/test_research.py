"""Research agent unit tests — schema validation, context compilation, and DB persistence."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.research_agent import ResearchAgent, ResearchBriefSchema


# ── Schema tests ────────────────────────────────────────────────────────────


def test_research_brief_schema_validates():
    """ResearchBriefSchema should validate valid data and reject invalid data."""
    # Valid data
    brief = ResearchBriefSchema(
        company_summary="A SaaS company providing project management tools.",
        target_customer="Mid-market technology companies with 50-500 employees.",
        likely_operational_pain=["Manual onboarding processes", "CRM data scattered across tools"],
        revenue_leakage_hypothesis=["Poor lead conversion due to no chatbot"],
        competitor_observations=["Asana and Monday.com dominate the market"],
        recommended_outreach_angle="Offer AI-powered chatbot to capture leads 24/7",
        confidence=0.72,
        sources_used=["enrichment_apollo", "audit_website", "signal_crm_pain"],
    )
    assert brief.confidence == 0.72
    assert len(brief.likely_operational_pain) == 2
    assert len(brief.sources_used) == 3

    # Invalid confidence (> 1.0)
    with pytest.raises(Exception):
        ResearchBriefSchema(
            company_summary="Test",
            target_customer="Test",
            likely_operational_pain=[],
            revenue_leakage_hypothesis=[],
            competitor_observations=[],
            recommended_outreach_angle="Test",
            confidence=1.5,
            sources_used=[],
        )

    # Invalid confidence (< 0.0)
    with pytest.raises(Exception):
        ResearchBriefSchema(
            company_summary="Test",
            target_customer="Test",
            likely_operational_pain=[],
            revenue_leakage_hypothesis=[],
            competitor_observations=[],
            recommended_outreach_angle="Test",
            confidence=-0.1,
            sources_used=[],
        )


# ── Prompt compilation tests ───────────────────────────────────────────────


def test_research_agent_compiles_context():
    """ResearchAgent._build_prompt should compile data into a structured prompt."""
    # Create mock objects with the right attributes
    company = MagicMock()
    company.name = "Acme Corp"
    company.domain = "acme.com"
    company.industry = "technology"
    company.sub_industry = "SaaS"
    company.description = "A tech company"
    company.employee_count = 50
    company.employee_count_range = "50-100"
    company.revenue_estimate = Decimal("5000000")
    company.revenue_range = "$1M-$10M"
    company.funding_status = "Series A"
    company.funding_total = Decimal("2000000")
    company.location = "San Francisco, CA"
    company.linkedin_url = "https://linkedin.com/company/acme"

    contact = MagicMock()
    contact.full_name = "Jane Doe"
    contact.title = "VP Operations"
    contact.seniority = "vp"
    contact.department = "Operations"
    contact.email = "jane@acme.com"
    contact.email_status = "verified"
    contact.phone = "+15551234567"
    contact.linkedin_url = "https://linkedin.com/in/janedoe"

    # Mock enrichment record
    enrichment = MagicMock()
    enrichment.enrichment_type = "company"
    enrichment.provider = "apollo"
    enrichment.data = {"company_size": 50, "tech_stack": ["React", "AWS", "HubSpot"]}

    # Mock signal
    signal = MagicMock()
    signal.category = "crm_pain"
    signal.evidence = "Complaining about HubSpot being too expensive"
    signal.confidence = Decimal("0.85")
    signal.source = "reddit"
    signal.detection_method = "rule"

    # Mock audit
    audit = MagicMock()
    audit.website_score = 45
    audit.page_speed_score = 60
    audit.mobile_score = 70
    audit.has_chatbot = False
    audit.has_booking = False
    audit.has_contact_form = True
    audit.has_email_capture = False
    audit.has_crm_form = True
    audit.has_tracking_scripts = True
    audit.has_support_widget = False
    audit.weak_cta = True
    audit.broken_forms = False
    audit.sales_angle = "No chatbot or booking tool — major opportunity"
    audit.technical_findings = [{"check": "ssl", "issue": "No SSL", "severity": "high"}]
    audit.conversion_findings = []
    audit.automation_findings = []

    # Mock lead source
    source = MagicMock()
    source.source_type = "reddit"
    source.source_name = "r/startups"
    source.source_url = "https://reddit.com/r/startups/abc123"
    source.raw_text = "We're struggling with CRM and manual processes at our startup."
    source.detected_signal_text = "crm_pain, manual_processes"

    prompt = ResearchAgent._build_prompt(
        company=company,
        contact=contact,
        enrichment_records=[enrichment],
        buying_signals=[signal],
        audits=[audit],
        lead_sources=[source],
    )

    # Verify key data is in the prompt
    assert "Acme Corp" in prompt
    # Use word-boundary-aware check to avoid substring false positives (e.g. "notacme.commerce")
    import re

    assert re.search(r"\bacme\.com\b", prompt, re.IGNORECASE) is not None
    assert "technology" in prompt
    assert "Jane Doe" in prompt
    assert "jane@acme.com" in prompt
    assert "crm_pain" in prompt
    assert "No chatbot" in prompt or "chatbot" in prompt.lower()
    assert "reddit" in prompt.lower()


# ── DB persistence test ─────────────────────────────────────────────────────


async def test_research_persists_to_db(db_session, test_team):
    """Research result should persist as AIResearchReport in the database."""
    from app.models.lead import Lead
    from app.models.company import Company
    from app.models.research import AIResearchReport

    # Create a company and lead
    company = Company(
        team_id=test_team.id,
        name="Research Test Corp",
        domain="researchtest.example.com",
        industry="technology",
    )
    db_session.add(company)
    await db_session.flush()

    lead = Lead(
        team_id=test_team.id,
        company_id=company.id,
        status="new",
    )
    db_session.add(lead)
    await db_session.flush()

    # Create a mock AIResearchReport directly (bypassing LLM call)
    report = AIResearchReport(
        lead_id=lead.id,
        version=1,
        company_summary="A technology company focused on research testing.",
        target_customer="Developers and QA engineers.",
        likely_operational_pain=["Slow test execution", "Manual test processes"],
        revenue_leakage_hypothesis=["Wasted engineering hours on manual testing"],
        competitor_observations=["Competitor X offers automated testing"],
        recommended_outreach_angle="Offer AI-powered test automation",
        confidence=Decimal("0.65"),
        model_used="gpt-4o",
        sources_used=["test_source"],
    )
    db_session.add(report)
    await db_session.flush()

    # Verify it was persisted
    from sqlalchemy import select

    result = await db_session.execute(select(AIResearchReport).where(AIResearchReport.lead_id == lead.id))
    fetched = result.scalar_one_or_none()
    assert fetched is not None
    assert fetched.company_summary == "A technology company focused on research testing."
    assert fetched.confidence == Decimal("0.65")
    assert len(fetched.likely_operational_pain) == 2
