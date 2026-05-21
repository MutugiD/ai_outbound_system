"""Tests for the Personalization Engine, Campaign System, Outreach Messages, Reply Classification, and Follow-Up Automation."""

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import SQLModel

# ── Model imports ────────────────────────────────────────────────────────────

from app.models.lead import Lead
from app.models.company import Company
from app.models.contact import Contact
from app.models.campaign import Campaign, CampaignStep, CampaignEnrollment
from app.models.message import OutreachMessage
from app.models.reply import Reply, ReplyClassification
from app.models.follow_up import FollowUpTask
from app.models.signal import BuyingSignal
from app.models.team import Team
from app.models.user import User


# ── Pytest fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def team_id():
    return uuid.uuid4()


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def lead_id():
    return uuid.uuid4()


@pytest.fixture
def campaign_id():
    return uuid.uuid4()


@pytest.fixture
def sample_company(team_id):
    return Company(
        id=uuid.uuid4(),
        team_id=team_id,
        name="Acme Corp",
        domain="acme.com",
        industry="technology",
        employee_count=50,
        revenue_estimate=Decimal("5000000"),
        description="A technology company building smart solutions.",
    )


@pytest.fixture
def sample_contact():
    return Contact(
        id=uuid.uuid4(),
        first_name="Jane",
        last_name="Smith",
        full_name="Jane Smith",
        title="VP of Operations",
        seniority="vp",
        email="jane@acme.com",
        email_status="verified",
    )


@pytest.fixture
def sample_lead(team_id, sample_company, sample_contact):
    return Lead(
        id=uuid.uuid4(),
        team_id=team_id,
        company_id=sample_company.id,
        contact_id=sample_contact.id,
        status="ready",
        pipeline_stage="ready_for_outreach",
        lead_score=75,
        score_band="hot",
    )


@pytest.fixture
def sample_signals(lead_id):
    return [
        BuyingSignal(
            id=uuid.uuid4(),
            lead_id=lead_id,
            category="crm_pain",
            evidence="We're drowning in spreadsheets for customer data",
            source="reddit",
            confidence=Decimal("0.85"),
            detection_method="rule",
        ),
        BuyingSignal(
            id=uuid.uuid4(),
            lead_id=lead_id,
            category="manual_processes",
            evidence="Still doing manual data entry for every order",
            source="website",
            confidence=Decimal("0.75"),
            detection_method="llm",
        ),
    ]


@pytest.fixture
def sample_campaign(team_id, user_id):
    return Campaign(
        id=uuid.uuid4(),
        team_id=team_id,
        name="Q1 Outreach",
        description="Quarterly outreach campaign",
        status="draft",
        goal="book_meeting",
        tone="professional",
        approval_mode="manual",
        send_limits={},
        created_by=user_id,
    )


