"""Contacts router: read and update contacts for CRM editing."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user_from_token
from app.models.contact import Contact
from app.models.company import Company
from app.models.user import User
from app.schemas.contact import ContactUpdate, ContactResponse, ContactDetailResponse

router = APIRouter(prefix="/contacts", tags=["contacts"])


async def _get_current_user(
    authorization: str = Query(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    return await get_current_user_from_token(token, db)


# ── Get contact ────────────────────────────────────────────────────────────


@router.get("/{contact_id}", response_model=ContactDetailResponse)
async def get_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Fetch company info for detail response
    company_name = None
    company_domain = None
    company_industry = None
    if contact.company_id:
        company_result = await db.execute(select(Company).where(Company.id == contact.company_id))
        company = company_result.scalar_one_or_none()
        if company:
            # Verify team ownership
            if company.team_id != current_user.team_id:
                raise HTTPException(status_code=404, detail="Contact not found")
            company_name = company.name
            company_domain = company.domain
            company_industry = company.industry

    resp = ContactDetailResponse.model_validate(contact, from_attributes=True)
    resp.company_name = company_name
    resp.company_domain = company_domain
    resp.company_industry = company_industry
    return resp


# ── Update contact ─────────────────────────────────────────────────────────


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Verify team ownership through the company relation
    if contact.company_id:
        company_result = await db.execute(select(Company).where(Company.id == contact.company_id))
        company = company_result.scalar_one_or_none()
        if company and company.team_id != current_user.team_id:
            raise HTTPException(status_code=404, detail="Contact not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contact, field, value)

    contact.updated_at = datetime.utcnow()
    db.add(contact)
    await db.flush()
    await db.refresh(contact)

    return ContactResponse.model_validate(contact, from_attributes=True)
