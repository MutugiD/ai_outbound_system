"""BuiltWith / Wappalyzer-style tech stack detection adapter.

Uses the BuiltWith API when available, and falls back to heuristic HTML
analysis (response headers + content patterns) when the API key is absent
or the request fails.
"""

import logging
import re
from typing import Any

import httpx

from app.config import settings
from app.services.enrichment.base_adapter import BaseEnrichmentAdapter

logger = logging.getLogger(__name__)

BUILTWITH_BASE_URL = "https://api.builtwith.com/free"

# ── Heuristic tech detection patterns ──────────────────────────────────────────

TECH_PATTERNS: dict[str, list[dict[str, Any]]] = {
    "CRM": [
        {"pattern": r"hubspot\.com/js", "name": "HubSpot"},
        {"pattern": r"salesforce\.com", "name": "Salesforce"},
        {"pattern": r"pardot\.com", "name": "Pardot"},
        {"pattern": r"activecampaign\.com", "name": "ActiveCampaign"},
        {"pattern": r"pipelinedeals\.com", "name": "PipelineDeals"},
    ],
    "Marketing": [
        {"pattern": r"gtm\.js|googletagmanager\.com", "name": "Google Tag Manager"},
        {"pattern": r"mailchimp\.com|mc\.js", "name": "Mailchimp"},
        {"pattern": r"klaviyo\.com", "name": "Klaviyo"},
        {"pattern": r"convertkit\.com", "name": "ConvertKit"},
        {"pattern": r"segment\.com|analytics\.js", "name": "Segment"},
    ],
    "Analytics": [
        {"pattern": r"google-analytics\.com|gtag|ga\(|_gaq", "name": "Google Analytics"},
        {"pattern": r"mixpanel\.com", "name": "Mixpanel"},
        {"pattern": r"amplitude\.com", "name": "Amplitude"},
        {"pattern": r"hotjar\.com", "name": "Hotjar"},
        {"pattern": r"clarity\.ms", "name": "Microsoft Clarity"},
    ],
    "Chatbot": [
        {"pattern": r"intercom\.io|intercomcdn\.com", "name": "Intercom"},
        {"pattern": r"drift\.com", "name": "Drift"},
        {"pattern": r"crisp\.chat", "name": "Crisp"},
        {"pattern": r"zendesk\.com/widget", "name": "Zendesk Chat"},
        {"pattern": r"tawk\.to", "name": "Tawk.to"},
        {"pattern": r"freshchat\.com", "name": "Freshchat"},
    ],
    "Booking": [
        {"pattern": r"calendly\.com", "name": "Calendly"},
        {"pattern": r"cal\.com|cal\.com", "name": "Cal.com"},
        {"pattern": r" calendly\.com|acuityscheduling\.com", "name": "Acuity Scheduling"},
        {"pattern": r"youcanbook\.me", "name": "YouCanBook.me"},
        {"pattern": r"meetings\.hubspot\.com", "name": "HubSpot Meetings"},
    ],
    "Payment": [
        {"pattern": r"stripe\.com|stripe\.js", "name": "Stripe"},
        {"pattern": r"paypal\.com|paypalobjects\.com", "name": "PayPal"},
        {"pattern": r"checkout\.shopify\.com", "name": "Shopify Payments"},
        {"pattern": r"squareup\.com", "name": "Square"},
    ],
    "CMS": [
        {"pattern": r"wp-content|wp-includes|wordpress", "name": "WordPress"},
        {"pattern": r"shopify\.com|shopify\.cloud", "name": "Shopify"},
        {"pattern": r"wix\.com|wixstatic\.com", "name": "Wix"},
        {"pattern": r"squarespace\.com", "name": "Squarespace"},
        {"pattern": r"webflow\.com|webflow\.io", "name": "Webflow"},
        {"pattern": r"ghost\.org", "name": "Ghost"},
        {"pattern": r"contentful\.com", "name": "Contentful"},
    ],
    "Ecommerce": [
        {"pattern": r"shopify\.com|shopify\.cloud|myshopify\.com", "name": "Shopify"},
        {"pattern": r"woocommerce", "name": "WooCommerce"},
        {"pattern": r"magento", "name": "Magento"},
        {"pattern": r"bigcommerce\.com", "name": "BigCommerce"},
    ],
}

HEADER_PATTERNS: dict[str, list[dict[str, Any]]] = {
    "CMS": [
        {"header": "x-powered-by", "pattern": r"express", "name": "Express"},
        {"header": "x-generator", "pattern": r"wordpress", "name": "WordPress"},
        {"header": "server", "pattern": r"cloudflare", "name": "Cloudflare"},
    ],
    "Analytics": [
        {"header": "server", "pattern": r"nginx", "name": "Nginx"},
    ],
}


