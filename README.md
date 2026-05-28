# AI Outbound Operating System

AI-powered outbound sales platform — lead intelligence, multi-channel outreach, campaign automation, and CRM in one system.

Built with FastAPI + SQLModel (backend), React 19 + Vite + Tailwind CSS (frontend), PostgreSQL + Redis + MinIO (infrastructure), and Celery (async tasks).

## Quick Start

```bash
# Start infrastructure (PostgreSQL, Redis, MinIO)
docker compose up -d db redis minio

# Backend
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload

# Migrations
alembic upgrade head

# Frontend
cd frontend
npm install
npm run dev

# Run tests
cd backend && pytest tests/ -v
cd frontend && npm run build  # type-check + build
```

| Service | URL |
|---------|-----|
| API Docs | http://localhost:8000/docs |
| Frontend | http://localhost:5173 |
| MinIO Console | http://localhost:9001 |
| Evolution API (WhatsApp) | http://localhost:8080 |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Frontend (React 19 + Vite + Tailwind CSS)         │
│  6 pages: Dashboard, Campaigns, Leads, Agents,     │
│  Analytics, Settings — Wakili-Mkononi navy/gold    │
├─────────────────────────────────────────────────────┤
│  Backend (FastAPI + SQLModel + Celery)             │
│  78 endpoints, 28 tables, 91 unit tests            │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ Source    │ │ Lead     │ │ Campaign         │   │
│  │ Adapters  │ │ Pipeline │ │ Engine           │   │
│  │ CSV/Reddit│ │ Normalize│ │ Personalization  │   │
│  │ Website/  │ │ Dedup    │ │ Scoring/Signals  │   │
│  │ LinkedIn  │ │ Enrich   │ │ Website Audit    │   │
│  └──────────┘ └──────────┘ └──────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ Channel Service (WhatsApp via Evolution API)  │   │
│  │ Outbound send, inbound webhooks, sessions    │   │
│  └──────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│  Infrastructure: PostgreSQL + pgvector, Redis,      │
│  MinIO (S3-compatible, no AWS needed), Celery       │
└─────────────────────────────────────────────────────┘
```

## Features

- **Lead Intelligence** — CSV import, Reddit scraping, website crawling, LinkedIn sourcing. Normalization, deduplication, enrichment (Apollo, Hunter, BuiltWith), buying signal detection (20 categories), lead scoring (8 dimensions), website audit
- **Campaign Engine** — Multi-channel outreach (email, LinkedIn, phone, WhatsApp), personalization strategies (5 types × 4 tones), message templates, response classification, follow-up automation
- **WhatsApp Channel** — Outbound/inbound WhatsApp messaging via Evolution API (Baileys). Session management (QR code pairing), webhook-based inbound replies, delivery receipts. No official Business API required.
- **Auth & Security** — JWT auth with email verification, CSRF protection, security headers, rate limiting
- **Dashboard** — KPI metrics, pipeline overview with progress bars, trend charts, activity feed

## Project Structure

```
ai_outbound_system/
├── backend/                 # FastAPI + SQLModel + Celery
│   ├── app/
│   │   ├── api/           # 78 REST endpoints
│   │   ├── core/          # Config, auth, security
│   │   ├── models/        # 28 SQLModel tables
│   │   ├── services/      # Business logic
│   │   │   ├── scraping/  # Source adapters (CSV, Reddit, Website, LinkedIn)
│   │   │   ├── leads/     # Pipeline: normalize, dedup, enrich, score, signals
│   │   │   ├── campaigns/ # Campaign engine, personalization, outreach
│   │   │   └── whatsapp/ # Evolution API client, session management
│   │   └── schemas/       # Pydantic models
│   ├── tests/             # 91 unit tests + e2e pipeline tests
│   ├── alembic/            # Database migrations
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/               # React 19 + Vite + TypeScript + Tailwind
│   ├── src/
│   │   ├── components/    # Common UI, dashboard, campaigns, leads, agents
│   │   ├── pages/          # 6 pages
│   │   ├── stores/         # Zustand state management
│   │   ├── services/       # API client
│   │   └── types/          # TypeScript types
│   ├── Dockerfile          # Nginx production build
│   └── package.json
├── docker-compose.yml      # PostgreSQL, Redis, MinIO, API
├── Makefile                # Common commands
└── .github/workflows/      # CI/CD
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, SQLModel, SQLAlchemy, Alembic |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 16 (pgvector) |
| Object Storage | MinIO (S3-compatible, no AWS needed) |
| Frontend | React 19, Vite 6, TypeScript, Tailwind CSS 4 |
| State | Zustand |
| LLM | OpenAI, Anthropic, OpenRouter + local Ollama fallback |

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in values. Key variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | JWT signing key |
| `S3_ENDPOINT_URL` | MinIO endpoint (default: `http://localhost:9000`) |
| `OPENAI_API_KEY` | OpenAI API key for LLM features |
| `EVOLUTION_API_URL` | Evolution API URL (default: `http://localhost:8080`) |
| `EVOLUTION_API_KEY` | Evolution API authentication key |

## Docker

```bash
# Development (infrastructure only)
docker compose up -d db redis minio

# Full stack (including WhatsApp)
docker compose up -d db redis minio evolution-api

# Production (with Nginx frontend)
docker compose --profile prod up -d
```

## Versioning, Deployments, Rollback

This repo uses **immutable image tags** for deployments.

### Release deploy (recommended)
- Create a SemVer tag like `v0.1.1` on `main` and push it:
  - `git tag v0.1.1`
  - `git push origin v0.1.1`
- This triggers `.github/workflows/deploy.yml` to build/push and deploy images tagged `v0.1.1`.

### Rollback
- GitHub Actions → **Deploy** workflow → run manually and set:
  - `image_tag` to a prior release tag (e.g. `v0.1.0`)
  - `environment` as needed

### Verify what’s running
- Backend exposes `GET /version` which returns `app_version` and `git_sha`.

## License

Proprietary — All rights reserved.
