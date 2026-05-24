"""Import all models so Alembic can detect them."""

from app.models.team import Team
from app.models.user import User
from app.models.company import Company
from app.models.contact import Contact
from app.models.lead import Lead
from app.models.lead_source import LeadSource
from app.models.deduplication import DeduplicationMatch
from app.models.enrichment import EnrichmentRecord
from app.models.signal import BuyingSignal
from app.models.audit import WebsiteAudit
from app.models.research import AIResearchReport
from app.models.score import LeadScore
from app.models.campaign import Campaign, CampaignStep, CampaignEnrollment
from app.models.message import OutreachMessage
from app.models.reply import Reply, ReplyClassification
from app.models.follow_up import FollowUpTask
from app.models.pipeline import PipelineTransition
from app.models.note import LeadNote
from app.models.email_account import EmailAccount
from app.models.job import Job
from app.models.activity import ActivityLog
from app.models.suppression import SuppressionList
from app.models.integration import Integration
from app.models.api_key import APIKey
from app.models.notification import Notification
from app.models.marketing import AudienceScanJob, AudienceSignal, MarketingUsageDaily, SocialPostDraft

__all__ = [
    "Team",
    "User",
    "Company",
    "Contact",
    "Lead",
    "LeadSource",
    "DeduplicationMatch",
    "EnrichmentRecord",
    "BuyingSignal",
    "WebsiteAudit",
    "AIResearchReport",
    "LeadScore",
    "Campaign",
    "CampaignStep",
    "CampaignEnrollment",
    "OutreachMessage",
    "Reply",
    "ReplyClassification",
    "FollowUpTask",
    "PipelineTransition",
    "LeadNote",
    "EmailAccount",
    "Job",
    "ActivityLog",
    "SuppressionList",
    "Integration",
    "APIKey",
    "Notification",
    "AudienceScanJob",
    "AudienceSignal",
    "MarketingUsageDaily",
    "SocialPostDraft",
]
