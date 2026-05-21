"""Lead deduplication service — checks for existing leads using primary and
secondary key matching before persisting new records.

Primary keys (exact match): email, company_domain, linkedin_url
Secondary keys (fuzzy match): company_name + location, contact_name + company_name
"""

import difflib
import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.company import Company
from app.models.contact import Contact
from app.services.scraping.base_adapter import NormalizedLead


# ── Result model ────────────────────────────────────────────────────────────


@dataclass
class DeduplicationResult:
    """Outcome of a deduplication check."""

    is_duplicate: bool = False
    matched_lead_id: Optional[uuid.UUID] = None
    match_reason: str = ""
    confidence: float = 0.0
    merged_data: dict = field(default_factory=dict)


# ── Fuzzy matching threshold ─────────────────────────────────────────────────

FUZZY_THRESHOLD = 0.85


class LeadDeduplicator:
    """Async service for checking and resolving lead duplicates."""

    def __init__(self, db: AsyncSession, fuzzy_threshold: float = FUZZY_THRESHOLD):
        self.db = db
        self.fuzzy_threshold = fuzzy_threshold

    # ── Public API ───────────────────────────────────────────────────────

    async def check_duplicate(
        self, lead: NormalizedLead, team_id: uuid.UUID
    ) -> DeduplicationResult:
        """Check if *lead* is a duplicate of an existing record.

        Checks primary keys (exact) first, then secondary keys (fuzzy).
        Returns a DeduplicationResult indicating whether a match was found.
        """
        # ── Primary key checks ────────────────────────────────────────
        result = await self._check_primary_keys(lead, team_id)
        if result.is_duplicate:
            return result

        # ── Secondary (fuzzy) key checks ──────────────────────────────
        result = await self._check_secondary_keys(lead, team_id)
        return result

    async def merge_or_create(
        self, lead: NormalizedLead, team_id: uuid.UUID, user_id: uuid.UUID
    ) -> Lead:
        """If a duplicate exists, merge new data into it. Otherwise create a new lead.

        Returns the (merged or created) Lead DB object.
        """
        dedup = await self.check_duplicate(lead, team_id)

        if dedup.is_duplicate and dedup.matched_lead_id:
            return await self._merge_into_existing(lead, dedup, team_id, user_id)
        else:
            return await self._create_new_lead(lead, team_id, user_id)

    # ── Primary key checks ────────────────────────────────────────────────

    async def _check_primary_keys(
        self, lead: NormalizedLead, team_id: uuid.UUID
    ) -> DeduplicationResult:
        """Check exact matches on email, company_domain, and linkedin_url."""

        # Email match — check contacts
        if lead.email:
            stmt = (
                select(Contact)
                .where(Contact.email == lead.email.lower())
            )
            result = await self.db.execute(stmt)
            contact = result.scalar_one_or_none()
            if contact:
                # Find the lead for this contact
                lead_stmt = (
                    select(Lead)
                    .where(Lead.contact_id == contact.id, Lead.team_id == team_id)
                )
                lead_result = await self.db.execute(lead_stmt)
                existing = lead_result.scalar_one_or_none()
                if existing:
                    return DeduplicationResult(
                        is_duplicate=True,
                        matched_lead_id=existing.id,
                        match_reason="email_exact",
                        confidence=1.0,
                    )

        # Domain match — check companies
        if lead.company_domain:
            stmt = (
                select(Company)
                .where(Company.domain == lead.company_domain.lower(), Company.team_id == team_id)
            )
            result = await self.db.execute(stmt)
            company = result.scalar_one_or_none()
            if company:
                lead_stmt = (
                    select(Lead)
                    .where(Lead.company_id == company.id, Lead.team_id == team_id)
                )
                lead_result = await self.db.execute(lead_stmt)
                existing = lead_result.scalar_one_or_none()
                if existing:
                    return DeduplicationResult(
                        is_duplicate=True,
                        matched_lead_id=existing.id,
                        match_reason="company_domain_exact",
                        confidence=0.95,
                    )

        # LinkedIn URL match — check contacts
        if lead.linkedin_url:
            stmt = select(Contact).where(Contact.linkedin_url == lead.linkedin_url)
            result = await self.db.execute(stmt)
            contact = result.scalar_one_or_none()
            if contact:
                lead_stmt = (
                    select(Lead)
                    .where(Lead.contact_id == contact.id, Lead.team_id == team_id)
                )
                lead_result = await self.db.execute(lead_stmt)
                existing = lead_result.scalar_one_or_none()
                if existing:
                    return DeduplicationResult(
                        is_duplicate=True,
                        matched_lead_id=existing.id,
                        match_reason="linkedin_url_exact",
                        confidence=0.95,
                    )

        return DeduplicationResult(is_duplicate=False)

    # ── Secondary (fuzzy) key checks ───────────────────────────────────────

    async def _check_secondary_keys(
        self, lead: NormalizedLead, team_id: uuid.UUID
    ) -> DeduplicationResult:
        """Fuzzy-match on company_name and contact_name, scoped to team."""

        if not lead.company_name:
            return DeduplicationResult(is_duplicate=False)

        # Fetch companies with similar names
        stmt = select(Company).where(Company.team_id == team_id)
        result = await self.db.execute(stmt)
        companies = list(result.scalars().all())

        best_company = None
        best_score = 0.0

        for company in companies:
            score = self._fuzzy_ratio(lead.company_name.lower(), (company.name or "").lower())
            if score >= self.fuzzy_threshold and score > best_score:
                best_company = company
                best_score = score

        if best_company:
            # If we also have a contact name, verify that too
            if lead.contact_name:
                contact_stmt = (
                    select(Contact)
                    .where(Contact.company_id == best_company.id)
                )
                contact_result = await self.db.execute(contact_stmt)
                contacts = list(contact_result.scalars().all())

                for contact in contacts:
                    full_name = (contact.full_name or "").lower()
                    contact_ratio = self._fuzzy_ratio(lead.contact_name.lower(), full_name)
                    if contact_ratio >= self.fuzzy_threshold:
                        lead_stmt = (
                            select(Lead)
                            .where(Lead.company_id == best_company.id, Lead.team_id == team_id)
                            .where(Lead.contact_id == contact.id)
                        )
                        existing = (await self.db.execute(lead_stmt)).scalar_one_or_none()
                        if existing:
                            return DeduplicationResult(
                                is_duplicate=True,
                                matched_lead_id=existing.id,
                                match_reason="company_name+contact_name_fuzzy",
                                confidence=min(best_score, contact_ratio),
                            )

            # Company name match alone (without contact verification)
            lead_stmt = (
                select(Lead)
                .where(Lead.company_id == best_company.id, Lead.team_id == team_id)
            )
            lead_result = await self.db.execute(lead_stmt)
            existing = lead_result.scalar_one_or_none()
            if existing:
                return DeduplicationResult(
                    is_duplicate=True,
                    matched_lead_id=existing.id,
                    match_reason="company_name_fuzzy",
                    confidence=best_score,
                )

        return DeduplicationResult(is_duplicate=False)

    # ── Merge logic ────────────────────────────────────────────────────────

    async def _merge_into_existing(
        self,
        lead: NormalizedLead,
        dedup: DeduplicationResult,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Lead:
        """Merge new lead data into an existing lead, without losing data."""
        stmt = select(Lead).where(Lead.id == dedup.matched_lead_id, Lead.team_id == team_id)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            return await self._create_new_lead(lead, team_id, user_id)

        # Merge: only fill in empty fields, never overwrite existing data
        # We need to update related company/contact too
        if existing.company_id and lead.company_name:
            company_stmt = select(Company).where(Company.id == existing.company_id)
            company_result = await self.db.execute(company_stmt)
            company = company_result.scalar_one_or_none()
            if company:
                if not company.industry and lead.industry:
                    company.industry = lead.industry
                if not company.domain and lead.company_domain:
                    company.domain = lead.company_domain
                self.db.add(company)

        if existing.contact_id and (lead.contact_name or lead.email):
            contact_stmt = select(Contact).where(Contact.id == existing.contact_id)
            contact_result = await self.db.execute(contact_stmt)
            contact = contact_result.scalar_one_or_none()
            if contact:
                if not contact.email and lead.email:
                    contact.email = lead.email
                if not contact.phone and lead.phone:
                    contact.phone = lead.phone
                if not contact.linkedin_url and lead.linkedin_url:
                    contact.linkedin_url = lead.linkedin_url
                if not contact.title and lead.contact_title:
                    contact.title = lead.contact_title
                self.db.add(contact)

        self.db.add(existing)
        await self.db.flush()
        return existing

    async def _create_new_lead(
        self,
        lead: NormalizedLead,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Lead:
        """Create a brand-new Lead with associated Company and Contact."""
        # Create company
        company = None
        if lead.company_name or lead.company_domain:
            company = Company(
                team_id=team_id,
                name=lead.company_name or lead.company_domain or "Unknown",
                domain=lead.company_domain,
                industry=lead.industry,
            )
            self.db.add(company)
            await self.db.flush()

        # Create contact
        contact = None
        if lead.contact_name or lead.email:
            # Parse contact name
            name_parts = (lead.contact_name or "").split(None, 1)
            first_name = name_parts[0] if name_parts else None
            last_name = name_parts[1] if len(name_parts) > 1 else None

            contact = Contact(
                company_id=company.id if company else None,
                first_name=first_name,
                last_name=last_name,
                full_name=lead.contact_name,
                email=lead.email,
                title=lead.contact_title,
                phone=lead.phone,
                linkedin_url=lead.linkedin_url,
            )
            self.db.add(contact)
            await self.db.flush()

        # Create lead
        new_lead = Lead(
            team_id=team_id,
            company_id=company.id if company else None,
            contact_id=contact.id if contact else None,
            status=lead.status,
            pipeline_stage="new",
        )
        self.db.add(new_lead)
        await self.db.flush()

        return new_lead

    # ── Fuzzy matching helper ─────────────────────────────────────────────

    @staticmethod
    def _fuzzy_ratio(a: str, b: str) -> float:
        """Return similarity ratio using difflib.SequenceMatcher."""
        return difflib.SequenceMatcher(None, a, b).ratio()