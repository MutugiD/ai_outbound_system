"""Contact Pydantic schemas for API request/response validation."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ContactCreate(BaseModel):
    company_id: Optional[uuid.UUID] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    title: Optional[str] = None
    seniority: Optional[str] = None
    department: Optional[str] = None
    email: Optional[str] = None
    email_status: str = "unverified"
    phone: Optional[str] = None
    phone_status: str = "unverified"
    linkedin_url: Optional[str] = None
    location: Optional[str] = None


class ContactUpdate(BaseModel):
    company_id: Optional[uuid.UUID] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    title: Optional[str] = None
    seniority: Optional[str] = None
    department: Optional[str] = None
    email: Optional[str] = None
    email_status: Optional[str] = None
    phone: Optional[str] = None
    phone_status: Optional[str] = None
    linkedin_url: Optional[str] = None
    location: Optional[str] = None


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
    phone_status: str
    linkedin_url: Optional[str] = None
    location: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactListResponse(BaseModel):
    items: list[ContactResponse]
    total: int
    page: int
    per_page: int
    pages: int
