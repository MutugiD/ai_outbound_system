"""Lead notes router: CRUD for CRM-style activity notes attached to leads."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import PaginationParams, get_current_user_from_token, paginated_response
from app.models.note import LeadNote
from app.models.lead import Lead
from app.models.user import User
from app.schemas.note import NoteCreate, NoteUpdate, NoteResponse, NoteListResponse

router = APIRouter(prefix="/leads/{lead_id}/notes", tags=["notes"])


async def _get_current_user(
    authorization: str = Query(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    return await get_current_user_from_token(token, db)


async def _verify_lead_access(lead_id: uuid.UUID, team_id: uuid.UUID, db: AsyncSession) -> Lead:
    """Ensure the lead exists and belongs to the user's team."""
    result = await db.execute(select(Lead).where(Lead.id == lead_id, Lead.team_id == team_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


# ── List notes ─────────────────────────────────────────────────────────────


@router.get("", response_model=NoteListResponse)
async def list_notes(
    lead_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    note_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    lead = await _verify_lead_access(lead_id, current_user.team_id, db)

    query = select(LeadNote).where(LeadNote.lead_id == lead_id)
    if note_type:
        query = query.where(LeadNote.note_type.in_(note_type.split(",")))

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate (newest first)
    query = query.order_by(LeadNote.created_at.desc())
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    notes = list(result.scalars().all())

    params = PaginationParams(page=page, per_page=per_page)
    return paginated_response(
        [NoteResponse.model_validate(n, from_attributes=True) for n in notes],
        total,
        params,
    )


# ── Create note ───────────────────────────────────────────────────────────


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    lead_id: uuid.UUID,
    body: NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    await _verify_lead_access(lead_id, current_user.team_id, db)

    note = LeadNote(
        lead_id=lead_id,
        user_id=current_user.id,
        content=body.content,
        note_type=body.note_type,
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)
    return NoteResponse.model_validate(note, from_attributes=True)


# ── Update note ────────────────────────────────────────────────────────────


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    lead_id: uuid.UUID,
    note_id: uuid.UUID,
    body: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    await _verify_lead_access(lead_id, current_user.team_id, db)

    result = await db.execute(select(LeadNote).where(LeadNote.id == note_id, LeadNote.lead_id == lead_id))
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    update_data = body.model_dump(exclude_unset=True)
    from datetime import datetime

    for field, value in update_data.items():
        setattr(note, field, value)
    note.updated_at = datetime.utcnow()

    db.add(note)
    await db.flush()
    await db.refresh(note)
    return NoteResponse.model_validate(note, from_attributes=True)


# ── Delete note ────────────────────────────────────────────────────────────


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    lead_id: uuid.UUID,
    note_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    await _verify_lead_access(lead_id, current_user.team_id, db)

    result = await db.execute(select(LeadNote).where(LeadNote.id == note_id, LeadNote.lead_id == lead_id))
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    await db.delete(note)
    await db.flush()
