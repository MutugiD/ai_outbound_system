"""Website audit engine — technical, conversion, and automation checks.

Produces a WebsiteAudit record with composite score and actionable sales_angle.

Checks performed:
  - **Technical**: page speed, mobile friendliness, SSL, broken links
  - **Conversion**: CTA clarity, booking buttons, contact forms, email capture
  - **Automation**: chatbot, calendar booking, CRM forms, tracking scripts, support widget
"""

import logging
import re
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.company import Company
from app.models.audit import WebsiteAudit
from app.services.activity_service import log_activity
from app.security_utils import sanitize_log, validate_url_for_fetch

logger = logging.getLogger(__name__)

# ── Detection patterns ─────────────────────────────────────────────────────────

CHATBOT_PATTERNS = [
    re.compile(r"intercom", re.IGNORECASE),
    re.compile(r"intercomcdn\.com", re.IGNORECASE),
    re.compile(r"drift\.com", re.IGNORECASE),
    re.compile(r"crisp\.chat", re.IGNORECASE),
    re.compile(r"zendesk\.com/widget", re.IGNORECASE),
    re.compile(r"tawk\.to", re.IGNORECASE),
    re.compile(r"freshchat\.com", re.IGNORECASE),
    re.compile(r"livechat\.com", re.IGNORECASE),
    re.compile(r"chatwoot", re.IGNORECASE),
    re.compile(r"chatra\.ai", re.IGNORECASE),
]

BOOKING_PATTERNS = [
    re.compile(r"calendly\.com", re.IGNORECASE),
    re.compile(r"cal\.com", re.IGNORECASE),
    re.compile(r"acuityscheduling\.com", re.IGNORECASE),
    re.compile(r"youcanbook\.me", re.IGNORECASE),
    re.compile(r"meetings\.hubspot\.com", re.IGNORECASE),
    re.compile(r"appointlet\.com", re.IGNORECASE),
    re.compile(r"schedule.*book|book.*schedule", re.IGNORECASE),
]

CRM_FORM_PATTERNS = [
    re.compile(r"hubspot\.com/(forms|js)", re.IGNORECASE),
    re.compile(r"salesforce\.com/(forms|webtolead)", re.IGNORECASE),
    re.compile(r"activecampaign\.com", re.IGNORECASE),
    re.compile(r"pardot\.com", re.IGNORECASE),
    re.compile(r"marketo\.com", re.IGNORECASE),
]

TRACKING_PATTERNS = [
    re.compile(r"google-analytics\.com|gtag|ga\(|_gaq|_gat", re.IGNORECASE),
    re.compile(r"connect\.facebook\.net|fbevents\.js|fbq\(", re.IGNORECASE),
    re.compile(r"googletagmanager\.com|gtm\.js", re.IGNORECASE),
    re.compile(r"segment\.com/analytics\.js", re.IGNORECASE),
    re.compile(r"mixpanel\.com", re.IGNORECASE),
    re.compile(r"amplitude\.com", re.IGNORECASE),
]

SUPPORT_WIDGET_PATTERNS = [
    re.compile(r"zendesk\.com/widget", re.IGNORECASE),
    re.compile(r"freshdesk\.com", re.IGNORECASE),
    re.compile(r"helpscout\.net", re.IGNORECASE),
    re.compile(r"intercom", re.IGNORECASE),
]

CTA_PATTERNS = [
    re.compile(
        r"(get started|start free|try free|sign up|book a demo|request access|contact sales|get a quote|schedule a call|talk to us)",
        re.IGNORECASE,
    ),
]

EMAIL_CAPTURE_PATTERNS = [
    re.compile(r"(newsletter|subscribe|email.*list|mailing.*list|join.*list)", re.IGNORECASE),
    re.compile(r"convertkit\.com|mailchimp\.com|klaviyo\.com|buttondown\.email", re.IGNORECASE),
]

CONTACT_FORM_PATTERNS = [
    re.compile(r"<form[^>]*(contact|inquiry|get.in.touch|reach.out)", re.IGNORECASE),
    re.compile(r"(contact.*form|form.*contact|get.in.touch)", re.IGNORECASE),
]

SSL_INDICATOR = re.compile(r"https://", re.IGNORECASE)

VALUE_PROP_PATTERNS = [
    re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL),
]


