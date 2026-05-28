# AI Runtime

## MVP Direction
The intelligence service is the AI boundary. It will absorb and normalize the current AI helpers from the monolith instead of leaving AI logic scattered across routes and workers.

## Planned Components
- `InferenceRouter`
- `OllamaProvider`
- task-specific model policies
- structured JSON validation
- retry and correction handling
- lead/conversation context builder

## Initial Service Responsibilities
- enrich promoted leads
- classify source quality
- assign score bands
- recommend an offer
- generate WhatsApp opener drafts
- classify inbound replies
- draft routine responses

## Guardrails
- AI output must be schema-validated
- low-confidence outputs route to review
- automated sends are policy-gated by campaign and channel services

## What Is Still Monolith-Bound
- existing `app/services/ai/*` modules
- reply classification helpers
- personalization engine

These are intentionally reused first, then extracted behind the intelligence service API/task boundary.
