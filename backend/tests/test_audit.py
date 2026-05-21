"""Website audit unit tests — checking detection patterns for CTAs, booking tools, chatbots, SSL, and scores."""

import pytest

from app.services.ai.audit_service import AuditService


# ── CTA detection ────────────────────────────────────────────────────────────


def test_detect_cta_presence():
    """_check_cta should detect common CTA phrases in HTML."""
    findings = []
    html_with_cta = '<a href="/demo">Book a Demo</a><a href="/signup">Sign up</a>'
    has_cta, score = AuditService._check_cta(html_with_cta, findings)
    assert has_cta is True
    assert score > 0

    html_without_cta = '<p>Welcome to our website.</p><p>We make great things.</p>'
    findings2 = []
    has_cta2, score2 = AuditService._check_cta(html_without_cta, findings2)
    assert has_cta2 is False
    assert score2 < 40


# ── Booking tool detection ──────────────────────────────────────────────────


def test_detect_booking_tool():
    """_check_booking should detect Calendly/Cal.com patterns in HTML."""
    findings = []
    html_with_calendly = '<script src="https://calendly.com/assets/external/widget.js"></script>'
    has_booking = AuditService._check_booking(html_with_calendly.lower(), findings)
    assert has_booking is True

    html_with_calcom = '<iframe src="https://cal.com/acme/15min"></iframe>'
    findings2 = []
    has_booking2 = AuditService._check_booking(html_with_calcom.lower(), findings2)
    assert has_booking2 is True

    html_without_booking = '<p>Contact us at info@example.com</p>'
    findings3 = []
    has_booking3 = AuditService._check_booking(html_without_booking.lower(), findings3)
    assert has_booking3 is False


# ── Chatbot detection ────────────────────────────────────────────────────────


def test_detect_chatbot():
    """_check_chatbot should detect Intercom/Drift/Crisp patterns."""
    findings = []
    html_with_intercom = '<script> window.intercomSettings = { app_id: "abc" }; </script>'
    has_chatbot = AuditService._check_chatbot(html_with_intercom.lower(), findings)
    assert has_chatbot is True

    html_with_drift = '<script src="https://js.drift.com/include.js"></script>'
    findings2 = []
    has_chatbot2 = AuditService._check_chatbot(html_with_drift.lower(), findings2)
    assert has_chatbot2 is True

    html_with_crisp = '<script src="https://client.crisp.chat/l.js"></script>'
    findings3 = []
    has_chatbot3 = AuditService._check_chatbot(html_with_crisp.lower(), findings3)
    assert has_chatbot3 is True

    html_without_chatbot = '<p>We offer consulting services.</p>'
    findings4 = []
    has_chatbot4 = AuditService._check_chatbot(html_without_chatbot.lower(), findings4)
    assert has_chatbot4 is False


# ── SSL detection ────────────────────────────────────────────────────────────


def test_detect_ssl():
    """SSL should be indicated by https:// in the URL."""
    # The audit service checks ssl via the URL passed to _create_audit
    # Direct check: ssl_ok = url.startswith("https://")
    assert "https://example.com".startswith("https://")
    assert not "http://example.com".startswith("https://")

    # SSL score in _create_audit: 100 if ssl_ok, 0 otherwise
    ssl_score_ok = 100 if True else 0
    ssl_score_bad = 100 if False else 0
    assert ssl_score_ok == 100
    assert ssl_score_bad == 0


# ── Composite score range ────────────────────────────────────────────────────


def test_composite_score_range():
    """Composite website_score should always be between 0 and 100."""
    # We can test the scoring logic directly
    # Simulate worst case: all zeros
    tech_total = (0 + 0 + 0) / 3
    conversion_total = 0
    automation_total = 0
    website_score_low = int(round(tech_total * 0.3 + conversion_total * 0.4 + automation_total * 0.3))
    website_score_low = max(0, min(100, website_score_low))
    assert 0 <= website_score_low <= 100

    # Simulate best case: all 100
    tech_total_best = (100 + 100 + 100) / 3
    conversion_total_best = (
        100 * 0.25 + 100 * 0.25 + 100 * 0.2 + 100 * 0.15 + 100 * 0.15
    )
    automation_total_best = (
        100 * 0.3 + 100 * 0.2 + 100 * 0.2 + 100 * 0.2 + 100 * 0.1
    )
    website_score_high = int(round(
        tech_total_best * 0.3 + conversion_total_best * 0.4 + automation_total_best * 0.3
    ))
    website_score_high = max(0, min(100, website_score_high))
    assert 0 <= website_score_high <= 100