"""Notification service — create, list, mark-read for team-scoped notifications."""

import uuid
from typing import Optional

from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationService:
    """Notification CRUD operations."""

    NOTIFICATION_TYPES = {
        "hot_lead",
        "reply_received",
        "campaign_completed",
        "meeting_booked",
        "task_due",
        "system",
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        type: str,
        title: str,
        message: Optional[str] = None,
        related_id: Optional[uuid.UUID] = None,
    ) -> Notification:
        """Create a new notification."""
        data = {}
        if related_id:
            data["related_id"] = str(related_id)

        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            data=data,
        )
        self.db.add(notification)
        await self.db.flush()
        return notification

    async def list_notifications(
        self,
        user_id: uuid.UUID,
        unread_only: bool = False,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[Notification], int]:
        """Paginated list of notifications for a user."""
        base_filter = Notification.user_id == user_id
        if unread_only:
            base_filter = and_(base_filter, Notification.is_read == False)  # noqa: E712

        count_result = await self.db.execute(
            select(func.count(Notification.id)).where(base_filter)
        )
        total = count_result.scalar() or 0

        result = await self.db.execute(
            select(Notification)
            .where(base_filter)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        notifications = result.scalars().all()
        return list(notifications), total

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Mark a single notification as read. Returns True if found."""
        result = await self.db.execute(
            select(Notification).where(
                and_(
                    Notification.id == notification_id,
                    Notification.user_id == user_id,
                )
            )
        )
        notification = result.scalar_one_or_none()
        if notification is None:
            return False

        notification.is_read = True
        self.db.add(notification)
        await self.db.flush()
        return True

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        """Mark all unread notifications as read for a user. Returns count updated."""
        result = await self.db.execute(
            select(Notification).where(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_read == False,  # noqa: E712
                )
            )
        )
        notifications = result.scalars().all()
        count = 0
        for n in notifications:
            n.is_read = True
            count += 1
        self.db.add_all(notifications)
        await self.db.flush()
        return count

    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        """Return the number of unread notifications for a user."""
        result = await self.db.execute(
            select(func.count(Notification.id)).where(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_read == False,  # noqa: E712
                )
            )
        )
        return result.scalar() or 0