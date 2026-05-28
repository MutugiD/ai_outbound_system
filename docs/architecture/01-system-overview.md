# System Overview

## Goal
Turn the current monolith into a modular monorepo with deployable backend services that can be extracted block by block without rewriting the existing CRM, AI, and campaign foundations.

## MVP Services
- `identity-service`: auth, users, teams, API keys
- `acquisition-service`: Google Maps source jobs, location targets, raw profile capture, provenance
- `crm-service`: companies, contacts, leads, activities, notes, suppression, promotion into CRM
- `intelligence-service`: AI enrichment, classification, score/offer generation, reply drafting
- `campaign-service`: campaign definitions, enrollments, sequencing, send eligibility
- `channel-service`: WhatsApp provider abstraction, delivery execution, inbound replies, conversation state

## Shared Infrastructure
- PostgreSQL: shared during MVP, with explicit domain ownership by table
- Redis: Celery broker and async workflow transport
- MinIO: scrape artifacts and source snapshots

## Runtime Shape
- Existing monolith app still runs on `app.main:app`
- New service apps run independently through:
  - `services.identity_service.main:app`
  - `services.acquisition_service.main:app`
  - `services.crm_service.main:app`
  - `services.intelligence_service.main:app`
  - `services.campaign_service.main:app`
  - `services.channel_service.main:app`

## Current MVP State
- Service-specific FastAPI apps are scaffolded.
- Acquisition service has first-class Google Maps source/job/location/raw-profile models.
- CRM ingestion is now reusable through `backend/services/crm_service/ingestion.py`.
- Phone-first identity is partially upgraded to support phone-only contacts and lead promotion.
- Dedicated Celery queues exist for acquisition, intelligence, campaign, and channel extraction.

## Post-MVP Direction
- Move from shared-table discipline to service-owned schemas.
- Replace implicit DB coupling with APIs and events.
- Add `analytics-service`.
