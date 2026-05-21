"""LeadService: CRUD operations, filtering, pagination, activity logging."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.company import Company
from app.models.contact import Contact
from app.models.lead_source import LeadSource
from app.models.activity import ActivityLog
from app.schemas.lead import LeadCreate, LeadUpdate


class LeadService:
    """Encapsulates all lead-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _log_activity(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        lead_id: uuid.UUID,
        action: str,
        details: dict | None = None,
    ) -> None:
        """Record an activity log entry for a lead mutation."""
        log = ActivityLog(
            team_id=team_id,
            user_id=user_id,
            lead_id=lead_id,
            action=action,
            details=details or {},
        )
        self.db.add(log)

    @staticmethod
    def _apply_filters(query, team_id: uuid.UUID, filters: dict[str, Any]):
        """Apply filter dict to a Lead query."""
        query = query.where(Lead.team_id == team_id)

        if "status" in filters:
            query = query.where(Lead.status.in_(filters["status"]))
        if "score_band" in filters:
            query = query.where(Lead.score_band.in_(filters["score_band"]))
        if "pipeline_stage" in filters:
            query = query.where(Lead.pipeline_stage.in_(filters["pipeline_stage"]))
        if "min_score" in filters:
            query = query.where(Lead.lead_score >= filters["min_score"])
        if "max_score" in filters:
            query = query.where(Lead.lead_score <= filters["max_score"])
        if "assigned_user_id" in filters:
            query = query.where(Lead.assigned_user_id == filters["assigned_user_id"])
        return query

    # ── List ─────────────────────────────────────────────────────────────

    async def list_leads(
        self,
        team_id: uuid.UUID,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 50,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Lead], int]:
        """Return paginated leads for a team, with optional filters."""
        filters = filters or {}
        query = select(Lead)

        # Join with Company for industry/source filters
        join_company = "industry" in filters or "search" in filters or "source" in filters
        if join_company:
            query = query.join(Company, Lead.company_id == Company.id, isouter=True)

        query = self._apply_filters(query, team_id, filters)

        # Text search (company name or contact info)
        if "search" in filters:
            term = f"%{filters['search']}%"
            query = query.where(
                or_(
                    Company.name.ilike(term),
                    Lead.next_action.ilike(term),
                )
            )

        if "industry" in filters:
            query = query.where(Company.industry.in_(filters["industry"]))

        # Count
        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        # Sort
        sort_col = getattr(Lead, sort_by, Lead.created_at)
        if sort_order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        result = await self.db.execute(query)
        leads = list(result.scalars().all())
        return leads, total

    # ── Get ───────────────────────────────────────────────────────────────

    async def get_lead(self, lead_id: uuid.UUID, team_id: uuid.UUID) -> Lead | None:
        """Fetch a single lead by ID, scoped to team."""
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id, Lead.team_id == team_id))
        return result.scalar_one_or_none()

    # ── Create ────────────────────────────────────────────────────────────

    async def create_lead(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        data: LeadCreate,
    ) -> Lead:
        """Create a new lead, optionally creating nested company/contact."""
        # Optionally create company
        company_id = data.company_id
        if data.company_name and not company_id:
            company = Company(
                team_id=team_id,
                name=data.company_name,
                domain=data.company_domain,
                industry=data.company_industry,
            )
            self.db.add(company)
            await self.db.flush()
            company_id = company.id

        # Optionally create contact
        contact_id = data.contact_id
        if data.contact_email and not contact_id:
            contact = Contact(
                company_id=company_id,
                first_name=data.contact_first_name,
                last_name=data.contact_last_name,
                email=data.contact_email,
                title=data.contact_title,
                linkedin_url=data.contact_linkedin_url,
                full_name=f"{data.contact_first_name or ''} {data.contact_last_name or ''}".strip() or None,
            )
            self.db.add(contact)
            await self.db.flush()
            contact_id = contact.id

        lead = Lead(
            team_id=team_id,
            company_id=company_id,
            contact_id=contact_id,
            status=data.status,
            pipeline_stage=data.pipeline_stage,
            assigned_user_id=data.assigned_user_id,
            next_action=data.next_action,
            next_action_at=data.next_action_at,
        )
        self.db.add(lead)
        await self.db.flush()
        await self.db.refresh(lead)

        # Activity log
        await self._log_activity(
            team_id=team_id,
            user_id=user_id,
            lead_id=lead.id,
            action="lead.created",
            details={"status": lead.status, "pipeline_stage": lead.pipeline_stage},
        )

        return lead

    # ── Update ───────────────────────────────────────────────────────────

    async def update_lead(
        self,
        lead_id: uuid.UUID,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        data: LeadUpdate,
    ) -> Lead | None:
        """Update a lead's fields and log the change."""
        lead = await self.get_lead(lead_id, team_id)
        if not lead:
            return None

        old_status = lead.status
        old_stage = lead.pipeline_stage

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(lead, field, value)

        lead.updated_at = datetime.utcnow()
        self.db.add(lead)
        await self.db.flush()
        await self.db.refresh(lead)

        # Log activity
        changes = {}
        if data.status is not None and old_status != lead.status:
            changes["status"] = {"from": old_status, "to": lead.status}
        if data.pipeline_stage is not None and old_stage != lead.pipeline_stage:
            changes["pipeline_stage"] = {"from": old_stage, "to": lead.pipeline_stage}

        await self._log_activity(
            team_id=team_id,
            user_id=user_id,
            lead_id=lead.id,
            action="lead.updated",
            details=changes or {"fields_updated": list(update_data.keys())},
        )

        return lead

    # ── Delete (soft: sets status to suppressed) ─────────────────────────

    async def delete_lead(self, lead_id: uuid.UUID, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Soft-delete a lead by setting status to 'suppressed'."""
        lead = await self.get_lead(lead_id, team_id)
        if not lead:
            raise ValueError("Lead not found")

        lead.status = "suppressed"
        lead.pipeline_stage = "suppressed"
        lead.updated_at = datetime.utcnow()
        self.db.add(lead)
        await self.db.flush()

        await self._log_activity(
            team_id=team_id,
            user_id=user_id,
            lead_id=lead.id,
            action="lead.deleted",
            details={"previous_status": lead.status},
        )
