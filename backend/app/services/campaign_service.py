"""Campaign service — manages campaigns, steps, enrollments, and execution.

Handles:
  - CRUD for campaigns and their steps
  - Enrolling leads into campaigns
  - Starting/pausing/completing campaigns
  - Progressing leads through campaign steps
  - Campaign analytics and metrics
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignStep, CampaignEnrollment
from app.models.lead import Lead
from app.models.message import OutreachMessage
from app.models.activity import ActivityLog
from app.services.activity_service import log_activity

logger = logging.getLogger(__name__)


class CampaignService:
    """Encapsulates all campaign-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Campaign CRUD ──────────────────────────────────────────────────────────

    async def create_campaign(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: Optional[str] = None,
        goal: Optional[str] = None,
        tone: str = "professional",
        approval_mode: str = "manual",
        send_limits: Optional[dict] = None,
        steps: Optional[list[dict]] = None,
    ) -> Campaign:
        """Create a new campaign with optional steps."""
        campaign = Campaign(
            team_id=team_id,
            name=name,
            description=description,
            goal=goal or "generate_interest",
            tone=tone,
            approval_mode=approval_mode,
            send_limits=send_limits or {},
            created_by=user_id,
        )
        self.db.add(campaign)
        await self.db.flush()
        await self.db.refresh(campaign)

        # Create steps if provided
        if steps:
            for idx, step_data in enumerate(steps):
                step = CampaignStep(
                    campaign_id=campaign.id,
                    step_order=step_data.get("step_order", idx + 1),
                    channel=step_data.get("channel", "email"),
                    delay_days=step_data.get("delay_days", idx * 3),
                    template_type=step_data.get("template_type", f"step_{idx + 1}"),
                    subject_template=step_data.get("subject_template"),
                    body_template=step_data.get("body_template"),
                )
                self.db.add(step)
            await self.db.flush()

        await log_activity(
            self.db, team_id=team_id, user_id=user_id,
            lead_id=None, action="campaign_created",
            details={"campaign_id": str(campaign.id), "name": name},
        )

        return campaign

    async def get_campaign(self, campaign_id: uuid.UUID, team_id: uuid.UUID) -> Optional[Campaign]:
        """Fetch a campaign by ID, scoped to team."""
        result = await self.db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.team_id == team_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_campaigns(
        self,
        team_id: uuid.UUID,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[Campaign], int]:
        """List campaigns for a team with optional filtering."""
        query = select(Campaign).where(Campaign.team_id == team_id)

        if status:
            query = query.where(Campaign.status == status)

        # Count
        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        # Sort by created_at desc
        query = query.order_by(Campaign.created_at.desc())
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        result = await self.db.execute(query)
        campaigns = list(result.scalars().all())
        return campaigns, total

    async def update_campaign(
        self,
        campaign_id: uuid.UUID,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        **updates: Any,
    ) -> Optional[Campaign]:
        """Update campaign fields."""
        campaign = await self.get_campaign(campaign_id, team_id)
        if not campaign:
            return None

        for field, value in updates.items():
            if hasattr(campaign, field) and value is not None:
                setattr(campaign, field, value)

        campaign.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(campaign)
        return campaign

    async def delete_campaign(self, campaign_id: uuid.UUID, team_id: uuid.UUID) -> bool:
        """Soft-delete a campaign (archive it)."""
        campaign = await self.get_campaign(campaign_id, team_id)
        if not campaign:
            return False

        campaign.status = "archived"
        campaign.updated_at = datetime.utcnow()
        await self.db.flush()
        return True

    # ── Campaign Steps ────────────────────────────────────────────────────────

    async def add_step(
        self,
        campaign_id: uuid.UUID,
        step_order: int,
        channel: str = "email",
        delay_days: int = 0,
        template_type: str = "initial_email",
        subject_template: Optional[str] = None,
        body_template: Optional[str] = None,
    ) -> CampaignStep:
        """Add a step to a campaign."""
        step = CampaignStep(
            campaign_id=campaign_id,
            step_order=step_order,
            channel=channel,
            delay_days=delay_days,
            template_type=template_type,
            subject_template=subject_template,
            body_template=body_template,
        )
        self.db.add(step)
        await self.db.flush()
        await self.db.refresh(step)
        return step

    async def get_steps(self, campaign_id: uuid.UUID) -> list[CampaignStep]:
        """Get all steps for a campaign, ordered by step_order."""
        result = await self.db.execute(
            select(CampaignStep)
            .where(CampaignStep.campaign_id == campaign_id)
            .order_by(CampaignStep.step_order)
        )
        return list(result.scalars().all())

    async def update_step(self, step_id: uuid.UUID, **updates: Any) -> Optional[CampaignStep]:
        """Update a campaign step."""
        result = await self.db.execute(select(CampaignStep).where(CampaignStep.id == step_id))
        step = result.scalar_one_or_none()
        if not step:
            return None

        for field, value in updates.items():
            if hasattr(step, field) and value is not None:
                setattr(step, field, value)

        await self.db.flush()
        await self.db.refresh(step)
        return step

    async def delete_step(self, step_id: uuid.UUID) -> bool:
        """Delete a campaign step."""
        result = await self.db.execute(select(CampaignStep).where(CampaignStep.id == step_id))
        step = result.scalar_one_or_none()
        if not step:
            return False
        await self.db.delete(step)
        await self.db.flush()
        return True

    # ── Enrollment ─────────────────────────────────────────────────────────────

    async def enroll_leads(
        self,
        campaign_id: uuid.UUID,
        lead_ids: list[uuid.UUID],
        team_id: uuid.UUID,
    ) -> list[CampaignEnrollment]:
        """Enroll leads into a campaign."""
        # Get campaign
        campaign = await self.get_campaign(campaign_id, team_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        # Get first step
        steps = await self.get_steps(campaign_id)
        first_step_index = 0

        enrollments = []
        for lead_id in lead_ids:
            # Check if lead is already enrolled
            existing = await self.db.execute(
                select(CampaignEnrollment).where(
                    CampaignEnrollment.campaign_id == campaign_id,
                    CampaignEnrollment.lead_id == lead_id,
                    CampaignEnrollment.status.in_(["pending", "in_progress"]),
                )
            )
            if existing.scalar_one_or_none():
                continue  # Skip already-enrolled leads

            enrollment = CampaignEnrollment(
                campaign_id=campaign_id,
                lead_id=lead_id,
                status="pending",
                current_step=first_step_index,
                next_step_at=datetime.utcnow(),
            )
            self.db.add(enrollment)
            enrollments.append(enrollment)

        await self.db.flush()
        for enrollment in enrollments:
            await self.db.refresh(enrollment)

        await log_activity(
            self.db, team_id=team_id, user_id=None,
            lead_id=None, action="leads_enrolled",
            details={"campaign_id": str(campaign_id), "count": len(enrollments)},
        )

        return enrollments

    async def remove_enrollment(self, enrollment_id: uuid.UUID) -> bool:
        """Stop/complete an enrollment (removes lead from campaign)."""
        result = await self.db.execute(
            select(CampaignEnrollment).where(CampaignEnrollment.id == enrollment_id)
        )
        enrollment = result.scalar_one_or_none()
        if not enrollment:
            return False

        enrollment.status = "stopped"
        await self.db.flush()
        return True

    async def get_enrollments(
        self,
        campaign_id: uuid.UUID,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[CampaignEnrollment], int]:
        """List enrollments for a campaign."""
        query = select(CampaignEnrollment).where(
            CampaignEnrollment.campaign_id == campaign_id
        )

        if status:
            query = query.where(CampaignEnrollment.status == status)

        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        query = query.order_by(CampaignEnrollment.enrolled_at.desc())
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        result = await self.db.execute(query)
        enrollments = list(result.scalars().all())
        return enrollments, total

    # ── Campaign Lifecycle ────────────────────────────────────────────────────

    async def start_campaign(self, campaign_id: uuid.UUID, team_id: uuid.UUID) -> Optional[Campaign]:
        """Activate a draft campaign, enrolling pending leads into the first step."""
        campaign = await self.get_campaign(campaign_id, team_id)
        if not campaign:
            return None

        if campaign.status not in ("draft", "paused"):
            raise ValueError(f"Cannot start campaign in status '{campaign.status}'")

        campaign.status = "active"
        campaign.updated_at = datetime.utcnow()

        # Update all pending enrollments
        result = await self.db.execute(
            select(CampaignEnrollment).where(
                CampaignEnrollment.campaign_id == campaign_id,
                CampaignEnrollment.status == "pending",
            )
        )
        for enrollment in result.scalars().all():
            enrollment.status = "in_progress"
            enrollment.next_step_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(campaign)

        await log_activity(
            self.db, team_id=team_id, user_id=None,
            lead_id=None, action="campaign_started",
            details={"campaign_id": str(campaign_id), "name": campaign.name},
        )

        return campaign

    async def pause_campaign(self, campaign_id: uuid.UUID, team_id: uuid.UUID) -> Optional[Campaign]:
        """Pause an active campaign."""
        campaign = await self.get_campaign(campaign_id, team_id)
        if not campaign or campaign.status != "active":
            return None

        campaign.status = "paused"
        campaign.updated_at = datetime.utcnow()
        await self.db.flush()
        return campaign

    async def complete_campaign(self, campaign_id: uuid.UUID, team_id: uuid.UUID) -> Optional[Campaign]:
        """Mark a campaign as completed."""
        campaign = await self.get_campaign(campaign_id, team_id)
        if not campaign:
            return None

        campaign.status = "completed"
        campaign.updated_at = datetime.utcnow()

        # Mark all in_progress enrollments as completed
        result = await self.db.execute(
            select(CampaignEnrollment).where(
                CampaignEnrollment.campaign_id == campaign_id,
                CampaignEnrollment.status == "in_progress",
            )
        )
        for enrollment in result.scalars().all():
            enrollment.status = "completed"
            enrollment.completed_at = datetime.utcnow()

        await self.db.flush()
        return campaign

    # ── Step Progression ──────────────────────────────────────────────────────

    async def advance_enrollment(
        self,
        enrollment_id: uuid.UUID,
    ) -> Optional[CampaignEnrollment]:
        """Advance an enrollment to the next step in the campaign.

        Returns the enrollment with updated current_step and next_step_at.
        Returns None if this was the last step (enrollment completes).
        """
        result = await self.db.execute(
            select(CampaignEnrollment).where(CampaignEnrollment.id == enrollment_id)
        )
        enrollment = result.scalar_one_or_none()
        if not enrollment:
            return None

        steps = await self.get_steps(enrollment.campaign_id)
        next_step_index = enrollment.current_step + 1

        if next_step_index >= len(steps):
            # Last step completed
            enrollment.status = "completed"
            enrollment.completed_at = datetime.utcnow()
            enrollment.current_step = next_step_index
            await self.db.flush()
            return enrollment

        # Advance to next step
        next_step = steps[next_step_index]
        enrollment.current_step = next_step_index
        enrollment.next_step_at = datetime.utcnow() + timedelta(days=next_step.delay_days)
        enrollment.status = "in_progress"

        await self.db.flush()
        await self.db.refresh(enrollment)
        return enrollment

    # ── Analytics ──────────────────────────────────────────────────────────────

    async def get_campaign_stats(self, campaign_id: uuid.UUID, team_id: uuid.UUID) -> dict:
        """Get analytics/stats for a campaign."""
        campaign = await self.get_campaign(campaign_id, team_id)
        if not campaign:
            return {}

        # Enrollment counts by status
        result = await self.db.execute(
            select(CampaignEnrollment.status, func.count(CampaignEnrollment.id))
            .where(CampaignEnrollment.campaign_id == campaign_id)
            .group_by(CampaignEnrollment.status)
        )
        enrollment_stats = dict(result.all())

        # Message counts by status
        result = await self.db.execute(
            select(OutreachMessage.status, func.count(OutreachMessage.id))
            .where(OutreachMessage.campaign_id == campaign_id)
            .group_by(OutreachMessage.status)
        )
        message_stats = dict(result.all())

        total_enrolled = sum(enrollment_stats.values())
        total_messages = sum(message_stats.values())

        return {
            "campaign_id": str(campaign_id),
            "name": campaign.name,
            "status": campaign.status,
            "goal": campaign.goal,
            "tone": campaign.tone,
            "enrollments": enrollment_stats,
            "total_enrolled": total_enrolled,
            "messages": message_stats,
            "total_messages": total_messages,
            "steps_count": len(await self.get_steps(campaign_id)),
        }

    async def get_enrollments_due_now(self, campaign_id: uuid.UUID) -> list[CampaignEnrollment]:
        """Get enrollments that are due for their next step right now."""
        now = datetime.utcnow()
        result = await self.db.execute(
            select(CampaignEnrollment).where(
                CampaignEnrollment.campaign_id == campaign_id,
                CampaignEnrollment.status == "in_progress",
                CampaignEnrollment.next_step_at <= now,
            )
        )
        return list(result.scalars().all())

    async def get_all_campaigns_due_now(self, team_id: uuid.UUID) -> list[dict]:
        """Get all active campaigns with enrollments due for the next step.

        Returns list of dicts with campaign and due enrollments.
        """
        now = datetime.utcnow()

        # Get active campaigns
        result = await self.db.execute(
            select(Campaign).where(
                Campaign.team_id == team_id,
                Campaign.status == "active",
            )
        )
        campaigns = list(result.scalars().all())

        due_items = []
        for campaign in campaigns:
            enrollments = await self.get_enrollments_due_now(campaign.id)
            if enrollments:
                due_items.append({
                    "campaign": campaign,
                    "enrollments": enrollments,
                })

        return due_items