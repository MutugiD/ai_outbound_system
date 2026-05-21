"""Export API endpoints — CSV and JSON lead export. Wakili-Mkononi navy/gold."""

import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user_from_token
from app.models.user import User
from app.services.export_service import ExportService

router = APIRouter(prefix="/export", tags=["export"])


async def _get_current_user(
    authorization: str = Query(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Extract token from query param and resolve user."""
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    return await get_current_user_from_token(token, db)


# ── Export Leads CSV ───────────────────────────────────────────────────────


@router.get("/leads/csv")
async def export_leads_csv(
    status: Optional[str] = Query(None),
    score_band: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Download leads as CSV file with proper content-disposition header."""
    svc = ExportService(db)
    filters = {}
    if status:
        filters["status"] = status
    if score_band:
        filters["score_band"] = score_band
    if source:
        filters["source"] = source
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    buf = await svc.export_leads_csv(current_user.team_id, filters=filters if filters else None)

    filename = f"leads_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Export Leads JSON ──────────────────────────────────────────────────────


@router.get("/leads/json")
async def export_leads_json(
    status: Optional[str] = Query(None),
    score_band: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Download leads as JSON."""
    svc = ExportService(db)
    filters = {}
    if status:
        filters["status"] = status
    if score_band:
        filters["score_band"] = score_band
    if source:
        filters["source"] = source
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    data = await svc.export_leads_json(current_user.team_id, filters=filters if filters else None)
    return JSONResponse(content={"leads": data, "total": len(data)})
