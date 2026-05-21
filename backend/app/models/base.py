"""SQLModel base with common column defaults."""

import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


def uuid_pk() -> uuid.UUID:
    return uuid.uuid4()


class BaseModel(SQLModel):
    """Base model providing common audit columns."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
