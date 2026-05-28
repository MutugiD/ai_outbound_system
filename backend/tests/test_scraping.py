"""Scraping service unit tests — CSV adapter, normalizer, and deduplicator."""

import csv
import os
import tempfile
import uuid

import pytest

from app.services.scraping.csv_adapter import CSVAdapter, COLUMN_ALIASES
from app.services.scraping.normalizer import LeadNormalizer
from app.services.scraping.base_adapter import RawLead


# ── CSV Adapter Tests ────────────────────────────────────────────────────────


async def test_csv_adapter_parses_valid_csv():
    """CSVAdapter should parse a valid CSV file into RawLead objects."""
    # Create a temp CSV file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Company", "Email", "Domain", "LinkedIn"])
        writer.writeheader()
        writer.writerow(
            {
                "Company": "Acme Corp",
                "Email": "john@acme.com",
                "Domain": "acme.com",
                "LinkedIn": "https://linkedin.com/in/johndoe",
            }
        )
        writer.writerow(
            {
                "Company": "Widget Inc",
                "Email": "jane@widget.com",
                "Domain": "widget.com",
                "LinkedIn": "",
            }
        )
        tmp_path = f.name

    try:
        adapter = CSVAdapter()
        raw_leads = await adapter.search({"file_path": tmp_path})
        assert len(raw_leads) == 2
        assert raw_leads[0].raw_data.get("company_name") == "Acme Corp"
        assert raw_leads[0].raw_data.get("email") == "john@acme.com"
        assert raw_leads[1].raw_data.get("company_name") == "Widget Inc"
    finally:
        os.unlink(tmp_path)


