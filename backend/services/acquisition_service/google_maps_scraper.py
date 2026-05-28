"""Low-volume Google Maps scraper for acquisition MVP validation."""

import asyncio
import logging
import re
from urllib.parse import quote_plus

from playwright.async_api import Browser, Page, async_playwright

logger = logging.getLogger(__name__)


class GoogleMapsPlaywrightScraper:
    """Scrape a small number of Google Maps business profiles for one query."""

    def __init__(self, *, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None

    async def __aenter__(self):
        await self._ensure_browser()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def _ensure_browser(self):
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def scrape_query(self, query: str, *, max_results: int = 10) -> list[dict]:
        """Scrape one Google Maps search query into business-profile dicts."""
        await self._ensure_browser()
        context = await self._browser.new_context(
            viewport={"width": 1440, "height": 960},
            locale="en-KE",
            timezone_id="Africa/Nairobi",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        try:
            url = f"https://www.google.com/maps/search/{quote_plus(query)}?hl=en"
            logger.info("Opening Google Maps query: %s", query)
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(5000)
            await self._dismiss_dialogs(page)
            await self._wait_for_results(page)

            card_links = await self._collect_card_links(page, max_results=max_results)
            profiles: list[dict] = []
            seen_urls: set[str] = set()

            for card_url in card_links:
                if card_url in seen_urls:
                    continue
                seen_urls.add(card_url)
                profile = await self._scrape_detail(context, card_url, query)
                if profile:
                    profiles.append(profile)
                if len(profiles) >= max_results:
                    break
                await asyncio.sleep(1.5)

            return profiles
        finally:
            await context.close()

    async def _dismiss_dialogs(self, page: Page):
        selectors = [
            'button:has-text("Accept all")',
            'button:has-text("Reject all")',
            'button:has-text("Not now")',
        ]
        for selector in selectors:
            try:
                locator = page.locator(selector)
                if await locator.count() > 0:
                    await locator.first.click(timeout=1500)
                    await page.wait_for_timeout(800)
                    return
            except Exception:
                continue

    async def _wait_for_results(self, page: Page):
        candidates = [
            '.hfpxzc',
            'a[href*="/maps/place/"]',
            'a[href*="/place/"]',
            '[role="feed"]',
            '[role="article"]',
        ]
        for _ in range(12):
            for selector in candidates:
                try:
                    if await page.locator(selector).count() > 0:
                        return
                except Exception:
                    continue
            await page.wait_for_timeout(2000)
        raise RuntimeError("Google Maps results did not load")

    async def _collect_card_links(self, page: Page, *, max_results: int) -> list[str]:
        feed = page.locator('[role="feed"]').first
        links: list[str] = []
        stagnant_rounds = 0

        for _ in range(10):
            hrefs = await page.locator('a[href*="/maps/place/"], a[href*="/place/"]').evaluate_all(
                """
                (elements) => elements
                  .map((el) => el.href)
                  .filter((href) => href && href.includes('/place/'))
                """
            )
            deduped = []
            seen = set()
            for href in hrefs:
                normalized = href.split("&")[0]
                if normalized not in seen:
                    seen.add(normalized)
                    deduped.append(normalized)

            if len(deduped) >= max_results:
                return deduped[:max_results]

            if len(deduped) > len(links):
                links = deduped
                stagnant_rounds = 0
            else:
                stagnant_rounds += 1

            if stagnant_rounds >= 2:
                break

            try:
                await feed.hover()
                await page.mouse.wheel(0, 2400)
            except Exception:
                await page.evaluate("window.scrollBy(0, 2400)")
            await page.wait_for_timeout(2500)

        return links[:max_results]

    async def _scrape_detail(self, context, detail_url: str, query: str) -> dict | None:
        page = await context.new_page()
        try:
            await page.goto(detail_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(3000)
            await self._dismiss_dialogs(page)

            name = await self._text_or_none(page, "h1")
            if not name:
                return None

            phone = await self._attribute_or_none(page, 'button[data-item-id^="phone:tel:"]', "aria-label")
            if phone:
                phone = self._clean_phone(phone)
            if not phone:
                phone = await self._text_or_none(page, 'button[data-item-id^="phone:tel:"]')
                phone = self._clean_phone(phone) if phone else None

            address = await self._attribute_or_none(page, 'button[data-item-id="address"]', "aria-label")
            if address and address.lower().startswith("address:"):
                address = address.split(":", 1)[1].strip()

            website = await self._attribute_or_none(page, 'a[data-item-id="authority"]', "href")
            google_maps_url = page.url
            category = await self._find_category(page)
            rating = self._parse_rating(
                await self._attribute_or_none(page, 'div[role="main"] span[role="img"]', "aria-label")
            )
            review_count = await self._parse_review_count(page)

            return {
                "query": query,
                "business_name": name,
                "category": category,
                "phone": phone,
                "website": website,
                "google_maps_url": google_maps_url,
                "address": address,
                "area": self._infer_area(address, query),
                "rating": rating,
                "review_count": review_count,
                "business_status": "active",
                "raw_payload": {
                    "query": query,
                    "scraped_url": google_maps_url,
                },
            }
        except Exception as exc:
            logger.warning("Failed to scrape detail page %s: %s", detail_url, exc)
            return None
        finally:
            await page.close()

    async def _find_category(self, page: Page) -> str | None:
        selectors = [
            'button[jsaction*="pane.rating.category"]',
            'div[role="main"] button[aria-label*="Category"]',
            'div[role="main"] span button',
        ]
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                text = await locator.text_content(timeout=1000)
                cleaned = self._clean_text(text)
                if cleaned and len(cleaned) < 80:
                    return cleaned
            except Exception:
                continue
        return None

    async def _parse_review_count(self, page: Page) -> int | None:
        try:
            text = await self._attribute_or_none(page, 'div[role="main"] span[role="img"]', "aria-label")
            if text:
                match = re.search(r"([\d,]+)\s+reviews", text)
                if match:
                    return int(match.group(1).replace(",", ""))
        except Exception:
            pass
        return None

    async def _text_or_none(self, page: Page, selector: str) -> str | None:
        try:
            locator = page.locator(selector).first
            text = await locator.text_content(timeout=2500)
            return self._clean_text(text)
        except Exception:
            return None

    async def _attribute_or_none(self, page: Page, selector: str, attr: str) -> str | None:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(timeout=2500)
            value = await locator.get_attribute(attr)
            return self._clean_text(value)
        except Exception:
            return None

    @staticmethod
    def _clean_text(value: str | None) -> str | None:
        if not value:
            return None
        cleaned = re.sub(r"\s+", " ", value).strip()
        return cleaned or None

    @staticmethod
    def _clean_phone(value: str | None) -> str | None:
        if not value:
            return None
        value = value.replace("Phone:", "").strip()
        return value or None

    @staticmethod
    def _parse_rating(value: str | None) -> float | None:
        if not value:
            return None
        match = re.search(r"([\d.]+)\s+stars?", value)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    @staticmethod
    def _infer_area(address: str | None, query: str) -> str | None:
        if address:
            parts = [part.strip() for part in address.split(",") if part.strip()]
            if parts:
                return parts[0]
        query_parts = [part.strip() for part in query.split() if part.strip()]
        return " ".join(query_parts[-3:]) if query_parts else None
