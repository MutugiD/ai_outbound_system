.PHONY: help up down restart logs migrate shell api worker scheduler

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Infrastructure ──────────────────────────────────────────────────

up: ## Start all infrastructure (db, redis, minio)
	docker compose up -d db redis minio

down: ## Stop all containers
	docker compose down

restart: ## Restart infrastructure
	docker compose restart db redis minio

logs: ## Tail container logs
	docker compose logs -f

# ── Database ─────────────────────────────────────────────────────────

migrate: ## Run Alembic migrations
	cd backend && alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create msg="add users table")
	cd backend && alembic revision --autogenerate -m "$(msg)"

migrate-downgrade: ## Rollback last migration
	cd backend && alembic downgrade -1

# ── Backend ───────────────────────────────────────────────────────────

install: ## Install Python dependencies
	cd backend && pip install -e ".[dev]"

api: ## Run API server with hot reload
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker: ## Run Celery worker
	cd backend && celery -A app.workers.celery_app worker -l info -Q scraping,enrichment,ai,outreach,inbox,default -c 4

scheduler: ## Run Celery beat scheduler
	cd backend && celery -A app.workers.celery_app beat -l info

# ── Testing ──────────────────────────────────────────────────────────

test: ## Run all tests
	cd backend && pytest -xvs

test-cov: ## Run tests with coverage
	cd backend && pytest --cov=app --cov-report=term-missing

# ── Database shell ────────────────────────────────────────────────────

shell: ## Open psql shell
	docker compose exec db psql -U outbound -d outbound_os

redis-cli: ## Open Redis CLI
	docker compose exec redis redis-cli