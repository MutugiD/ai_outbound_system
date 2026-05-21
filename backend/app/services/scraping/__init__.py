"""Scraping adapters and services for lead source data ingestion."""

from app.services.scraping.base_adapter import BaseLeadSourceAdapter, RawLead, NormalizedLead
from app.services.scraping.csv_adapter import CSVAdapter
from app.services.scraping.reddit_adapter import RedditAdapter
from app.services.scraping.linkedin_adapter import LinkedInJobsAdapter
from app.services.scraping.website_adapter import WebsiteAdapter
from app.services.scraping.normalizer import LeadNormalizer
from app.services.scraping.deduplicator import LeadDeduplicator

__all__ = [
    "BaseLeadSourceAdapter",
    "RawLead",
    "NormalizedLead",
    "CSVAdapter",
    "RedditAdapter",
    "LinkedInJobsAdapter",
    "WebsiteAdapter",
    "LeadNormalizer",
    "LeadDeduplicator",
]