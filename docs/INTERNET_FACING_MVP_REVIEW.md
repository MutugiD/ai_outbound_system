# AI Outbound OS — Internet-facing MVP review (security-first)

Date: 2026-05-24  
Branch: `codex/internet-facing-mvp-security`

## Current setup (what’s in the repo today)

### Backend
- FastAPI app in `backend/app/main.py` with `/api/v1/*` routers and `GET /health`.
- DB layer: SQLModel + SQLAlchemy async (`backend/app/database.py`) with Alembic migrations in `backend/alembic`.
- Async jobs: Celery + Redis (`backend/app/workers/*`) with a Beat scheduler (`backend/app/workers/celery_app.py`).
- Core domains (models): leads/companies/contacts, enrichment records, campaigns/enrollments/steps, outreach messages, replies + reply classifications, follow-up tasks, notifications, API keys, email accounts.

### Frontend
- Present in `frontend/` (not fully reviewed here for auth wiring). The backend now enforces JWT on most routes, so the frontend must attach `Authorization: Bearer <access_token>`.

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
- `website_adapter.py` now validates URLs + validates redirect destinations; blocks localhost/private/metadata targets and enforces scheme safety.

### P1 — Secrets & sensitive data (DONE)
- Server-side encryption-at-rest implemented for provider secrets stored in DB (`backend/app/crypto.py`).
- API keys: stop treating `APIKey.key_hash` as “encrypted”; store:
  - `key_hash` as keyed HMAC hash for lookup/dedup,
  - `ciphertext` for the encrypted secret,
  - `last4`, `key_id`, `rotated_at` fields for clarity/rotation.
- Email accounts: renamed token columns to `*_ciphertext` and added `*_key_id` + `rotated_at`.

### MVP enablement — Async jobs become real (DONE)
- Enrichment/signal/score/research/audit workloads now queue real Celery tasks and return task IDs.
- Added task status endpoint: `GET /api/v1/tasks/{task_id}`.
- Follow-up processor runs on Celery Beat every 5 minutes.

### MVP loop #2 — Campaigns → message generation → sending (DONE for Resend)
- Outbound provider integration implemented for **Resend**:
  - `send_message` task sends email via Resend REST API and stores provider IDs/status.
  - Campaign enrollments due processor runs every minute and auto-sends when `campaign.approval_mode == "auto"`.
  - Manual mode: approve then `POST /api/v1/outreach/messages/{message_id}/send`.

### MVP loop #3 — Inbox → replies → classification → follow-ups → analytics (DONE for Resend inbound)
- Resend webhooks endpoint verifies Svix signatures: `POST /api/v1/webhooks/resend`.
- Handles:
  - Delivery lifecycle events (`email.delivered/opened/clicked/bounced/failed/...`) → updates `OutreachMessage`.
  - Inbound `email.received` → fetches body via Receiving API, creates `Reply`, enqueues classification + follow-up automation via Celery.

### PENDING / known gaps
- Frontend auth wiring: frontend must implement login + token storage + attach `Authorization` header for protected API calls.
- Inbox polling (`check_inboxes`) remains placeholder; the intended MVP posture is webhook-first (Resend inbound), but if you need IMAP/Graph polling, that’s still future work.
- Webhook idempotency is implemented for inbound replies via `Reply.provider_inbound_id`; delivery events are idempotent by overwriting message status fields, but there’s no persistent “event id” store yet.
- Production hardening still recommended:
  - restrict `CORS_ORIGINS` to real domains (no `*`),
  - run behind TLS (so HSTS is enabled),
  - central structured logging + secret redaction,
  - DB migrations in deploy (ensure `alembic upgrade head` runs before app start).

## Security review (detailed)

### AuthN/AuthZ
- ✅ Bearer token parsing is centralized and consistent.
- ✅ Refresh tokens are rejected for API access (`type != "access"`).
- ✅ Protected routes return `401` when auth is missing/invalid (not FastAPI’s default `422`).
- ⚠️ Ensure all newly-added routers follow `Depends(get_current_user)` (webhooks are intentionally exempt and instead use signature verification).

### SSRF / outbound fetch
- ✅ URL validation + redirect validation for website crawling is in place.
- ⚠️ Any future adapters that fetch user-supplied URLs must reuse the same validation helpers.

### Rate limiting / cost control
- ✅ Rate limits exist for auth/scraping/enrichment.
- ⚠️ Consider adding limits to outbound send + webhook endpoints if traffic is expected to spike (webhooks already have a moderate limit).

### Secrets handling
- ✅ Provider secrets stored in DB are encrypted-at-rest.
- ✅ Hashing is keyed (HMAC) for lookup/dedup; ciphertext is stored separately.
- ⚠️ Key rotation is supported structurally (`key_id`, `rotated_at`) but operational runbooks are not yet written.

### Webhooks
- ✅ Resend webhooks are signature verified using Svix headers (`svix-id`, `svix-timestamp`, `svix-signature`).
- ✅ Inbound replies are deduped by provider inbound ID.
- ⚠️ Consider persisting processed event IDs for delivery events too if you need strict idempotency guarantees.

## Ops notes (how to run/verify locally)

Backend (example):
- `cd backend`
- Run migrations: `alembic upgrade head`
- Start stack (dev): `docker compose --profile dev up -d`

Resend configuration:
- `RESEND_API_KEY` must be set.
- `OUTREACH_FROM_EMAIL` must be a verified sending identity.
- Set `OUTREACH_REPLY_TO` to include the message UUID for inbound mapping, e.g. `replies+{message_id}@yourdomain.com`.
- Configure Resend webhook events to hit `POST /api/v1/webhooks/resend` and set `RESEND_WEBHOOK_SECRET`.

