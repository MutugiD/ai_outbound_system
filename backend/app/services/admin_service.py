"""Admin service — user management and API key management, team-scoped."""

import uuid
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.api_key import APIKey
from app.config import settings
from app.crypto import encrypt_secret, keyed_hash_secret


class AdminService:
    """Admin operations scoped to a team."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── User CRUD ──────────────────────────────────────────────────────────

    async def list_users(self, team_id: uuid.UUID, page: int = 1, per_page: int = 50) -> tuple[list[User], int]:
        """Paginated user list for the given team."""
        # Total count
        count_result = await self.db.execute(select(func.count(User.id)).where(User.team_id == team_id))
        total = count_result.scalar() or 0

        # Paginated results
        result = await self.db.execute(
            select(User)
            .where(User.team_id == team_id)
            .order_by(User.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        users = result.scalars().all()
        return list(users), total

    async def update_user(self, user_id: uuid.UUID, data: dict) -> Optional[User]:
        """Update user role, is_active, etc. Returns updated user or None."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return None

        for field, value in data.items():
            if value is not None and hasattr(user, field):
                setattr(user, field, value)

        self.db.add(user)
        await self.db.flush()
        return user

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        """Soft-delete user by setting is_active=False."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return False

        user.is_active = False
        self.db.add(user)
        await self.db.flush()
        return True

    # ── API Key CRUD ───────────────────────────────────────────────────────

    async def list_api_keys(self, team_id: uuid.UUID, page: int = 1, per_page: int = 50) -> tuple[list[APIKey], int]:
        """List team's API keys (provider, last4, status)."""
        count_result = await self.db.execute(select(func.count(APIKey.id)).where(APIKey.team_id == team_id))
        total = count_result.scalar() or 0

        result = await self.db.execute(
            select(APIKey)
            .where(APIKey.team_id == team_id)
            .order_by(APIKey.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        keys = result.scalars().all()
        return list(keys), total

    async def create_api_key(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        provider: str,
        key_plaintext: str,
        name: Optional[str] = None,
    ) -> APIKey:
        """Create a new API key for the team."""
        key_hash = keyed_hash_secret(key_plaintext)
        ciphertext = encrypt_secret(key_plaintext)
        last4 = key_plaintext[-4:] if key_plaintext and len(key_plaintext) >= 4 else ""
        key = APIKey(
            team_id=team_id,
            user_id=user_id,
            key_hash=key_hash,
            ciphertext=ciphertext,
            key_id=settings.ENCRYPTION_KEY_ID,
            last4=last4,
            name=name or f"{provider} key",
            permissions=["read"],
        )
        self.db.add(key)
        await self.db.flush()
        return key

    async def delete_api_key(self, key_id: uuid.UUID) -> bool:
        """Soft-delete API key (remove from DB — model has no is_active)."""
        result = await self.db.execute(select(APIKey).where(APIKey.id == key_id))
        key = result.scalar_one_or_none()
        if key is None:
            return False

        await self.db.delete(key)
        await self.db.flush()
        return True
