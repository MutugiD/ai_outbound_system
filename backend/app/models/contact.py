"""Contact model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class Contact(SQLModel, table=True):
    __tablename__ = "contacts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    company_id: Optional[uuid.UUID] = Field(default=None, foreign_key="companies.id")
    first_name: Optional[str] = Field(default=None, max_length=255)
    last_name: Optional[str] = Field(default=None, max_length=255)
    full_name: Optional[str] = Field(default=None, max_length=500)
    title: Optional[str] = Field(default=None, max_length=255)
    seniority: Optional[str] = Field(default=None, max_length=50)  # c_suite, vp, director, manager, individual
    department: Optional[str] = Field(default=None, max_length=100)
    email: Optional[str] = Field(default=None, max_length=320)
    email_status: str = Field(default="unverified", max_length=20)  # unverified, verified, invalid, risky
    phone: Optional[str] = Field(default=None, max_length=50)
    phone_status: str = Field(default="unverified", max_length=20)
    linkedin_url: Optional[str] = Field(default=None, max_length=1024)
    location: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_contacts_company", "company_id"),
        Index("idx_contacts_email", "email"),
        Index("idx_contacts_linkedin", "linkedin_url"),
    )