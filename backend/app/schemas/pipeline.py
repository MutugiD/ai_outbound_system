"""Pydantic schemas for pipeline transition API request/response validation."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PipelineTransitionRequest(BaseModel):
    to_stage: str = Field(max_length=50)
    reason: Optional[str] = None
    note_content: Optional[str] = Field(default=None, max_length=5000)
    note_type: Optional[str] = Field(default="update", max_length=50)


class PipelineTransitionResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    from_stage: Optional[str] = None
    to_stage: str
    reason: Optional[str] = None
    transitioned_by: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PipelineTransitionDetailResponse(PipelineTransitionResponse):
    """Transition response with note info if a note was created."""

    note_id: Optional[uuid.UUID] = None
