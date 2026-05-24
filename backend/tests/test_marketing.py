import pytest


@pytest.mark.asyncio
async def test_marketing_routes_require_auth(client):
    resp = await client.get("/api/v1/marketing/analytics/overview")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_audience_scan_enforces_daily_scan_requests_max(client, db_session, test_team, auth_headers, monkeypatch):
    # Patch Celery enqueue so tests don't require a broker.
    from app.api import marketing as marketing_api

    class DummyResult:
        id = "test-task-id"

    monkeypatch.setattr(marketing_api.run_audience_scan_task, "delay", lambda *_a, **_k: DummyResult())

    test_team.settings = {
        "marketing": {
            "budgets": {"daily_scan_requests_max": 1, "daily_audience_signals_max": 50, "per_scan_max_results": 10},
            "platforms": {"enabled": ["reddit"]},
            "discovery": {"keywords": ["crm"], "subreddits": ["startups"], "timeframe": "week"},
        }
    }
    db_session.add(test_team)
    await db_session.flush()

    resp1 = await client.post("/api/v1/marketing/audience-scans", json={"platforms": ["reddit"]}, headers=auth_headers)
    assert resp1.status_code == 202

    resp2 = await client.post("/api/v1/marketing/audience-scans", json={"platforms": ["reddit"]}, headers=auth_headers)
    assert resp2.status_code == 429


@pytest.mark.asyncio
async def test_audience_scan_job_team_scoped(client, db_session, test_team, test_user, auth_headers, monkeypatch):
    from app.models.team import Team
    from app.models.user import User
    from app.api import marketing as marketing_api

    class DummyResult:
        id = "test-task-id"

    monkeypatch.setattr(marketing_api.run_audience_scan_task, "delay", lambda *_a, **_k: DummyResult())

    # Create a second team/user
    other_team = Team(name="Other Team")
    db_session.add(other_team)
    await db_session.flush()
    other_user = User(
        team_id=other_team.id,
        email="other@example.com",
        password_hash=test_user.password_hash,
        full_name="Other",
        role="admin",
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.flush()

    # Create a scan job for the primary user/team
    test_team.settings = {"marketing": {"budgets": {"daily_scan_requests_max": 10, "per_scan_max_results": 5}}}
    db_session.add(test_team)
    await db_session.flush()

    resp = await client.post("/api/v1/marketing/audience-scans", json={"platforms": ["reddit"]}, headers=auth_headers)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Build headers for the other user
    from jose import jwt
    from app.config import settings
    import time

    other_token = jwt.encode(
        {"sub": str(other_user.id), "team_id": str(other_user.team_id), "exp": int(time.time()) + 3600, "type": "access"},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # Other team cannot access the job
    resp_other = await client.get(f"/api/v1/marketing/audience-scans/{job_id}", headers=other_headers)
    assert resp_other.status_code == 404
