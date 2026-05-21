"""APIKey model per ARCHITECTURE.md schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, JSON, Numeric
from sqlmodel import Field, SQLModel


class APIKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="teams.id")
    user_id: uuid.UUID = Field(foreign_key="users.id")
    key_hash: str = Field(unique=True, max_length=1024)
    name: str = Field(max_length=255)
    permissions: list = Field(default=["read"],sa_column=Column(JSON))
    last_used_at: Optional[datetime] = Field(default=None)
    expires_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)