@pytest.fixture
def sample_campaign_step(campaign_id):
    return CampaignStep(
        id=uuid.uuid4(),
        campaign_id=campaign_id,
        step_order=1,
        channel="email",
        delay_days=0,
        template_type="initial_email",
        subject_template="Quick question about {{company_name}}",
        body_template="Hi {{first_name}},\n\nI noticed {{company_name}}...",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. PERSONALIZATION ENGINE TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestPersonalizationContext:
    """Tests for the PersonalizationContext builder."""

    def test_build_prompt_context_with_all_data(self, sample_lead, sample_company, sample_contact, sample_signals):
        from app.services.ai.personalization_engine import PersonalizationContext

        ctx = PersonalizationContext(
            lead=sample_lead,
            company=sample_company,
            contact=sample_contact,
            signals=sample_signals,
        )

        context_text = ctx.build_prompt_context()

        # Should contain contact info
        assert "Jane Smith" in context_text
        assert "VP of Operations" in context_text

        # Should contain company info
        assert "Acme Corp" in context_text
        assert "technology" in context_text

        # Should contain signals
        assert "crm_pain" in context_text
        assert "manual_processes" in context_text

    def test_build_prompt_context_minimal(self, sample_lead):
        from app.services.ai.personalization_engine import PersonalizationContext

        ctx = PersonalizationContext(lead=sample_lead)
        context_text = ctx.build_prompt_context()
        assert context_text  # Should always return something

    def test_get_top_signals(self, sample_lead, sample_signals):
        from app.services.ai.personalization_engine import PersonalizationContext

        ctx = PersonalizationContext(lead=sample_lead, signals=sample_signals)
        top = ctx.get_top_signals(2)
        assert len(top) <= 2
        # Highest confidence signal should be first
        if len(top) >= 2:
            assert float(top[0].confidence) >= float(top[1].confidence)

    def test_get_contact_first_name(self, sample_lead, sample_contact):
        from app.services.ai.personalization_engine import PersonalizationContext

        ctx = PersonalizationContext(lead=sample_lead, contact=sample_contact)
        assert ctx.get_contact_first_name() == "Jane"

    def test_get_contact_first_name_fallback(self, sample_lead):
        from app.services.ai.personalization_engine import PersonalizationContext

        ctx = PersonalizationContext(lead=sample_lead)
        assert ctx.get_contact_first_name() == "there"


class TestPersonalizationEngineStrategies:
    """Tests for strategy definitions and tone guidelines."""

    def test_strategies_defined(self):
        from app.services.ai.personalization_engine import STRATEGIES, STRATEGY_DESCRIPTIONS

        assert "pain_point" in STRATEGIES
        assert "compliment" in STRATEGIES
        assert "question" in STRATEGIES
        assert "insight" in STRATEGIES
        assert "direct" in STRATEGIES

        for strategy in STRATEGIES:
            assert strategy in STRATEGY_DESCRIPTIONS

    def test_tone_guidelines_defined(self):
        from app.services.ai.personalization_engine import TONE_GUIDELINES

        assert "professional" in TONE_GUIDELINES
        assert "casual" in TONE_GUIDELINES
        assert "direct" in TONE_GUIDELINES
        assert "consultative" in TONE_GUIDELINES


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CAMPAIGN SYSTEM TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestCampaignModel:
    """Tests for Campaign, CampaignStep, and CampaignEnrollment models."""

    def test_campaign_creation(self, team_id, user_id):
        campaign = Campaign(
            team_id=team_id,
            name="Test Campaign",
            description="A test campaign",
            status="draft",
            goal="book_meeting",
            tone="professional",
            approval_mode="manual",
            send_limits={"daily_limit": 100},
            created_by=user_id,
        )
        assert campaign.name == "Test Campaign"
        assert campaign.status == "draft"
        assert campaign.goal == "book_meeting"
        assert campaign.tone == "professional"
        assert campaign.approval_mode == "manual"
        assert campaign.send_limits == {"daily_limit": 100}

    def test_campaign_step_creation(self, campaign_id):
        step = CampaignStep(
            campaign_id=campaign_id,
            step_order=1,
            channel="email",
            delay_days=3,
            template_type="initial_email",
            subject_template="Hello {{first_name}}",
            body_template="This is a template.",
        )
        assert step.campaign_id == campaign_id
        assert step.step_order == 1
        assert step.channel == "email"
        assert step.delay_days == 3

    def test_campaign_enrollment_creation(self, campaign_id, lead_id):
        enrollment = CampaignEnrollment(
            campaign_id=campaign_id,
            lead_id=lead_id,
            status="pending",
            current_step=0,
            next_step_at=datetime.utcnow(),
        )
        assert enrollment.status == "pending"
        assert enrollment.current_step == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. MESSAGE MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestOutreachMessageModel:
    """Tests for OutreachMessage model."""

    def test_message_creation(self, lead_id, campaign_id):
        msg = OutreachMessage(
            lead_id=lead_id,
            campaign_id=campaign_id,
            channel="email",
            subject="Quick question",
            body="Hi Jane, I wanted to reach out...",
            personalization_sources=["signal:crm_pain", "company:Acme Corp"],
            status="draft",
        )
        assert msg.lead_id == lead_id
        assert msg.campaign_id == campaign_id
        assert msg.channel == "email"
        assert msg.subject == "Quick question"
        assert msg.status == "draft"
        assert len(msg.personalization_sources) == 2

    def test_message_status_values(self, lead_id):
        """Test all valid message statuses."""
        valid_statuses = [
            "draft", "pending_approval", "approved", "scheduled",
            "sent", "delivered", "opened", "clicked", "replied", "bounced", "failed",
        ]
        for status in valid_statuses:
            msg = OutreachMessage(lead_id=lead_id, channel="email", body="test", status=status)
            assert msg.status == status


# ═══════════════════════════════════════════════════════════════════════════════
# 4. REPLY CLASSIFICATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestReplyClassifier:
    """Tests for the ReplyClassifier rule-based classification."""

    def test_quick_classify_unsubscribe(self):
        from app.services.ai.reply_classifier import ReplyClassifier

        classifier = ReplyClassifier()
        result = classifier._quick_classify("Please unsubscribe me from this list.")
        assert result is not None
        assert result.classification == "unsubscribe"
        assert result.confidence >= 0.9

    def test_quick_classify_out_of_office(self):
        from app.services.ai.reply_classifier import ReplyClassifier

        classifier = ReplyClassifier()
        result = classifier._quick_classify("I am currently out of the office and will return on Monday.")
        assert result is not None
        assert result.classification == "out_of_office"

    def test_quick_classify_short_text(self):
        from app.services.ai.reply_classifier import ReplyClassifier

        classifier = ReplyClassifier()
        result = classifier._quick_classify("ok")
        assert result is not None
        assert result.classification == "no_response"

    def test_quick_classify_neutral_reply(self):
        """Neutral replies should return None (needs LLM classification)."""
        from app.services.ai.reply_classifier import ReplyClassifier

        classifier = ReplyClassifier()
        result = classifier._quick_classify("Thanks for the info, I'll think about it.")
        assert result is None  # No quick match, needs LLM

    def test_quick_classify_spam(self):
        from app.services.ai.reply_classifier import ReplyClassifier

        classifier = ReplyClassifier()
        result = classifier._quick_classify("Click here to claim your free money now!")
        assert result is not None
        assert result.classification == "spam"

    def test_category_descriptions_complete(self):
        from app.services.ai.reply_classifier import VALID_CATEGORIES, CATEGORY_DESCRIPTIONS

        for category in VALID_CATEGORIES:
            assert category in CATEGORY_DESCRIPTIONS, f"Missing description for {category}"


class TestReplyClassificationModel:
    """Tests for Reply and ReplyClassification models."""

    def test_reply_creation(self, lead_id):
        reply = Reply(
            lead_id=lead_id,
            channel="email",
            subject="Re: Quick question",
            body="Thanks for reaching out. I'm interested in learning more.",
            from_email="jane@acme.com",
            from_name="Jane Smith",
        )
        assert reply.lead_id == lead_id
        assert reply.channel == "email"
        assert reply.body == "Thanks for reaching out. I'm interested in learning more."

    def test_reply_classification_creation(self, lead_id):
        reply_id = uuid.uuid4()
        classification = ReplyClassification(
            reply_id=reply_id,
            lead_id=lead_id,
            classification="positive_interest",
            subtype="engaged",
            confidence=Decimal("0.92"),
            summary="Prospect expressed interest in learning more.",
            recommended_action="send_follow_up",
            draft_response="Great to hear! I'd love to set up a 15-min call...",
            model_used="gpt-4o-mini",
        )
        assert classification.classification == "positive_interest"
        assert classification.confidence == Decimal("0.92")
        assert classification.recommended_action == "send_follow_up"
        assert classification.draft_response is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. FOLLOW-UP AUTOMATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestFollowUpDelays:
    """Tests for follow-up timing configuration."""

    def test_all_categories_have_delays(self):
        from app.services.follow_up_service import FOLLOW_UP_DELAYS
        from app.services.ai.reply_classifier import VALID_CATEGORIES

        # Every valid reply category should have a delay rule
        for category in VALID_CATEGORIES:
            assert category in FOLLOW_UP_DELAYS, f"Missing delay rule for {category}"

    def test_urgent_categories_have_short_delays(self):
        from app.services.follow_up_service import FOLLOW_UP_DELAYS

        assert FOLLOW_UP_DELAYS["meeting_request"]["delay_hours"] <= 1
        assert FOLLOW_UP_DELAYS["positive_interest"]["delay_hours"] <= 4

    def test_negative_categories_immediate_suppression(self):
        from app.services.follow_up_service import FOLLOW_UP_DELAYS

        assert FOLLOW_UP_DELAYS["unsubscribe"]["delay_hours"] == 0
        assert FOLLOW_UP_DELAYS["not_interested"]["delay_hours"] == 0
        assert FOLLOW_UP_DELAYS["unsubscribe"]["task_type"] == "suppress_lead"

    def test_ooo_has_long_delay(self):
        from app.services.follow_up_service import FOLLOW_UP_DELAYS

        assert FOLLOW_UP_DELAYS["out_of_office"]["delay_hours"] >= 168  # 1 week


class TestFollowUpTaskModel:
    """Tests for FollowUpTask model."""

    def test_task_creation(self, lead_id):
        task = FollowUpTask(
            lead_id=lead_id,
            task_type="send_message",
            due_at=datetime.utcnow(),
            status="pending",
            data={"classification": "positive_interest", "recommended_action": "send_follow_up"},
        )
        assert task.lead_id == lead_id
        assert task.task_type == "send_message"
        assert task.status == "pending"
        assert task.data["classification"] == "positive_interest"

    def test_all_task_types(self, lead_id):
        """Verify all documented task types."""
        valid_task_types = [
            "send_message", "book_meeting", "draft_objection_response",
            "schedule_reminder", "suppress_lead",
        ]
        for task_type in valid_task_types:
            task = FollowUpTask(
                lead_id=lead_id,
                task_type=task_type,
                status="pending",
                data={},
            )
            assert task.task_type == task_type


# ═══════════════════════════════════════════════════════════════════════════════
# 6. SCHEMA VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestCampaignSchemas:
    """Tests for Campaign Pydantic schemas."""

    def test_campaign_create_schema(self):
        from app.schemas.outreach import CampaignCreate

        data = CampaignCreate(
            name="Test Campaign",
            description="A test",
            goal="book_meeting",
            tone="professional",
        )
        assert data.name == "Test Campaign"
        assert data.goal == "book_meeting"

    def test_campaign_step_create_schema(self):
        from app.schemas.outreach import CampaignStepCreate

        data = CampaignStepCreate(
            step_order=1,
            channel="email",
            delay_days=3,
            template_type="initial_email",
            subject_template="Hello",
            body_template="Message body",
        )
        assert data.step_order == 1
        assert data.delay_days == 3

    def test_enroll_leads_request_schema(self):
        from app.schemas.outreach import EnrollLeadsRequest

        lead_ids = [uuid.uuid4(), uuid.uuid4()]
        data = EnrollLeadsRequest(lead_ids=lead_ids)
        assert len(data.lead_ids) == 2


class TestMessageSchemas:
    """Tests for Message Pydantic schemas."""

    def test_generate_messages_request(self):
        from app.schemas.outreach import GenerateMessagesRequest

        data = GenerateMessagesRequest(
            lead_id=uuid.uuid4(),
            channel="email",
            strategies=["pain_point", "question"],
            tone="professional",
            goal="generate_interest",
            num_variants=2,
        )
        assert data.channel == "email"
        assert len(data.strategies) == 2
        assert data.num_variants == 2


class TestReplySchemas:
    """Tests for Reply Pydantic schemas."""

    def test_reply_create_schema(self):
        from app.schemas.outreach import ReplyCreate

        data = ReplyCreate(
            lead_id=uuid.uuid4(),
            channel="email",
            body="I'm interested in learning more.",
            from_email="jane@acme.com",
            from_name="Jane Smith",
        )
        assert data.channel == "email"
        assert data.body == "I'm interested in learning more."

    def test_classify_text_request_schema(self):
        from app.schemas.outreach import ClassifyTextRequest

        data = ClassifyTextRequest(
            reply_text="Please send me more info",
            original_subject="Quick question about your product",
        )
        assert "more info" in data.reply_text

    def test_classify_text_response_schema(self):
        from app.schemas.outreach import ClassifyTextResponse

        data = ClassifyTextResponse(
            classification="positive_interest",
            subtype="engaged",
            confidence=0.85,
            summary="Prospect wants more info",
            recommended_action="send_follow_up",
            draft_response="Here's more info...",
        )
        assert data.classification == "positive_interest"
        assert data.confidence == 0.85


class TestFollowUpSchemas:
    """Tests for FollowUp Pydantic schemas."""

    def test_reschedule_task_request(self):
        from app.schemas.outreach import RescheduleTaskRequest
        from datetime import datetime, timedelta

        data = RescheduleTaskRequest(new_due_at=datetime.utcnow() + timedelta(days=3))
        assert data.new_due_at is not None