"""Pydantic schemas for Admin API requests/responses — Wakili-Mkononi navy/gold."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import AliasChoices, BaseModel, EmailStr, Field


# ── User CRUD ──────────────────────────────────────────────────────────────


class UserUpdateRequest(BaseModel):
    """Admin update user payload."""

    role: Optional[str] = None
    is_active: Optional[bool] = None
    full_name: Optional[str] = None


class AdminUserResponse(BaseModel):
    """Admin user list/detail response."""

    id: uuid.UUID
    team_id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserListResponse(BaseModel):
    """Paginated user list."""

    items: list[AdminUserResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ── API Key CRUD ────────────────────────────────────────────────────────────


class APIKeyCreateRequest(BaseModel):
    """Create API key payload."""

    provider: str = Field(..., max_length=100, description="Wakili-Mkononi — provider name (e.g. openai, sendgrid)")
    key: str = Field(
        ...,
        validation_alias=AliasChoices("key", "key_encrypted"),
        description="API key value (plaintext; encrypted-at-rest server-side)",
    )
    name: Optional[str] = None


class APIKeyResponse(BaseModel):
    """API key list item — masked for security."""

    id: uuid.UUID
    team_id: uuid.UUID
    provider: str
    name: Optional[str] = None
    last4: str = ""
    status: str = "active"
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyListResponse(BaseModel):
    """Paginated API key list."""

    items: list[APIKeyResponse]
    total: int
    page: int
    per_page: int
    pages: int
