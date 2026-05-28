"""Acquisition service helpers."""

import re
from typing import Any

from services.acquisition_service.industry_configs import get_industry_config

GENERIC_LOCATION_TERMS = {
    "nairobi",
    "kenya",
    "county",
    "road",
    "rd",
    "street",
    "st",
    "area",
    "town",
}


def build_queries(industry_class: str, location_query: str) -> list[str]:
    """Expand industry templates into concrete queries for one location."""
    config = get_industry_config(industry_class)
    return [template.format(location=location_query) for template in config.get("query_templates", [])]


def filter_profiles_for_target(
    *,
    profiles: list[dict[str, Any]],
    industry_class: str,
    location_query: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Filter profiles down to location-specific, reachable SME candidates."""
    config = get_industry_config(industry_class)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    for profile in profiles:
        rejection_reason = _rejection_reason(
            profile=profile,
            location_query=location_query,
            config=config,
        )
        if rejection_reason:
            rejected.append(
                {
                    "business_name": profile.get("business_name", "unknown"),
                    "reason": rejection_reason,
                }
            )
            continue
        accepted.append(profile)

    return accepted, rejected


def _rejection_reason(*, profile: dict[str, Any], location_query: str, config: dict[str, Any]) -> str | None:
    haystack = " ".join(
        part
        for part in [
            _clean(profile.get("business_name")),
            _clean(profile.get("category")),
            _clean(profile.get("address")),
            _clean(profile.get("area")),
        ]
        if part
    )

    if not _matches_requested_location(haystack, location_query):
        return "outside_requested_location"

    excluded_terms = [term.lower() for term in config.get("excluded_terms", [])]
    if any(term in haystack for term in excluded_terms):
        return "excluded_business_type"

    large_business_terms = [term.lower() for term in config.get("large_business_terms", [])]
    if any(term in haystack for term in large_business_terms):
        return "likely_not_sme"

    target_terms = [term.lower() for term in config.get("target_terms", [])]
    if target_terms and not any(term in haystack for term in target_terms):
        return "not_target_business"

    if not profile.get("phone"):
        return "missing_phone"

    return None


def _matches_requested_location(haystack: str, location_query: str) -> bool:
    normalized_haystack = _clean(haystack)
    if not normalized_haystack:
        return False

    segments = [segment.strip().lower() for segment in location_query.split(",") if segment.strip()]
    primary_segment = _clean(segments[0]) if segments else _clean(location_query)
    if not primary_segment:
        return False

    if primary_segment in normalized_haystack:
        return True

    tokens = [
        token
        for token in re.split(r"[^a-z0-9]+", primary_segment)
        if token and token not in GENERIC_LOCATION_TERMS
    ]
    if len(tokens) >= 2:
        return all(token in normalized_haystack for token in tokens)
    if tokens:
        return tokens[0] in normalized_haystack
    return False


def _clean(value: Any) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())
