# Service Boundaries

## Identity Service
Purpose:
- Team identity
- User auth
- API key issuance
- Service-to-service auth baseline

Owns:
- users
- teams
- api keys
- integration credentials metadata

## Acquisition Service
Purpose:
- Define one-industry, multi-location source jobs
- Materialize queries
- Run Google Maps acquisition
- Store raw profiles and provenance

Owns:
- `google_maps_sources`
- `google_maps_location_targets`
- `google_maps_raw_profiles`
- `acquisition_jobs`

Inbound dependencies:
- identity for user/team context

Outbound dependencies:
- crm promotion flow
- intelligence enrichment after promotion

## CRM Service
Purpose:
- Manage companies, contacts, leads, notes, activities, suppression
- Normalize and deduplicate source-derived leads
- Promote reviewed acquisition records into CRM

Owns:
- companies
- contacts
- leads
- notes
- activities
- lead_sources
- suppression

Boundary rules:
- phone is a first-class identity field
- phone-only contacts are valid
- source provenance must survive promotion

## Intelligence Service
Purpose:
- Enrichment
- Industry-aware classification
- Scoring
- Offer generation
- WhatsApp message and reply drafting

Owns:
- AI policies
- prompt contracts
- inference routing
- structured response validation

## Campaign Service
Purpose:
- Campaign definitions
- Enrollment state
- Sequencing
- Queue planning
- Send eligibility

Owns:
- campaigns
- follow-up planning
- enrollment lifecycle

Boundary rule:
- campaign service decides what should be sent
- channel service decides how it gets delivered

## Channel Service
Purpose:
- Provider integrations
- Conversation state
- Delivery execution
- Inbound webhook ingestion

Owns:
- outbound/inbound message lifecycle
- provider session/runtime state
- WhatsApp channel abstractions

Boundary rule:
- no business qualification logic lives here
- AI may draft responses, but channel owns execution and delivery state