async def test_csv_adapter_handles_column_aliases():
    """CSVAdapter should map alternative column names to canonical fields."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
        # Use alias names: "Organization" instead of "Company", "Website" instead of "Domain"
        writer = csv.DictWriter(f, fieldnames=["Organization", "Website", "Contact", "EmailAddress"])
        writer.writeheader()
        writer.writerow(
            {
                "Organization": "Beta LLC",
                "Website": "www.beta.com",
                "Contact": "Bob Smith",
                "EmailAddress": "bob@beta.com",
            }
        )
        tmp_path = f.name

    try:
        adapter = CSVAdapter()
        raw_leads = await adapter.search({"file_path": tmp_path})
        assert len(raw_leads) == 1
        data = raw_leads[0].raw_data
        assert data.get("company_name") == "Beta LLC"
        assert data.get("company_domain") == "www.beta.com"
        assert data.get("contact_name") == "Bob Smith"
        assert data.get("email") == "bob@beta.com"
    finally:
        os.unlink(tmp_path)


# ── Normalizer Tests ────────────────────────────────────────────────────────


def test_normalizer_cleans_company_names():
    """LeadNormalizer should remove LLC, Inc, Ltd suffixes and title-case."""
    normalizer = LeadNormalizer()

    # LLC removal
    raw = RawLead(source_type="csv_import", company_name="Acme LLC", raw_data={})
    result = normalizer.normalize(raw)
    assert result.company_name == "Acme"

    # Inc removal
    raw = RawLead(source_type="csv_import", company_name="Widget Inc", raw_data={})
    result = normalizer.normalize(raw)
    assert result.company_name == "Widget"

    # Ltd removal
    raw = RawLead(source_type="csv_import", company_name="Global Ltd", raw_data={})
    result = normalizer.normalize(raw)
    assert result.company_name == "Global"

    # Combined suffixes
    raw = RawLead(source_type="csv_import", company_name="TechCorp Corporation", raw_data={})
    result = normalizer.normalize(raw)
    assert "Corporation" not in result.company_name


def test_normalizer_normalizes_domains():
    """LeadNormalizer should strip www., lowercase, and remove protocols."""
    normalizer = LeadNormalizer()

    # www. removal
    raw = RawLead(source_type="csv_import", company_name="Test", raw_data={"company_domain": "www.example.com"})
    result = normalizer.normalize(raw)
    assert result.company_domain == "example.com"

    # Lowercase
    raw = RawLead(source_type="csv_import", company_name="Test", raw_data={"company_domain": "EXAMPLE.COM"})
    result = normalizer.normalize(raw)
    assert result.company_domain == "example.com"

    # Protocol removal
    raw = RawLead(source_type="csv_import", company_name="Test", raw_data={"company_domain": "https://example.com"})
    result = normalizer.normalize(raw)
    assert result.company_domain == "example.com"


def test_normalizer_normalizes_phones():
    """LeadNormalizer should format phone numbers to E.164."""
    normalizer = LeadNormalizer()

    # Full E.164 number should pass through
    raw = RawLead(
        source_type="csv_import",
        company_name="Test",
        raw_data={"phone": "+14155551234"},
    )
    result = normalizer.normalize(raw)
    assert result.phone == "+14155551234"

    # 10-digit US number with valid area/exchange code
    raw = RawLead(
        source_type="csv_import",
        company_name="Test",
        raw_data={"phone": "4155551234"},
    )
    result = normalizer.normalize(raw)
    assert result.phone is not None

    # Kenya local number should still use the KE default region
    raw = RawLead(
        source_type="csv_import",
        company_name="Test",
        raw_data={"phone": "0722123456"},
    )
    result = normalizer.normalize(raw)
    assert result.phone == "+254722123456"
    assert result.phone.startswith("+1") or result.phone.startswith("+")

    # Number with formatting that parses as valid US
    raw = RawLead(
        source_type="csv_import",
        company_name="Test",
        raw_data={"phone": "+1 (415) 555-1234"},
    )
    result = normalizer.normalize(raw)
    assert result.phone is not None


def test_normalizer_normalizes_linkedin_urls():
    """LeadNormalizer should normalize LinkedIn URLs to canonical form."""
    normalizer = LeadNormalizer()

    # Add https if missing
    raw = RawLead(source_type="csv_import", company_name="Test", url="linkedin.com/in/johndoe", raw_data={})
    result = normalizer.normalize(raw)
    assert result.linkedin_url == "https://linkedin.com/in/johndoe"

    # Remove www
    raw = RawLead(
        source_type="csv_import", company_name="Test", url="https://www.linkedin.com/in/janesmith", raw_data={}
    )
    result = normalizer.normalize(raw)
    assert result.linkedin_url == "https://linkedin.com/in/janesmith"

    # Normalize http to https
    raw = RawLead(source_type="csv_import", company_name="Test", url="http://linkedin.com/in/bob", raw_data={})
    result = normalizer.normalize(raw)
    assert result.linkedin_url.startswith("https://")


# ── Deduplicator Tests ─────────────────────────────────────────────────────


async def test_deduplicator_detects_email_duplicates(db_session, test_team):
    """LeadDeduplicator should detect duplicate leads by email."""
    from app.services.scraping.deduplicator import LeadDeduplicator, DeduplicationResult
    from app.services.scraping.base_adapter import NormalizedLead, RawLead

    # First, create an existing record via deduplicator
    dedup = LeadDeduplicator(db_session)
    lead1 = NormalizedLead(
        company_name="Acme Corp",
        company_domain="acme.com",
        email="unique-dedupe@acme.com",
        contact_name="John Doe",
        source="csv_import",
    )
    created = await dedup.merge_or_create(lead1, test_team.id, uuid.uuid4())
    await db_session.flush()

    # Now try to create a lead with the same email
    lead2 = NormalizedLead(
        company_name="Acme Corp",
        company_domain="acme.com",
        email="unique-dedupe@acme.com",
        contact_name="John Doe",
        source="csv_import",
    )
    result = await dedup.check_duplicate(lead2, test_team.id)
    assert result.is_duplicate is True
    assert "email" in result.match_reason
