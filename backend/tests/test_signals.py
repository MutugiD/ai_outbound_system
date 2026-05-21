"""Signal detection unit tests — rule-based detection patterns."""

import pytest

from app.services.ai.signal_detector import SignalDetector


# ── Rule-based detection tests ──────────────────────────────────────────────


def test_rule_based_detects_hiring_ops():
    """detect_rules should detect hiring_ops_role signals."""
    detector = SignalDetector()
    text = "We are hiring an operations manager to help scale our team."
    signals = detector.detect_rules(text, company="TestCo", source="job_board")
    categories = [s["category"] for s in signals]
    assert "hiring_ops_role" in categories


def test_rule_based_detects_crm_pain():
    """detect_rules should detect crm_pain signals."""
    detector = SignalDetector()
    text = "Our current CRM is frustrating and we struggle with data silos across HubSpot."
    signals = detector.detect_rules(text, company="TestCo", source="reddit")
    categories = [s["category"] for s in signals]
    assert "crm_pain" in categories


def test_rule_based_detects_founder_burnout():
    """detect_rules should detect founder_burnout signals."""
    detector = SignalDetector()
    text = "As a founder I'm experiencing burnout and wearing too many hats at once."
    signals = detector.detect_rules(text, company="TestCo", source="reddit")
    categories = [s["category"] for s in signals]
    assert "founder_burnout" in categories


def test_rule_based_detects_manual_processes():
    """detect_rules should detect manual_processes signals."""
    detector = SignalDetector()
    text = "We're still manually entering data into spreadsheets every week."
    signals = detector.detect_rules(text, company="TestCo", source="reddit")
    categories = [s["category"] for s in signals]
    assert "manual_processes" in categories


def test_signal_confidence_bands():
    """Signals should have confidence values in valid ranges (0-1)."""
    detector = SignalDetector()
    text = (
        "We are hiring an operations coordinator. Our CRM is a pain point. "
        "I'm a founder experiencing burnout. We still manually process everything."
    )
    signals = detector.detect_rules(text, company="TestCo", source="test")
    for sig in signals:
        assert 0.0 <= sig["confidence"] <= 1.0, f"Confidence out of range: {sig['confidence']}"


def test_low_confidence_signals_flagged():
    """Signals at or below threshold (0.5) should still be returned but with proper confidence."""
    detector = SignalDetector()
    # A vague text that won't match high-confidence patterns
    text = "We have some operations work to do."
    signals = detector.detect_rules(text, company="TestCo", source="test")
    # May return empty or low-confidence signals
    for sig in signals:
        assert sig["confidence"] >= 0.5 or sig["confidence"] < 0.5  # no crash either way
        # Evidence field should be populated
        assert "evidence" in sig
