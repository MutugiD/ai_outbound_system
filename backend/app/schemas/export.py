"""Pydantic schemas for Export API — Wakili-Mkononi navy/gold."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ExportFilters(BaseModel):
    """Filters for lead export — passed as query params."""
    status: Optional[str] = None
    score_band: Optional[str] = None
    source: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None