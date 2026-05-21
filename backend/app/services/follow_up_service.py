"""Follow-up automation service — manages follow-up tasks based on reply classifications.

Handles:
  - Creating follow-up tasks from reply classification results
  - Scheduling follow-up messages at appropriate intervals
  - Managing cadence for different reply types
  - Auto-generating draft responses for positive replies
  - Suppression of leads who opt out
  - Processing the follow-up task queue
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.reply import Reply, ReplyClassification
from app.models.campaign import CampaignEnrollment
from app.models.follow_up import FollowUpTask
from app.models.message import OutreachMessage
from app.models.suppression import SuppressionList
from app.services.ai.personalization_engine import PersonalizationEngine
from app.services.ai.reply_classifier import ReplyCategory
from app.services.activity_service import log_activity

logger = logging.getLogger(__name__)

# ── Follow-up timing rules ──────────────────────────────────────────────────
# How long to wait before following up, based on classification type

FOLLOW_UP_DELAYS: dict[str, dict] = {
    "positive_interest": {
        "delay_hours": 2,
        "task_type": "send_message",
        "priority": "high",
    },
    "meeting_request": {
        "delay_hours": 1,
        "task_type": "book_meeting",
        "priority": "urgent",
    },
    "objection": {
        "delay_hours": 24,
        "task_type": "draft_objection_response",
        "priority": "high",
    },
    "not_now": {
        "delay_hours": 72,  # 3 days
        "task_type": "schedule_reminder",
        "priority": "low",
    },
    "question": {
        "delay_hours": 4,
        "task_type": "send_message",
        "priority": "high",
    },
    "referral": {
        "delay_hours": 4,
        "task_type": "send_message",
        "priority": "high",
    },
    "out_of_office": {
        "delay_hours": 168,  # 1 week
        "task_type": "schedule_reminder",
        "priority": "low",
    },
    "not_interested": {
        "delay_hours": 0,  # Immediate — suppress
        "task_type": "suppress_lead",
        "priority": "medium",
    },
    "unsubscribe": {
        "delay_hours": 0,  # Immediate — suppress
        "task_type": "suppress_lead",
        "priority": "urgent",
    },
    "spam": {
        "delay_hours": 0,  # Immediate — suppress
        "task_type": "suppress_lead",
        "priority": "low",
    },
    "no_response": {
        "delay_hours": 48,
        "task_type": "send_follow_up",
        "priority": "medium",
    },
}


class FollowUpAutomation:
    """Manages follow-up tasks based on reply classifications and campaign cadence.

    Usage::

        automation = FollowUpAutomation(db=db)
        # Process a new reply classification
        tasks = await automation.process_classification(classification_id, reply_id)
        # Process due tasks
        await automation.process_due_tasks()
    """

    def __init__(self, db: AsyncSession, personalization_engine: Optional[PersonalizationEngine] = None):
        self.db = db
        self._engine = personalization_engine

    @property
    def engine(self) -> PersonalizationEngine:
        if self._engine is None:
            self._engine = PersonalizationEngine()
        return self._engine

    # ── Process Classification ────────────────────────────────────────────────

    async def process_classification(
        self,
        classification_id: uuid.UUID,
    ) -> list[FollowUpTask]:
        """Create follow-up tasks based on a reply classification.

        Parameters
        ----------
        classification_id : UUID
            The ReplyClassification to process.

        Returns
        -------
        list[FollowUpTask]
            The created follow-up tasks.
        """
        # Load classification
        result = await self.db.execute(
            select(ReplyClassification).where(ReplyClassification.id == classification_id)
        )
        classification = result.scalar_one_or_none()
        if not classification:
            raise ValueError(f"Classification {classification_id} not found")

        category = classification.classification
        lead_id = classification.lead_id

        # Get timing rules
        rules = FOLLOW_UP_DELAYS.get(category, FOLLOW_UP_DELAYS["no_response"])
        delay_hours = rules["delay_hours"]
        task_type = rules["task_type"]

        tasks = []

        # Handle suppression immediately
        if task_type == "suppress_lead":
            task = await self._create_suppression_task(
                lead_id=lead_id,
                reason=category,
                source=f"classification:{classification_id}",
            )
            tasks.append(task)
            return tasks

        # Create follow-up task
        due_at = datetime.utcnow() + timedelta(hours=delay_hours)

        # Build task data
        task_data = {
            "classification_id": str(classification_id),
            "classification": category,
            "subtype": classification.subtype,
            "recommended_action": classification.recommended_action,
            "summary": classification.summary,
        }

        # For meeting requests, include the draft response
        if classification.draft_response and task_type in ("send_message", "book_meeting"):
            task_data["draft_response"] = classification.draft_response

        task = FollowUpTask(
            lead_id=lead_id,
            task_type=task_type,
            due_at=due_at,
            status="pending",
            data=task_data,
        )
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        tasks.append(task)

        # Also pause the campaign enrollment if lead is in one
        if category in ("not_now", "out_of_office"):
            await self._pause_enrollment_for_lead(lead_id)

        await log_activity(
            self.db,
            team_id=(await self._get_lead_team_id(lead_id)) or uuid.UUID(int=0),
            user_id=None,
            lead_id=lead_id,
            action="follow_up_scheduled",
            details={
                "task_type": task_type,
                "classification": category,
                "due_at": due_at.isoformat(),
            },
        )

        return tasks

    # ── Suppression ───────────────────────────────────────────────────────────

    async def _create_suppression_task(
        self,
        lead_id: uuid.UUID,
        reason: str,
        source: str,
    ) -> FollowUpTask:
        """Create a suppression task for a lead."""
        task = FollowUpTask(
            lead_id=lead_id,
            task_type="suppress_lead",
            due_at=datetime.utcnow(),  # Immediate
            status="pending",
            data={
                "reason": reason,
                "source": source,
            },
        )
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def execute_suppression(self, task: FollowUpTask, team_id: uuid.UUID) -> bool:
        """Execute a suppression task: add to suppression list and stop enrollments."""
        lead_id = task.lead_id
        reason = task.data.get("reason", "unsubscribe")

        # Get lead's contact info for email
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            return False

        # Get contact email
        email = None
        if lead.contact_id:
            from app.models.contact import Contact
            result = await self.db.execute(
                select(Contact).where(Contact.id == lead.contact_id)
            )
            contact = result.scalar_one_or_none()
            if contact and contact.email:
                email = contact.email

        # Add to suppression list
        if email:
            # Check if already suppressed
            result = await self.db.execute(
                select(SuppressionList).where(
                    SuppressionList.team_id == team_id,
                    SuppressionList.email == email,
                )
            )
            existing = result.scalar_one_or_none()
            if not existing:
                suppression = SuppressionList(
                    team_id=team_id,
                    email=email,
                    reason=reason,
                    source=task.data.get("source", "follow_up_automation"),
                )
                self.db.add(suppression)

        # Stop all campaign enrollments for this lead
        result = await self.db.execute(
            select(CampaignEnrollment).where(
                CampaignEnrollment.lead_id == lead_id,
                CampaignEnrollment.status.in_(["pending", "in_progress"]),
            )
        )
        for enrollment in result.scalars().all():
            enrollment.status = "stopped"

        # Update lead status
        lead.status = "suppressed"
        lead.pipeline_stage = "suppressed"
        lead.updated_at = datetime.utcnow()
        self.db.add(lead)

        task.status = "completed"
        task.completed_at = datetime.utcnow()
        self.db.add(task)

        await self.db.flush()

        await log_activity(
            self.db, team_id=team_id, user_id=None,
            lead_id=lead_id, action="lead_suppressed",
            details={"reason": reason, "email": email},
        )

        return True

    # ── Process Due Tasks ──────────────────────────────────────────────────────

    async def process_due_tasks(self, team_id: uuid.UUID) -> list[FollowUpTask]:
        """Process all follow-up tasks that are due.

        Executes pending tasks whose due_at has passed.
        """
        now = datetime.utcnow()

        result = await self.db.execute(
            select(FollowUpTask).where(
                FollowUpTask.status == "pending",
                FollowUpTask.due_at <= now,
            ).order_by(FollowUpTask.due_at)
        )
        due_tasks = list(result.scalars().all())

        processed = []
        for task in due_tasks:
            try:
                await self._execute_task(task, team_id)
                processed.append(task)
            except Exception as exc:
                logger.error("Failed to execute follow-up task %s: %s", task.id, exc)
                task.status = "failed"
                task.data = {**task.data, "error": str(exc)} if task.data else {"error": str(exc)}
                self.db.add(task)

        await self.db.flush()
        return processed

    async def _execute_task(self, task: FollowUpTask, team_id: uuid.UUID) -> None:
        """Execute a single follow-up task."""
        task_type = task.task_type

        if task_type == "suppress_lead":
            await self.execute_suppression(task, team_id)

        elif task_type == "send_message":
            await self._execute_send_message(task, team_id)

        elif task_type == "book_meeting":
            await self._execute_book_meeting(task, team_id)

        elif task_type == "draft_objection_response":
            await self._execute_objection_response(task, team_id)

        elif task_type == "schedule_reminder":
            await self._execute_reminder(task, team_id)

        elif task_type == "send_follow_up":
            await self._execute_send_follow_up(task, team_id)

        else:
            logger.warning("Unknown task type: %s", task_type)
            task.status = "completed"
            task.completed_at = datetime.utcnow()

    async def _execute_send_message(self, task: FollowUpTask, team_id: uuid.UUID) -> None:
        """Generate and schedule a personalized follow-up message."""
        lead_id = task.lead_id
        classification = task.data.get("classification", "positive_interest")
        draft_response = task.data.get("draft_response")

        # Generate a personalized message
        try:
            messages = await self.engine.generate_messages(
                lead_id=lead_id,
                db=self.db,
                channel="email",
                strategies=["pain_point", "question"],
                tone="professional",
                goal="book_meeting" if classification == "meeting_request" else "generate_interest",
                num_variants=1,
            )
            # Take the first generated message
            if messages:
                message = messages[0]
                # If we have a draft response, prefer it but also store the generated one
                if draft_response:
                    # Create additional context note
                    note = f"[AI Draft from classification: {draft_response}]"
                    message.body = f"{note}\n\n---\n\n{message.body}"
                    self.db.add(message)

        except Exception as exc:
            logger.error("Failed to generate follow-up message for lead %s: %s", lead_id, exc)

        task.status = "completed"
        task.completed_at = datetime.utcnow()
        self.db.add(task)
        await self.db.flush()

    async def _execute_book_meeting(self, task: FollowUpTask, team_id: uuid.UUID) -> None:
        """Create a meeting-request follow-up message."""
        lead_id = task.lead_id

        try:
            messages = await self.engine.generate_messages(
                lead_id=lead_id,
                db=self.db,
                channel="email",
                strategies=["direct"],
                tone="professional",
                goal="book_meeting",
                num_variants=1,
            )
        except Exception as exc:
            logger.error("Failed to generate meeting request for lead %s: %s", lead_id, exc)

        task.status = "completed"
        task.completed_at = datetime.utcnow()
        self.db.add(task)
        await self.db.flush()

    async def _execute_objection_response(self, task: FollowUpTask, team_id: uuid.UUID) -> None:
        """Generate a draft response to an objection."""
        lead_id = task.lead_id
        subtype = task.data.get("subtype", "general")
        summary = task.data.get("summary", "")

        try:
            messages = await self.engine.generate_messages(
                lead_id=lead_id,
                db=self.db,
                channel="email",
                strategies=["insight"],
                tone="consultative",
                goal="generate_interest",
                custom_instructions=f"The prospect raised an objection: {summary}. Subtype: {subtype}. Address their concern directly and offer value.",
                num_variants=1,
            )
        except Exception as exc:
            logger.error("Failed to generate objection response for lead %s: %s", lead_id, exc)

        task.status = "completed"
        task.completed_at = datetime.utcnow()
        self.db.add(task)
        await self.db.flush()

    async def _execute_reminder(self, task: FollowUpTask, team_id: uuid.UUID) -> None:
        """Create a reminder to follow up later (e.g., after OOO)."""
        # For reminders, schedule a new follow-up message
        lead_id = task.lead_id

        # Simple approach: create a new send_message task
        reminder = FollowUpTask(
            lead_id=lead_id,
            task_type="send_follow_up",
            due_at=datetime.utcnow() + timedelta(hours=24),
            status="pending",
            data={
                "reason": "reminder_after_ooo",
                "original_classification": task.data.get("classification", "out_of_office"),
            },
        )
        self.db.add(reminder)

        task.status = "completed"
        task.completed_at = datetime.utcnow()
        self.db.add(task)
        await self.db.flush()

    async def _execute_send_follow_up(self, task: FollowUpTask, team_id: uuid.UUID) -> None:
        """Send a follow-up message to a lead who hasn't responded."""
        lead_id = task.lead_id

        try:
            messages = await self.engine.generate_messages(
                lead_id=lead_id,
                db=self.db,
                channel="email",
                strategies=["compliment", "direct"],
                tone="professional",
                goal="generate_interest",
                custom_instructions="This is a follow-up message — the prospect hasn't responded to previous outreach. Be brief, add new value, don't repeat previous messages.",
                num_variants=1,
            )
        except Exception as exc:
            logger.error("Failed to generate follow-up for lead %s: %s", lead_id, exc)

        task.status = "completed"
        task.completed_at = datetime.utcnow()
        self.db.add(task)
        await self.db.flush()

    # ── Campaign Cadence ──────────────────────────────────────────────────────

    async def schedule_campaign_step(
        self,
        enrollment_id: uuid.UUID,
        step_index: int,
        delay_days: int,
        channel: str = "email",
    ) -> FollowUpTask:
        """Schedule a follow-up task for a campaign step."""
        result = await self.db.execute(
            select(CampaignEnrollment).where(CampaignEnrollment.id == enrollment_id)
        )
        enrollment = result.scalar_one_or_none()
        if not enrollment:
            raise ValueError(f"Enrollment {enrollment_id} not found")

        due_at = datetime.utcnow() + timedelta(days=delay_days)

        task = FollowUpTask(
            lead_id=enrollment.lead_id,
            campaign_enrollment_id=enrollment_id,
            task_type="send_message",
            due_at=due_at,
            status="pending",
            data={
                "step_index": step_index,
                "channel": channel,
                "context": "campaign",
            },
        )
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_lead_team_id(self, lead_id: uuid.UUID) -> Optional[uuid.UUID]:
        """Get the team ID for a lead."""
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        return lead.team_id if lead else None

    async def _pause_enrollment_for_lead(self, lead_id: uuid.UUID) -> None:
        """Pause campaign enrollments for a lead (e.g., for 'not now' or OOO)."""
        result = await self.db.execute(
            select(CampaignEnrollment).where(
                CampaignEnrollment.lead_id == lead_id,
                CampaignEnrollment.status == "in_progress",
            )
        )
        for enrollment in result.scalars().all():
            enrollment.status = "paused"

    # ── Task Management ────────────────────────────────────────────────────────

    async def get_pending_tasks(
        self,
        lead_id: Optional[uuid.UUID] = None,
        task_type: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[FollowUpTask], int]:
        """List pending follow-up tasks, optionally filtered."""
        query = select(FollowUpTask).where(FollowUpTask.status == "pending")

        if lead_id:
            query = query.where(FollowUpTask.lead_id == lead_id)
        if task_type:
            query = query.where(FollowUpTask.task_type == task_type)

        # Count
        from sqlalchemy import func
        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        query = query.order_by(FollowUpTask.due_at.asc())
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        result = await self.db.execute(query)
        tasks = list(result.scalars().all())
        return tasks, total

    async def cancel_task(self, task_id: uuid.UUID) -> bool:
        """Cancel a pending task."""
        result = await self.db.execute(
            select(FollowUpTask).where(FollowUpTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task or task.status != "pending":
            return False

        task.status = "cancelled"
        await self.db.flush()
        return True

    async def reschedule_task(
        self, task_id: uuid.UUID, new_due_at: datetime
    ) -> Optional[FollowUpTask]:
        """Reschedule a pending task to a new time."""
        result = await self.db.execute(
            select(FollowUpTask).where(FollowUpTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task or task.status != "pending":
            return None

        task.due_at = new_due_at
        await self.db.flush()
        await self.db.refresh(task)
        return task