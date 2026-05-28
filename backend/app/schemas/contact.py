"""Pydantic schemas for Contact API request/response validation."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Update ────────────────────────────────────────────────────────────────


class ContactUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, max_length=255)
    last_name: Optional[str] = Field(default=None, max_length=255)
    full_name: Optional[str] = Field(default=None, max_length=500)
    title: Optional[str] = Field(default=None, max_length=255)
    seniority: Optional[str] = Field(default=None, max_length=50)
    department: Optional[str] = Field(default=None, max_length=100)
    email: Optional[str] = Field(default=None, max_length=320)
    email_status: Optional[str] = Field(default=None, max_length=20)
    phone: Optional[str] = Field(default=None, max_length=50)
    raw_phone: Optional[str] = Field(default=None, max_length=50)
    normalized_phone: Optional[str] = Field(default=None, max_length=50)
    whatsapp_phone: Optional[str] = Field(default=None, max_length=50)
    phone_status: Optional[str] = Field(default=None, max_length=20)
    linkedin_url: Optional[str] = Field(default=None, max_length=1024)
    location: Optional[str] = Field(default=None, max_length=500)
    company_id: Optional[uuid.UUID] = None


# ── Response ──────────────────────────────────────────────────────────────


class ContactResponse(BaseModel):
    id: uuid.UUID
    company_id: Optional[uuid.UUID] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    title: Optional[str] = None
    seniority: Optional[str] = None
    department: Optional[str] = None
    email: Optional[str] = None
    email_status: str
    phone: Optional[str] = None
    raw_phone: Optional[str] = None
    normalized_phone: Optional[str] = None
    whatsapp_phone: Optional[str] = None
    phone_status: str
    linkedin_url: Optional[str] = None
    location: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactDetailResponse(ContactResponse):
    """Contact with nested company info."""

    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    company_industry: Optional[str] = None
