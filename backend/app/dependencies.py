"""Shared FastAPI dependencies: auth, pagination helpers."""

import uuid
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User


# ── Pagination ────────────────────────────────────────────────────────────


class PaginationParams:
    """Common pagination query parameters."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    ):
        self.page = page
        self.per_page = per_page

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        return self.per_page


def paginated_response(items: list, total: int, params: PaginationParams) -> dict:
    """Build a standard paginated response envelope."""
    return {
        "items": items,
        "total": total,
        "page": params.page,
        "per_page": params.per_page,
        "pages": (total + params.per_page - 1) // params.per_page if total else 0,
    }


# ── Auth helpers ──────────────────────────────────────────────────────────


async def get_current_user(
    token: str = Depends(...),  # placeholder; real extraction from header below
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the current user from the Authorization header.

    This is a convenience wrapper; the actual token extraction is done in the
    routers via OAuth2PasswordBearer. This function is intended to be called
    after the token string has been obtained.
    """
    raise NotImplementedError("Use get_current_user_from_token instead.")


async def get_current_user_from_token(token: str, db: AsyncSession) -> User:
    """Validate a JWT access token and return the corresponding User."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def get_current_team(user: User = Depends(get_current_user)):  # noqa: F821
    """Return the team context for the current user."""
    # In a team-scoped app the team is always derived from the user.
    return user.team_id


def require_role(*roles: str):
    """Dependency factory that enforces the user has one of the given roles."""

    async def _check(user: User = Depends(get_current_user)):  # noqa: F821
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _check
