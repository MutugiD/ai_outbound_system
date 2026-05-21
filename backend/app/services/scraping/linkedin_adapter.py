"""LinkedIn Jobs adapter — scrapes public job listings via Playwright (NO LOGIN REQUIRED).

LinkedIn's public job search works in guest mode. This adapter:
1. Navigates to the job search URL without authentication
2. Dismisses sign-in popups automatically
3. Extracts job card data (title, company, location, date, URL)
4. Optionally visits individual job detail pages for full descriptions
5. Detects buying signals in job descriptions
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.scraping.base_adapter import BaseLeadSourceAdapter, NormalizedLead, RawLead
from app.security_utils import sanitize_log

logger = logging.getLogger(__name__)

# ── Buying signals ─────────────────────────────────────────────────────────

BUYING_SIGNAL_KEYWORDS: list[str] = [
    "CRM",
    "Salesforce",
    "HubSpot",
    "automation",
    "scaling",
    "operations",
    "ops manager",
    "revenue operations",
    "sales ops",
    "marketing ops",
    "growth",
    "outbound",
    "lead generation",
    "SDR",
    "BDR",
    "sales development",
    "account executive",
    "customer success",
    "onboarding",
    "data entry",
    "manual process",
    "spreadsheet",
    "workflow",
    "pipeline",
    "prospecting",
]

# ── Time window map ────────────────────────────────────────────────────────

TIME_WINDOW_MAP: dict[str, str] = {
    "24h": "r86400",
    "1d": "r86400",
    "7d": "r604800",
    "1w": "r604800",
    "30d": "r2592000",
    "1m": "r2592000",
}


class LinkedInJobsAdapter(BaseLeadSourceAdapter):
    """Scrape LinkedIn public job search using Playwright (guest mode, no login).

    Parameters
    ----------
    headless : bool
        Run browser in headless mode (default True).
    max_scroll_pages : int
        Max pages to scroll/load per search (default 5).
    detail_pages : bool
        Whether to visit individual job detail pages for full descriptions.
    """

    def __init__(
        self,
        headless: bool = True,
        max_scroll_pages: int = 5,
        detail_pages: bool = True,
    ):
        self.headless = headless
        self.max_scroll_pages = max_scroll_pages
        self.detail_pages = detail_pages
        self._browser = None
        self._playwright = None

    @property
    def source_name(self) -> str:
        return "linkedin_jobs"

    # ── Public interface ─────────────────────────────────────────────────

    async def search(self, query: dict[str, Any]) -> list[RawLead]:
        """Search LinkedIn public job listings.

        Parameters
        ----------
        query : dict
            Required keys:
            - keywords: str — job search query (e.g. "CRM manager", "sales operations")
            Optional keys:
            - location: str — geographic filter (default: "United States")
            - time_window: str — "24h", "7d", "30d" (default: "7d")
            - remote: bool — filter for remote jobs (default: True via f_WT=2)
            - limit: int — max results (default: 50)
        """
        keywords = query.get("keywords", "")
        if not keywords:
            raise ValueError("LinkedInAdapter requires 'keywords' in query")
        location = query.get("location", "United States")
        time_window = TIME_WINDOW_MAP.get(query.get("time_window", "7d"), "r604800")
        remote = query.get("remote", True)
        limit = query.get("limit", 50)

        search_url = self._build_search_url(keywords, location, time_window, remote)
        logger.info("LinkedInAdapter: searching %s", sanitize_log(search_url))

        try:
            job_cards = await self._scrape_search_page(search_url)
        except Exception as exc:
            logger.error("LinkedIn search failed: %s", exc)
            raise

        # Optionally visit detail pages
        if self.detail_pages and job_cards:
            job_cards = await self._enrich_with_details(job_cards)

        # Limit results
        job_cards = job_cards[:limit]

        # Convert to RawLead
        raw_leads = [self._card_to_raw(card) for card in job_cards]

        # Deduplicate by job_id
        seen_ids: set[str] = set()
        unique: list[RawLead] = []
        for raw in raw_leads:
            job_id = raw.raw_data.get("job_id", "")
            if job_id and job_id in seen_ids:
                continue
            if job_id:
                seen_ids.add(job_id)
            unique.append(raw)

        logger.info("LinkedInAdapter found %d unique jobs", len(unique))
        return unique

    async def extract(self, raw: RawLead) -> NormalizedLead:
        """Map a LinkedIn job card RawLead to NormalizedLead."""
        data = raw.raw_data
        description = data.get("description", "") or data.get("selftext", "") or ""

        return NormalizedLead(
            company_name=self._clean_str(data.get("company")),
            company_domain=None,  # Not directly available from job cards
            contact_name=None,  # Job postings don't list a contact
            contact_title=self._clean_str(data.get("title")),
            email=None,
            phone=None,
            linkedin_url=data.get("job_url"),
            source=self.source_name,
            source_url=data.get("job_url"),
            raw_text=description[:4000] if description else raw.raw_text,
            country=self._extract_country(data.get("location", "")),
            industry=None,
            status="new",
        )

    async def validate(self, lead: NormalizedLead) -> bool:
        """A LinkedIn lead is valid if at least a company name or URL exists."""
        return bool(lead.company_name or lead.source_url)

    # ── URL builder ──────────────────────────────────────────────────────

    @staticmethod
    def _build_search_url(keywords: str, location: str, time_window: str, remote: bool) -> str:
        from urllib.parse import quote_plus

        kw = quote_plus(keywords)
        loc = quote_plus(location)
        url = f"https://www.linkedin.com/jobs/search/?keywords={kw}&location={loc}&f_TPR={time_window}&sortBy=DD"
        if remote:
            url += "&f_WT=2"
        return url

    # ── Playwright scraping ──────────────────────────────────────────────

    async def _ensure_browser(self):
        """Launch Playwright browser if not already running."""
        if self._browser is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "playwright is required for LinkedInAdapter. "
                "Install it with: pip install playwright && playwright install chromium"
            )

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)

    async def close(self) -> None:
        """Close the browser."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def _scrape_search_page(self, url: str) -> list[dict]:
        """Navigate to the search page, dismiss sign-in dialog, scroll, and extract cards."""
        await self._ensure_browser()
        context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # Dismiss sign-in dialog / overlay
            await self._dismiss_sign_in_dialog(page)

            # Scroll to load more results
            for _ in range(self.max_scroll_pages):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
                # Click "Load more" button if present
                load_more = page.locator('button:has-text("See more jobs")')
                if await load_more.count() > 0:
                    try:
                        await load_more.first.click()
                        await asyncio.sleep(2)
                    except Exception:
                        pass

            # Extract job cards
            cards = await self._extract_job_cards(page)
            return cards
        finally:
            await context.close()

    async def _dismiss_sign_in_dialog(self, page) -> None:
        """Dismiss LinkedIn sign-in modal/overlay that blocks guest access."""
        # Try common dismiss selectors
        dismiss_selectors = [
            'button[action="dismiss"]',
            'button[data-tracking-control="dismiss"]',
            'button[aria-label="Dismiss"]',
            "button.modal__dismiss",
            ".overlay__dismiss",
            'button:has-text("Dismiss")',
            'button:has-text("Sign in later")',
        ]
        for selector in dismiss_selectors:
            try:
                btn = page.locator(selector)
                if await btn.count() > 0:
                    await btn.first.click()
                    await asyncio.sleep(1)
                    return
            except Exception:
                continue

        # Try pressing Escape as a fallback
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
        except Exception:
            pass

    async def _extract_job_cards(self, page) -> list[dict]:
        """Extract all job card data from the loaded search page."""
        js_code = r"""
        () => {
            const cards = [];
            const links = document.querySelectorAll('a[href*="/jobs/view/"]');
            for (const link of links) {
                const card = {};
                card.job_url = link.href;
                card.job_id = (link.href.match(/\/jobs\/view\/(\d+)/) || [])[1] || '';

                // Walk up to find the card container
                let container = link.closest('li') || link.closest('div[class*="job-search-card"]') || link.parentElement;
                for (let i = 0; i < 5 && container; i++) {
                    if (container.querySelector && container.querySelector('h3')) break;
                    container = container.parentElement;
                }
                if (!container) continue;

                const h3 = container.querySelector('h3') || container.querySelector('[class*="base-search-card__title"]');
                card.title = h3 ? h3.textContent.trim() : link.textContent.trim();

                const h4 = container.querySelector('h4') || container.querySelector('[class*="base-search-card__subtitle"]');
                card.company = h4 ? h4.textContent.trim() : '';

                const locEl = container.querySelector('[class*="job-search-card__location"]') || container.querySelector('.job-search-card__location');
                card.location = locEl ? locEl.textContent.trim() : '';

                const timeEl = container.querySelector('time') || container.querySelector('[class*="job-search-card__listdate"]');
                card.posted_date = timeEl ? timeEl.getAttribute('datetime') || timeEl.textContent.trim() : '';
                card.posted_label = timeEl ? timeEl.textContent.trim() : '';

                cards.push(card);
            }
            return cards;
        }
        """
        try:
            results = await page.evaluate(js_code)
            return results if isinstance(results, list) else []
        except Exception as exc:
            logger.warning("Failed to extract job cards: %s", exc)
            return []

    async def _enrich_with_details(self, cards: list[dict]) -> list[dict]:
        """Visit detail pages for each job card to get full descriptions."""
        await self._ensure_browser()
        context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        enriched = []
        try:
            for card in cards:
                job_url = card.get("job_url")
                if not job_url:
                    enriched.append(card)
                    continue

                page = await context.new_page()
                try:
                    await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(2)
                    await self._dismiss_sign_in_dialog(page)

                    # Extract job description
                    description = await self._extract_job_description(page)
                    card["description"] = description

                    # Detect buying signals
                    full_text = f"{card.get('title', '')} {description}"
                    card["buying_signals"] = self._detect_buying_signals(full_text)

                except Exception as exc:
                    logger.warning("Failed to scrape detail for %s: %s", job_url, exc)
                    card["description"] = ""
                finally:
                    await page.close()

                enriched.append(card)
                # Rate limiting: 2-3 seconds between page loads
                await asyncio.sleep(2.5)
        finally:
            await context.close()

        return enriched

    async def _extract_job_description(self, page) -> str:
        """Extract the job description text from a LinkedIn job detail page."""
        js_code = """
        () => {
            // Try the main description container
            const descEl = document.querySelector('.description__text') ||
                           document.querySelector('.show-more-less-html__markup') ||
                           document.querySelector('[class*="jobs-description__content"]') ||
                           document.querySelector('[class*="jobs-unified-top-card__description"]');
            if (descEl) return descEl.innerText;
            // Fallback: largest text block
            const allDivs = document.querySelectorAll('div');
            let best = '';
            for (const div of allDivs) {
                if (div.innerText && div.innerText.length > best.length && div.innerText.length < 20000) {
                    best = div.innerText;
                }
            }
            return best;
        }
        """
        try:
            text = await page.evaluate(js_code)
            return text or ""
        except Exception:
            return ""

    # ── Buying signal detection ──────────────────────────────────────────

    @staticmethod
    def _detect_buying_signals(text: str) -> list[str]:
        """Return list of buying signal keywords found in the text."""
        text_lower = text.lower()
        return [kw for kw in BUYING_SIGNAL_KEYWORDS if kw.lower() in text_lower]

    # ── Card → RawLead conversion ────────────────────────────────────────

    @staticmethod
    def _card_to_raw(card: dict) -> RawLead:
        title = card.get("title", "")
        company = card.get("company", "")
        location = card.get("location", "")
        description = card.get("description", "")
        url = card.get("job_url", "")
        job_id = card.get("job_id", "")

        raw_text = f"{title} at {company}"
        if location:
            raw_text += f" - {location}"
        if description:
            raw_text += f"\n\n{description}"

        return RawLead(
            source_type="linkedin_jobs",
            source_url=url,
            raw_text=raw_text[:4000],
            raw_data={
                "title": title,
                "company": company,
                "location": location,
                "posted_date": card.get("posted_date", ""),
                "posted_label": card.get("posted_label", ""),
                "job_id": job_id,
                "job_url": url,
                "description": description[:2000] if description else "",
                "buying_signals": card.get("buying_signals", []),
            },
            company_name=company or None,
            contact_name=None,
            title=title or None,
            url=url or None,
            scraped_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _clean_str(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        stripped = value.strip()
        return stripped or None

    @staticmethod
    def _extract_country(location: str) -> Optional[str]:
        """Naive country extraction from a location string."""
        if not location:
            return None
        # Simple heuristic: last comma-separated segment often contains country
        parts = [p.strip() for p in location.split(",")]
        if len(parts) >= 2:
            candidate = parts[-1].strip()
            if len(candidate) <= 60:
                return candidate
        return parts[-1] if parts else None
