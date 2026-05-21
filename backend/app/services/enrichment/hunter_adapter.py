"""Hunter.io enrichment adapter — email finding and verification."""

import logging
from typing import Any

import httpx

from app.config import settings
from app.services.enrichment.base_adapter import BaseEnrichmentAdapter

logger = logging.getLogger(__name__)

HUNTER_BASE_URL = "https://api.hunter.io/v2"


class HunterAdapter(BaseEnrichmentAdapter):
    """Enrichment adapter for Hunter.io (email finder + verifier).

    Rate limited to 25 req/month on free tier, 1000/mo on starter.
    Requires ``settings.HUNTER_API_KEY``.
    """

    # Conservative: 10/min to avoid burning monthly quota too fast
    requests_per_minute = 10

    @property
    def provider_name(self) -> str:
        return "hunter"

    # ── Contact enrichment (email finder) ──────────────────────────────────

    async def enrich_contact(self, lead_data: dict) -> dict:
        """Find and verify an email address using Hunter.io Email Finder.

        Requires ``first_name``, ``last_name``, and ``company_domain`` (or ``company_name``).
        """
        api_key = settings.HUNTER_API_KEY
        if not api_key:
            logger.warning("Hunter API key not configured — skipping contact enrichment")
            return self._empty_result("HUNTER_API_KEY not configured")

        first_name = lead_data.get("first_name", "")
        last_name = lead_data.get("last_name", "")
        domain = lead_data.get("company_domain", "")
        company_name = lead_data.get("company_name", "")

        if not (first_name and last_name):
            return self._empty_result("Need first_name and last_name for email finder")

        if not domain and not company_name:
            return self._empty_result("Need company_domain or company_name for email finder")

        await self._rate_limit()

        params: dict[str, Any] = {
            "api_key": api_key,
            "first_name": first_name,
            "last_name": last_name,
        }
        if domain:
            params["domain"] = domain
        elif company_name:
            params["company"] = company_name

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{HUNTER_BASE_URL}/email-finder", params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.warning("Hunter rate limit hit for email finder")
                return self._empty_result("rate_limited")
            logger.error("Hunter email finder HTTP error: %s", exc)
            return self._empty_result(str(exc))
        except Exception as exc:
            logger.error("Hunter email finder error: %s", exc)
            return self._empty_result(str(exc))

        email_data = data.get("data", {})
        if not email_data:
            return self._empty_result("No email found")

        enriched = {
            "email": email_data.get("email"),
            "email_status": self._map_email_status(email_data.get("result")),
            "email_score": email_data.get("score"),  # Hunter confidence score
            "first_name": email_data.get("first_name"),
            "last_name": email_data.get("last_name"),
            "linkedin_url": email_data.get("linkedin"),
            "phone": email_data.get("phone"),
        }

        # If email was found, also verify it
        email = enriched.get("email")
        if email:
            verify_result = await self._verify_email(email, api_key)
            if verify_result and "error" not in verify_result:
                enriched["email_status"] = verify_result.get("data", {}).get("result", enriched["email_status"])
                enriched["email_verification_confidence"] = verify_result.get("data", {}).get("score")

        confidence = (email_data.get("score") or 0) / 100.0

        return {
            "data": {k: v for k, v in enriched.items() if v is not None},
            "confidence": confidence,
            "source": self.provider_name,
        }

    # ── Company enrichment (domain search) ──────────────────────────────────

    async def enrich_company(self, domain: str) -> dict:
        """Get company email pattern and general info from Hunter domain search."""
        api_key = settings.HUNTER_API_KEY
        if not api_key:
            return self._empty_result("HUNTER_API_KEY not configured")

        await self._rate_limit()

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{HUNTER_BASE_URL}/domain-search",
                    params={"api_key": api_key, "domain": domain, "limit": 10},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                return self._empty_result("rate_limited")
            logger.error("Hunter domain search HTTP error: %s", exc)
            return self._empty_result(str(exc))
        except Exception as exc:
            logger.error("Hunter domain search error: %s", exc)
            return self._empty_result(str(exc))

        domain_data = data.get("data", {})
        meta = domain_data.get("meta", {})

        enriched = {
            "domain": domain,
            "email_pattern": meta.get("pattern"),
            "organization": domain_data.get("organization"),
        }

        # Flatten email results for key contacts
        emails = domain_data.get("emails", [])
        if emails:
            enriched["sample_emails"] = [
                {
                    "email": e.get("value"),
                    "type": e.get("type"),
                    "first_name": e.get("first_name"),
                    "last_name": e.get("last_name"),
                    "position": e.get("position"),
                    "seniority": e.get("seniority"),
                    "department": e.get("department"),
                }
                for e in emails[:5]
                if e.get("value")
            ]

        return {
            "data": {k: v for k, v in enriched.items() if v is not None},
            "confidence": 0.7,
            "source": self.provider_name,
        }

    # ── Tech stack detection ───────────────────────────────────────────────

    async def detect_tech_stack(self, domain: str) -> dict:
        """Hunter does not detect tech stacks. Returns empty result."""
        return self._empty_tech_result("Hunter does not detect tech stacks")

    # ── Email verification ──────────────────────────────────────────────────

    async def verify_email(self, email: str) -> dict:
        """Verify an email address using Hunter.io Email Verifier.

        Returns a dict with:
            - ``email``: the verified address
            - ``status``: deliverable / undeliverable / risky / unknown
            - ``confidence``: Hunter confidence score (0-1)
            - ``source``: provider name
        """
        api_key = settings.HUNTER_API_KEY
        if not api_key:
            return {
                "email": email,
                "status": "unknown",
                "confidence": 0.0,
                "source": self.provider_name,
                "error": "HUNTER_API_KEY not configured",
            }

        result = await self._verify_email(email, api_key)
        if result and "error" not in result:
            data = result.get("data", {})
            return {
                "email": email,
                "status": self._map_email_status(data.get("result")),
                "confidence": (data.get("score") or 0) / 100.0,
                "source": self.provider_name,
            }
        return {
            "email": email,
            "status": "unknown",
            "confidence": 0.0,
            "source": self.provider_name,
            "error": result.get("error", "Verification failed") if result else "No response",
        }

    async def _verify_email(self, email: str, api_key: str) -> dict | None:
        """Internal: call Hunter email verifier API."""
        await self._rate_limit()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{HUNTER_BASE_URL}/email-verifier",
                    params={"api_key": api_key, "email": email},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.warning("Hunter rate limit hit for email verification")
            else:
                logger.error("Hunter email verifier HTTP error: %s", exc)
            return None
        except Exception as exc:
            logger.error("Hunter email verifier error: %s", exc)
            return None

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _map_email_status(hunter_result: str | None) -> str:
        """Map Hunter.io email result string to our canonical statuses."""
        mapping = {
            "deliverable": "verified",
            "undeliverable": "invalid",
            "risky": "risky",
            "unknown": "unverified",
        }
        return mapping.get(hunter_result, "unverified")
