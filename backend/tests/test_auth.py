"""Auth API integration tests."""

import pytest
from httpx import AsyncClient


async def test_register_creates_team_and_user(client: AsyncClient):
    """POST /api/v1/auth/register should create a team and user."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"newuser_{id(object)}@example.com",
            "password": "securepass123",
            "full_name": "New User",
            "team_name": "New Team",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["email"] is not None
    assert data["role"] == "admin"
    assert "team_id" in data


async def test_login_returns_jwt(client: AsyncClient, db_session):
    """POST /api/v1/auth/login should return a valid JWT pair."""
    from app.models.team import Team
    from app.models.user import User
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    team = Team(name=f"LoginTest {id(object)}")
    db_session.add(team)
    await db_session.flush()

    email = f"logintest_{id(object)}@example.com"
    user = User(
        team_id=team.id,
        email=email,
        password_hash=pwd_context.hash("loginpass123"),
        full_name="Login Test",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "loginpass123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


async def test_refresh_returns_new_token(client: AsyncClient, db_session):
    """POST /api/v1/auth/refresh with a valid refresh token should return new tokens."""
    from app.models.team import Team
    from app.models.user import User
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    team = Team(name=f"RefreshTest {id(object)}")
    db_session.add(team)
    await db_session.flush()

    email = f"refreshtest_{id(object)}@example.com"
    user = User(
        team_id=team.id,
        email=email,
        password_hash=pwd_context.hash("refreshpass123"),
        full_name="Refresh Test",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    # Login first to get refresh token
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "refreshpass123"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


async def test_me_returns_user_info(client: AsyncClient, test_user, auth_token):
    """GET /api/v1/auth/me with a valid token should return user info."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200


async def test_unauthorized_access_returns_401(client: AsyncClient):
    """Requests without auth should return 401 or redirect."""
    resp = await client.get("/api/v1/leads")
    assert resp.status_code == 401
