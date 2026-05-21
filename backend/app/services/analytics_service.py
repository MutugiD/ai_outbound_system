"""Analytics service — dashboard KPIs, campaign/source/channel/pipeline/score/signal analytics.

All methods use async SQLAlchemy sessions and enforce team isolation.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_, case, text, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.lead_source import LeadSource
from app.models.campaign import Campaign, CampaignEnrollment
from app.models.message import OutreachMessage
from app.models.reply import Reply, ReplyClassification
from app.models.signal import BuyingSignal
from app.models.score import LeadScore
from app.models.pipeline import PipelineTransition


class AnalyticsService:
    """Analytics queries scoped to a team."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Overview ──────────────────────────────────────────────────────────

    async def get_overview_stats(self, team_id: uuid.UUID) -> dict:
        """Return top-level dashboard KPIs for the team."""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Total leads
        total_result = await self.db.execute(
            select(func.count(Lead.id)).where(Lead.team_id == team_id)
        )
        total_leads = total_result.scalar() or 0

        # New leads today
        new_today_result = await self.db.execute(
            select(func.count(Lead.id)).where(
                and_(Lead.team_id == team_id, Lead.created_at >= today_start)
            )
        )
        new_leads_today = new_today_result.scalar() or 0

        # Hot leads (score_band in ('hot', 'very_hot'))
        hot_result = await self.db.execute(
            select(func.count(Lead.id)).where(
                and_(Lead.team_id == team_id, Lead.score_band.in_(["hot", "very_hot"]))
            )
        )
        hot_leads = hot_result.scalar() or 0

        # Messages sent
        msg_sent_result = await self.db.execute(
            select(func.count(OutreachMessage.id))
            .select_from(OutreachMessage)
            .join(Lead, OutreachMessage.lead_id == Lead.id)
            .where(and_(Lead.team_id == team_id, OutreachMessage.status.in_(["sent", "delivered", "opened", "clicked", "replied"])))
        )
        messages_sent = msg_sent_result.scalar() or 0

        # Reply rate (replied messages / sent messages)
        replied_result = await self.db.execute(
            select(func.count(OutreachMessage.id))
            .select_from(OutreachMessage)
            .join(Lead, OutreachMessage.lead_id == Lead.id)
            .where(and_(Lead.team_id == team_id, OutreachMessage.status == "replied"))
        )
        replied_count = replied_result.scalar() or 0
        reply_rate = round(replied_count / messages_sent, 4) if messages_sent > 0 else 0.0

        # Interested replies (positive classification)
        interested_result = await self.db.execute(
            select(func.count(ReplyClassification.id))
            .select_from(ReplyClassification)
            .join(Lead, ReplyClassification.lead_id == Lead.id)
            .where(and_(Lead.team_id == team_id, ReplyClassification.classification == "interested"))
        )
        interested_replies = interested_result.scalar() or 0

        # Booked calls (leads with pipeline_stage = 'meeting_booked')
        booked_result = await self.db.execute(
            select(func.count(Lead.id)).where(
                and_(Lead.team_id == team_id, Lead.pipeline_stage == "meeting_booked")
            )
        )
        booked_calls = booked_result.scalar() or 0

        # Pipeline value (= total leads not lost or suppressed)
        pipeline_result = await self.db.execute(
            select(func.count(Lead.id)).where(
                and_(Lead.team_id == team_id, ~Lead.pipeline_stage.in_(["lost", "suppressed"])))
        )
        pipeline_value = pipeline_result.scalar() or 0

        # Conversion rate (won / total active leads)
        won_result = await self.db.execute(
            select(func.count(Lead.id)).where(
                and_(Lead.team_id == team_id, Lead.pipeline_stage == "won")
            )
        )
        won_count = won_result.scalar() or 0
        conversion_rate = round(won_count / pipeline_value, 4) if pipeline_value > 0 else 0.0

        # Top source
        top_source_result = await self.db.execute(
            select(LeadSource.source_type, func.count(LeadSource.id).label("cnt"))
            .select_from(LeadSource)
            .join(Lead, LeadSource.lead_id == Lead.id)
            .where(Lead.team_id == team_id)
            .group_by(LeadSource.source_type)
            .order_by(text("cnt DESC"))
            .limit(1)
        )
        top_source_row = top_source_result.first()
        top_source = top_source_row[0] if top_source_row else None

        # Top campaign
        top_campaign_result = await self.db.execute(
            select(Campaign.name, func.count(CampaignEnrollment.id).label("cnt"))
            .select_from(Campaign)
            .join(CampaignEnrollment, Campaign.id == CampaignEnrollment.campaign_id)
            .where(Campaign.team_id == team_id)
            .group_by(Campaign.name)
            .order_by(text("cnt DESC"))
            .limit(1)
        )
        top_campaign_row = top_campaign_result.first()
        top_campaign = top_campaign_row[0] if top_campaign_row else None

        return {
            "total_leads": total_leads,
            "new_leads_today": new_leads_today,
            "hot_leads": hot_leads,
            "messages_sent": messages_sent,
            "reply_rate": reply_rate,
            "interested_replies": interested_replies,
            "booked_calls": booked_calls,
            "pipeline_value": pipeline_value,
            "conversion_rate": conversion_rate,
            "top_source": top_source,
            "top_campaign": top_campaign,
        }

    # ── Campaign Analytics ────────────────────────────────────────────────

    async def get_campaign_analytics(
        self,
        team_id: uuid.UUID,
        campaign_id: Optional[uuid.UUID] = None,
        date_range: Optional[tuple[datetime, datetime]] = None,
    ) -> list[dict]:
        """Per-campaign stats: enrolled, sent, open/reply/bounce rates."""
        # Base campaign filter
        campaign_filter = [Campaign.team_id == team_id]
        if campaign_id:
            campaign_filter.append(Campaign.id == campaign_id)

        # Fetch campaigns
        campaigns_result = await self.db.execute(
            select(Campaign).where(and_(*campaign_filter))
        )
        campaigns = campaigns_result.scalars().all()

        results = []
        for campaign in campaigns:
            # Enrolled leads
            enrolled_result = await self.db.execute(
                select(func.count(CampaignEnrollment.id)).where(
                    CampaignEnrollment.campaign_id == campaign.id
                )
            )
            enrolled = enrolled_result.scalar() or 0

            # Messages for this campaign
            msg_base = (
                select(func.count(OutreachMessage.id))
                .select_from(OutreachMessage)
                .join(Lead, OutreachMessage.lead_id == Lead.id)
                .where(
                    and_(
                        Lead.team_id == team_id,
                        OutreachMessage.campaign_id == campaign.id,
                    )
                )
            )
            if date_range:
                msg_base = msg_base.where(
                    OutreachMessage.created_at >= date_range[0],
                    OutreachMessage.created_at <= date_range[1],
                )

            # Messages sent
            sent_result = await self.db.execute(
                msg_base.where(OutreachMessage.status.in_(["sent", "delivered", "opened", "clicked", "replied"]))
            )
            messages_sent = sent_result.scalar() or 0

            # Opened
            opened_result = await self.db.execute(
                msg_base.where(OutreachMessage.status.in_(["opened", "clicked", "replied"]))
            )
            opened = opened_result.scalar() or 0

            # Replied
            replied_result = await self.db.execute(
                msg_base.where(OutreachMessage.status == "replied")
            )
            replied = replied_result.scalar() or 0

            # Positive replies
            positive_result = await self.db.execute(
                select(func.count(ReplyClassification.id))
                .select_from(ReplyClassification)
                .join(Lead, ReplyClassification.lead_id == Lead.id)
                .join(Reply, ReplyClassification.reply_id == Reply.id, isouter=True)
                .join(OutreachMessage, Reply.message_id == OutreachMessage.id, isouter=True)
                .where(
                    and_(
                        Lead.team_id == team_id,
                        OutreachMessage.campaign_id == campaign.id,
                        ReplyClassification.classification == "interested",
                    )
                )
            )
            positive = positive_result.scalar() or 0

            # Bounced
            bounced_result = await self.db.execute(
                msg_base.where(OutreachMessage.status == "bounced")
            )
            bounced = bounced_result.scalar() or 0

            # Booked calls
            booked_result = await self.db.execute(
                select(func.count(Lead.id))
                .select_from(CampaignEnrollment)
                .join(Lead, CampaignEnrollment.lead_id == Lead.id)
                .where(
                    and_(
                        CampaignEnrollment.campaign_id == campaign.id,
                        Lead.pipeline_stage == "meeting_booked",
                    )
                )
            )
            booked = booked_result.scalar() or 0

            results.append({
                "campaign_id": str(campaign.id),
                "campaign_name": campaign.name,
                "enrolled": enrolled,
                "messages_sent": messages_sent,
                "open_rate": round(opened / messages_sent, 4) if messages_sent > 0 else 0.0,
                "reply_rate": round(replied / messages_sent, 4) if messages_sent > 0 else 0.0,
                "positive_reply_rate": round(positive / messages_sent, 4) if messages_sent > 0 else 0.0,
                "booked_calls": booked,
                "bounce_rate": round(bounced / messages_sent, 4) if messages_sent > 0 else 0.0,
            })

        return results

    # ── Source Analytics ───────────────────────────────────────────────────

    async def get_source_analytics(self, team_id: uuid.UUID) -> list[dict]:
        """Leads by source, reply rate, and conversion by source."""
        # Leads per source
        source_result = await self.db.execute(
            select(LeadSource.source_type, func.count(LeadSource.id).label("leads"))
            .select_from(LeadSource)
            .join(Lead, LeadSource.lead_id == Lead.id)
            .where(Lead.team_id == team_id)
            .group_by(LeadSource.source_type)
        )
        source_rows = source_result.all()

        results = []
        for source_type, leads in source_rows:
            # Reply rate for this source
            reply_rate = 0.0
            reply_result = await self.db.execute(
                select(func.count(OutreachMessage.id))
                .select_from(OutreachMessage)
                .join(Lead, OutreachMessage.lead_id == Lead.id)
                .join(LeadSource, LeadSource.lead_id == Lead.id)
                .where(
                    and_(
                        Lead.team_id == team_id,
                        LeadSource.source_type == source_type,
                        OutreachMessage.status == "replied",
                    )
                )
            )
            replied_in_source = reply_result.scalar() or 0

            total_in_source = leads if leads > 0 else 1
            reply_rate = round(replied_in_source / total_in_source, 4)

            # Conversion — leads that reached 'won' from this source
            conv_result = await self.db.execute(
                select(func.count(Lead.id))
                .select_from(Lead)
                .join(LeadSource, LeadSource.lead_id == Lead.id)
                .where(
                    and_(
                        Lead.team_id == team_id,
                        LeadSource.source_type == source_type,
                        Lead.pipeline_stage == "won",
                    )
                )
            )
            converted = conv_result.scalar() or 0
            conversion_rate = round(converted / total_in_source, 4)

            results.append({
                "source": source_type,
                "leads": leads,
                "reply_rate": reply_rate,
                "conversion_rate": conversion_rate,
            })

        return results

    # ── Channel Analytics ─────────────────────────────────────────────────

    async def get_channel_analytics(self, team_id: uuid.UUID) -> list[dict]:
        """Messages by channel, reply rate, conversion rate."""
        channel_result = await self.db.execute(
            select(
                OutreachMessage.channel,
                func.count(OutreachMessage.id).label("messages"),
            )
            .select_from(OutreachMessage)
            .join(Lead, OutreachMessage.lead_id == Lead.id)
            .where(Lead.team_id == team_id)
            .group_by(OutreachMessage.channel)
        )
        channel_rows = channel_result.all()

        results = []
        for channel, messages in channel_rows:
            # Replied
            replied_result = await self.db.execute(
                select(func.count(OutreachMessage.id))
                .select_from(OutreachMessage)
                .join(Lead, OutreachMessage.lead_id == Lead.id)
                .where(
                    and_(
                        Lead.team_id == team_id,
                        OutreachMessage.channel == channel,
                        OutreachMessage.status == "replied",
                    )
                )
            )
            replied = replied_result.scalar() or 0
            reply_rate = round(replied / messages, 4) if messages > 0 else 0.0

            # Conversion
            conv_result = await self.db.execute(
                select(func.count(Lead.id))
                .select_from(OutreachMessage)
                .join(Lead, OutreachMessage.lead_id == Lead.id)
                .where(
                    and_(
                        Lead.team_id == team_id,
                        OutreachMessage.channel == channel,
                        Lead.pipeline_stage == "won",
                    )
                )
            )
            converted = conv_result.scalar() or 0
            conversion_rate = round(converted / messages, 4) if messages > 0 else 0.0

            results.append({
                "channel": channel,
                "messages": messages,
                "reply_rate": reply_rate,
                "conversion_rate": conversion_rate,
            })

        return results

    # ── Pipeline Analytics ────────────────────────────────────────────────

    async def get_pipeline_analytics(self, team_id: uuid.UUID) -> dict:
        """Leads in each pipeline stage with conversion rates between stages."""
        # Count leads per pipeline stage
        stage_result = await self.db.execute(
            select(Lead.pipeline_stage, func.count(Lead.id).label("count"))
            .where(Lead.team_id == team_id)
            .group_by(Lead.pipeline_stage)
            .order_by(func.count(Lead.id).desc())
        )
        stage_rows = stage_result.all()
        stages = [{"stage": s, "count": c} for s, c in stage_rows]

        # Standard pipeline stage order for conversion computation
        stage_order = [
            "new", "enriched", "researched", "scored", "ready_for_outreach",
            "contacted", "replied", "interested", "meeting_booked", "proposal_sent", "won",
        ]

        # Compute conversion rates between consecutive stages
        stage_counts = {s: c for s, c in stage_rows}
        conversions = []
        for i in range(len(stage_order) - 1):
            from_stage = stage_order[i]
            to_stage = stage_order[i + 1]
            from_count = stage_counts.get(from_stage, 0)
            to_count = stage_counts.get(to_stage, 0)
            rate = round(to_count / from_count, 4) if from_count > 0 else 0.0
            conversions.append({
                "from_stage": from_stage,
                "to_stage": to_stage,
                "rate": rate,
            })

        return {
            "stages": stages,
            "conversions": conversions,
        }

    # ── Score Distribution ────────────────────────────────────────────────

    async def get_lead_score_distribution(self, team_id: uuid.UUID) -> list[dict]:
        """Count of leads per score_band."""
        result = await self.db.execute(
            select(Lead.score_band, func.count(Lead.id).label("count"))
            .where(Lead.team_id == team_id)
            .group_by(Lead.score_band)
            .order_by(func.count(Lead.id).desc())
        )
        return [{"score_band": sb, "count": c} for sb, c in result.all()]

    # ── Signal Category Distribution ──────────────────────────────────────

    async def get_signal_category_distribution(self, team_id: uuid.UUID) -> list[dict]:
        """Count of buying signals per category."""
        result = await self.db.execute(
            select(BuyingSignal.category, func.count(BuyingSignal.id).label("count"))
            .select_from(BuyingSignal)
            .join(Lead, BuyingSignal.lead_id == Lead.id)
            .where(Lead.team_id == team_id)
            .group_by(BuyingSignal.category)
            .order_by(func.count(BuyingSignal.id).desc())
        )
        return [{"category": cat, "count": c} for cat, c in result.all()]