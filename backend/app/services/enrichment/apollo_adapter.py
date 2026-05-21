"""Apollo.io enrichment adapter — contact and company enrichment via Apollo APIs."""

import logging
from typing import Any

import httpx

from app.config import settings
from app.services.enrichment.base_adapter import BaseEnrichmentAdapter

logger = logging.getLogger(__name__)

APOLLO_BASE_URL = "https://api.apollo.io/v1"


class ApolloAdapter(BaseEnrichmentAdapter):
    """Enrichment adapter for Apollo.io (People + Organizations APIs).

    Rate limited to 100 req/min (free tier).  Requires ``settings.APOLLO_API_KEY``.
    """

    requests_per_minute = 100

    @property
    def provider_name(self) -> str:
        return "apollo"

    # ── Contact enrichment ────────────────────────────────────────────────

    async def enrich_contact(self, lead_data: dict) -> dict:
        """Enrich a contact using Apollo People Search / Mixed Search.

        Expects ``lead_data`` with at least one of: ``email``, ``first_name``
        + ``last_name`` + ``company_domain``.
        """
        api_key = settings.APOLLO_API_KEY
        if not api_key:
            logger.warning("Apollo API key not configured — skipping contact enrichment")
            return self._empty_result("APOLLO_API_KEY not configured")

        await self._rate_limit()

        # Build search params
        params: dict[str, Any] = {"api_key": api_key}
        if lead_data.get("email"):
            params["email"] = lead_data["email"]
        if lead_data.get("first_name"):
            params["first_name"] = lead_data["first_name"]
        if lead_data.get("last_name"):
            params["last_name"] = lead_data["last_name"]
        if lead_data.get("company_domain"):
            params["organization_domains[]"] = [lead_data["company_domain"]]
        if lead_data.get("title"):
            params["person_titles[]"] = [lead_data["title"]]

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{APOLLO_BASE_URL}/people/mixed_search",
                    json=params,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.warning("Apollo rate limit hit for contact enrichment")
                return self._empty_result("rate_limited")
            logger.error("Apollo contact enrichment HTTP error: %s", exc)
            return self._empty_result(str(exc))
        except Exception as exc:
            logger.error("Apollo contact enrichment error: %s", exc)
            return self._empty_result(str(exc))

        # Parse response
        people = data.get("people", [])
        if not people:
            return self._empty_result("No matching contact found")

        person = people[0]
        org = person.get("organization", {}) or {}

        enriched = {
            "email": person.get("email"),
            "email_status": person.get("email_status", "unknown"),
            "phone": person.get("phone_numbers", [None])[0] if person.get("phone_numbers") else None,
            "title": person.get("title"),
            "seniority": person.get("seniority"),
            "department": person.get("departments", [None])[0] if person.get("departments") else None,
            "linkedin_url": person.get("linkedin_url"),
            "location": person.get("city") or person.get("state") or person.get("country"),
            "company_name": org.get("name"),
            "company_size": org.get("employee_count"),
            "company_industry": org.get("industry"),
            "company_revenue": org.get("estimated_arr_usd"),
            "company_location": org.get("city") or org.get("state") or org.get("country"),
        }

        # Confidence based on email status
        conf_map = {"verified": 0.95, "likely": 0.75, "unlikely": 0.4, "unknown": 0.5}
        confidence = conf_map.get(person.get("email_status", "unknown"), 0.5)

        return {
            "data": {k: v for k, v in enriched.items() if v is not None},
            "confidence": confidence,
            "source": self.provider_name,
        }

    # ── Company enrichment ───────────────────────────────────────────────

    async def enrich_company(self, domain: str) -> dict:
        """Enrich a company using the Apollo Organizations API."""
        api_key = settings.APOLLO_API_KEY
        if not api_key:
            logger.warning("Apollo API key not configured — skipping company enrichment")
            return self._empty_result("APOLLO_API_KEY not configured")

        await self._rate_limit()

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{APOLLO_BASE_URL}/organizations/enrich",
                    params={"api_key": api_key, "domain": domain},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                return self._empty_result("rate_limited")
            logger.error("Apollo company enrichment HTTP error: %s", exc)
            return self._empty_result(str(exc))
        except Exception as exc:
            logger.error("Apollo company enrichment error: %s", exc)
            return self._empty_result(str(exc))

        org = data.get("organization", data)
        if not org:
            return self._empty_result("No matching organization found")

        enriched = {
            "company_name": org.get("name"),
            "domain": domain,
            "company_size": org.get("employee_count"),
            "company_industry": org.get("industry"),
            "company_sub_industry": org.get("sub_industry"),
            "company_revenue": org.get("estimated_arr_usd"),
            "company_location": org.get("city") or org.get("state") or org.get("country"),
            "funding_status": org.get("funding_stage"),
            "funding_total": org.get("total_funding_usd"),
            "linkedin_url": org.get("linkedin_url"),
            "phone": org.get("phone"),
            "description": org.get("short_description") or org.get("description"),
        }

        return {
            "data": {k: v for k, v in enriched.items() if v is not None},
            "confidence": 0.85,
            "source": self.provider_name,
        }

    # ── Tech stack detection ───────────────────────────────────────────────

    async def detect_tech_stack(self, domain: str) -> dict:
        """Apollo does not provide tech stack detection natively.

        Returns an empty result so the fallback chain can delegate to BuiltWith.
        """
        return self._empty_tech_result("Apollo does not provide tech stack data")