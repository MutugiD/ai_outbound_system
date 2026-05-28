# Data Ownership

## Shared DB During MVP
MVP uses one Postgres instance, but ownership is explicit by table and service.

## Acquisition-Owned Tables
- `google_maps_sources`
- `google_maps_location_targets`
- `google_maps_raw_profiles`
- `acquisition_jobs`

## CRM-Owned Tables
- `companies`
- `contacts`
- `leads`
- `lead_sources`
- `lead_notes`
- `activity_logs`
- `suppression_lists`

## Campaign-Owned Tables
- existing campaign and follow-up tables remain owned by campaign logic even while they still live in the shared DB

## Channel-Owned Tables
- existing message/reply/channel delivery tables remain owned by channel logic as extraction continues

## Provenance Rules
Every promoted lead from acquisition must preserve:
- `source_type`
- `source_url`
- `source_query`
- `source_location`
- `provider_record_id`
- `scraped_at`
- `promotion_status`

## Phone Identity Rules
Contacts now support:
- `raw_phone`
- `normalized_phone`
- `whatsapp_phone`

Dedup order for source-driven ingestion:
1. normalized phone
2. email
3. company domain
4. LinkedIn URL
5. fuzzy company/contact matching

## Post-MVP Migration Path
- move service tables into service-owned schemas
- add outbox/event tables per service
- split databases only after query and operational boundaries harden
