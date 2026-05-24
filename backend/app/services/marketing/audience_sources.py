"""Audience discovery sources (Reddit/HN first).

Returns normalized signal dicts that can be persisted as AudienceSignal records.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.security_utils import sanitize_log
from app.services.scraping.reddit_adapter import RedditAdapter


async def scan_reddit(
    *,
    keywords: list[str],
    subreddits: list[str],
    timeframe: str,
    per_scan_max_results: int,
) -> list[dict[str, Any]]:
    adapter = RedditAdapter(subreddits=subreddits or None, buying_signals=keywords or None)
    raws = await adapter.search(
        {
            "keywords": keywords,
            "subreddits": subreddits,
            "timeframe": timeframe,
            "limit": per_scan_max_results,
        }
    )

    signals: list[dict[str, Any]] = []
    for raw in raws:
        data = raw.raw_data or {}
        created_utc = data.get("created_utc") or 0
        created_at = None
        try:
            created_at = datetime.fromtimestamp(float(created_utc), tz=timezone.utc) if created_utc else None
        except Exception:
            created_at = None

        title = (data.get("title") or "")[:512] or None
        body = (data.get("selftext") or "")[:2048] or None

        signals.append(
            {
                "platform": "reddit",
                "source_url": raw.source_url or raw.url,
                "external_id": str(data.get("id") or "") or None,
                "title": title,
                "body_excerpt": body,
                "author": (data.get("author") or "")[:255] or None,
                "community": (data.get("subreddit") or "")[:255] or None,
                "engagement": int(data.get("score") or 0) if data.get("score") is not None else None,
                "matched_keywords": keywords,
                "intent_label": None,
                "confidence": None,
                "metadata": {
                    "num_comments": data.get("num_comments"),
                    "link_flair_text": data.get("link_flair_text"),
                },
                "source_created_at": created_at,
            }
        )
    return signals


async def scan_hacker_news(
    *,
    keywords: list[str],
    per_scan_max_results: int,
    recency_days: int = 7,
) -> list[dict[str, Any]]:
    """Search HN via Algolia (public) for keyword matches."""
    signals: list[dict[str, Any]] = []

    # Avoid "infinite" queries
    keywords = [k for k in keywords if k and len(k) <= 64][:25]
    if not keywords:
        return signals

    # Algolia supports `numericFilters=created_at_i>...` for recency.
    cutoff = int(time.time()) - (recency_days * 86400)

    async with httpx.AsyncClient(timeout=15.0) as client:
        for kw in keywords:
            try:
                resp = await client.get(
                    "https://hn.algolia.com/api/v1/search_by_date",
                    params={
                        "query": kw,
                        "tags": "story",
                        "hitsPerPage": min(per_scan_max_results, 100),
                        "numericFilters": f"created_at_i>{cutoff}",
                    },
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
            except Exception:
                continue

            for hit in data.get("hits", [])[:per_scan_max_results]:
                object_id = str(hit.get("objectID") or "")
                hn_url = f"https://news.ycombinator.com/item?id={object_id}" if object_id else None
                title = (hit.get("title") or hit.get("story_title") or "")[:512] or None
                excerpt = (hit.get("story_text") or hit.get("comment_text") or "")[:2048] or None

                created_at = None
                try:
                    if hit.get("created_at_i"):
                        created_at = datetime.fromtimestamp(int(hit["created_at_i"]), tz=timezone.utc)
                except Exception:
                    created_at = None

                signals.append(
                    {
                        "platform": "hn",
                        "source_url": hn_url,
                        "external_id": object_id or None,
                        "title": title,
                        "body_excerpt": excerpt,
                        "author": sanitize_log(str(hit.get("author") or ""))[:255] or None,
                        "community": "hackernews",
                        "engagement": hit.get("points"),
                        "matched_keywords": [kw],
                        "intent_label": None,
                        "confidence": None,
                        "metadata": {
                            "url": sanitize_log(str(hit.get("url") or "")),
                            "num_comments": hit.get("num_comments"),
                        },
                        "source_created_at": created_at,
                    }
                )

    return signals

