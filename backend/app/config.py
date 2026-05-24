"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import List

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration. All values can be overridden via env vars."""

    PROJECT_NAME: str = "AI Outbound OS"
    VERSION: str = "0.1.0"
    APP_VERSION: str = ""
    GIT_SHA: str = ""
    APP_ENV: str = "development"
    DEBUG: bool = False

    # ── Database ────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://outbound:outbound@localhost:5432/outbound_os"
    DATABASE_URL_SYNC: str = Field(
        default="postgresql+psycopg2://outbound:outbound@localhost:5432/outbound_os",
        validation_alias=AliasChoices("DATABASE_URL_SYNC", "SYNC_DATABASE_URL"),
    )
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # ── Redis ───────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Auth / JWT ──────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production-32chars!!"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── LLM ─────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # ── Enrichment providers ────────────────────────────────────────────
    APOLLO_API_KEY: str = ""
    HUNTER_API_KEY: str = ""
    PDL_API_KEY: str = ""
    DROPCONTACT_API_KEY: str = ""
    BUILTWITH_API_KEY: str = ""

    # ── Email providers ─────────────────────────────────────────────────
    # ── Email Provider ──────────────────────────────────────────────────
    # Brevo (primary): higher free daily volume.
    BREVO_API_KEY: str = ""
    # Configure Brevo webhooks to send `Authorization: Bearer <token>`.
    BREVO_WEBHOOK_BEARER_TOKEN: str = ""

    # Resend (secondary): Svix-signed webhooks + Receiving API.
    RESEND_API_KEY: str = ""
    RESEND_WEBHOOK_SECRET: str = ""
    RESEND_WEBHOOK_TOLERANCE_SECONDS: int = 300

    # Other providers (optional / future)
    SENDGRID_API_KEY: str = ""
    SMARTLEAD_API_KEY: str = ""

    # Outbound email identity
    OUTREACH_FROM_EMAIL: str = ""
    OUTREACH_FROM_NAME: str = ""
    OUTREACH_REPLY_TO: str = ""

    # ── Gmail Inbox (IMAP polling for replies) ─────────────────────────
    GMAIL_INBOX_EMAIL: str = ""
    GMAIL_INBOX_APP_PASSWORD: str = ""
    INBOX_POLL_INTERVAL_MINUTES: int = 2
    AUTO_RESPOND_ENABLED: bool = False  # Start disabled for safety

    # ── Scraping / Search ───────────────────────────────────────────────
    SERPAPI_KEY: str = ""
    GOOGLE_PAGESPEED_KEY: str = ""

    # ── Communication ──────────────────────────────────────────────────
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""

    # ── Object Storage (MinIO local — NO AWS needed) ───────────────────
    # Uses MinIO in docker-compose, NOT AWS S3.
    # For production, you CAN use S3-compatible services (AWS, GCS, etc.)
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minio"
    S3_SECRET_KEY: str = "minio123"
    S3_BUCKET: str = "outbound-os"

    # ── Celery ──────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── CORS ────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # ── Encryption ──────────────────────────────────────────────────────
    ENCRYPTION_KEY: str = "change-me-32-bytes-encryption-key!"
    ENCRYPTION_KEY_ID: str = "v1"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Module-level singleton for convenient imports: `from app.config import settings`
settings = get_settings()
