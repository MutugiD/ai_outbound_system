"""Companies router: list, get, update."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import PaginationParams, get_current_user_from_token, paginated_response
from app.models.company import Company
from app.models.user import User
from app.schemas.company import (
    CompanyCreate,
    CompanyUpdate,
    CompanyResponse,
    CompanyListResponse,
)

router = APIRouter(prefix="/companies", tags=["companies"])


async def _get_current_user(authorization: str = Query(..., alias="Authorization"), db: AsyncSession = Depends(get_db)):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    return await get_current_user_from_token(token, db)


# ── List companies ────────────────────────────────────────────────────────


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_get_current_user),
):
    query = select(Company).where(Company.team_id == current_user.team_id)

    if search:
        query = query.where(Company.name.ilike(f"%{search}%"))
    if industry:
        query = query.where(Company.industry == industry)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page).order_by(Company.created_at.desc())
    result = await db.execute(query)
    companies = result.scalars().all()

    params = PaginationParams(page=page, per_page=per_page)
    return paginated_response(
        [CompanyResponse.model_validate(c, from_attributes=True) for c in companies],
        total,
        params,
    )


# ── Get company ───────────────────────────────────────────────────────────


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_get_current_user),
):
    company = (await db.execute(
        select(Company).where(Company.id == company_id, Company.team_id == current_user.team_id)
    )).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyResponse.model_validate(company, from_attributes=True)


# ── Update company ────────────────────────────────────────────────────────


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_get_current_user),
):
    company = (await db.execute(
        select(Company).where(Company.id == company_id, Company.team_id == current_user.team_id)
    )).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(company, field, value)

    db.add(company)
    await db.flush()
    await db.refresh(company)
    return CompanyResponse.model_validate(company, from_attributes=True)