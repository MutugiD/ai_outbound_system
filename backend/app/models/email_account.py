"""EmailAccount model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, JSON, Numeric
from sqlmodel import Field, SQLModel


class EmailAccount(SQLModel, table=True):
    __tablename__ = "email_accounts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id")
    user_id: uuid.UUID = Field(foreign_key="users.id")
    provider: str = Field(max_length=50)  # gmail, outlook, sendgrid, resend
    email_address: str = Field(max_length=320)
    access_token_encrypted: str = Field(max_length=4096)
    refresh_token_encrypted: Optional[str] = Field(default=None, max_length=4096)
    provider_metadata: dict = Field(default={}, sa_column=Column(JSON))

    is_sending_account: bool = Field(default=False)
    is_inbox_account: bool = Field(default=False)
    daily_send_limit: int = Field(default=100)
    sends_today: int = Field(default=0)
    last_reset_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="active", max_length=20)  # active, disconnected, rate_limited
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
