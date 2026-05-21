"""Activity logging service — write-only helper used across API routes and services."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityLog

# ── Canonical action types ─────────────────────────────────────────────────
# Keeping these as a module-level constant (not an Enum) so new actions can be
# added without a migration every time.
ACTION_TYPES: list[str] = [
    "lead_created",
    "lead_enriched",
    "signal_detected",
    "audit_completed",
    "research_completed",
    "score_calculated",
    "message_generated",
    "message_sent",
    "message_approved",
    "message_rejected",
    "reply_received",
    "reply_classified",
    "stage_changed",
    "note_added",
    "campaign_created",
    "campaign_started",
    "campaign_paused",
    "campaign_completed",
    "leads_enrolled",
    "lead_suppressed",
    "follow_up_scheduled",
    "follow_up_executed",
]


async def log_activity(
    db: AsyncSession,
    team_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    lead_id: Optional[uuid.UUID],
    action: str,
    details: Optional[dict] = None,
) -> ActivityLog:
    """Create an ActivityLog record.

    Parameters
    ----------
    db : AsyncSession
        The async database session (injected by FastAPI dependency).
    team_id : UUID
        Team scope for multi-tenancy.
    user_id : UUID | None
        The user who triggered the action (None for system/background actions).
    lead_id : UUID | None
        Optional lead this activity relates to.
    action : str
        One of the ACTION_TYPES (or a custom dot-namespaced string).
    details : dict | None
        Arbitrary JSON-serialisable metadata.

    Returns
    -------
    ActivityLog
        The persisted ActivityLog instance (not yet committed — caller
        should commit or rely on the get_db auto-commit).
    """
    entry = ActivityLog(
        team_id=team_id,
        user_id=user_id,
        lead_id=lead_id,
        action=action,
        details=details or {},
    )
    db.add(entry)
    await db.flush()
    return entry