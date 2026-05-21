"""Reddit search adapter — discovers buying-signal posts via Reddit's public JSON API.

No API key is required; this uses the public ``.json`` endpoints with a
proper User-Agent header. Rate limiting is enforced at 60 requests/min.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote_plus

import httpx

from app.services.scraping.base_adapter import BaseLeadSourceAdapter, NormalizedLead, RawLead

logger = logging.getLogger(__name__)

# ── Defaults ───────────────────────────────────────────────────────────────

DEFAULT_SUBREDDITS: list[str] = [
    "startups",
    "Entrepreneur",
    "smallbusiness",
    "SaaS",
    "sales",
    "marketing",
    "CRM",
    "B2BSales",
    "growthacking",
    "venturecapital",
]

DEFAULT_BUYING_SIGNALS: list[str] = [
    "hiring",
    "CRM",
    "automation",
    "scaling",
    "manual process",
    "looking for",
    "recommend",
    "need help",
    "any tool",
    "switching from",
    "frustrated with",
    "budget",
    "evaluating",
    "comparison",
    "seeking",
    "recommendations",
]

USER_AGENT = "AI-Outbound-OS/0.1 (research; contact@example.com)"

# ── Rate limiter (token-bucket, per-module) ───────────────────────────────


class _RateLimiter:
    """Simple token-bucket rate limiter (max *rate* requests per *period* seconds)."""

    def __init__(self, rate: int = 60, period: float = 60.0):
        self.rate = rate
        self.period = period
        self._tokens = rate
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.rate, self._tokens + elapsed * (self.rate / self.period))
            self._last_refill = now
            if self._tokens < 1:
                sleep_time = (1 - self._tokens) / (self.rate / self.period)
                await asyncio.sleep(sleep_time)
            self._tokens -= 1


# ── Adapter ────────────────────────────────────────────────────────────────


class RedditAdapter(BaseLeadSourceAdapter):
    """Search Reddit for buying-signal posts using the public JSON API.

    Parameters
    ----------
    subreddits : list[str]
        Subreddit names (without ``r/``) to search. Defaults to DEFAULT_SUBREDDITS.
    buying_signals : list[str]
        Keywords that indicate a buying signal. Defaults to DEFAULT_BUYING_SIGNALS.
    """

    def __init__(
        self,
        subreddits: Optional[list[str]] = None,
        buying_signals: Optional[list[str]] = None,
    ):
        self.subreddits = subreddits or list(DEFAULT_SUBREDDITS)
        self.buying_signals = buying_signals or list(DEFAULT_BUYING_SIGNALS)
        self._limiter = _RateLimiter(rate=60, period=60.0)
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def source_name(self) -> str:
        return "reddit"

    # ── Public interface ─────────────────────────────────────────────────

    async def search(self, query: dict[str, Any]) -> list[RawLead]:
        """Search Reddit for buying-signal posts.

        Parameters
        ----------
        query : dict
            Optional keys:
            - keywords: list[str]  — overrides self.buying_signals
            - subreddits: list[str] — overrides self.subreddits
            - limit: int            — max results per subreddit (default 25)
            - timeframe: str        — one of hour, day, week, month, year, all
        """
        keywords = query.get("keywords", self.buying_signals)
        subreddits = query.get("subreddits", self.subreddits)
        limit = min(query.get("limit", 25), 100)
        timeframe = query.get("timeframe", "week")

        all_raws: list[RawLead] = []
        client = await self._get_client()

        for sr in subreddits:
            for kw in keywords:
                url = (
                    f"https://www.reddit.com/r/{sr}/search.json"
                    f"?q={quote_plus(kw)}"
                    f"&sort=new&t={timeframe}"
                    f"&limit={limit}"
                    f"&restrict_sr=on"
                )
                results = await self._fetch_search(client, url)
                all_raws.extend(results)
                # Small inter-request delay to avoid hammering Reddit
                await asyncio.sleep(0.5)

        # Deduplicate by post URL
        seen_urls: set[str] = set()
        unique: list[RawLead] = []
        for raw in all_raws:
            if raw.source_url and raw.source_url not in seen_urls:
                seen_urls.add(raw.source_url)
                unique.append(raw)
            elif not raw.source_url:
                unique.append(raw)

        logger.info("RedditAdapter found %d unique leads", len(unique))
        return unique

    async def extract(self, raw: RawLead) -> NormalizedLead:
        """Map a Reddit RawLead to NormalizedLead.

        For Reddit, the post title/selftext may contain company mentions but
        we primarily capture the post as a signal source.
        """
        data = raw.raw_data
        title = data.get("title", "")
        selftext = data.get("selftext", "") or ""

        # Attempt to extract company name from title (e.g. "[Hiring] Acme Corp ...")
        company_name = self._extract_company_from_title(title)

        return NormalizedLead(
            company_name=company_name or None,
            company_domain=None,
            contact_name=data.get("author"),
            contact_title=None,
            email=self._extract_email_from_text(selftext),
            phone=None,
            linkedin_url=None,
            source=self.source_name,
            source_url=raw.source_url,
            raw_text=f"{title}\n\n{selftext}"[:4000],  # cap length
            country=None,
            industry=None,
            status="new",
        )

    async def validate(self, lead: NormalizedLead) -> bool:
        """A Reddit lead is valid if it has *some* text content (the post)."""
        return bool(lead.raw_text and lead.raw_text.strip())

    # ── Internals ─────────────────────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                timeout=15.0,
                follow_redirects=True,
            )
        return self._client

    async def _fetch_search(self, client: httpx.AsyncClient, url: str) -> list[RawLead]:
        await self._limiter.acquire()
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("Reddit returned %d for %s", resp.status_code, url)
                return []
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Reddit request failed: %s", exc)
            return []

        results: list[RawLead] = []
        children = data.get("data", {}).get("children", [])
        for child in children:
            post = child.get("data", {})
            if not post:
                continue
            # Only link posts and self-posts (skip stickies, etc.)
            if post.get("stickied", False):
                continue

            subreddit = post.get("subreddit", "")
            permalink = post.get("url", "") or f"https://www.reddit.com{post.get('permalink', '')}"
            if not permalink.startswith("http"):
                permalink = f"https://www.reddit.com{permalink}"

            raw = RawLead(
                source_type="reddit",
                source_url=permalink,
                raw_text=(post.get("title", "") + "\n" + (post.get("selftext", "") or ""))[:4000],
                raw_data={
                    "title": post.get("title", ""),
                    "selftext": post.get("selftext", "") or "",
                    "subreddit": subreddit,
                    "author": post.get("author", ""),
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "created_utc": post.get("created_utc", 0),
                    "url": permalink,
                    "link_flair_text": post.get("link_flair_text"),
                },
                company_name=None,  # will be filled by extract()
                contact_name=post.get("author"),
                title=post.get("title"),
                url=permalink,
                scraped_at=datetime.fromtimestamp(post.get("created_utc", 0) or time.time(), tz=timezone.utc),
            )
            results.append(raw)

        return results

    @staticmethod
    def _extract_company_from_title(title: str) -> Optional[str]:
        """Try to pull a company name from post titles like '[Hiring] Acme Corp ...'"""
        import re

        # Match patterns like [Hiring] Company Name or "Company Name is hiring"
        m = re.match(r"^\[(?:Hiring|Looking for|Need)\]\s*(.+?)(?:\s+is\s+|\s+-\s+|\s+[-–]\s+)", title, re.I)
        if m:
            return m.group(1).strip()
        m = re.match(r"^(.+?)\s+(?:is\s+)?(?:hiring|looking for|seeking)", title, re.I)
        if m:
            return m.group(1).strip()
        return None

    @staticmethod
    def _extract_email_from_text(text: str) -> Optional[str]:
        """Extract an email address from text, if present."""
        import re

        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        m = re.search(pattern, text)
        return m.group(0) if m else None

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
