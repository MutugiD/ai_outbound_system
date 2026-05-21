"""Base enrichment adapter defining the contract for all enrichment data providers.

Each adapter wraps a specific third-party API (Apollo, Hunter, BuiltWith, etc.)
and implements methods for contact enrichment, company enrichment, and tech stack
detection.  All methods return dicts with enrichment data, a confidence score, and
the source/provider name, making results easy to merge and persist.

Rate limiting is built-in via a simple token-bucket implementation that can be
configured per provider.
"""

import abc
import asyncio
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BaseEnrichmentAdapter(abc.ABC):
    """Abstract base class for enrichment data providers.

    Subclasses must implement:
        - enrich_contact(lead_data) -> dict
        - enrich_company(domain) -> dict
        - detect_tech_stack(domain) -> list[str]

    Rate limiting is handled via a simple per-instance token bucket.  Set
    ``requests_per_minute`` on the subclass to control throughput.
    """

    requests_per_minute: int = 60  # default, override per provider

    def __init__(self) -> None:
        self._last_request_time: float = 0.0
        self._min_interval: float = 60.0 / self.requests_per_minute
        self._lock = asyncio.Lock()

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier (e.g. 'apollo', 'hunter')."""

    # ── Abstract methods ──────────────────────────────────────────────────

    @abc.abstractmethod
    async def enrich_contact(self, lead_data: dict) -> dict:
        """Enrich contact information for a lead.

        Parameters
        ----------
        lead_data : dict
            Must include at least ``company_domain`` or ``email``.
            May also include ``first_name``, ``last_name``, ``title``, etc.

        Returns
        -------
        dict
            Enrichment data with keys: ``data``, ``confidence`` (0-1), ``source``.
        """

    @abc.abstractmethod
    async def enrich_company(self, domain: str) -> dict:
        """Enrich company information from a domain.

        Returns
        -------
        dict
            Enrichment data with keys: ``data``, ``confidence`` (0-1), ``source``.
        """

    @abc.abstractmethod
    async def detect_tech_stack(self, domain: str) -> dict:
        """Detect technologies used by a company's website.

        Returns
        -------
        dict
            Enrichment data with keys:
            ``data`` (list of detected technologies),
            ``confidence`` (0-1), ``source``.
        """

    # ── Rate limiting ────────────────────────────────────────────────────

    async def _rate_limit(self) -> None:
        """Block until enough time has passed per the rate limit."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_time = time.monotonic()

    # ── Helpers ──────────────────────────────────────────────────────────

    def _empty_result(self, error: str) -> dict:
        """Return a standard empty enrichment result with an error note."""
        return {
            "data": {},
            "confidence": 0.0,
            "source": self.provider_name,
            "error": error,
        }

    def _empty_tech_result(self, error: str) -> dict:
        """Return an empty tech-stack enrichment result with an error note."""
        return {
            "data": [],
            "confidence": 0.0,
            "source": self.provider_name,
            "error": error,
        }


# ── Fallback chain helper ────────────────────────────────────────────────────


async def run_with_fallback(
    adapters: list[BaseEnrichmentAdapter],
    method_name: str,
    *args: Any,
    **kwargs: Any,
) -> dict:
    """Try each adapter in order until one succeeds.

    Parameters
    ----------
    adapters : list[BaseEnrichmentAdapter]
        Ordered list of adapters to try (primary first).
    method_name : str
        Name of the method to call on each adapter (e.g. ``enrich_contact``).

    Returns
    -------
    dict
        The first non-error result, or the last error result if all fail.
    """
    last_result: Optional[dict] = None
    for adapter in adapters:
        try:
            method = getattr(adapter, method_name)
            result = await method(*args, **kwargs)
            if "error" not in result or result.get("confidence", 0) > 0:
                return result
            last_result = result
            logger.warning(
                "Adapter %s returned error for %s: %s",
                adapter.provider_name,
                method_name,
                result.get("error"),
            )
        except Exception as exc:
            logger.warning(
                "Adapter %s failed for %s: %s", adapter.provider_name, method_name, exc
            )
            last_result = adapter._empty_result(str(exc))
    return last_result or adapters[-1]._empty_result("All adapters failed")