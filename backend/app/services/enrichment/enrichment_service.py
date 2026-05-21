"""Enrichment orchestration service — coordinates the enrichment pipeline.

The pipeline:
  1. Contact enrichment (Apollo → Hunter fallback)
  2. Company enrichment (Apollo)
  3. Tech stack detection (BuiltWith with heuristic fallback)
  4. Email verification (Hunter)

Each step is independent; failure of one step does not block the others
(partial enrichment).  Results are stored in ``enrichment_records`` and the
lead's status is updated to ``enriched`` on success.
"""

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.company import Company
from app.models.contact import Contact
from app.models.enrichment import EnrichmentRecord
from app.models.job import Job
from app.services.activity_service import log_activity
from app.services.job_service import create_job, update_job_status
from app.services.enrichment.base_adapter import run_with_fallback
from app.services.enrichment.apollo_adapter import ApolloAdapter
from app.services.enrichment.hunter_adapter import HunterAdapter
from app.services.enrichment.builtwith_adapter import BuiltWithAdapter
from app.security_utils import sanitize_log

logger = logging.getLogger(__name__)

# ── Adapter singletons (stateless, safe to reuse) ─────────────────────────────

_apollo = ApolloAdapter()
_hunter = HunterAdapter()
_builtwith = BuiltWithAdapter()


