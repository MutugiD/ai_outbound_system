"""Acquisition domain models for Google Maps source jobs."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Index, JSON
from sqlmodel import Field, SQLModel


class GoogleMapsSource(SQLModel, table=True):
    __tablename__ = "google_maps_sources"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id", index=True)
    name: str = Field(max_length=255)
    industry_class: str = Field(max_length=64)
    promotion_mode: str = Field(default="review", max_length=20)
    max_results_per_location: int = Field(default=100)
    require_phone: bool = Field(default=True)
    require_address: bool = Field(default=False)
    country_code: str = Field(default="KE", max_length=8)
    status: str = Field(default="queued", max_length=30)
    created_by: Optional[uuid.UUID] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_google_maps_sources_team", "team_id"),
        Index("idx_google_maps_sources_status", "status"),
    )


class GoogleMapsLocationTarget(SQLModel, table=True):
    __tablename__ = "google_maps_location_targets"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source_id: uuid.UUID = Field(foreign_key="google_maps_sources.id", index=True)
    location_label: str = Field(max_length=255)
    location_query: str = Field(max_length=255)
    radius_km: int = Field(default=5)
    query_templates: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="queued", max_length=30)
    results_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_google_maps_locations_source", "source_id"),
        Index("idx_google_maps_locations_status", "status"),
    )


class GoogleMapsRawProfile(SQLModel, table=True):
    __tablename__ = "google_maps_raw_profiles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source_id: uuid.UUID = Field(foreign_key="google_maps_sources.id", index=True)
    location_target_id: Optional[uuid.UUID] = Field(default=None, foreign_key="google_maps_location_targets.id")
    query: str = Field(max_length=255)
    business_name: str = Field(max_length=500)
    category: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    website: Optional[str] = Field(default=None, max_length=1024)
    google_maps_url: Optional[str] = Field(default=None, max_length=2048)
    address: Optional[str] = Field(default=None, max_length=500)
    area: Optional[str] = Field(default=None, max_length=255)
    rating: Optional[float] = Field(default=None)
    review_count: Optional[int] = Field(default=None)
    latitude: Optional[float] = Field(default=None)
    longitude: Optional[float] = Field(default=None)
    business_status: str = Field(default="active", max_length=30)
    raw_payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    promotion_status: str = Field(default="pending_review", max_length=30)

    __table_args__ = (
        Index("idx_google_maps_raw_profiles_source", "source_id"),
        Index("idx_google_maps_raw_profiles_url", "google_maps_url"),
        Index("idx_google_maps_raw_profiles_phone", "phone"),
    )


class AcquisitionJob(SQLModel, table=True):
    __tablename__ = "acquisition_jobs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source_id: uuid.UUID = Field(foreign_key="google_maps_sources.id", index=True)
    job_type: str = Field(default="google_maps_scrape", max_length=50)
    status: str = Field(default="queued", max_length=30)
    task_id: Optional[str] = Field(default=None, max_length=255)
    error: Optional[str] = Field(default=None, max_length=2048)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    __table_args__ = (
        Index("idx_acquisition_jobs_source", "source_id"),
        Index("idx_acquisition_jobs_status", "status"),
    )

