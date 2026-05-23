"""Pydantic schemas for LeadNote API request/response validation."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Create ────────────────────────────────────────────────────────────────


class NoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    note_type: str = Field(default="general", max_length=50)


# ── Update ────────────────────────────────────────────────────────────────


class NoteUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    note_type: Optional[str] = Field(default=None, max_length=50)


# ── Response ──────────────────────────────────────────────────────────────


class NoteResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    user_id: uuid.UUID
    content: str
    note_type: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── List ──────────────────────────────────────────────────────────────────


class NoteListResponse(BaseModel):
    items: list[NoteResponse]
    total: int
    page: int
    per_page: int
    pages: int
