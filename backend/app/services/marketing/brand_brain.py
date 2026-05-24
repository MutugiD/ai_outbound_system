"""Brand Brain derivation: website -> draft marketing profile.

This is intentionally lightweight: it provides a usable starting point for a team
and can be refined by the user over time.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any
from urllib.parse import urlparse

from app.security_utils import sanitize_log, validate_url_for_fetch
from app.services.scraping.website_adapter import WebsiteAdapter

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{2,}")

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "your",
    "you",
    "our",
    "are",
    "was",
    "were",
    "have",
    "has",
    "can",
    "will",
    "their",
    "they",
    "them",
    "but",
    "not",
    "all",
    "any",
    "into",
    "out",
    "over",
    "under",
    "about",
    "more",
    "less",
    "than",
    "just",
    "what",
    "when",
    "where",
    "why",
    "how",
    "who",
}


def _extract_domain(website_url: str) -> str:
    validated = validate_url_for_fetch(website_url)
    parsed = urlparse(validated)
    return parsed.hostname or website_url


def _keywords_from_text(text: str, max_keywords: int = 25) -> list[str]:
    words = [w.lower() for w in _WORD_RE.findall(text or "") if w]
    words = [w for w in words if w not in _STOPWORDS and len(w) <= 32]
    counts = Counter(words)
    ranked = [w for w, _ in counts.most_common(max_keywords * 2)]
    # De-dup near duplicates
    out: list[str] = []
    seen: set[str] = set()
    for w in ranked:
        if w in seen:
            continue
        if w.isdigit():
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= max_keywords:
            break
    return out


async def derive_brand_brain(website_url: str) -> dict[str, Any]:
    """Derive a draft Brand Brain from a website crawl (SSRF-safe)."""
    domain = _extract_domain(website_url)
    adapter = WebsiteAdapter(max_pages=6, timeout=15.0)

    # Crawl a handful of pages and stitch text into a corpus
    raw_pages = await adapter.search({"domain": domain})
    combined = "\n\n".join([(p.raw_text or "") for p in raw_pages if p and p.raw_text])[:50_000]

    keywords = _keywords_from_text(combined, max_keywords=25)
    summary = (combined.strip()[:600] + "…") if len(combined.strip()) > 600 else combined.strip()

    # Default voice rules inspired by "sounds like you, not AI"
    voice_rules = [
        "Write like a human founder, not corporate.",
        "Use specific details and examples; avoid vague hype.",
        "Prefer short sentences and simple words.",
        "Avoid buzzwords and filler (e.g. 'revolutionary', 'game-changer').",
        "Ask one thoughtful question when appropriate.",
    ]

    return {
        "website_url": website_url,
        "domain": domain,
        "product_summary": summary or f"Derived from {sanitize_log(domain)}",
        "positioning": {
            "value_prop": "Draft: clarify who it's for, the pain, and the promised outcome.",
            "icp": "Draft: founders/teams who need a clearer go-to-market motion.",
        },
        "voice_rules": voice_rules,
        "keywords": keywords,
    }

