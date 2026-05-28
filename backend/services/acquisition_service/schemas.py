"""Schemas for acquisition service APIs."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GoogleMapsLocationTargetCreate(BaseModel):
    location_label: str = Field(max_length=255)
    location_query: str = Field(max_length=255)
    radius_km: int = Field(default=5, ge=1, le=100)


class GoogleMapsSourceCreate(BaseModel):
    name: str = Field(max_length=255)
    industry_class: str = Field(max_length=64)
    max_results_per_location: int = Field(default=100, ge=1, le=500)
    promotion_mode: str = Field(default="review", max_length=20)
    require_phone: bool = True
    require_address: bool = False
    country_code: str = Field(default="KE", max_length=8)
    locations: list[GoogleMapsLocationTargetCreate] = Field(min_length=1)


class GoogleMapsLocationTargetResponse(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    location_label: str
    location_query: str
    radius_km: int
    query_templates: list[str]
    status: str
    results_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class GoogleMapsPromoteRequest(BaseModel):
    profile_ids: list[uuid.UUID] | None = None


class GoogleMapsSourceResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    name: str
    industry_class: str
    promotion_mode: str
    max_results_per_location: int
    require_phone: bool
    require_address: bool
    country_code: str
    status: str
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    locations: list[GoogleMapsLocationTargetResponse] = []

    model_config = {"from_attributes": True}


class GoogleMapsRawProfileResponse(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    location_target_id: Optional[uuid.UUID] = None
    query: str
    business_name: str
    category: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    google_maps_url: Optional[str] = None
    address: Optional[str] = None
    area: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    business_status: str
    scraped_at: datetime
    promotion_status: str

    model_config = {"from_attributes": True}


class AcquisitionJobResponse(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    job_type: str
    status: str
    task_id: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
