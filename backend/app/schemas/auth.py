"""Auth Pydantic schemas."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=255)
    team_name: str = Field(..., min_length=1, max_length=255)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
