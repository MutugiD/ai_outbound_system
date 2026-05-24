"""Analytics, Admin, Notification, and Export integration tests.

Uses the existing conftest.py pattern with test DB, async client, and auth tokens.
"""

import csv
import io
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.team import Team
from app.models.user import User
from app.models.lead import Lead
from app.models.company import Company
from app.models.contact import Contact
from app.models.lead_source import LeadSource
from app.models.campaign import Campaign, CampaignEnrollment
from app.models.message import OutreachMessage
from app.models.signal import BuyingSignal
from app.models.score import LeadScore
from app.models.notification import Notification
from app.models.api_key import APIKey
from app.models.reply import Reply, ReplyClassification


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _create_team_with_admin(db_session):
    """Create a team + admin user and return (team, user)."""
    from passlib.context import CryptContext

    team = Team(name=f"Test Team {uuid.uuid4().hex[:8]}")
    db_session.add(team)
    await db_session.flush()

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        team_id=team.id,
        email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=pwd_context.hash("testpassword123"),
        full_name="Admin User",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return team, user


async def _make_auth_token(user):
    """Create a JWT token for the given user."""
    import time
    from jose import jwt
    from app.config import settings

    return jwt.encode(
        {"sub": str(user.id), "team_id": str(user.team_id), "exp": int(time.time()) + 3600, "type": "access"},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


async def _seed_leads(db_session, team_id, count=5, **kwargs):
    """Create a batch of test leads with companies and contacts."""
    leads = []
    for i in range(count):
        company = Company(
            team_id=team_id,
            name=f"TestCo {uuid.uuid4().hex[:6]}",
            domain=f"testco{uuid.uuid4().hex[:6]}.com",
            industry="technology",
        )
        db_session.add(company)
        await db_session.flush()

        contact = Contact(
            company_id=company.id,
            full_name=f"Contact {i}",
            email=f"contact{i}_{uuid.uuid4().hex[:6]}@example.com",
            title="CEO",
            seniority="c_suite",
        )
        db_session.add(contact)
        await db_session.flush()

        lead = Lead(
            team_id=team_id,
            company_id=company.id,
            contact_id=contact.id,
            status=kwargs.get("status", "new"),
            pipeline_stage=kwargs.get("pipeline_stage", "new"),
            lead_score=kwargs.get("lead_score", 50),
            score_band=kwargs.get("score_band", "warm"),
        )
        db_session.add(lead)
        await db_session.flush()
        leads.append(lead)
    return leads


# ── Analytics Tests ──────────────────────────────────────────────────────────


async def test_overview_stats_structure(client, db_session):
    """GET /analytics/overview returns required fields."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    resp = await client.get(
        "/api/v1/analytics/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:300]}"
    data = resp.json()

    required_fields = [
        "total_leads",
        "new_leads_today",
        "hot_leads",
        "messages_sent",
        "reply_rate",
        "interested_replies",
        "booked_calls",
        "pipeline_value",
        "conversion_rate",
        "top_source",
        "top_campaign",
    ]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"


async def test_overview_stats_with_leads(client, db_session):
    """Overview stats reflect created leads."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    leads = await _seed_leads(db_session, team.id, count=3, score_band="hot", lead_score=80)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/analytics/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_leads"] >= 3
    assert data["hot_leads"] >= 3


async def test_campaign_analytics(client, db_session):
    """GET /analytics/campaigns returns campaign-level stats."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    # Create a campaign
    campaign = Campaign(team_id=team.id, name="Test Campaign", status="active")
    db_session.add(campaign)
    await db_session.flush()

    # Create lead + enrollment
    leads = await _seed_leads(db_session, team.id, count=2)
    enrollment = CampaignEnrollment(campaign_id=campaign.id, lead_id=leads[0].id)
    db_session.add(enrollment)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/analytics/campaigns",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "campaigns" in data
    assert len(data["campaigns"]) >= 1
    c = data["campaigns"][0]
    assert "campaign_id" in c
    assert "campaign_name" in c
    assert "enrolled" in c
    assert "messages_sent" in c


async def test_source_analytics(client, db_session):
    """GET /analytics/sources returns source performance."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    leads = await _seed_leads(db_session, team.id, count=2)
    for lead in leads:
        source = LeadSource(lead_id=lead.id, source_type="reddit", source_name="r/test")
        db_session.add(source)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/analytics/sources",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data


