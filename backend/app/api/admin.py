"""Admin API endpoints — user management and API key management.

All endpoints require admin role. Wakili-Mkononi navy/gold.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user_from_token, PaginationParams, paginated_response
from app.models.user import User
from app.schemas.admin import (
    UserUpdateRequest,
    AdminUserResponse,
    AdminUserListResponse,
    APIKeyCreateRequest,
    APIKeyResponse,
    APIKeyListResponse,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])


async def _get_admin_user(
    authorization: str = Query(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Extract token and verify admin role."""
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    user = await get_current_user_from_token(token, db)
    if user.role not in ("admin", "manager"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# ── User Management ────────────────────────────────────────────────────────


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_admin_user),
):
    """List team users (paginated). Admin-only."""
    svc = AdminService(db)
    users, total = await svc.list_users(current_user.team_id, page=page, per_page=per_page)
    params = PaginationParams(page=page, per_page=per_page)
    resp = paginated_response(
        [AdminUserResponse.model_validate(u, from_attributes=True) for u in users],
        total,
        params,
    )
    return AdminUserListResponse(**resp)


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_admin_user),
):
    """Update user role and/or active status. Admin-only."""
    svc = AdminService(db)
    data = body.model_dump(exclude_unset=True)
    user = await svc.update_user(user_id, data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUserResponse.model_validate(user, from_attributes=True)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_admin_user),
):
    """Deactivate a user (soft delete). Admin-only."""
    svc = AdminService(db)
    deleted = await svc.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")


# ── API Key Management ────────────────────────────────────────────────────


@router.get("/api-keys", response_model=APIKeyListResponse)
async def list_api_keys(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_admin_user),
):
    """List team API keys. Admin-only."""
    svc = AdminService(db)
    keys, total = await svc.list_api_keys(current_user.team_id, page=page, per_page=per_page)

    items = []
    for k in keys:
        # Mask the key hash to show last 4 chars
        last4 = k.key_hash[-4:] if k.key_hash and len(k.key_hash) >= 4 else "****"
        items.append(APIKeyResponse(
            id=k.id,
            team_id=k.team_id,
            provider=k.name.split()[0] if k.name else "unknown",
            name=k.name,
            last4=last4,
            status="active",
            last_used_at=k.last_used_at,
            created_at=k.created_at,
        ))

    params = PaginationParams(page=page, per_page=per_page)
    resp = paginated_response(items, total, params)
    return APIKeyListResponse(**resp)


@router.post("/api-keys", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: APIKeyCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_admin_user),
):
    """Create a new API key. Admin-only."""
    svc = AdminService(db)
    key = await svc.create_api_key(
        team_id=current_user.team_id,
        user_id=current_user.id,
        provider=body.provider,
        key_encrypted=body.key_encrypted,
        name=body.name,
    )
    last4 = key.key_hash[-4:] if key.key_hash and len(key.key_hash) >= 4 else "****"
    return APIKeyResponse(
        id=key.id,
        team_id=key.team_id,
        provider=body.provider,
        name=key.name,
        last4=last4,
        status="active",
        last_used_at=key.last_used_at,
        created_at=key.created_at,
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_admin_user),
):
    """Delete an API key. Admin-only."""
    svc = AdminService(db)
    deleted = await svc.delete_api_key(key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found")