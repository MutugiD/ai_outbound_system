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
    """Send an outreach message via the configured email provider.

    Current MVP integration: Resend (if configured).
    """
    import asyncio
    from sqlalchemy import select
    from app.models.lead import Lead
    from app.models.contact import Contact
    from app.models.suppression import SuppressionList
    from app.models.message import OutreachMessage
    from app.config import settings
    from app.services.activity_service import log_activity
    from app.services.email.resend_service import send_email

    async def _send():
        async with async_session() as db:
            result = await db.execute(select(OutreachMessage).where(OutreachMessage.id == uuid.UUID(message_id)))
            message = result.scalar_one_or_none()
            if not message:
                logger.error("Message %s not found", message_id)
                return {"message_id": message_id, "status": "not_found"}

            if message.status not in ("approved", "scheduled"):
                logger.warning("Message %s not in sendable state: %s", message_id, message.status)
                return {"message_id": message_id, "status": "skipped", "reason": f"status={message.status}"}

            lead = (await db.execute(select(Lead).where(Lead.id == message.lead_id))).scalar_one_or_none()
            if not lead:
                message.status = "failed"
                message.error = "Lead not found"
                db.add(message)
                await db.commit()
                return {"message_id": message_id, "status": "failed", "error": "lead_not_found"}

            to_email: str | None = None
            if lead.contact_id:
                contact = (await db.execute(select(Contact).where(Contact.id == lead.contact_id))).scalar_one_or_none()
                if contact and contact.email:
                    to_email = contact.email

            if not to_email:
                message.status = "failed"
                message.error = "No contact email for lead"
                db.add(message)
                await db.commit()
                return {"message_id": message_id, "status": "failed", "error": "missing_recipient_email"}

            suppressed = (
                await db.execute(
                    select(SuppressionList).where(
                        SuppressionList.team_id == lead.team_id,
                        SuppressionList.email == to_email,
                    )
                )
            ).scalar_one_or_none()
            if suppressed:
                message.status = "skipped"
                message.to_email = to_email
                message.error = f"suppressed:{suppressed.reason}"
                db.add(message)
                await db.commit()
                return {"message_id": message_id, "status": "skipped", "reason": "suppressed"}

            subject = message.subject or "Quick question"
            try:
                reply_to = None
                if settings.OUTREACH_REPLY_TO:
                    try:
                        reply_to = settings.OUTREACH_REPLY_TO.format(message_id=str(message.id), lead_id=str(lead.id))
                    except Exception:
                        reply_to = settings.OUTREACH_REPLY_TO

                result = await send_email(
                    to_email=to_email,
                    subject=subject,
                    text_body=message.body,
                    reply_to=reply_to,
                )
                message.provider = "resend"
                message.provider_message_id = result.provider_message_id
                message.to_email = to_email
                message.status = "sent"
                message.sent_at = datetime.utcnow()
                message.error = None
                db.add(message)

                await log_activity(
                    db,
                    team_id=lead.team_id,
                    user_id=None,
                    lead_id=lead.id,
                    action="message_sent",
                    details={
                        "message_id": message_id,
                        "provider": message.provider,
                        "provider_message_id": message.provider_message_id,
                        "to": to_email,
                    },
                )

                await db.commit()
                logger.info(
                    "Message %s sent via Resend (provider_message_id=%s)", message_id, result.provider_message_id
                )
                return {
                    "message_id": message_id,
                    "status": "sent",
                    "provider": "resend",
                    "provider_message_id": result.provider_message_id,
                }
            except Exception as exc:
                logger.exception("Failed to send message %s: %s", message_id, exc)
                message.provider = "resend"
                message.to_email = to_email
                message.status = "failed"
                message.error = str(exc)
                db.add(message)
                await db.commit()
                return {"message_id": message_id, "status": "failed", "error": str(exc)}

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_send())
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

    Generates a personalized message for the current step and then advances the enrollment.
    """
    import asyncio
    from datetime import datetime
    from sqlalchemy import select

    from app.models.campaign import Campaign, CampaignEnrollment
    from app.services.campaign_service import CampaignService
    from app.services.ai.personalization_engine import PersonalizationEngine

    async def _process():
        async with async_session() as db:
            svc = CampaignService(db)
            engine = PersonalizationEngine()

            # Load enrollment
            enrollment_result = await db.execute(
                select(CampaignEnrollment).where(CampaignEnrollment.id == uuid.UUID(enrollment_id))
            )
            enrollment = enrollment_result.scalar_one_or_none()
            if not enrollment:
                logger.warning("Enrollment %s not found or already completed", enrollment_id)
                return {"enrollment_id": enrollment_id, "status": "not_found"}

            if enrollment.status not in ("in_progress", "pending"):
                return {"enrollment_id": enrollment_id, "status": "skipped", "reason": f"status={enrollment.status}"}

            # Get campaign steps
            steps = await svc.get_steps(enrollment.campaign_id)
            if not steps:
                return {"enrollment_id": enrollment_id, "status": "no_steps"}
            if enrollment.current_step >= len(steps):
                # Enrollment is out of range; mark completed to avoid infinite retries.
                enrollment.status = "completed"
                enrollment.completed_at = datetime.utcnow()
                await db.commit()
                return {"enrollment_id": enrollment_id, "status": "completed"}

            # Generate message for current step
            current_step = steps[enrollment.current_step]
            campaign_result = await db.execute(select(Campaign).where(Campaign.id == enrollment.campaign_id))
            campaign = campaign_result.scalar_one_or_none()
            processed_step = enrollment.current_step

            try:
                messages = await engine.generate_for_campaign_step(
                    lead_id=enrollment.lead_id,
                    campaign_step_id=current_step.id,
                    db=db,
                    tone=campaign.tone if campaign else "professional",
                    goal=campaign.goal if campaign else "generate_interest",
                )

                # Auto-approve + schedule send if configured
                if campaign and campaign.approval_mode == "auto":
                    for msg in messages:
                        msg.status = "scheduled"
                        msg.approved_at = datetime.utcnow()
                        db.add(msg)
                        send_message.delay(str(msg.id))

                # Advance enrollment after message is generated/scheduled
                await svc.advance_enrollment(uuid.UUID(enrollment_id))
                await db.commit()
                return {
                    "enrollment_id": enrollment_id,
                    "status": "step_processed",
                    "message_count": len(messages),
                    "step": processed_step,
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
    name="app.workers.outreach_tasks.process_due_campaign_enrollments",
    queue="outreach",
)
def process_due_campaign_enrollments(self, team_id: str, **kwargs):
    """Queue processing for all campaign enrollments due for a team."""
    import asyncio
    from datetime import datetime
    from sqlalchemy import select

    from app.models.campaign import Campaign, CampaignEnrollment

    async def _process():
        async with async_session() as db:
            now = datetime.utcnow()
            due = list(
                (
                    await db.execute(
                        select(CampaignEnrollment.id)
                        .join(Campaign, Campaign.id == CampaignEnrollment.campaign_id)
                        .where(
                            Campaign.team_id == uuid.UUID(team_id),
                            Campaign.status == "active",
                            CampaignEnrollment.status.in_(["in_progress", "pending"]),
                            CampaignEnrollment.next_step_at.is_not(None),
                            CampaignEnrollment.next_step_at <= now,
                        )
                        .order_by(CampaignEnrollment.next_step_at)
                    )
                )
                .scalars()
                .all()
            )

            for enrollment_id in due:
                process_campaign_step.delay(str(enrollment_id))

            return {"team_id": team_id, "queued": len(due), "enrollment_ids": [str(e) for e in due]}

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_process())
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.workers.outreach_tasks.process_due_campaign_enrollments_all_teams",
    queue="outreach",
)
def process_due_campaign_enrollments_all_teams(self, **kwargs):
    """Queue due campaign enrollments processing for all teams."""
    import asyncio
    from sqlalchemy import select

    from app.models.team import Team

    async def _process():
        async with async_session() as db:
            team_ids = list((await db.execute(select(Team.id))).scalars().all())
            for team_id in team_ids:
                process_due_campaign_enrollments.delay(str(team_id))
            return {"queued_teams": len(team_ids)}

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
    name="app.workers.outreach_tasks.process_follow_ups_all_teams",
    queue="outreach",
)
def process_follow_ups_all_teams(self, **kwargs):
    """Process due follow-up tasks for all teams (beat-scheduled)."""
    import asyncio
    from sqlalchemy import select
    from app.models.team import Team
    from app.services.follow_up_service import FollowUpAutomation

    async def _process():
        async with async_session() as db:
            team_ids = list((await db.execute(select(Team.id))).scalars().all())
            automation = FollowUpAutomation(db)

            processed_total = 0
            processed_task_ids: list[str] = []
            for team_id in team_ids:
                processed = await automation.process_due_tasks(team_id=team_id)
                processed_total += len(processed)
                processed_task_ids.extend([str(t.id) for t in processed])

            await db.commit()
            return {"processed_count": processed_total, "task_ids": processed_task_ids}

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