class EnrichmentService:
    """Orchestrates the full enrichment pipeline for a lead."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Public API ──────────────────────────────────────────────────────────

    async def enrich_lead(self, lead_id: uuid.UUID) -> dict:
        """Run the full enrichment pipeline for a lead.

        Returns a summary dict with enrichment results for each step.
        """
        # Fetch lead and related records
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Fetch company/contact
        company: Optional[Company] = None
        contact: Optional[Contact] = None
        domain: Optional[str] = None

        if lead.company_id:
            result = await self.db.execute(select(Company).where(Company.id == lead.company_id))
            company = result.scalar_one_or_none()
            domain = company.domain if company else None

        if lead.contact_id:
            result = await self.db.execute(select(Contact).where(Contact.id == lead.contact_id))
            contact = result.scalar_one_or_none()

        # Create a Job record for tracking
        job = await create_job(self.db, job_type="lead_enrichment", lead_id=lead_id, company_id=lead.company_id)
        await update_job_status(self.db, job.id, "running")

        summary: dict = {"lead_id": str(lead_id), "steps": {}}
        errors: list[str] = []

        # ── Step 1: Contact enrichment (Apollo → Hunter fallback) ──────
        lead_data = {
            "company_domain": domain,
            "email": contact.email if contact else None,
            "first_name": contact.first_name if contact else None,
            "last_name": contact.last_name if contact else None,
            "title": contact.title if contact else None,
            "linkedin_url": contact.linkedin_url if contact else None,
        }
        try:
            contact_result = await run_with_fallback([_apollo, _hunter], "enrich_contact", lead_data)
            summary["steps"]["contact_enrichment"] = contact_result
            await self._store_enrichment(
                lead_id=lead_id,
                provider=contact_result.get("source", "fallback"),
                enrichment_type="contact",
                data=contact_result.get("data", {}),
                confidence=contact_result.get("confidence", 0),
            )
            await self._update_contact(contact, contact_result.get("data", {}))
        except Exception as exc:
            logger.error(
                "Contact enrichment failed for lead %s: %s", sanitize_log(str(lead_id)), sanitize_log(str(exc))
            )
            summary["steps"]["contact_enrichment"] = {"error": str(exc)}
            errors.append(f"contact: {exc}")

        # ── Step 2: Company enrichment (Apollo) ─────────────────────────
        if domain:
            try:
                company_result = await _apollo.enrich_company(domain)
                summary["steps"]["company_enrichment"] = company_result
                await self._store_enrichment(
                    lead_id=lead_id,
                    provider=company_result.get("source", "apollo"),
                    enrichment_type="company",
                    data=company_result.get("data", {}),
                    confidence=company_result.get("confidence", 0),
                )
                await self._update_company(company, company_result.get("data", {}))
            except Exception as exc:
                logger.error(
                    "Company enrichment failed for lead %s: %s", sanitize_log(str(lead_id)), sanitize_log(str(exc))
                )
                summary["steps"]["company_enrichment"] = {"error": str(exc)}
                errors.append(f"company: {exc}")
        else:
            summary["steps"]["company_enrichment"] = {"skipped": "No domain available"}

        # ── Step 3: Tech stack detection (BuiltWith) ─────────────────────
        if domain:
            try:
                tech_result = await _builtwith.detect_tech_stack(domain)
                summary["steps"]["tech_stack"] = tech_result
                await self._store_enrichment(
                    lead_id=lead_id,
                    provider=tech_result.get("source", "builtwith"),
                    enrichment_type="tech_stack",
                    data={"technologies": tech_result.get("data", [])},
                    confidence=tech_result.get("confidence", 0),
                )
            except Exception as exc:
                logger.error(
                    "Tech stack detection failed for lead %s: %s", sanitize_log(str(lead_id)), sanitize_log(str(exc))
                )
                summary["steps"]["tech_stack"] = {"error": str(exc)}
                errors.append(f"tech_stack: {exc}")
        else:
            summary["steps"]["tech_stack"] = {"skipped": "No domain available"}

        # ── Step 4: Email verification (Hunter) ──────────────────────────
        email = contact.email if contact else None
        if email:
            try:
                verify_result = await _hunter.verify_email(email)
                summary["steps"]["email_verification"] = verify_result
                if contact and verify_result.get("status"):
                    contact.email_status = verify_result["status"]
                    self.db.add(contact)
                    await self.db.flush()
            except Exception as exc:
                logger.error(
                    "Email verification failed for lead %s: %s", sanitize_log(str(lead_id)), sanitize_log(str(exc))
                )
                summary["steps"]["email_verification"] = {"error": str(exc)}
                errors.append(f"email_verify: {exc}")

        # ── Finalize ─────────────────────────────────────────────────────
        lead.status = "enriched"
        lead.updated_at = datetime.utcnow()
        self.db.add(lead)
        await self.db.flush()

        # Update job status
        job_status = "completed" if not errors else "completed"  # partial success still completed
        job_result = {"errors": errors} if errors else None
        await update_job_status(self.db, job.id, job_status, result=job_result)

        # Log activity
        await log_activity(
            self.db,
            team_id=lead.team_id,
            user_id=None,  # system action
            lead_id=lead_id,
            action="lead_enriched",
            details={"providers_used": list(summary["steps"].keys()), "errors": errors},
        )

        summary["status"] = "enriched" if not errors else "partially_enriched"
        summary["errors"] = errors if errors else None
        return summary

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _store_enrichment(
        self,
        lead_id: uuid.UUID,
        provider: str,
        enrichment_type: str,
        data: dict,
        confidence: float = 0.0,
    ) -> EnrichmentRecord:
        """Persist an enrichment record."""
        record = EnrichmentRecord(
            lead_id=lead_id,
            provider=provider,
            enrichment_type=enrichment_type,
            data=data,
            confidence=Decimal(str(round(confidence, 4))),
            enriched_at=datetime.utcnow(),
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def _update_contact(self, contact: Optional[Contact], data: dict) -> None:
        """Merge enrichment data into the contact record."""
        if not contact or not data:
            return
        field_map = {
            "email": "email",
            "email_status": "email_status",
            "phone": "phone",
            "title": "title",
            "seniority": "seniority",
            "department": "department",
            "linkedin_url": "linkedin_url",
            "location": "location",
        }
        for src_key, dst_key in field_map.items():
            value = data.get(src_key)
            if value and not getattr(contact, dst_key, None):
                setattr(contact, dst_key, value)
        contact.updated_at = datetime.utcnow()
        self.db.add(contact)
        await self.db.flush()

    async def _update_company(self, company: Optional[Company], data: dict) -> None:
        """Merge enrichment data into the company record."""
        if not company or not data:
            return
        field_map = {
            "company_name": "name",
            "company_industry": "industry",
            "company_sub_industry": "sub_industry",
            "company_size": "employee_count",
            "company_revenue": "revenue_estimate",
            "company_location": "location",
            "funding_status": "funding_status",
            "funding_total": "funding_total",
            "description": "description",
            "phone": "phone",
        }
        for src_key, dst_key in field_map.items():
            value = data.get(src_key)
            if value and not getattr(company, dst_key, None):
                setattr(company, dst_key, value)
        # Also set employee_count_range from employee_count if not already set
        if data.get("company_size") and not company.employee_count_range:
            size = data["company_size"]
            if size < 10:
                company.employee_count_range = "1-9"
            elif size < 50:
                company.employee_count_range = "10-49"
            elif size < 200:
                company.employee_count_range = "50-199"
            elif size < 1000:
                company.employee_count_range = "200-999"
            else:
                company.employee_count_range = "1000+"
        company.updated_at = datetime.utcnow()
        self.db.add(company)
        await self.db.flush()