class BuiltWithAdapter(BaseEnrichmentAdapter):
    """Tech stack detection via BuiltWith API with heuristic fallback.

    Uses ``settings.BUILTWITH_API_KEY`` for the BuiltWith API.  If the key
    is absent or the API call fails, falls back to heuristic detection by
    fetching the website's HTML and matching known scripts/headers.
    """

    requests_per_minute = 20

    @property
    def provider_name(self) -> str:
        return "builtwith"

    # ── Contact enrichment (not supported) ──────────────────────────────────

    async def enrich_contact(self, lead_data: dict) -> dict:
        """BuiltWith does not provide contact enrichment."""
        return self._empty_result("BuiltWith does not provide contact data")

    # ── Company enrichment (basic from domain data) ────────────────────────

    async def enrich_company(self, domain: str) -> dict:
        """BuiltWith returns some company meta alongside tech data.

        Delegates to detect_tech_stack and extracts company-level info.
        """
        tech_result = await self.detect_tech_stack(domain)
        return {
            "data": {
                "domain": domain,
                "technologies": tech_result.get("data", []),
            },
            "confidence": tech_result.get("confidence", 0.0),
            "source": self.provider_name,
        }

    # ── Tech stack detection ───────────────────────────────────────────────

    async def detect_tech_stack(self, domain: str) -> dict:
        """Detect technologies used by a website.

        Tries BuiltWith API first, then falls back to heuristic detection.
        """
        api_key = settings.BUILTWITH_API_KEY
        if api_key:
            result = await self._detect_via_api(domain, api_key)
            if result.get("confidence", 0) > 0:
                return result
            logger.info("BuiltWith API returned no data for %s, falling back to heuristics", domain)

        # Heuristic fallback
        return await self._detect_via_heuristics(domain)

    async def _detect_via_api(self, domain: str, api_key: str) -> dict:
        """Query BuiltWith API for domain technology data."""
        await self._rate_limit()

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{BUILTWITH_BASE_URL}/{api_key}",
                    params={"LOOKUP": domain},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                return self._empty_tech_result("rate_limited")
            logger.error("BuiltWith API HTTP error for %s: %s", domain, exc)
            return self._empty_tech_result(str(exc))
        except Exception as exc:
            logger.error("BuiltWith API error for %s: %s", domain, exc)
            return self._empty_tech_result(str(exc))

        # Parse BuiltWith response — group by category
        technologies: list[str] = []
        categories: dict[str, list[str]] = {}

        # BuiltWith free API returns Groups array
        groups = data.get("Groups", [])
        for group in groups:
            cat = group.get("Name", "unknown")
            cat = self._normalize_category(cat)
            for tech in group.get("Technologies", []):
                tech_name = tech.get("Name", "")
                if tech_name:
                    technologies.append(tech_name)
                    categories.setdefault(cat, []).append(tech_name)

        if not technologies:
            return self._empty_tech_result("No technologies found via BuiltWith")

        return {
            "data": technologies,
            "categories": categories,
            "confidence": 0.9,
            "source": self.provider_name,
        }

    async def _detect_via_heuristics(self, domain: str) -> dict:
        """Fetch homepage HTML and detect technologies via pattern matching."""
        url = f"https://{domain}"
        html_content = ""
        response_headers: dict[str, str] = {}

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url)
                html_content = resp.text
                response_headers = dict(resp.headers)
        except Exception as exc:
            logger.warning("Failed to fetch %s for heuristic detection: %s", domain, exc)
            # Still try with http
            try:
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    resp = await client.get(f"http://{domain}")
                    html_content = resp.text
                    response_headers = dict(resp.headers)
            except Exception as exc2:
                logger.warning("Failed to fetch %s (http fallback): %s", domain, exc2)
                return self._empty_tech_result(f"Could not fetch website: {exc2}")

        html_lower = html_content.lower()
        technologies: list[str] = []
        categories: dict[str, list[str]] = {}

        # Check HTML content patterns
        for category, patterns in TECH_PATTERNS.items():
            for pat_info in patterns:
                if re.search(pat_info["pattern"], html_lower):
                    technologies.append(pat_info["name"])
                    categories.setdefault(category, []).append(pat_info["name"])

        # Check response header patterns
        headers_lower = {k.lower(): v.lower() for k, v in response_headers.items()}
        for category, patterns in HEADER_PATTERNS.items():
            for pat_info in patterns:
                header_val = headers_lower.get(pat_info["header"].lower(), "")
                if re.search(pat_info["pattern"], header_val):
                    if pat_info["name"] not in technologies:
                        technologies.append(pat_info["name"])
                        categories.setdefault(category, []).append(pat_info["name"])

        if not technologies:
            return self._empty_tech_result("No technologies detected via heuristics")

        return {
            "data": technologies,
            "categories": categories,
            "confidence": 0.6,  # lower confidence for heuristic detection
            "source": f"{self.provider_name}_heuristic",
        }

    @staticmethod
    def _normalize_category(bw_category: str) -> str:
        """Map BuiltWith category names to our canonical categories."""
        mapping = {
            "Analytics": "Analytics",
            "Advertising": "Marketing",
            "CMS": "CMS",
            "CRM Software": "CRM",
            "Ecommerce": "Ecommerce",
            "Widgets": "Chatbot",
            "JavaScript Libraries": "CMS",
            "Marketing Automation": "Marketing",
            "Payment Processing": "Payment",
            "Scheduling": "Booking",
        }
        return mapping.get(bw_category, bw_category)