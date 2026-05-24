"""Celery application configuration with Redis broker, task routes, and beat schedule."""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "ai_outbound_os",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# ── Serializer & result settings ──────────────────────────────────────────
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,
    timezone="UTC",
    enable_utc=True,
)

# ── Task routes: map task name prefixes to queues ──────────────────────────
celery_app.conf.task_routes = {
    "app.workers.scraping_tasks.*": {"queue": "scraping"},
    "app.workers.enrichment_tasks.*": {"queue": "enrichment"},
    "app.workers.ai_tasks.*": {"queue": "ai"},
    "app.workers.outreach_tasks.*": {"queue": "outreach"},
    "app.workers.inbox_tasks.*": {"queue": "inbox"},
}

# ── Default queue for uncategorized tasks ──────────────────────────────────
celery_app.conf.task_default_queue = "default"

# ── Beat schedule: periodic tasks ─────────────────────────────────────────
celery_app.conf.beat_schedule = {
    "check-inboxes": {
        "task": "app.workers.inbox_tasks.check_inboxes",
        "schedule": crontab(minute="*/2"),  # every 2 minutes
    },
    "daily-lead-discovery": {
        "task": "app.workers.scraping_tasks.run_daily_lead_discovery",
        "schedule": crontab(hour=6, minute=0),  # 06:00 UTC daily
    },
    "process-follow-ups": {
        "task": "app.workers.outreach_tasks.process_follow_ups_all_teams",
        "schedule": crontab(minute="*/5"),  # every 5 minutes
    },
    "process-campaigns": {
        "task": "app.workers.outreach_tasks.process_due_campaign_enrollments_all_teams",
        "schedule": crontab(minute="*/1"),  # every minute
    },
}

# ── Auto-discover tasks from registered modules ────────────────────────────
celery_app.autodiscover_tasks(
    [
        "app.workers.scraping_tasks",
        "app.workers.enrichment_tasks",
        "app.workers.ai_tasks",
        "app.workers.outreach_tasks",
        "app.workers.inbox_tasks",
    ]
)
