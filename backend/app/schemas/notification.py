"""Pydantic schemas for Notification API responses — Wakili-Mkononi navy/gold."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    """Single notification response."""
    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    title: str
    message: Optional[str] = None
    data: dict = {}
    is_read: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    """Paginated notification list."""
    items: list[NotificationResponse]
    total: int
    page: int
    per_page: int
    pages: int


class UnreadCountResponse(BaseModel):
    """Unread notification count."""
    unread_count: int


class MarkAllReadResponse(BaseModel):
    """Result of marking all notifications as read."""
    updated: int