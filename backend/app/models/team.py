"""Team model."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column, JSON, Numeric
from sqlmodel import Field, SQLModel

from app.models.base import BaseModel


class Team(SQLModel, table=True):
    __tablename__ = "teams"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    plan: str = Field(default="free", max_length=20)  # free, pro, enterprise
    settings: dict = Field(default={}, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)