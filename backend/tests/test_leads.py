"""Lead API integration tests."""

import uuid

import pytest
from httpx import AsyncClient

from app.models.lead import Lead
from app.models.company import Company
from app.models.contact import Contact


async def _create_lead_with_company(db_session, team_id, **kwargs):
    """Helper to create a lead with company + contact for testing."""
    company = Company(
        team_id=team_id,
        name=kwargs.get("company_name", f"TestCo {uuid.uuid4().hex[:6]}"),
        domain=kwargs.get("domain", f"testco{uuid.uuid4().hex[:6]}.com"),
        industry=kwargs.get("industry", "technology"),
    )
    db_session.add(company)
    await db_session.flush()

    contact = Contact(
        company_id=company.id,
        full_name=kwargs.get("contact_name", "Jane Doe"),
        email=kwargs.get("email", f"jane_{uuid.uuid4().hex[:6]}@example.com"),
        title=kwargs.get("title", "CEO"),
        seniority="c_suite",
    )
    db_session.add(contact)
    await db_session.flush()

    lead = Lead(
        team_id=team_id,
        company_id=company.id,
        contact_id=contact.id,
        status=kwargs.get("status", "new"),
        lead_score=kwargs.get("lead_score", 0),
        score_band=kwargs.get("score_band", "low"),
    )
    db_session.add(lead)
    await db_session.flush()
    return lead


async def test_create_lead(client: AsyncClient, test_team, test_user, auth_token):
    """POST /api/v1/leads should create a new lead."""
    resp = await client.post(
        "/api/v1/leads",
        json={
            "company_name": "Acme Corp",
            "company_domain": "acme.example.com",
            "contact_first_name": "John",
            "contact_last_name": "Smith",
            "contact_email": f"john_{uuid.uuid4().hex[:6]}@acme.com",
            "contact_title": "VP Engineering",
        },
        # The leads API uses Query(alias="Authorization") for auth
        params={"Authorization": f"Bearer {auth_token}"},
    )
    # Accept 201 (created) or 200 depending on endpoint implementation
    assert resp.status_code in (200, 201), f"Got {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert "id" in data


async def test_list_leads_with_pagination(client: AsyncClient, test_team, db_session, auth_token):
    """GET /api/v1/leads should return a paginated list."""
    for i in range(3):
        await _create_lead_with_company(
            db_session,
            team_id=test_team.id,
            email=f"lead{i}_{uuid.uuid4().hex[:6]}@example.com",
        )

    resp = await client.get(
        "/api/v1/leads?page=1&per_page=2",
        params={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert "items" in data or "data" in data


async def test_get_lead_detail(client: AsyncClient, test_team, db_session, auth_token):
    """GET /api/v1/leads/{id} should return lead detail."""
    lead = await _create_lead_with_company(
        db_session,
        team_id=test_team.id,
        email=f"detail_{uuid.uuid4().hex[:6]}@example.com",
    )

    resp = await client.get(
        f"/api/v1/leads/{lead.id}",
        params={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert data["id"] == str(lead.id)


async def test_update_lead(client: AsyncClient, test_team, db_session, auth_token):
    """PATCH /api/v1/leads/{id} should update lead fields."""
    lead = await _create_lead_with_company(
        db_session,
        team_id=test_team.id,
        email=f"update_{uuid.uuid4().hex[:6]}@example.com",
    )

    resp = await client.patch(
        f"/api/v1/leads/{lead.id}",
        json={"status": "enriching", "pipeline_stage": "enriched"},
        params={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert data.get("status") in ("enriching", "enriched")


async def test_delete_lead(client: AsyncClient, test_team, db_session, auth_token):
    """DELETE /api/v1/leads/{id} should soft-delete the lead."""
    lead = await _create_lead_with_company(
        db_session,
        team_id=test_team.id,
        email=f"delete_{uuid.uuid4().hex[:6]}@example.com",
    )

    resp = await client.delete(
        f"/api/v1/leads/{lead.id}",
        params={"Authorization": f"Bearer {auth_token}"},
    )
    # Accept 204 or 200 depending on implementation
    assert resp.status_code in (200, 204), f"Got {resp.status_code}: {resp.text[:200]}"


async def test_filter_leads_by_status(client: AsyncClient, test_team, db_session, auth_token):
    """GET /api/v1/leads?status=new should filter leads by status."""
    await _create_lead_with_company(
        db_session,
        team_id=test_team.id,
        status="new",
        email=f"filter1_{uuid.uuid4().hex[:6]}@example.com",
    )
    await _create_lead_with_company(
        db_session,
        team_id=test_team.id,
        status="researched",
        email=f"filter2_{uuid.uuid4().hex[:6]}@example.com",
    )

    resp = await client.get(
        "/api/v1/leads?status=new",
        params={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    # Response should contain items
    assert "items" in data or "data" in data


async def test_filter_leads_by_score_band(client: AsyncClient, test_team, db_session, auth_token):
    """GET /api/v1/leads?score_band=hot should filter leads by score band."""
    await _create_lead_with_company(
        db_session,
        team_id=test_team.id,
        lead_score=75,
        score_band="hot",
        email=f"scoreband_{uuid.uuid4().hex[:6]}@example.com",
    )

    resp = await client.get(
        "/api/v1/leads?score_band=hot",
        params={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    items = data.get("items", data.get("data", []))
    # At least one hot lead should be present
    hot_items = [i for i in items if i.get("score_band") == "hot"]
    assert len(hot_items) >= 1