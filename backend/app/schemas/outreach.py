"""Campaign, Message, Reply, and FollowUp Pydantic schemas for API validation."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# CAMPAIGN SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class CampaignStepCreate(BaseModel):
    step_order: int = Field(ge=1, description="Step order (1-indexed)")
    channel: str = Field(default="email", max_length=20)
    delay_days: int = Field(default=0, ge=0)
    template_type: str = Field(default="initial_email", max_length=50)
    subject_template: Optional[str] = None
    body_template: Optional[str] = None


class CampaignStepUpdate(BaseModel):
    step_order: Optional[int] = None
    channel: Optional[str] = None
    delay_days: Optional[int] = None
    template_type: Optional[str] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None


class CampaignStepResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    step_order: int
    channel: str
    delay_days: int
    template_type: str
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignCreate(BaseModel):
    name: str = Field(max_length=255)
    description: Optional[str] = None
    goal: Optional[str] = Field(default="generate_interest", max_length=100)
    tone: str = Field(default="professional", max_length=50)
    approval_mode: str = Field(default="manual", max_length=20)
    send_limits: dict = Field(default_factory=dict)
    steps: Optional[list[CampaignStepCreate]] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    goal: Optional[str] = None
    tone: Optional[str] = None
    approval_mode: Optional[str] = None
    send_limits: Optional[dict] = None


class CampaignResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    name: str
    description: Optional[str] = None
    status: str
    goal: Optional[str] = None
    tone: str
    approval_mode: str
    send_limits: dict = {}
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignDetailResponse(CampaignResponse):
    """Campaign with nested steps."""
    steps: list[CampaignStepResponse] = []


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int
    page: int
    per_page: int
    pages: int


class CampaignEnrollmentResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    lead_id: uuid.UUID
    status: str
    current_step: int
    next_step_at: Optional[datetime] = None
    enrolled_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EnrollLeadsRequest(BaseModel):
    lead_ids: list[uuid.UUID]


class CampaignStatsResponse(BaseModel):
    campaign_id: str
    name: str
    status: str
    goal: Optional[str] = None
    tone: str
    enrollments: dict
    total_enrolled: int
    messages: dict
    total_messages: int
    steps_count: int


# ═══════════════════════════════════════════════════════════════════════════════
# MESSAGE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class MessageResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    campaign_id: Optional[uuid.UUID] = None
    campaign_step_id: Optional[uuid.UUID] = None
    channel: str
    subject: Optional[str] = None
    body: str
    personalization_sources: list = []
    status: str
    approved_by: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total: int
    page: int
    per_page: int
    pages: int


class MessageApprovalRequest(BaseModel):
    action: str = Field(description="approve or reject")


class GenerateMessagesRequest(BaseModel):
    lead_id: uuid.UUID
    channel: str = "email"
    strategies: Optional[list[str]] = None
    tone: str = "professional"
    goal: str = "generate_interest"
    custom_instructions: Optional[str] = None
    num_variants: int = Field(default=2, ge=1, le=5)
    model: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# REPLY SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class ReplyCreate(BaseModel):
    lead_id: uuid.UUID
    message_id: Optional[uuid.UUID] = None
    channel: str = "email"
    subject: Optional[str] = None
    body: str
    from_email: Optional[str] = None
    from_name: Optional[str] = None


class ReplyResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    message_id: Optional[uuid.UUID] = None
    channel: str
    subject: Optional[str] = None
    body: str
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    received_at: datetime

    model_config = {"from_attributes": True}


class ReplyClassificationResponse(BaseModel):
    id: uuid.UUID
    reply_id: uuid.UUID
    lead_id: uuid.UUID
    classification: str
    subtype: Optional[str] = None
    confidence: float
    summary: Optional[str] = None
    recommended_action: Optional[str] = None
    draft_response: Optional[str] = None
    model_used: Optional[str] = None
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ClassifyReplyRequest(BaseModel):
    reply_id: uuid.UUID
    model: Optional[str] = None


class ClassifyTextRequest(BaseModel):
    """Classify raw reply text without persisting."""
    reply_text: str
    original_subject: Optional[str] = None
    original_body: Optional[str] = None
    contact_context: Optional[str] = None


class ClassifyTextResponse(BaseModel):
    classification: str
    subtype: Optional[str] = None
    confidence: float
    summary: str
    recommended_action: str
    draft_response: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# FOLLOW-UP SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class FollowUpTaskResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    campaign_enrollment_id: Optional[uuid.UUID] = None
    task_type: str
    due_at: Optional[datetime] = None
    status: str
    data: dict = {}
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FollowUpTaskListResponse(BaseModel):
    items: list[FollowUpTaskResponse]
    total: int
    page: int
    per_page: int
    pages: int


class RescheduleTaskRequest(BaseModel):
    new_due_at: datetime


class ProcessClassificationRequest(BaseModel):
    classification_id: uuid.UUID