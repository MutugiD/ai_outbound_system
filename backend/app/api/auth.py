"""Auth router: registration, login, refresh, and current-user."""

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user_from_token
from app.models.team import Team
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_access_token(user_id: str, team_id: str) -> str:
    expires = int(time.time()) + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    payload = {"sub": user_id, "team_id": team_id, "exp": expires, "type": "access"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _create_refresh_token(user_id: str, team_id: str) -> str:
    expires = int(time.time()) + settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    payload = {"sub": user_id, "team_id": team_id, "exp": expires, "type": "refresh"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ── Register ──────────────────────────────────────────────────────────────


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check uniqueness
    existing = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create team
    team = Team(name=body.team_name)
    db.add(team)
    await db.flush()

    # Create user
    user = User(
        team_id=team.id,
        email=body.email,
        password_hash=_hash_password(body.password),
        full_name=body.full_name,
        role="admin",  # First user in team is admin
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


# ── Login ─────────────────────────────────────────────────────────────────


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    # Update last_login
    user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()

    access = _create_access_token(str(user.id), str(user.team_id))
    refresh = _create_refresh_token(str(user.id), str(user.team_id))
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── Refresh ───────────────────────────────────────────────────────────────


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(body.refresh_token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = (await db.execute(select(User).where(User.id == payload["sub"]))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access = _create_access_token(str(user.id), str(user.team_id))
    refresh = _create_refresh_token(str(user.id), str(user.team_id))
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── Me ────────────────────────────────────────────────────────────────────


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(lambda token: token)):
    """Stub — actual token extraction done in dependency."""
    return current_user
