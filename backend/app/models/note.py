"""Lead notes for CRM-style activity tracking."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Index, Text
from sqlmodel import Field, SQLModel


class LeadNote(SQLModel, table=True):
    __tablename__ = "lead_notes"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lead_id: uuid.UUID = Field(foreign_key="leads.id", index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    content: str = Field(sa_column=Text())
    note_type: str = Field(default="general", max_length=50)  # general, call, email, meeting, update
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)

    __table_args__ = (
        Index("idx_lead_notes_lead", "lead_id"),
        Index("idx_lead_notes_user", "user_id"),
        Index("idx_lead_notes_created", "created_at"),
    )
