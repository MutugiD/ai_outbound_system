"""Scoring engine unit tests — weight validation, score bands, and explanations."""

import pytest

from app.services.ai.scoring_service import ScoringService, WEIGHTS, SCORE_BANDS, _band


# ── Weight validation ──────────────────────────────────────────────────────


def test_score_dimensions_sum_to_100_percent():
    """Scoring weights should sum to exactly 1.0 (100%)."""
    total = sum(WEIGHTS.values())
    assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"


# ── Score band mapping ──────────────────────────────────────────────────────


def test_very_hot_score_band():
    """Scores 85-100 should map to 'very_hot'."""
    for score in [85, 90, 95, 100]:
        assert _band(score) == "very_hot", f"Score {score} should be very_hot"


def test_hot_score_band():
    """Scores 70-84 should map to 'hot'."""
    for score in [70, 75, 80, 84]:
        assert _band(score) == "hot", f"Score {score} should be hot"
    # Boundary: 85 is very_hot
    assert _band(85) == "very_hot"


def test_warm_score_band():
    """Scores 55-69 should map to 'warm'."""
    for score in [55, 60, 65, 69]:
        assert _band(score) == "warm", f"Score {score} should be warm"
    # Boundary: 70 is hot
    assert _band(70) == "hot"


# ── Contactability dimension ────────────────────────────────────────────────


def test_low_score_no_contactability():
    """No email should result in lower contactability score."""
    from app.models.contact import Contact

    # Contact with no email
    contact_no_email = Contact(
        full_name="Jane Doe",
        phone="+15551234567",
        linkedin_url="https://linkedin.com/in/janedoe",
    )
    score_no_email = ScoringService._score_contactability(contact_no_email, [])

    # Contact with verified email
    contact_with_email = Contact(
        full_name="Jane Doe",
        email="jane@example.com",
        email_status="verified",
        phone="+15551234567",
        linkedin_url="https://linkedin.com/in/janedoe",
    )
    score_with_email = ScoringService._score_contactability(contact_with_email, [])

    assert score_with_email > score_no_email, (
        f"Contact with email ({score_with_email}) should score higher than without ({score_no_email})"
    )


# ── Explanation generation ──────────────────────────────────────────────────


def test_score_explanation_generated():
    """ScoringService._generate_explanation should return a non-empty string."""
    # We test the static method directly with mock inputs
    explanation = ScoringService._generate_explanation(
        lead_id=None,
        total=75,
        band="hot",
        buying_intent=60,
        urgency=70,
        operational_pain=80,
        scaling_pressure=50,
        budget_probability=60,
        website_weakness=40,
        contactability=85,
        recency=70,
        signals=[],
    )
    assert explanation is not None
    assert len(explanation) > 0