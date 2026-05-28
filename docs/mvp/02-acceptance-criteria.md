# MVP Acceptance Criteria

## Service Split
- identity, acquisition, CRM, intelligence, campaign, and channel can each boot as separate FastAPI apps
- acquisition, intelligence, campaign, and channel have dedicated Celery queues

## Acquisition
- operator can create a Google Maps source for one industry and multiple locations
- source job materializes location-specific query templates
- source and raw-profile domain models persist successfully

## CRM
- phone-only leads can be normalized and persisted
- dedup checks phone before email/domain/linkedin
- lead source provenance is stored for promoted leads

## Promotion
- reviewed Google Maps profiles can be promoted into CRM through a reusable ingestion helper
- promotion creates or merges CRM records instead of duplicating logic per route

## Architecture
- docs describe service ownership, data ownership, and MVP vs post-MVP boundaries
