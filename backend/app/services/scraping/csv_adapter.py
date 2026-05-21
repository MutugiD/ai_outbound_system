"""CSV import adapter — reads a CSV file and maps it to NormalizedLead objects.

Supports both file-path strings and FastAPI UploadFile objects. Column name
variations are handled by the COLUMN_ALIASES mapping, which maps canonical
NormalizedLead fields to common header names found in real-world CSVs.
"""

import csv
import io
import logging
from pathlib import Path
from typing import Any, Optional, Union

from fastapi import UploadFile

from app.services.scraping.base_adapter import BaseLeadSourceAdapter, NormalizedLead, RawLead
from app.security_utils import safe_path

logger = logging.getLogger(__name__)

# ── Column name aliases ────────────────────────────────────────────────────
# Keys are canonical NormalizedLead field names; values are alternative column
# headers that might appear in a user-supplied CSV.

COLUMN_ALIASES: dict[str, list[str]] = {
    "company_name": [
        "Company",
        "company_name",
        "Organization",
        "organization",
        "Company Name",
        "CompanyName",
        "company",
        "employer",
        "Employer",
        "Org",
        "org",
        "Business",
        "business",
    ],
    "company_domain": [
        "Domain",
        "company_domain",
        "Website",
        "website",
        "domain",
        "URL",
        "url",
        "Company Website",
        "company_website",
        "Web",
        "web",
    ],
    "contact_name": [
        "Contact",
        "contact_name",
        "Name",
        "Full Name",
        "full_name",
        "Contact Name",
        "ContactName",
        "Person",
        "person",
        "name",
    ],
    "contact_title": ["Title", "contact_title", "Job Title", "job_title", "Role", "role", "Position", "position"],
    "email": ["Email", "email", "E-mail", "EmailAddress", "email_address", "Work Email", "work_email", "Email Address"],
    "phone": [
        "Phone",
        "phone",
        "Phone Number",
        "phone_number",
        "Telephone",
        "telephone",
        "Tel",
        "tel",
        "Mobile",
        "mobile",
    ],
    "linkedin_url": ["LinkedIn", "linkedin_url", "LinkedIn URL", "linkedin", "LinkedIn Profile", "linkedin_profile"],
    "country": ["Country", "country", "Nation", "nation", "Location", "location", "Country/Region"],
    "industry": ["Industry", "industry", "Sector", "sector", "Vertical", "vertical", "Industry Category"],
}


class CSVAdapter(BaseLeadSourceAdapter):
    """Import leads from a CSV file."""

    @property
    def source_name(self) -> str:
        return "csv_import"

    # ── Public interface ─────────────────────────────────────────────────

    async def search(self, query: dict[str, Any]) -> list[RawLead]:
        """Read a CSV and return RawLead objects for each row.

        Parameters
        ----------
        query : dict
            Must contain one of:
            - file_path: str — local filesystem path to the CSV
            - file: UploadFile — FastAPI upload object

            Optional:
            - delimiter: str (default ",")
            - encoding: str (default "utf-8")
        """
        file_input: Union[str, UploadFile, None] = query.get("file") or query.get("file_path")
        if file_input is None:
            raise ValueError("CSVAdapter requires 'file_path' or 'file' in query")

        delimiter = query.get("delimiter", ",")
        encoding = query.get("encoding", "utf-8")

        if isinstance(file_input, (str, Path)):
            return await self._read_from_path(str(file_input), delimiter, encoding)
        elif isinstance(file_input, UploadFile):
            return await self._read_from_upload(file_input, delimiter, encoding)
        else:
            raise TypeError(f"Unsupported file input type: {type(file_input)}")

    async def extract(self, raw: RawLead) -> NormalizedLead:
        """Map a RawLead (row dict) to a NormalizedLead.

        The heavy lifting (column alias mapping) was already done in search().
        Here we just transfer fields and apply light cleaning.
        """
        data = raw.raw_data
        return NormalizedLead(
            company_name=self._clean_str(data.get("company_name")),
            company_domain=self._clean_str(data.get("company_domain")),
            contact_name=self._clean_str(data.get("contact_name")),
            contact_title=self._clean_str(data.get("contact_title")),
            email=self._clean_str(data.get("email")),
            phone=self._clean_str(data.get("phone")),
            linkedin_url=self._clean_str(data.get("linkedin_url")),
            source=self.source_name,
            source_url=raw.source_url,
            raw_text=raw.raw_text,
            country=self._clean_str(data.get("country")),
            industry=self._clean_str(data.get("industry")),
            status="new",
        )

    async def validate(self, lead: NormalizedLead) -> bool:
        """A lead is valid if at least one identifying field is populated."""
        return any(
            [
                lead.company_name,
                lead.company_domain,
                lead.email,
                lead.linkedin_url,
            ]
        )

    # ── Internals ─────────────────────────────────────────────────────────

    async def _read_from_path(self, path: str, delimiter: str, encoding: str) -> list[RawLead]:
        # Prevent path traversal: use safe_path() to construct a clean path
        # inside the hardcoded SAFE_CSV_DIR, breaking the taint chain.
        # This ensures the final filesystem path is built from a trusted
        # directory constant plus a sanitised basename, not from user input.
        safe_file_path = safe_path(path)
        with open(safe_file_path, newline="", encoding=encoding) as fh:
            content = fh.read()
        return self._parse_csv_string(content, delimiter)

    async def _read_from_upload(self, upload: UploadFile, delimiter: str, encoding: str) -> list[RawLead]:
        content = await upload.read()
        text = content.decode(encoding)
        return self._parse_csv_string(text, delimiter)

    def _parse_csv_string(self, text: str, delimiter: str) -> list[RawLead]:
        """Parse CSV text and return a list of RawLead objects, deduplicating
        rows that map to the same (email or company_domain + contact_name)."""
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError("CSV file appears empty or has no headers")

        # Build reverse lookup: alias -> canonical field
        alias_map: dict[str, str] = {}
        for canonical, aliases in COLUMN_ALIASES.items():
            for alias in aliases:
                alias_map[alias.lower().strip()] = canonical

        # Map actual headers
        header_to_canonical: dict[str, str] = {}
        for header in reader.fieldnames:
            key = header.strip().lower()
            if key in alias_map:
                header_to_canonical[header.strip()] = alias_map[key]

        raw_leads: list[RawLead] = []
        seen_keys: set[tuple] = set()

        for row_idx, row in enumerate(reader, start=2):  # header is row 1
            mapped: dict[str, Optional[str]] = {}
            for header, canonical in header_to_canonical.items():
                val = row.get(header, "").strip() if row.get(header) else None
                mapped[canonical] = val or None

            # Dedup key: email if present, else (company_domain + contact_name)
            email = (mapped.get("email") or "").strip().lower()
            domain = (mapped.get("company_domain") or "").strip().lower()
            name = (mapped.get("contact_name") or "").strip().lower()
            dedup_key = (email,) if email else (domain, name)
            if dedup_key in seen_keys:
                logger.debug("Skipping duplicate CSV row %d: %s", row_idx, dedup_key)
                continue
            seen_keys.add(dedup_key)

            raw_lead = RawLead(
                source_type=self.source_name,
                source_url=mapped.get("company_domain"),
                raw_text=None,
                raw_data={k: v for k, v in mapped.items() if v is not None},
                company_name=mapped.get("company_name"),
                contact_name=mapped.get("contact_name"),
                title=mapped.get("contact_title"),
                url=mapped.get("linkedin_url") or mapped.get("company_domain"),
                scraped_at=__import__("datetime").datetime.utcnow(),
            )
            raw_leads.append(raw_lead)

        logger.info("CSVAdapter parsed %d leads from CSV", len(raw_leads))
        return raw_leads

    @staticmethod
    def _clean_str(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        stripped = value.strip()
        return stripped or None
