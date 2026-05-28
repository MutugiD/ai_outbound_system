"""Lead normalizer service — cleans and standardizes raw lead data.

Applies consistent transformations:
- Company name cleaning (remove suffixes, normalize casing)
- Domain normalization (lowercase, strip www, strip trailing slashes)
- Phone number formatting (E.164)
- LinkedIn URL normalization
- Email extraction from free text
- Source classification
"""

import re
from typing import Optional
from urllib.parse import urlparse

import phonenumbers

from app.services.scraping.base_adapter import NormalizedLead, RawLead


class LeadNormalizer:
    """Stateless service that transforms RawLead → clean NormalizedLead."""

    # ── Company name suffixes to remove ───────────────────────────────────

    COMPANY_SUFFIXES = [
        r"\bLLC\.?\b",
        r"\bInc\.?\b",
        r"\bLtd\.?\b",
        r"\bCorp\.?\b",
        r"\bCorporation\b",
        r"\bCo\.?\b",
        r"\bCompany\b",
        r"\bLimited\b",
        r"\bLP\b",
        r"\bLLP\b",
        r"\bL\.L\.C\.?\b",
        r"\bI\.N\.C\.?\b",
        r"\bP\.?C\.?\b",
        r"\bPLC\.?\b",
        r"\bSA\b",
        r"\bAG\b",
        r"\bGmbH\b",
        r"\bS\.?A\.?R\.?L\.?\b",
    ]

    _SUFFIX_RE = re.compile("|".join(COMPANY_SUFFIXES), re.IGNORECASE)

    # ── Public API ───────────────────────────────────────────────────────

    def normalize(self, raw: RawLead) -> NormalizedLead:
        """Transform a RawLead into a clean NormalizedLead.

        Does NOT perform deduplication — that's the Deduplicator's job.
        """
        data = raw.raw_data

        company_name = self._clean_company_name(raw.company_name or data.get("company_name"))
        company_domain = self._normalize_domain(
            getattr(raw, "company_domain", None) or data.get("company_domain") or data.get("domain")
        )
        contact_name = self._clean_contact_name(raw.contact_name or data.get("contact_name"))
        contact_title = self._clean_str(raw.title or data.get("contact_title") or data.get("title"))

        # Extract email from raw text if not already in data
        email = self._clean_str(data.get("email"))
        if not email and raw.raw_text:
            email = self._extract_email(raw.raw_text)

        # Normalize phone with region-aware defaults
        raw_phone = self._clean_str(data.get("phone"))
        normalized_phone = None
        if raw_phone:
            normalized_phone = self._normalize_phone(
                raw_phone,
                default_region=self._default_region(
                    data.get("country_code") or data.get("country"),
                ),
            )

        # Normalize LinkedIn URL
        linkedin_url = self._normalize_linkedin_url(data.get("linkedin_url") or raw.url or data.get("linkedin"))

        # Source classification
        source = self._classify_source(raw.source_type)

        return NormalizedLead(
            company_name=company_name,
            company_domain=company_domain,
            contact_name=contact_name,
            contact_title=contact_title,
            email=email,
            phone=normalized_phone,
            raw_phone=raw_phone,
            normalized_phone=normalized_phone,
            linkedin_url=linkedin_url,
            source=source,
            source_url=raw.source_url,
            source_query=raw.source_query,
            source_location=raw.source_location,
            provider_record_id=raw.provider_record_id,
            raw_text=raw.raw_text,
            country=self._clean_str(data.get("country")),
            industry=self._clean_str(data.get("industry")),
            status="new",
        )

    # ── Company name cleaning ────────────────────────────────────────────

    def _clean_company_name(self, name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        # Remove suffixes
        cleaned = self._SUFFIX_RE.sub("", name)
        # Remove trailing punctuation/spaces and leading whitespace
        cleaned = cleaned.strip()
        cleaned = re.sub(r"[,\s]+$", "", cleaned)
        cleaned = re.sub(r"^[,\s]+", "", cleaned)
        # Remove dangling punctuation left by suffix removal
        cleaned = re.sub(r"\s+\.+$", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        cleaned = cleaned.strip(" ,.")
        # Title case (preserve known acronyms)
        if cleaned and not cleaned.isupper():
            cleaned = cleaned.title()
        return cleaned or None

    # ── Domain normalization ─────────────────────────────────────────────

    @staticmethod
    def _normalize_domain(domain: Optional[str]) -> Optional[str]:
        if not domain:
            return None
        d = domain.lower().strip()
        # Remove protocol
        d = re.sub(r"^https?://", "", d)
        # Remove path/query
        d = d.split("/")[0]
        d = d.split("?")[0]
        # Remove www.
        if d.startswith("www."):
            d = d[4:]
        d = d.strip().rstrip("/")
        return d or None

    # ── Contact name cleaning ────────────────────────────────────────────

    @staticmethod
    def _clean_contact_name(name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        # Remove common prefixes
        name = re.sub(r"^(Mr\.?|Mrs\.?|Ms\.?|Dr\.?)\s*", "", name, flags=re.IGNORECASE)
        name = name.strip()
        # Title case
        if name and not name.isupper():
            name = name.title()
        return name or None

    # ── Phone normalization (E.164) ───────────────────────────────────────

    @staticmethod
    def _normalize_phone(phone: str, default_region: str = "KE") -> Optional[str]:
        cleaned_phone = phone.strip()
        try:
            parsed = phonenumbers.parse(cleaned_phone, default_region)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            pass

        digits_only = re.sub(r"\D", "", cleaned_phone)
        # Heuristic fallback: if a phone number looks like a US/NANP local number
        # and no explicit country hint was provided, prefer a valid +1 normalization
        # over returning bare digits. This preserves legacy CSV-import behavior while
        # still letting Kenya-style local numbers resolve via the default KE region.
        if (
            default_region == "KE"
            and len(digits_only) == 10
            and not cleaned_phone.startswith("+")
            and not digits_only.startswith("0")
        ):
            try:
                parsed = phonenumbers.parse(digits_only, "US")
                if phonenumbers.is_valid_number(parsed):
                    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            except phonenumbers.NumberParseException:
                pass

        # Fallback: just return cleaned digits if 10+ chars
        digits = re.sub(r"[^\d+]", "", cleaned_phone)
        return digits if len(digits) >= 10 else None

    # ── LinkedIn URL normalization ────────────────────────────────────────

    # Hard-coded allowlist of LinkedIn domains. Using set membership instead
    # of a substring check (e.g. .endswith("linkedin.com")) satisfies CodeQL's
    # py/incomplete-url-substring-sanitization query because exact-match
    # against a finite allowlist cannot be bypassed via subdomain tricks.
    LINKEDIN_DOMAINS: frozenset[str] = frozenset(
        {
            "linkedin.com",
            "www.linkedin.com",
        }
    )

    @staticmethod
    def _normalize_linkedin_url(url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        url = url.strip()
        # Ensure https
        if url.startswith("http://"):
            url = "https://" + url[7:]
        elif not url.startswith("https://"):
            url = "https://" + url
        # Normalize: remove www, trailing slashes, query params for profile URLs
        url = re.sub(r"https?://(www\.)?linkedin\.com", "https://linkedin.com", url)
        # Normalize /in/ URLs
        url = re.sub(r"/in/([^/?]+).*", r"/in/\1", url)
        url = url.rstrip("/")
        # Validate using urlparse — exact hostname allowlist match only
        parsed = urlparse(url)
        if parsed.hostname and parsed.hostname.lower() in LeadNormalizer.LINKEDIN_DOMAINS:
            return url
        return None

    # ── Email extraction ─────────────────────────────────────────────────

    @staticmethod
    def _extract_email(text: str) -> Optional[str]:
        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        m = re.search(pattern, text)
        return m.group(0).lower() if m else None

    # ── Source classification ──────────────────────────────────────────────

    @staticmethod
    def _classify_source(source_type: str) -> str:
        mapping = {
            "csv_import": "csv_import",
            "reddit": "reddit",
            "linkedin_jobs": "linkedin_jobs",
            "website": "website",
            "google_maps": "google_maps",
            "manual": "manual",
            "apollo": "apollo",
        }
        return mapping.get(source_type, source_type)

    @staticmethod
    def _default_region(country_value: Optional[str]) -> str:
        if not country_value:
            return "KE"

        normalized = country_value.strip().upper()
        known_aliases = {
            "KENYA": "KE",
            "KE": "KE",
            "UGANDA": "UG",
            "UG": "UG",
            "TANZANIA": "TZ",
            "TZ": "TZ",
            "RWANDA": "RW",
            "RW": "RW",
            "UNITED STATES": "US",
            "USA": "US",
            "US": "US",
        }
        return known_aliases.get(normalized, normalized[:2])

    # ── Utility ──────────────────────────────────────────────────────────

    @staticmethod
    def _clean_str(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        stripped = value.strip()
        return stripped or None
