"""Notification API endpoints — Wakili-Mkononi navy/gold."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import PaginationParams, get_current_user, paginated_response
from app.models.user import User
from app.schemas.notification import (
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
    MarkAllReadResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── List notifications ─────────────────────────────────────────────────────


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List notifications for the current user (paginated, optional unread filter)."""
    svc = NotificationService(db)
    notifications, total = await svc.list_notifications(
        user_id=current_user.id,
        unread_only=unread_only,
        page=page,
        per_page=per_page,
    )
    params = PaginationParams(page=page, per_page=per_page)
    resp = paginated_response(
        [NotificationResponse.model_validate(n, from_attributes=True) for n in notifications],
        total,
        params,
    )
    return NotificationListResponse(**resp)


# ── Mark read ──────────────────────────────────────────────────────────────


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a single notification as read."""
    svc = NotificationService(db)
    found = await svc.mark_read(notification_id, current_user.id)
    if not found:
        raise HTTPException(status_code=404, detail="Notification not found")

    # Re-fetch the updated notification
    from sqlalchemy import select
    from app.models.notification import Notification

    result = await db.execute(select(Notification).where(Notification.id == notification_id))
    notification = result.scalar_one()
    return NotificationResponse.model_validate(notification, from_attributes=True)


# ── Mark all read ──────────────────────────────────────────────────────────


@router.post("/mark-all-read", response_model=MarkAllReadResponse)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all unread notifications as read for the current user."""
    svc = NotificationService(db)
    count = await svc.mark_all_read(current_user.id)
    return MarkAllReadResponse(updated=count)


# ── Unread count ───────────────────────────────────────────────────────────


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the count of unread notifications for the current user."""
    svc = NotificationService(db)
    count = await svc.get_unread_count(current_user.id)
    return UnreadCountResponse(unread_count=count)
