"""Test fixtures for the AI Outbound OS test suite.

Uses the running Postgres instance with database "outbound_os_test".
"""

import asyncio
import os
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

# ── Test database ────────────────────────────────────────────────────────────

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://outbound:outbound@localhost:5432/outbound_os_test",
)


# ── Engine + session (per-function to avoid event loop conflicts with asyncpg) ─


@pytest_asyncio.fixture
async def db_session():
    """Yield a test DB session. Creates tables before each test, drops after."""
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=5, max_overflow=5, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db():
    """Yield a test DB session that rolls back after each test (isolated)."""
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=5, max_overflow=5, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


# ── App / Client ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(db_session):
    """Async test client using httpx with ASGI transport."""
    from app.main import app
    from app.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Test team + user fixtures ──────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_team(db_session):
    """Create a test team."""
    from app.models.team import Team

    team = Team(name=f"Test Team {uuid.uuid4().hex[:8]}")
    db_session.add(team)
    await db_session.flush()
    return team


@pytest_asyncio.fixture
async def test_user(db_session, test_team):
    """Create a test user in the test team."""
    from app.models.user import User
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        team_id=test_team.id,
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=pwd_context.hash("testpassword123"),
        full_name="Test User",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user):
    """Return Authorization headers with a valid JWT for the test user."""
    from jose import jwt
    from app.config import settings

    import time

    token = jwt.encode(
        {
            "sub": str(test_user.id),
            "team_id": str(test_user.team_id),
            "exp": int(time.time()) + 3600,
            "type": "access",
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def auth_token(test_user):
    """Return a JWT access token string for the test user."""
    from jose import jwt
    from app.config import settings

    import time

    return jwt.encode(
        {
            "sub": str(test_user.id),
            "team_id": str(test_user.team_id),
            "exp": int(time.time()) + 3600,
            "type": "access",
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )