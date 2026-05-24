"""AI-related Celery tasks.

Implements the async AI/service-layer work behind enrichment, scoring, research,
and reply classification.
"""

import asyncio
import logging
import uuid

from sqlalchemy import select

from app.database import async_session
from app.models.company import Company
from app.models.lead import Lead
from app.services.ai.audit_service import AuditService
from app.services.ai.llm_service import LLMService
from app.services.ai.reply_classifier import ReplyClassifier
from app.services.ai.research_agent import ResearchAgent
from app.services.ai.scoring_service import ScoringService
from app.services.ai.signal_detector import SignalDetector
from app.workers.base_task import BaseTask
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.ai_tasks.detect_buying_signals",
    queue="ai",
)
def detect_buying_signals(self, lead_id: str, method: str = "both", model: str | None = None, **kwargs):
    """Detect buying signals for a lead and persist BuyingSignal rows."""

    async def _run():
        async with async_session() as db:
            llm = LLMService() if method in ("llm", "both") else None
            detector = SignalDetector(llm_service=llm)
            signals = await detector.detect_signals(uuid.UUID(lead_id), db, method=method, model=model)
            await db.commit()
            return {"lead_id": lead_id, "signals_detected": len(signals), "signal_ids": [str(s.id) for s in signals]}

    logger.info("Task detect_buying_signals started — lead_id=%s", lead_id)
    result = _run_async(_run())
    logger.info("Task detect_buying_signals completed — lead_id=%s", lead_id)
    return result


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.ai_tasks.calculate_lead_score",
    queue="ai",
)
def calculate_lead_score(self, lead_id: str, **kwargs):
    """Calculate and persist a composite lead score for a lead."""

    async def _run():
        async with async_session() as db:
            svc = ScoringService(db)
            score = await svc.calculate_score(uuid.UUID(lead_id))
            await db.commit()
            return {
                "lead_id": lead_id,
                "total_score": score.total_score,
                "score_band": score.score_band,
            }

    logger.info("Task calculate_lead_score started — lead_id=%s", lead_id)
    result = _run_async(_run())
    logger.info("Task calculate_lead_score completed — lead_id=%s", lead_id)
    return result


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.ai_tasks.generate_research_brief",
    queue="ai",
)
def generate_research_brief(self, lead_id: str, **kwargs):
    """Generate and persist an AI research brief for a lead."""

    async def _run():
        async with async_session() as db:
            agent = ResearchAgent()
            report = await agent.generate_research(uuid.UUID(lead_id), db)
            await db.commit()
            return {"lead_id": lead_id, "report_id": str(report.id), "version": report.version, "model_used": report.model_used}

    logger.info("Task generate_research_brief started — lead_id=%s", lead_id)
    result = _run_async(_run())
    logger.info("Task generate_research_brief completed — lead_id=%s", lead_id)
    return result


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.ai_tasks.audit_website",
    queue="ai",
)
def audit_website(self, lead_id: str, **kwargs):
    """Run a website audit for a lead's company (if domain exists)."""

    async def _run():
        async with async_session() as db:
            lead = (await db.execute(select(Lead).where(Lead.id == uuid.UUID(lead_id)))).scalar_one_or_none()
            if not lead or not lead.company_id:
                return {"lead_id": lead_id, "status": "skipped", "reason": "no_company"}

            company = (await db.execute(select(Company).where(Company.id == lead.company_id))).scalar_one_or_none()
            if not company or not company.domain:
                return {"lead_id": lead_id, "status": "skipped", "reason": "no_domain"}

            svc = AuditService(db)
            audit = await svc.audit_website(company.id, company.domain)
            await db.commit()
            return {"lead_id": lead_id, "company_id": str(company.id), "audit_id": str(audit.id), "website_score": audit.website_score}

    logger.info("Task audit_website started — lead_id=%s", lead_id)
    result = _run_async(_run())
    logger.info("Task audit_website completed — lead_id=%s", lead_id)
    return result


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.ai_tasks.audit_company_website",
    queue="ai",
)
def audit_company_website(self, company_id: str, domain: str | None = None, **kwargs):
    """Run a website audit for a company (domain optional; falls back to company.domain)."""

    async def _run():
        async with async_session() as db:
            company = (await db.execute(select(Company).where(Company.id == uuid.UUID(company_id)))).scalar_one_or_none()
            if not company:
                return {"company_id": company_id, "status": "not_found"}

            audit_domain = domain or company.domain
            if not audit_domain:
                return {"company_id": company_id, "status": "skipped", "reason": "no_domain"}

            svc = AuditService(db)
            audit = await svc.audit_website(company.id, audit_domain)
            await db.commit()
            return {"company_id": company_id, "audit_id": str(audit.id), "website_score": audit.website_score}

    logger.info("Task audit_company_website started — company_id=%s", company_id)
    result = _run_async(_run())
    logger.info("Task audit_company_website completed — company_id=%s", company_id)
    return result


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.ai_tasks.classify_reply",
    queue="ai",
)
def classify_reply(self, reply_id: str, **kwargs):
    """Classify an inbound reply and persist ReplyClassification rows."""

    async def _run():
        async with async_session() as db:
            classifier = ReplyClassifier()
            classification = await classifier.classify(uuid.UUID(reply_id), db)
            await db.commit()
            return {
                "reply_id": reply_id,
                "classification_id": str(classification.id),
                "classification": classification.classification,
                "subtype": classification.subtype,
                "confidence": float(classification.confidence),
            }

    logger.info("Task classify_reply started — reply_id=%s", reply_id)
    result = _run_async(_run())
    logger.info("Task classify_reply completed — reply_id=%s", reply_id)
    return result
