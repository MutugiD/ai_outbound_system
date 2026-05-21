"""Website crawler adapter — uses httpx + Trafilatura for clean text extraction.

Crawls common company pages (homepage, about, services, pricing, careers, contact)
and returns both raw HTML and clean article text for each page.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

from app.services.scraping.base_adapter import BaseLeadSourceAdapter, NormalizedLead, RawLead

logger = logging.getLogger(__name__)

# ── Default crawl paths ────────────────────────────────────────────────────

DEFAULT_PATHS: list[str] = [
    "/",  # homepage
    "/about",
    "/about-us",
    "/services",
    "/solutions",
    "/pricing",
    "/careers",
    "/jobs",
    "/contact",
    "/team",
]

# ── Rate limiter ───────────────────────────────────────────────────────────


class _DomainRateLimiter:
    """Per-domain rate limiter ensuring max 1 request/second per domain."""

    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}
        self._global_lock = asyncio.Lock()

    async def acquire(self, domain: str) -> None:
        async with self._global_lock:
            if domain not in self._locks:
                self._locks[domain] = asyncio.Lock()

        async with self._locks[domain]:
            now = asyncio.get_event_loop().time()
            last = self._last_request.get(domain, 0)
            elapsed = now - last
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            self._last_request[domain] = asyncio.get_event_loop().time()


# ── Adapter ────────────────────────────────────────────────────────────────


class WebsiteAdapter(BaseLeadSourceAdapter):
    """Crawl a company website and extract text content.

    Parameters
    ----------
    paths : list[str]
        URL paths to crawl (relative to the domain root).
    max_pages : int
        Maximum number of pages to fetch per domain.
    timeout : float
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        paths: Optional[list[str]] = None,
        max_pages: int = 10,
        timeout: float = 15.0,
    ):
        self.paths = paths or list(DEFAULT_PATHS)
        self.max_pages = max_pages
        self.timeout = timeout
        self._rate_limiter = _DomainRateLimiter()
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def source_name(self) -> str:
        return "website"

    # ── Public interface ─────────────────────────────────────────────────

    async def search(self, query: dict[str, Any]) -> list[RawLead]:
        """Crawl a website for company information.

        Parameters
        ----------
        query : dict
            Required keys:
            - domain: str — the domain to crawl (e.g. "acme.com")
            Optional keys:
            - paths: list[str] — overrides self.paths
            - max_pages: int — overrides self.max_pages
        """
        domain = query.get("domain", "")
        if not domain:
            raise ValueError("WebsiteAdapter requires 'domain' in query")

        # Normalize domain to base URL
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        base_url = domain.rstrip("/")

        paths = query.get("paths", self.paths)
        max_pages = query.get("max_pages", self.max_pages)

        client = await self._get_client()
        parsed_domain = urlparse(base_url).netloc or base_url

        results: list[RawLead] = []

        for path in paths[:max_pages]:
            url = urljoin(base_url + "/", path.lstrip("/"))
            await self._rate_limiter.acquire(parsed_domain)

            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code != 200:
                    logger.debug("WebsiteAdapter: %s returned %d", url, resp.status_code)
                    continue

                html = resp.text
                clean_text = self._extract_text(html)

                # Only include pages with meaningful content
                if len(clean_text.strip()) < 50:
                    logger.debug("WebsiteAdapter: skipping %s (too little text)", url)
                    continue

                raw = RawLead(
                    source_type="website",
                    source_url=url,
                    raw_text=clean_text[:8000],
                    raw_data={
                        "domain": parsed_domain,
                        "path": path,
                        "status_code": resp.status_code,
                        "content_length": len(html),
                        "clean_text_length": len(clean_text),
                    },
                    company_name=self._extract_company_from_text(clean_text) or parsed_domain.split(".")[0].title(),
                    contact_name=None,
                    title=None,
                    url=url,
                    scraped_at=datetime.now(timezone.utc),
                )
                results.append(raw)

            except (httpx.HTTPError, Exception) as exc:
                logger.warning("WebsiteAdapter error fetching %s: %s", url, exc)
                continue

        logger.info("WebsiteAdapter crawled %d pages for %s", len(results), parsed_domain)
        return results

    async def extract(self, raw: RawLead) -> NormalizedLead:
        """Map a website page RawLead to NormalizedLead."""
        data = raw.raw_data
        domain = data.get("domain", "")

        # Try to extract contact info from the text
        text = raw.raw_text or ""
        email = self._extract_email(text)
        phone = self._extract_phone(text)

        return NormalizedLead(
            company_name=raw.company_name,
            company_domain=self._normalize_domain(domain),
            contact_name=None,
            contact_title=None,
            email=email,
            phone=phone,
            linkedin_url=self._extract_linkedin(text),
            source=self.source_name,
            source_url=raw.source_url,
            raw_text=text[:4000],
            country=self._extract_country(text),
            industry=self._extract_industry(text),
            status="new",
        )

    async def validate(self, lead: NormalizedLead) -> bool:
        """A website lead is valid if it has a domain or company name."""
        return bool(lead.company_name or lead.company_domain)

    # ── Internals ───────────────────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                },
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    def _extract_text(self, html: str) -> str:
        """Extract clean article text from HTML using trafilatura (fallback: regex)."""
        try:
            import trafilatura

            text = trafilatura.extract(html, include_comments=False, include_tables=False)
            if text:
                return text
        except ImportError:
            logger.debug("trafilatura not installed, using regex fallback")
        except Exception as exc:
            logger.debug("trafilatura extraction failed: %s", exc)

        # Regex fallback: strip HTML tags
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _extract_email(text: str) -> Optional[str]:
        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        m = re.search(pattern, text)
        return m.group(0) if m else None

    @staticmethod
    def _extract_phone(text: str) -> Optional[str]:
        # US/international phone pattern
        pattern = r"(?:\+?1?\s*(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4})"
        m = re.search(pattern, text)
        return m.group(0).strip() if m else None

    @staticmethod
    def _extract_linkedin(text: str) -> Optional[str]:
        pattern = r"https?://(?:www\.)?linkedin\.com/(?:in|company)/[a-zA-Z0-9_-]+"
        m = re.search(pattern, text)
        return m.group(0) if m else None

    @staticmethod
    def _extract_company_from_text(text: str) -> Optional[str]:
        """Attempt to extract a company name from page text."""
        # Look for patterns like "About Acme Corp" or "Acme Corp is a..."
        patterns = [
            r"About\s+([\w\s&]+?(?:Inc|LLC|Ltd|Corp|Co|Company))\b",
            r"^([A-Z][\w\s&]+?(?:Inc|LLC|Ltd|Corp|Co|Company))\s+(?:is|was|provides|offers)",
        ]
        for pat in patterns:
            m = re.search(pat, text[:2000])
            if m:
                return m.group(1).strip()
        return None

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        d = domain.lower().strip()
        if d.startswith("www."):
            d = d[4:]
        d = d.rstrip("/")
        return d

    @staticmethod
    def _extract_country(text: str) -> Optional[str]:
        # Simple keyword search for common country mentions
        country_patterns = [
            r"(?:located in|based in|headquartered in)\s+([\w\s]+?)(?:[,.\n]|$)",
        ]
        for pat in country_patterns:
            m = re.search(pat, text[:3000], re.IGNORECASE)
            if m:
                return m.group(1).strip()[:100]
        return None

    @staticmethod
    def _extract_industry(text: str) -> Optional[str]:
        # Naive industry extraction
        industries = [
            "SaaS",
            "FinTech",
            "HealthTech",
            "EdTech",
            "eCommerce",
            "Manufacturing",
            "Consulting",
            "Marketing",
            "Real Estate",
            "Insurance",
            "Healthcare",
            "Technology",
            "AI/ML",
            "Cybersecurity",
            "Logistics",
            "Retail",
        ]
        text_lower = text.lower()
        for ind in industries:
            if ind.lower() in text_lower:
                return ind
        return None

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
