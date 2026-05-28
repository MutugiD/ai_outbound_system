"""Reusable CRM ingestion helpers for source-derived leads."""

import logging
import uuid
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead_source import LeadSource
from app.services.scraping.base_adapter import RawLead
from app.services.scraping.deduplicator import LeadDeduplicator
from app.services.scraping.normalizer import LeadNormalizer

logger = logging.getLogger(__name__)

_normalizer = LeadNormalizer()


def build_google_maps_raw_lead(
    *,
    business_name: str,
    query: str,
    area: str | None,
    phone: str | None,
    website: str | None,
    google_maps_url: str | None,
    address: str | None,
    category: str | None,
    review_count: int | None,
    rating: float | None,
    provider_record_id: str,
    scraped_at,
) -> RawLead:
    """Convert a stored Google Maps raw profile into the generic ingestion shape."""
    parsed_website = urlparse(website) if website else None
    domain = parsed_website.netloc if parsed_website and parsed_website.netloc else None
    if domain and domain.startswith("www."):
        domain = domain[4:]

    return RawLead(
        source_type="google_maps",
        source_url=google_maps_url,
        source_query=query,
        source_location=area,
        provider_record_id=provider_record_id,
        company_name=business_name,
        raw_data={
            "company_name": business_name,
            "company_domain": domain,
            "domain": domain,
            "phone": phone,
            "country_code": "KE",
            "industry": category,
            "address": address,
            "review_count": review_count,
            "rating": rating,
            "website": website,
            "google_maps_url": google_maps_url,
        },
        raw_text=address,
        scraped_at=scraped_at or datetime.utcnow(),
    )


async def ingest_raw_leads(
    raw_leads: list[RawLead],
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Normalize, deduplicate, and persist raw leads into CRM."""
    dedup = LeadDeduplicator(db)
    created = 0
    merged = 0
    skipped = 0
    errors = 0
    sources_created = 0

    for raw in raw_leads:
        try:
            normalized = _normalizer.normalize(raw)

            if (
                not normalized.company_name
                and not normalized.company_domain
                and not normalized.email
                and not normalized.linkedin_url
                and not normalized.phone
            ):
                skipped += 1
                continue

            existing_check = await dedup.check_duplicate(normalized, team_id)
            lead = await dedup.merge_or_create(normalized, team_id, user_id)
            if not lead:
                errors += 1
                continue

            db.add(
                LeadSource(
                    lead_id=lead.id,
                    source_type=raw.source_type,
                    source_url=raw.source_url,
                    source_name=raw.raw_data.get("title") or raw.raw_data.get("subreddit") or raw.source_type,
                    source_query=raw.source_query,
                    source_location=raw.source_location,
                    acquisition_method=raw.source_type,
                    provider_record_id=raw.provider_record_id,
                    scraped_at=raw.scraped_at,
                    promotion_status="merged" if existing_check.is_duplicate else "promoted",
                    raw_text=raw.raw_text[:4000] if raw.raw_text else None,
                    detected_signal_text=",".join(raw.raw_data.get("buying_signals", []))
                    if raw.raw_data.get("buying_signals")
                    else None,
                )
            )
            sources_created += 1

            if existing_check.is_duplicate:
                merged += 1
            else:
                created += 1

        except Exception as exc:
            errors += 1
            logger.warning("Error ingesting lead from %s: %s", raw.source_type, exc)

    await db.flush()
    return {
        "total": len(raw_leads),
        "created": created,
        "merged": merged,
        "skipped": skipped,
        "errors": errors,
        "sources_created": sources_created,
    }
