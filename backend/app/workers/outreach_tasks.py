"""Outreach Celery tasks — message scheduling, campaign step progression, and follow-up processing."""

import logging
import uuid
from datetime import datetime

from app.workers.celery_app import celery_app
from app.workers.base_task import BaseTask
from app.database import async_session

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.outreach_tasks.send_message",
    queue="outreach",
)
def send_message(self, message_id: str, **kwargs):
    """Send an outreach message via the configured email provider."""
    import asyncio
    from sqlalchemy import select
    from app.models.message import OutreachMessage
    from app.services.email.email_service import EmailService

    async def _send():
        async with async_session() as db:
            svc = EmailService(db)
            result = await svc.send_message(uuid.UUID(message_id))
            return {"message_id": message_id, "status": result.status}

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_send())
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.outreach_tasks.send_pending_emails",
    queue="outreach",
)
def send_pending_emails(**kwargs):
    """Send all approved messages that are due."""
    import asyncio
    from app.services.email.email_service import EmailService

    async def _send():
        async with async_session() as db:
            service = EmailService(db)
            result = await service.send_pending_messages(limit=50)
            logger.info("Sent batch: %s", result)
            return result

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_send())
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.outreach_tasks.advance_campaign_enrollments",
    queue="outreach",
)
def advance_campaign_enrollments(**kwargs):
    """Advance campaign enrollments whose next_step_at has passed."""
    import asyncio
    from datetime import timezone
    from app.services.campaign_service import CampaignService

    async def _advance():
        async with async_session() as db:
            service = CampaignService(db)
            # Get all teams with active campaigns — use a zero UUID for now
            # In production, iterate over all active team IDs
            from sqlalchemy import select as sa_select
            from app.models.campaign import Campaign

            result = await db.execute(sa_select(Campaign).where(Campaign.status == "active"))
            campaigns = list(result.scalars().all())

            results = []
            for campaign in campaigns:
                enrollments = await service.get_enrollments_due_now(campaign.id)
                for enrollment in enrollments:
                    res = await service.advance_enrollment(enrollment.id)
                    results.append({"enrollment_id": str(enrollment.id), "advanced": bool(res)})

            logger.info("Advanced %d enrollments", len(results))
            return results

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_advance())
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.outreach_tasks.process_campaign_step",
    queue="outreach",
)
def process_campaign_step(self, enrollment_id: str, **kwargs):
    """Process the next step for a campaign enrollment.

    Generates personalized message for the current step and advances the enrollment.
    """
    import asyncio
    from app.services.campaign_service import CampaignService
    from app.services.ai.personalization_engine import PersonalizationEngine

    async def _process():
        async with async_session() as db:
            svc = CampaignService(db)
            engine = PersonalizationEngine()

            # Advance enrollment to next step
            enrollment = await svc.advance_enrollment(uuid.UUID(enrollment_id))
            if not enrollment:
                logger.warning("Enrollment %s not found or already completed", enrollment_id)
                return {"enrollment_id": enrollment_id, "status": "not_found"}

            # If enrollment completed (was last step), we're done
            if enrollment.status == "completed":
                return {"enrollment_id": enrollment_id, "status": "completed"}

            # Get campaign steps
            steps = await svc.get_steps(enrollment.campaign_id)
            if not steps or enrollment.current_step >= len(steps):
                return {"enrollment_id": enrollment_id, "status": "no_steps"}

            # Generate message for current step
            current_step = steps[enrollment.current_step]
            campaign = await svc.get_campaign(enrollment.campaign_id, uuid.UUID(int=0))

            try:
                messages = await engine.generate_for_campaign_step(
                    lead_id=enrollment.lead_id,
                    campaign_step_id=current_step.id,
                    db=db,
                    tone=campaign.tone if campaign else "professional",
                    goal=campaign.goal if campaign else "generate_interest",
                )
                await db.commit()
                return {
                    "enrollment_id": enrollment_id,
                    "status": "step_processed",
                    "message_count": len(messages),
                    "step": enrollment.current_step,
                }
            except Exception as exc:
                logger.error("Failed to generate step message: %s", exc)
                await db.rollback()
                return {"enrollment_id": enrollment_id, "status": "error", "error": str(exc)}

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_process())
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.outreach_tasks.process_follow_ups",
    queue="outreach",
)
def process_follow_ups(self, team_id: str, **kwargs):
    """Process all due follow-up tasks for a team.

    Scheduled via Celery Beat (every 5 minutes).
    """
    import asyncio
    from app.services.follow_up_service import FollowUpAutomation

    async def _process():
        async with async_session() as db:
            automation = FollowUpAutomation(db)
            processed = await automation.process_due_tasks(team_id=uuid.UUID(team_id))
            await db.commit()

            return {
                "team_id": team_id,
                "processed_count": len(processed),
                "task_ids": [str(t.id) for t in processed],
            }

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_process())
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.outreach_tasks.classify_reply",
    queue="outreach",
)
def classify_reply(self, reply_id: str, **kwargs):
    """Classify a reply and create follow-up tasks.

    Triggered when a new reply is received.
    """
    import asyncio
    from app.services.ai.reply_classifier import ReplyClassifier
    from app.services.follow_up_service import FollowUpAutomation

    async def _classify():
        async with async_session() as db:
            classifier = ReplyClassifier()
            automation = FollowUpAutomation(db)

            # Classify the reply
            classification = await classifier.classify(
                reply_id=uuid.UUID(reply_id),
                db=db,
            )

            # Create follow-up tasks based on classification
            tasks = await automation.process_classification(classification.id)

            await db.commit()

            return {
                "reply_id": reply_id,
                "classification": classification.classification,
                "subtype": classification.subtype,
                "confidence": float(classification.confidence),
                "follow_up_tasks": len(tasks),
            }

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_classify())
    finally:
        loop.close()