class AuditService:
    """Website audit engine — runs technical, conversion, and automation checks."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Public API ──────────────────────────────────────────────────────────

    async def audit_website(
        self,
        company_id: uuid.UUID,
        domain: str,
    ) -> WebsiteAudit:
        """Run a full website audit for a company.

        Parameters
        ----------
        company_id : UUID
            The company ID to associate the audit with.
        domain : str
            The domain to audit (e.g. ``example.com``).

        Returns
        -------
        WebsiteAudit
            The persisted audit record with scores and findings.
        """
        # Fetch company for logging
        result = await self.db.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()

        # Normalise and validate domain/URL (SSRF prevention)
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"

        url = validate_url_for_fetch(domain.rstrip("/"))

        # ── Fetch the website ────────────────────────────────────────────
        html_content = ""
        response_headers: dict[str, str] = {}
        response_time_ms: float = 0.0
        ssl_ok = False
        status_code = 0

        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                start_time = datetime.now()
                resp = await client.get(url)
                elapsed = (datetime.now() - start_time).total_seconds()
                response_time_ms = elapsed * 1000
                status_code = resp.status_code
                html_content = resp.text
                response_headers = dict(resp.headers)
                ssl_ok = url.startswith("https://")
        except Exception as exc:
            logger.warning("Failed to fetch %s for audit: %s", sanitize_log(url), sanitize_log(str(exc)))
            # Try http fallback
            try:
                http_url = validate_url_for_fetch(url.replace("https://", "http://"))
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                    start_time = datetime.now()
                    resp = await client.get(http_url)
                    elapsed = (datetime.now() - start_time).total_seconds()
                    response_time_ms = elapsed * 1000
                    status_code = resp.status_code
                    html_content = resp.text
                    response_headers = dict(resp.headers)
                    ssl_ok = False
            except Exception as exc2:
                logger.error("Failed to fetch %s (http fallback): %s", sanitize_log(url), sanitize_log(str(exc2)))
                # Create a minimal audit even on complete failure
                return await self._create_audit(
                    company_id=company_id,
                    url=url,
                    html_content="",
                    headers={},
                    response_time_ms=0,
                    status_code=0,
                    ssl_ok=False,
                )

        # ── Run audits ───────────────────────────────────────────────────
        audit = await self._create_audit(
            company_id=company_id,
            url=url,
            html_content=html_content,
            headers=response_headers,
            response_time_ms=response_time_ms,
            status_code=status_code,
            ssl_ok=ssl_ok,
        )

        # Log activity
        team_id = company.team_id if company else uuid.UUID(int=0)
        await log_activity(
            self.db,
            team_id=team_id,
            user_id=None,
            lead_id=None,
            action="audit_completed",
            details={"company_id": str(company_id), "domain": domain, "score": audit.website_score},
        )

        return audit

    # ── Audit implementation ────────────────────────────────────────────────

    async def _create_audit(
        self,
        company_id: uuid.UUID,
        url: str,
        html_content: str,
        headers: dict[str, str],
        response_time_ms: float,
        status_code: int,
        ssl_ok: bool,
    ) -> WebsiteAudit:
        """Run all audit checks and create a WebsiteAudit record."""
        html_lower = html_content.lower()

        # ── Technical checks ────────────────────────────────────────────
        technical_findings: list[dict] = []
        page_speed_score = self._check_page_speed(response_time_ms, status_code, technical_findings)
        mobile_score = self._check_mobile(html_lower, technical_findings)
        ssl_score = 100 if ssl_ok else 0
        if not ssl_ok:
            technical_findings.append(
                {"check": "ssl", "issue": "No SSL certificate (HTTPS not detected)", "severity": "high"}
            )

        # Broken links check (simplified — check main page status)
        if status_code >= 400:
            technical_findings.append(
                {"check": "status_code", "issue": f"Main page returned HTTP {status_code}", "severity": "high"}
            )

        # ── Conversion checks ──────────────────────────────────────────
        conversion_findings: list[dict] = []

        has_cta, cta_clarity_score = self._check_cta(html_content, conversion_findings)
        has_booking = self._check_booking(html_lower, conversion_findings)
        has_contact_form = self._check_contact_form(html_lower, conversion_findings)
        has_email_capture = self._check_email_capture(html_lower, conversion_findings)
        value_prop_score = self._check_value_prop(html_content, conversion_findings)

        # ── Automation checks ──────────────────────────────────────────
        automation_findings: list[dict] = []

        has_chatbot = self._check_chatbot(html_lower, automation_findings)
        has_tracking = self._check_tracking(html_lower, automation_findings)
        has_crm_form = self._check_crm_forms(html_lower, automation_findings)
        has_support = self._check_support_widget(html_lower, automation_findings)

        # ── Composite score ─────────────────────────────────────────────
        # Weight: technical (30%) + conversion (40%) + automation (30%)
        tech_total = (page_speed_score + mobile_score + ssl_score) / 3
        conversion_total = (
            (cta_clarity_score * 0.25)
            + (100 if has_booking else 0) * 0.25
            + (100 if has_contact_form else 0) * 0.2
            + (100 if has_email_capture else 0) * 0.15
            + value_prop_score * 0.15
        )
        automation_total = (
            (100 if has_chatbot else 0) * 0.3
            + (100 if has_booking else 0) * 0.2  # booking counts for automation too
            + (100 if has_crm_form else 0) * 0.2
            + (100 if has_tracking else 0) * 0.2
            + (100 if has_support else 0) * 0.1
        )

        website_score = int(round(tech_total * 0.3 + conversion_total * 0.4 + automation_total * 0.3))
        website_score = max(0, min(100, website_score))

        # ── Weak CTA flag ───────────────────────────────────────────────
        weak_cta = not has_cta or cta_clarity_score < 40

        # ── Broken forms flag ───────────────────────────────────────────
        broken_forms = not has_contact_form and not has_booking and not has_email_capture

        # ── Generate sales angle ────────────────────────────────────────
        sales_angle = self._generate_sales_angle(
            has_chatbot=has_chatbot,
            has_booking=has_booking,
            has_contact_form=has_contact_form,
            has_email_capture=has_email_capture,
            has_tracking=has_tracking,
            weak_cta=weak_cta,
            page_speed_score=page_speed_score,
            mobile_score=mobile_score,
            ssl_ok=ssl_ok,
            company_id=company_id,
        )

        # ── Persist ─────────────────────────────────────────────────────
        domain = urlparse(url).netloc or url

        audit = WebsiteAudit(
            company_id=company_id,
            website_score=website_score,
            page_speed_score=page_speed_score,
            mobile_score=mobile_score,
            has_chatbot=has_chatbot,
            has_booking=has_booking,
            has_contact_form=has_contact_form,
            has_email_capture=has_email_capture,
            has_crm_form=has_crm_form,
            has_tracking_scripts=has_tracking,
            has_support_widget=has_support,
            broken_forms=broken_forms,
            weak_cta=weak_cta,
            technical_findings=technical_findings,
            conversion_findings=conversion_findings,
            automation_findings=automation_findings,
            sales_angle=sales_angle,
            raw_content_url=url,
        )
        self.db.add(audit)
        await self.db.flush()
        await self.db.refresh(audit)

        return audit

    # ── Individual check methods ────────────────────────────────────────────

    @staticmethod
    def _check_page_speed(response_time_ms: float, status_code: int, findings: list) -> int:
        """Score page speed based on response time."""
        if response_time_ms == 0:
            findings.append({"check": "page_speed", "issue": "Could not measure page speed", "severity": "high"})
            return 20

        if response_time_ms < 500:
            return 95
        elif response_time_ms < 1000:
            score = int(95 - (response_time_ms - 500) / 10)
            findings.append(
                {"check": "page_speed", "issue": f"Page load: {response_time_ms:.0f}ms (acceptable)", "severity": "low"}
            )
            return max(score, 70)
        elif response_time_ms < 2000:
            findings.append(
                {"check": "page_speed", "issue": f"Page load: {response_time_ms:.0f}ms (slow)", "severity": "medium"}
            )
            return max(int(70 - (response_time_ms - 1000) / 33), 30)
        elif response_time_ms < 5000:
            findings.append(
                {"check": "page_speed", "issue": f"Page load: {response_time_ms:.0f}ms (very slow)", "severity": "high"}
            )
            return max(int(30 - (response_time_ms - 2000) / 100), 10)
        else:
            findings.append(
                {
                    "check": "page_speed",
                    "issue": f"Page load: {response_time_ms:.0f}ms (extremely slow)",
                    "severity": "critical",
                }
            )
            return 5

    @staticmethod
    def _check_mobile(html: str, findings: list) -> int:
        """Check mobile friendliness (viewport meta tag)."""
        has_viewport = "viewport" in html
        if has_viewport:
            return 90
        findings.append(
            {"check": "mobile", "issue": "No viewport meta tag — likely not mobile-friendly", "severity": "high"}
        )
        return 20

    @staticmethod
    def _check_cta(html: str, findings: list) -> tuple[bool, int]:
        """Check CTA clarity. Returns (has_cta, clarity_score)."""
        for pattern in CTA_PATTERNS:
            if pattern.search(html):
                # CTA found — check how prominent
                count = len(pattern.findall(html))
                score = min(40 + count * 10, 100)
                return True, score

        findings.append({"check": "cta", "issue": "No clear call-to-action detected", "severity": "high"})
        return False, 15

    @staticmethod
    def _check_booking(html: str, findings: list) -> bool:
        """Check for booking/scheduling buttons."""
        for pattern in BOOKING_PATTERNS:
            if pattern.search(html):
                return True
        findings.append(
            {"check": "booking", "issue": "No booking/scheduling integration detected", "severity": "medium"}
        )
        return False

    @staticmethod
    def _check_contact_form(html: str, findings: list) -> bool:
        """Check for contact forms."""
        for pattern in CONTACT_FORM_PATTERNS:
            if pattern.search(html):
                return True
        # Broader check: any <form> element
        if "<form" in html:
            return True
        findings.append({"check": "contact_form", "issue": "No contact form detected", "severity": "medium"})
        return False

    @staticmethod
    def _check_email_capture(html: str, findings: list) -> bool:
        """Check for email capture/newsletter signup."""
        for pattern in EMAIL_CAPTURE_PATTERNS:
            if pattern.search(html):
                return True
        findings.append({"check": "email_capture", "issue": "No email capture mechanism detected", "severity": "low"})
        return False

    @staticmethod
    def _check_value_prop(html: str, findings: list) -> int:
        """Check for a value proposition above the fold (in h1/h2 tags)."""
        for pattern in VALUE_PROP_PATTERNS:
            matches = pattern.findall(html)
            if matches:
                # Found header content — score based on content
                return 70  # has headers with content
        findings.append(
            {"check": "value_prop", "issue": "No clear value proposition in header tags", "severity": "medium"}
        )
        return 20

    @staticmethod
    def _check_chatbot(html: str, findings: list) -> bool:
        """Check for chatbot/live chat."""
        for pattern in CHATBOT_PATTERNS:
            if pattern.search(html):
                return True
        findings.append(
            {"check": "chatbot", "issue": "No chatbot or live chat integration detected", "severity": "medium"}
        )
        return False

    @staticmethod
    def _check_tracking(html: str, findings: list) -> bool:
        """Check for analytics/tracking scripts."""
        for pattern in TRACKING_PATTERNS:
            if pattern.search(html):
                return True
        findings.append({"check": "tracking", "issue": "No analytics tracking detected", "severity": "low"})
        return False

    @staticmethod
    def _check_crm_forms(html: str, findings: list) -> bool:
        """Check for CRM/marketing form integrations."""
        for pattern in CRM_FORM_PATTERNS:
            if pattern.search(html):
                return True
        findings.append({"check": "crm_forms", "issue": "No CRM form integration detected", "severity": "low"})
        return False

    @staticmethod
    def _check_support_widget(html: str, findings: list) -> bool:
        """Check for support/help widgets."""
        for pattern in SUPPORT_WIDGET_PATTERNS:
            if pattern.search(html):
                return True
        findings.append({"check": "support_widget", "issue": "No support widget detected", "severity": "low"})
        return False

    # ── Sales angle generation ──────────────────────────────────────────────

    @staticmethod
    def _generate_sales_angle(
        has_chatbot: bool,
        has_booking: bool,
        has_contact_form: bool,
        has_email_capture: bool,
        has_tracking: bool,
        weak_cta: bool,
        page_speed_score: int,
        mobile_score: int,
        ssl_ok: bool,
        company_id: uuid.UUID,
    ) -> str:
        """Generate a human-readable sales angle based on audit findings."""
        angles: list[str] = []

        if not has_chatbot:
            angles.append(
                "No chatbot detected — opportunity to implement AI-powered customer engagement "
                "to capture leads 24/7 and reduce support volume by 30-40%."
            )
        if not has_booking:
            angles.append(
                "No booking system detected — adding a scheduling tool (e.g., Calendly/Cal.com) "
                "can increase meeting bookings by 2-3x."
            )
        if weak_cta:
            angles.append(
                "Weak or missing call-to-action — optimizing the CTA can significantly "
                "improve conversion rates on landing pages."
            )
        if not has_contact_form:
            angles.append(
                "No contact form found — a well-placed contact form can capture "
                "inbound leads that would otherwise be lost."
            )
        if not has_email_capture:
            angles.append(
                "No email capture mechanism — adding a newsletter signup or lead magnet can build a nurture pipeline."
            )
        if not has_tracking:
            angles.append("No analytics tracking detected — without data, they can't optimize their conversion funnel.")
        if not ssl_ok:
            angles.append("No SSL certificate — this hurts SEO ranking and visitor trust.")
        if page_speed_score < 50:
            angles.append(
                f"Slow page speed (score: {page_speed_score}/100) — every second of delay reduces conversions by ~7%."
            )
        if mobile_score < 50:
            angles.append(
                "Poor mobile experience — over 50% of web traffic is mobile, "
                "a poorly optimized site loses half its potential leads."
            )

        if not angles:
            return "Website appears well-optimized. Focus on conversion optimization and automation layers for incremental gains."

        return " | ".join(angles)
