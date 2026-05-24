# AI Outbound OS — Security review guide (internet-facing MVP)

Date: 2026-05-24

## Current setup (what’s in the repo today)

### Backend
- FastAPI app in `backend/app/main.py` with `/api/v1/*` routers and `GET /health`.
- DB layer: SQLModel + SQLAlchemy async (`backend/app/database.py`) with Alembic migrations in `backend/alembic`.
- Async jobs: Celery + Redis (`backend/app/workers/*`) with a Beat scheduler (`backend/app/workers/celery_app.py`).
- Core domains (models): leads/companies/contacts, enrichment records, campaigns/enrollments/steps, outreach messages, replies + reply classifications, follow-up tasks, notifications, API keys, email accounts.

### Frontend
- Present in `frontend/`. The backend enforces JWT on most routes, so the frontend must attach `Authorization: Bearer <access_token>`.

### Deployment
- `docker-compose.yml` supports separate `dev` vs `prod` profiles (prod is image-based, deploy workflow pulls images).
- GitHub deploy workflow uses `GET /health` and `--profile prod`.

## What’s implemented vs pending (mapped to the MVP plan)

### P0 — Authentication & Authorization (DONE)
- JWT bearer tokens standardized to the HTTP `Authorization` header across protected routes.
- One shared dependency for auth enforcement (`backend/app/dependencies.py`), including claim checks (`type == "access"`, `sub` required, exp enforced).
- `/api/v1/auth/me` uses real auth dependency (no stub).
- Enrichment endpoints require auth and enforce team scoping consistently.

### P0/P1 — API hardening (DONE)
- Security headers middleware at API layer: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and HSTS when HTTPS.
- Rate limiting added (Redis-backed with in-memory fallback) and applied to auth + scraping + enrichment endpoints.

### P1 — SSRF & crawler safety (DONE)
- `website_adapter.py` validates URLs + redirect destinations; blocks localhost/private/metadata targets and enforces scheme safety.

### P1 — Secrets & sensitive data (DONE)
- Server-side encryption-at-rest implemented for provider secrets stored in DB (`backend/app/crypto.py`).
- API keys: store keyed HMAC hash for lookup/dedup + ciphertext separately; include `last4`, `key_id`, `rotated_at` fields for clarity/rotation.
- Email accounts: token columns use `*_ciphertext` and include `*_key_id` + `rotated_at`.

### MVP enablement — Async jobs become real (DONE)
- Enrichment/signal/score/research/audit workloads queue real Celery tasks and return task IDs.
- Task status endpoint: `GET /api/v1/tasks/{task_id}`.
- Follow-up processor runs on Celery Beat every 5 minutes.

### MVP loop #2 — Campaigns → message generation → sending (DONE for Brevo/Resend)
- Outbound provider integration supports **Brevo (primary)** with **Resend (fallback)**:
  - `send_message` selects Brevo when `BREVO_API_KEY` is configured; otherwise uses Resend when `RESEND_API_KEY` is configured.
  - Campaign enrollments due processor runs every minute and auto-sends when `campaign.approval_mode == "auto"`.
  - Manual mode: approve then `POST /api/v1/outreach/messages/{message_id}/send`.

### MVP loop #3 — Inbox → replies → classification → follow-ups → analytics (DONE for webhooks)
- Resend webhooks endpoint verifies Svix signatures: `POST /api/v1/webhooks/resend`.
- Brevo webhooks endpoint verifies a configured bearer token: `POST /api/v1/webhooks/brevo`.
- Handles:
  - Delivery lifecycle events (`email.delivered/opened/clicked/bounced/failed/...`) → updates `OutreachMessage`.
  - Inbound replies → creates `Reply`, enqueues classification + follow-up automation via Celery.

### Marketing + Outreach (multi-client) — Brand Brain → Signals → Drafts → Analytics (PARTIAL)
This repo supports onboarding many clients/teams while keeping scraping predictable and safe:
- **Source of truth**: per-team config and hard caps live in `Team.settings["marketing"]`.
- **Hard quotas (server-enforced)**:
  - `daily_audience_signals_max`
  - `daily_scan_requests_max`
  - `per_scan_max_results`
- **Async audience discovery**: scans are enqueued via HTTP and executed by Celery on a dedicated `marketing` queue. This avoids synchronous scraping that won't scale across many clients with different N/day requirements.

Implemented APIs (team-scoped, auth required):
- `PUT /api/v1/marketing/settings` — merge into `Team.settings["marketing"]`
- `POST /api/v1/marketing/brand-brain/derive` — website → draft Brand Brain (stored by default)
- `POST /api/v1/marketing/audience-scans` — enqueue scan (returns `job_id` + `task_id`)
- `GET /api/v1/marketing/audience-scans/{job_id}` — job status + counters
- `GET /api/v1/marketing/audience-signals` — signals list (pagination + filters)
- `POST /api/v1/marketing/post-drafts/generate` — drafts from Brand Brain + optional signal context
- `GET /api/v1/marketing/analytics/overview` — per-day usage counters

Notes:
- Current sources: **Reddit + Hacker News** (X/LinkedIn are placeholders for later).
- Draft generation uses a deterministic template fallback (works without LLM keys).

### PENDING / known gaps
- Webhook event idempotency for delivery events (inbound is deduped by provider inbound ID where available).
- Production hardening still recommended: strict `CORS_ORIGINS`, TLS, structured logging + secret redaction, and running `alembic upgrade head` before app start.

## Ops notes (how to run/verify locally)

Backend (example):
- `cd backend`
- Run migrations: `alembic upgrade head`
- Start stack (dev): `docker compose --profile dev up -d`

Brevo configuration (primary):
- `BREVO_API_KEY` must be set.
- Configure Brevo webhooks to hit `POST /api/v1/webhooks/brevo` and set a bearer token (store it in `BREVO_WEBHOOK_BEARER_TOKEN`).

Resend configuration (fallback / secondary):
- `RESEND_API_KEY` must be set.
- `OUTREACH_FROM_EMAIL` must be a verified sending identity.
- Set `OUTREACH_REPLY_TO` to include the message UUID for inbound mapping, e.g. `replies+{message_id}@yourdomain.com`.
- Configure Resend webhook events to hit `POST /api/v1/webhooks/resend` and set `RESEND_WEBHOOK_SECRET`.

## Deployment versioning & rollback

This repo deploys **immutable image tags** (SemVer tags like `v0.1.1`).

### Deploy a release
- Create and push a tag on `main` (example):
  - `git tag v0.1.1`
  - `git push origin v0.1.1`
- This triggers `.github/workflows/deploy.yml` to build/push and deploy images tagged `v0.1.1`.

### Rollback
- GitHub Actions → **Deploy** workflow → run manually and set:
  - `image_tag` to an older tag (example: `v0.1.0`)
  - `environment` as needed

### Verify what’s running
- Backend exposes `GET /version` returning:
  - `app_version` (deploy tag when built by workflow)
  - `git_sha`
