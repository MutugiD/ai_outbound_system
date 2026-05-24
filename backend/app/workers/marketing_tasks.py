"""Marketing Celery tasks: async audience discovery with team quotas."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime

from sqlalchemy import select

from app.models.marketing import AudienceScanJob, AudienceSignal, MarketingUsageDaily
from app.models.team import Team
from app.security_utils import sanitize_log
from app.services.marketing.audience_sources import scan_hacker_news, scan_reddit
from app.services.marketing.budgets import get_marketing_settings, remaining_signals_budget
from app.workers.base_task import BaseTask
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.marketing_tasks.run_audience_scan",
    queue="marketing",
)
def run_audience_scan(self, job_id: str, **kwargs):
    """Run an audience scan job and persist AudienceSignal records.

    Hard caps enforced:
      - daily_audience_signals_max (stop early)
      - per_scan_max_results (cap per source run)
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except Exception:
        logger.warning("Invalid scan job id: %s", sanitize_log(job_id))
        return {"status": "invalid_job_id"}

    session = self._get_sync_session()
    try:
        job = session.get(AudienceScanJob, job_uuid)
        if not job:
            logger.warning("AudienceScanJob %s not found", sanitize_log(job_id))
            return {"status": "not_found"}

        team = session.get(Team, job.team_id)
        if not team:
            job.status = "failed"
            job.error = "Team not found"
            job.completed_at = datetime.utcnow()
            session.add(job)
            session.commit()
            return {"status": "failed", "error": "team_not_found"}

        job.status = "running"
        job.started_at = datetime.utcnow()
        session.add(job)
        session.commit()

        today = date.today()
        usage = (
            session.execute(
                select(MarketingUsageDaily).where(
                    MarketingUsageDaily.team_id == team.id, MarketingUsageDaily.day == today
                )
            )
            .scalars()
            .first()
        )
        if not usage:
            usage = MarketingUsageDaily(team_id=team.id, day=today)
            session.add(usage)
            session.commit()

        remaining = remaining_signals_budget(team, usage)
        if remaining <= 0:
            job.status = "completed"
            job.stop_reason = "quota_reached"
            job.completed_at = datetime.utcnow()
            usage.scans_completed += 1
            usage.updated_at = datetime.utcnow()
            session.add_all([job, usage])
            session.commit()
            return {"status": "completed", "stop_reason": "quota_reached", "signals_saved": 0}

        params = dict(job.params or {})
        platforms = list(params.get("platforms") or ["reddit", "hn"])
        keywords = list(params.get("keywords") or [])
        subreddits = list(params.get("subreddits") or [])
        timeframe = str(params.get("timeframe") or "week")
        per_scan_max_results = int(params.get("per_scan_max_results") or 25)

        # Clamp to team budget default
        marketing = get_marketing_settings(team)
        budgets = marketing.get("budgets") or {}
        per_scan_budget = int(budgets.get("per_scan_max_results") or per_scan_max_results)
        per_scan_max_results = max(1, min(per_scan_max_results, per_scan_budget))

        found = 0
        kept = 0
        deduped = 0

        for platform in platforms:
            if remaining <= 0:
                break

            platform_norm = str(platform).lower().strip()
            scan_results: list[dict] = []

            try:
                if platform_norm == "reddit":
                    scan_results = asyncio.run(
                        scan_reddit(
                            keywords=keywords,
                            subreddits=subreddits,
                            timeframe=timeframe,
                            per_scan_max_results=per_scan_max_results,
                        )
                    )
                elif platform_norm in ("hn", "hackernews", "hacker_news"):
                    scan_results = asyncio.run(
                        scan_hacker_news(
                            keywords=keywords,
                            per_scan_max_results=per_scan_max_results,
                            recency_days=7,
                        )
                    )
                else:
                    logger.info("Skipping unsupported platform: %s", sanitize_log(platform_norm))
                    continue
            except Exception:
                logger.exception("Scan failed for platform=%s job=%s", sanitize_log(platform_norm), job.id)
                continue

            scan_results = [r for r in scan_results if r.get("source_url")]
            found += len(scan_results)

            urls = [str(r["source_url"]) for r in scan_results if r.get("source_url")]
            if not urls:
                continue

            existing = set(
                session.execute(
                    select(AudienceSignal.source_url).where(
                        AudienceSignal.team_id == team.id,
                        AudienceSignal.platform == platform_norm,
                        AudienceSignal.source_url.in_(urls),
                    )
                )
                .scalars()
                .all()
            )

            for r in scan_results:
                if remaining <= 0:
                    break

                url = str(r.get("source_url") or "")
                if not url or url in existing:
                    deduped += 1
                    continue

                signal = AudienceSignal(
                    team_id=team.id,
                    platform=platform_norm,
                    source_url=url[:2048],
                    external_id=(str(r.get("external_id"))[:255] if r.get("external_id") else None),
                    title=(str(r.get("title"))[:512] if r.get("title") else None),
                    body_excerpt=(str(r.get("body_excerpt"))[:2048] if r.get("body_excerpt") else None),
                    author=(str(r.get("author"))[:255] if r.get("author") else None),
                    community=(str(r.get("community"))[:255] if r.get("community") else None),
                    engagement=(int(r.get("engagement")) if r.get("engagement") is not None else None),
                    matched_keywords=list(r.get("matched_keywords") or []),
                    intent_label=(str(r.get("intent_label"))[:50] if r.get("intent_label") else None),
                    confidence=(float(r.get("confidence")) if r.get("confidence") is not None else None),
                    extra=dict(r.get("metadata") or {}),
                    source_created_at=r.get("source_created_at"),
                )
                session.add(signal)
                kept += 1
                remaining -= 1
                usage.signals_saved += 1
                existing.add(url)

            session.commit()

        job.found_count = found
        job.kept_count = kept
        job.deduped_count = deduped

        if remaining <= 0:
            job.stop_reason = "quota_reached"

        job.status = "completed"
        job.completed_at = datetime.utcnow()
        usage.scans_completed += 1
        usage.updated_at = datetime.utcnow()

        session.add_all([job, usage])
        session.commit()
        return {
            "status": "completed",
            "found": found,
            "saved": kept,
            "deduped": deduped,
            "stop_reason": job.stop_reason,
        }
    except Exception as exc:
        try:
            job = session.get(AudienceScanJob, job_uuid)
            if job:
                job.status = "failed"
                job.error = str(exc)[:2000]
                job.completed_at = datetime.utcnow()
                session.add(job)
                session.commit()
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()
