"""Marketing pipeline models: audience scans, signals, drafts, and usage.

These tables are team-scoped (multi-tenant) and designed to support
quota-aware, async scraping at internet-facing SaaS posture.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Column, Index, JSON
from sqlmodel import Field, SQLModel


class AudienceScanJob(SQLModel, table=True):
    __tablename__ = "audience_scan_jobs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id", index=True)

    status: str = Field(default="queued", max_length=20)  # queued, running, completed, failed
    params: dict = Field(default_factory=dict, sa_column=Column(JSON))

    found_count: int = Field(default=0)
    kept_count: int = Field(default=0)
    deduped_count: int = Field(default=0)

    stop_reason: Optional[str] = Field(default=None, max_length=200)
    error: Optional[str] = Field(default=None, max_length=2048)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    __table_args__ = (
        Index("idx_audience_scan_jobs_team_status", "team_id", "status"),
        Index("idx_audience_scan_jobs_created_at", "created_at"),
    )


class AudienceSignal(SQLModel, table=True):
    __tablename__ = "audience_signals"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id", index=True)

    platform: str = Field(max_length=30, index=True)  # reddit, hn, x, linkedin, etc.
    source_url: str = Field(max_length=2048)
    external_id: Optional[str] = Field(default=None, max_length=255)

    title: Optional[str] = Field(default=None, max_length=512)
    body_excerpt: Optional[str] = Field(default=None, max_length=2048)
    author: Optional[str] = Field(default=None, max_length=255)
    community: Optional[str] = Field(default=None, max_length=255)  # subreddit, hn, etc.

    engagement: Optional[int] = Field(default=None)  # score/upvotes/etc.
    matched_keywords: list = Field(default_factory=list, sa_column=Column(JSON))
    intent_label: Optional[str] = Field(default=None, max_length=50)
    confidence: Optional[float] = Field(default=None)

    extra: dict = Field(default_factory=dict, sa_column=Column("metadata", JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    source_created_at: Optional[datetime] = Field(default=None)

    __table_args__ = (
        Index(
            "uq_audience_signals_team_platform_url",
            "team_id",
            "platform",
            "source_url",
            unique=True,
        ),
        Index("idx_audience_signals_team_created_at", "team_id", "created_at"),
    )


class MarketingUsageDaily(SQLModel, table=True):
    __tablename__ = "marketing_usage_daily"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id", index=True)
    day: date = Field(index=True)

    scans_requested: int = Field(default=0)
    scans_completed: int = Field(default=0)
    signals_saved: int = Field(default=0)
    drafts_generated: int = Field(default=0)
    llm_tokens_used: int = Field(default=0)

    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("uq_marketing_usage_daily_team_day", "team_id", "day", unique=True),
    )


class SocialPostDraft(SQLModel, table=True):
    __tablename__ = "social_post_drafts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id", index=True)
    platform: str = Field(max_length=30, index=True)
    goal: Optional[str] = Field(default=None, max_length=100)

    audience_signal_id: Optional[uuid.UUID] = Field(default=None, foreign_key="audience_signals.id")

    content: str = Field(sa_column_kwargs={"nullable": False})
    variant: int = Field(default=0)

    extra: dict = Field(default_factory=dict, sa_column=Column("metadata", JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_social_post_drafts_team_created_at", "team_id", "created_at"),
    )
