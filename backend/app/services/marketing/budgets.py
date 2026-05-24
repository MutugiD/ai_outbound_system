"""Marketing quota helpers (team-scoped hard caps).

Budgets live in `Team.settings["marketing"]["budgets"]` and are enforced as hard caps.
If a cap is exceeded, the request/job should be rejected/stopped cleanly.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import MarketingUsageDaily
from app.models.team import Team


DEFAULT_BUDGETS_BY_PLAN: dict[str, dict[str, int]] = {
    "free": {
        "daily_audience_signals_max": 50,
        "daily_scan_requests_max": 10,
        "per_scan_max_results": 25,
    },
    "pro": {
        "daily_audience_signals_max": 200,
        "daily_scan_requests_max": 50,
        "per_scan_max_results": 50,
    },
    "enterprise": {
        "daily_audience_signals_max": 1000,
        "daily_scan_requests_max": 250,
        "per_scan_max_results": 100,
    },
}


def deep_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge `patch` into `base` (returns a new dict)."""
    merged: dict[str, Any] = dict(base or {})
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_marketing_settings(team: Team) -> dict[str, Any]:
    settings = dict(team.settings or {})
    marketing = dict(settings.get("marketing") or {})

    # Defaults by plan (can be overridden per-team in settings)
    defaults = DEFAULT_BUDGETS_BY_PLAN.get(team.plan or "free", DEFAULT_BUDGETS_BY_PLAN["free"])
    budgets = dict(defaults)
    budgets.update(dict(marketing.get("budgets") or {}))

    marketing.setdefault("brand_brain", {})
    marketing.setdefault("platforms", {"enabled": ["reddit", "hn"]})
    marketing.setdefault("discovery", {})
    marketing.setdefault("schedule", {"scan_frequency": "daily"})
    marketing["budgets"] = budgets

    return marketing


async def get_or_create_usage(db: AsyncSession, team_id: uuid.UUID, day: date) -> MarketingUsageDaily:
    result = await db.execute(
        select(MarketingUsageDaily).where(MarketingUsageDaily.team_id == team_id, MarketingUsageDaily.day == day)
    )
    usage = result.scalar_one_or_none()
    if usage:
        return usage
    usage = MarketingUsageDaily(team_id=team_id, day=day)
    db.add(usage)
    await db.flush()
    return usage


def _quota_exceeded(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


async def enforce_scan_request_budget(db: AsyncSession, team: Team, day: date) -> MarketingUsageDaily:
    """Increment scans_requested if under cap; otherwise raise 429."""
    marketing = get_marketing_settings(team)
    budgets = marketing.get("budgets") or {}
    max_scans = int(budgets.get("daily_scan_requests_max") or 0)
    if max_scans <= 0:
        # Safety default: don't allow unlimited scans without explicit config.
        raise _quota_exceeded("Scan quota is not configured")

    usage = await get_or_create_usage(db, team.id, day)
    if usage.scans_requested >= max_scans:
        raise _quota_exceeded("Daily scan request quota reached")

    usage.scans_requested += 1
    usage.updated_at = datetime.utcnow()
    db.add(usage)
    return usage


def remaining_signals_budget(team: Team, usage: MarketingUsageDaily) -> int:
    marketing = get_marketing_settings(team)
    budgets = marketing.get("budgets") or {}
    max_signals = int(budgets.get("daily_audience_signals_max") or 0)
    if max_signals <= 0:
        return 0
    remaining = max_signals - int(usage.signals_saved or 0)
    return max(0, remaining)
