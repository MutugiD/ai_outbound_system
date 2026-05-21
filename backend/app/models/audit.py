"""WebsiteAudit model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Index, JSON
from sqlmodel import Field, SQLModel


class WebsiteAudit(SQLModel, table=True):
    __tablename__ = "website_audits"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    company_id: uuid.UUID = Field(foreign_key="companies.id")
    website_score: Optional[int] = Field(default=None)
    page_speed_score: Optional[int] = Field(default=None)
    mobile_score: Optional[int] = Field(default=None)
    has_chatbot: Optional[bool] = Field(default=None)
    has_booking: Optional[bool] = Field(default=None)
    has_contact_form: Optional[bool] = Field(default=None)
    has_email_capture: Optional[bool] = Field(default=None)
    has_crm_form: Optional[bool] = Field(default=None)
    has_tracking_scripts: Optional[bool] = Field(default=None)
    has_support_widget: Optional[bool] = Field(default=None)
    broken_forms: Optional[bool] = Field(default=None)
    weak_cta: Optional[bool] = Field(default=None)
    technical_findings: list = Field(default=[], sa_column=Column(JSON))
    conversion_findings: list = Field(default=[], sa_column=Column(JSON))
    automation_findings: list = Field(default=[], sa_column=Column(JSON))
    sales_angle: Optional[str] = Field(default=None)
    raw_content_url: Optional[str] = Field(default=None, max_length=2048)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("idx_audits_company", "company_id"),
    )