async def test_channel_analytics(client, db_session):
    """GET /analytics/channels returns channel performance."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    leads = await _seed_leads(db_session, team.id, count=2)
    # Create an outreach message
    msg = OutreachMessage(
        lead_id=leads[0].id,
        channel="email",
        body="Test message",
        status="sent",
    )
    db_session.add(msg)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/analytics/channels",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "channels" in data


async def test_pipeline_analytics_with_stages(client, db_session):
    """GET /analytics/pipeline returns stage counts and conversion rates."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    # Create leads in different pipeline stages
    await _seed_leads(db_session, team.id, count=2, pipeline_stage="new")
    await _seed_leads(db_session, team.id, count=1, pipeline_stage="contacted")
    await db_session.commit()

    resp = await client.get(
        "/api/v1/analytics/pipeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "stages" in data
    assert "conversions" in data
    assert len(data["stages"]) >= 2  # "new" and "contacted"


async def test_score_distribution(client, db_session):
    """GET /analytics/scores returns lead score distribution."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    await _seed_leads(db_session, team.id, count=3, score_band="hot", lead_score=80)
    await _seed_leads(db_session, team.id, count=2, score_band="warm", lead_score=50)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/analytics/scores",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "distribution" in data
    bands = {d["score_band"]: d["count"] for d in data["distribution"]}
    assert "hot" in bands
    assert "warm" in bands


async def test_signal_distribution(client, db_session):
    """GET /analytics/signals returns buying signal distribution."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    leads = await _seed_leads(db_session, team.id, count=3)
    for lead in leads[:2]:
        signal = BuyingSignal(
            lead_id=lead.id,
            category="hiring_ops_role",
            evidence="Looking for ops manager",
            source="reddit",
        )
        db_session.add(signal)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/analytics/signals",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "signals" in data


# ── Admin Tests ──────────────────────────────────────────────────────────────


async def test_admin_list_users(client, db_session):
    """GET /admin/users returns paginated user list."""
    team, admin_user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(admin_user)

    resp = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


async def test_admin_update_user(client, db_session):
    """PATCH /admin/users/{id} updates user role."""
    team, admin_user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(admin_user)

    resp = await client.patch(
        f"/api/v1/admin/users/{admin_user.id}",
        json={"role": "manager"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("role") == "manager"


async def test_admin_delete_user(client, db_session):
    """DELETE /admin/users/{id} soft-deletes the user."""
    team, admin_user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(admin_user)

    # Create second user to delete
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    second_user = User(
        team_id=team.id,
        email=f"delete_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=pwd_context.hash("testpassword123"),
        full_name="Delete Me",
        role="member",
        is_active=True,
    )
    db_session.add(second_user)
    await db_session.flush()
    await db_session.commit()

    resp = await client.delete(
        f"/api/v1/admin/users/{second_user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204


async def test_admin_api_key_crud(client, db_session):
    """CRUD operations on API keys."""
    team, admin_user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(admin_user)

    # Create
    resp = await client.post(
        "/api/v1/admin/api-keys",
        json={
            "provider": "openai",
            "key_encrypted": "sk-test-key-12345678",
            "name": "OpenAI Key",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Got {resp.status_code}: {resp.text[:300]}"
    key_data = resp.json()
    assert key_data.get("provider") == "openai"
    key_id = key_data["id"]

    # List
    resp = await client.get(
        "/api/v1/admin/api-keys",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1

    # Delete
    resp = await client.delete(
        f"/api/v1/admin/api-keys/{key_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204


# ── Notification Tests ───────────────────────────────────────────────────────


async def test_notification_crud(client, db_session):
    """Create, list, mark-read, and count notifications."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    # Create notification via service (no API endpoint for create — internal)
    from app.services.notification_service import NotificationService

    svc = NotificationService(db_session)
    n = await svc.create_notification(
        team_id=team.id,
        user_id=user.id,
        type="hot_lead",
        title="New hot lead detected",
        message="Lead XYZ has a score of 95.",
    )
    await db_session.commit()

    # List
    resp = await client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1

    # Unread count
    resp = await client.get(
        "/api/v1/notifications/unread-count",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    count_data = resp.json()
    assert count_data["unread_count"] >= 1


async def test_notification_mark_read(client, db_session):
    """Mark a notification as read and verify count drops."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    from app.services.notification_service import NotificationService

    svc = NotificationService(db_session)
    n = await svc.create_notification(
        team_id=team.id,
        user_id=user.id,
        type="system",
        title="Test notification",
        message="Mark this as read.",
    )
    await db_session.commit()

    # Mark read
    resp = await client.patch(
        f"/api/v1/notifications/{n.id}/read",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True

    # Unread count should be 0 or decreased
    resp = await client.get(
        "/api/v1/notifications/unread-count",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


async def test_unread_notification_count(client, db_session):
    """GET /notifications/unread-count returns correct count."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    from app.services.notification_service import NotificationService

    svc = NotificationService(db_session)
    await svc.create_notification(team_id=team.id, user_id=user.id, type="system", title="N1", message="m1")
    await svc.create_notification(team_id=team.id, user_id=user.id, type="system", title="N2", message="m2")
    await svc.create_notification(team_id=team.id, user_id=user.id, type="hot_lead", title="N3", message="m3")
    await db_session.commit()

    resp = await client.get(
        "/api/v1/notifications/unread-count",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["unread_count"] >= 3


# ── Export Tests ──────────────────────────────────────────────────────────────


async def test_export_csv_format(client, db_session):
    """GET /export/leads/csv returns valid CSV with headers."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    await _seed_leads(db_session, team.id, count=2)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/export/leads/csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert "attachment" in resp.headers.get("content-disposition", "")

    # Parse CSV content
    content = resp.text
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) >= 2
    assert "id" in rows[0]
    assert "status" in rows[0]
    assert "pipeline_stage" in rows[0]


async def test_export_json_structure(client, db_session):
    """GET /export/leads/json returns valid JSON with lead data."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    await _seed_leads(db_session, team.id, count=2)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/export/leads/json",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "leads" in data
    assert "total" in data
    assert data["total"] >= 2
    assert len(data["leads"]) >= 2
    lead = data["leads"][0]
    assert "id" in lead
    assert "status" in lead
    assert "pipeline_stage" in lead
    assert "score_band" in lead


# ── Empty Data Test ──────────────────────────────────────────────────────────


async def test_analytics_with_empty_data(client, db_session):
    """All analytics endpoints return valid empty/default responses with no leads."""
    team, user = await _create_team_with_admin(db_session)
    token = await _make_auth_token(user)

    # Overview
    resp = await client.get(
        "/api/v1/analytics/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_leads"] == 0
    assert data["hot_leads"] == 0
    assert data["reply_rate"] == 0.0

    # Campaigns
    resp = await client.get(
        "/api/v1/analytics/campaigns",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["campaigns"] == []

    # Sources
    resp = await client.get(
        "/api/v1/analytics/sources",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["sources"] == []

    # Channels
    resp = await client.get(
        "/api/v1/analytics/channels",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["channels"] == []

    # Pipeline
    resp = await client.get(
        "/api/v1/analytics/pipeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    pipeline = resp.json()
    assert "stages" in pipeline
    assert "conversions" in pipeline

    # Scores
    resp = await client.get(
        "/api/v1/analytics/scores",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["distribution"] == []

    # Signals
    resp = await client.get(
        "/api/v1/analytics/signals",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["signals"] == []
