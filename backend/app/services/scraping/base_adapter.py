"""Base adapter defining the contract for all lead source adapters.

RawLead and NormalizedLead are Pydantic models (NOT database models) used as
intermediate transport objects between scraping, normalization, and persistence.
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Pydantic transport models ──────────────────────────────────────────────


class RawLead(BaseModel):
    """Unprocessed lead data as extracted from a source (before normalization)."""

    source_type: str  # csv_import, reddit, linkedin_jobs, website, etc.
    source_url: Optional[str] = None
    source_query: Optional[str] = None
    source_location: Optional[str] = None
    provider_record_id: Optional[str] = None
    raw_text: Optional[str] = None
    raw_data: dict[str, Any] = Field(default_factory=dict)
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class NormalizedLead(BaseModel):
    """Clean, validated lead data ready for deduplication and persistence."""

    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    contact_name: Optional[str] = None
    contact_title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    raw_phone: Optional[str] = None
    normalized_phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    source: str = "manual"
    source_url: Optional[str] = None
    source_query: Optional[str] = None
    source_location: Optional[str] = None
    provider_record_id: Optional[str] = None
    raw_text: Optional[str] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    status: str = "new"


# ── Adapter abstract base class ─────────────────────────────────────────────


class BaseLeadSourceAdapter(ABC):
    """Abstract base class every lead source adapter must implement.

    Lifecycle:
        1. search(query) -> list[RawLead]        — fetch raw data from source
        2. extract(raw) -> NormalizedLead        — map & normalize a single record
        3. validate(normalized) -> bool           — sanity-check before persisting

    Adapters are stateless; they receive configuration at construction time and
    should not hold mutable state between calls.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable identifier for this source (e.g. 'csv_import', 'reddit')."""

    @abstractmethod
    async def search(self, query: dict[str, Any]) -> list[RawLead]:
        """Search the source for leads matching *query* and return raw results.

        Parameters
        ----------
        query : dict
            Source-specific search parameters. Common keys:
            - keywords: str            — free-text search terms
            - location: str            — geographic filter
            - limit: int               — max results to return
            - subreddits: list[str]    — (Reddit) subreddit names
            - file_path: str           — (CSV) path to CSV file
            - domain: str              — (Website) domain to crawl

        Returns
        -------
        list[RawLead]
            Unprocessed records from the source.
        """

    @abstractmethod
    async def extract(self, raw: RawLead) -> NormalizedLead:
        """Map a single RawLead into a NormalizedLead.

        Subclasses should override this when the default field mapping is
        insufficient (e.g., extracting a domain from a URL, cleaning titles).

        Parameters
        ----------
        raw : RawLead
            One raw record produced by :meth:`search`.

        Returns
        -------
        NormalizedLead
            Clean, validated lead data.
        """

    @abstractmethod
    async def validate(self, lead: NormalizedLead) -> bool:
        """Return True if *lead* has enough information to be persisted.

        Minimum requirement: at least one of (company_name, company_domain,
        email, linkedin_url, phone) must be populated.
        """

    # ── Convenience runner ───────────────────────────────────────────────

    async def run(self, query: dict[str, Any]) -> list[tuple[RawLead, NormalizedLead]]:
        """Execute the full search → extract → validate pipeline.

        Returns only (raw, normalized) pairs that pass validation.
        """
        raws = await self.search(query)
        results: list[tuple[RawLead, NormalizedLead]] = []
        for raw in raws:
            normalized = await self.extract(raw)
            if await self.validate(normalized):
                results.append((raw, normalized))
        return results
