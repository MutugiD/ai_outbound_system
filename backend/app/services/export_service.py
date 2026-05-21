"""Export service — CSV and JSON export of lead data, team-scoped with filters."""

import csv
import io
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.lead_source import LeadSource
from app.models.company import Company
from app.models.contact import Contact


class ExportService:
    """Lead data export with filtering."""

    CSV_COLUMNS = [
        "id", "status", "pipeline_stage", "lead_score", "score_band",
        "source", "company_name", "contact_name", "contact_email",
        "created_at", "updated_at",
    ]

    def __init__(self, db: AsyncSession):
        self.db = db

    def _build_query(self, team_id: uuid.UUID, filters: Optional[dict] = None):
        """Build the base query with optional filters."""
        query = (
            select(Lead, Company.name, Contact.full_name, Contact.email, LeadSource.source_type)
            .select_from(Lead)
            .join(Company, Lead.company_id == Company.id, isouter=True)
            .join(Contact, Lead.contact_id == Contact.id, isouter=True)
            .join(LeadSource, LeadSource.lead_id == Lead.id, isouter=True)
            .where(Lead.team_id == team_id)
        )

        if filters:
            if filters.get("status"):
                query = query.where(Lead.status == filters["status"])
            if filters.get("score_band"):
                query = query.where(Lead.score_band == filters["score_band"])
            if filters.get("source"):
                query = query.where(LeadSource.source_type == filters["source"])
            if filters.get("date_from"):
                query = query.where(Lead.created_at >= filters["date_from"])
            if filters.get("date_to"):
                query = query.where(Lead.created_at <= filters["date_to"])

        return query.order_by(Lead.created_at.desc())

    async def export_leads_csv(
        self, team_id: uuid.UUID, filters: Optional[dict] = None
    ) -> io.StringIO:
        """Export leads to CSV and return a StringIO buffer."""
        query = self._build_query(team_id, filters)
        result = await self.db.execute(query)
        rows = result.all()

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=self.CSV_COLUMNS)
        writer.writeheader()

        for row in rows:
            lead = row[0]
            company_name = row[1] or ""
            contact_name = row[2] or ""
            contact_email = row[3] or ""
            source = row[4] or ""

            writer.writerow({
                "id": str(lead.id),
                "status": lead.status,
                "pipeline_stage": lead.pipeline_stage,
                "lead_score": lead.lead_score,
                "score_band": lead.score_band,
                "source": source,
                "company_name": company_name,
                "contact_name": contact_name,
                "contact_email": contact_email,
                "created_at": lead.created_at.isoformat() if lead.created_at else "",
                "updated_at": lead.updated_at.isoformat() if lead.updated_at else "",
            })

        buf.seek(0)
        return buf

    async def export_leads_json(
        self, team_id: uuid.UUID, filters: Optional[dict] = None
    ) -> list[dict]:
        """Export leads as a list of dicts."""
        query = self._build_query(team_id, filters)
        result = await self.db.execute(query)
        rows = result.all()

        data = []
        for row in rows:
            lead = row[0]
            company_name = row[1] or ""
            contact_name = row[2] or ""
            contact_email = row[3] or ""
            source = row[4] or ""

            data.append({
                "id": str(lead.id),
                "status": lead.status,
                "pipeline_stage": lead.pipeline_stage,
                "lead_score": lead.lead_score,
                "score_band": lead.score_band,
                "source": source,
                "company_name": company_name,
                "contact_name": contact_name,
                "contact_email": contact_email,
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
                "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
            })

        return data