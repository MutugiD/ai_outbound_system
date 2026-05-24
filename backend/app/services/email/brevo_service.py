"""Brevo email provider integration (outbound transactional sends).

Uses Brevo Transactional Email API:
  POST https://api.brevo.com/v3/smtp/email
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings


@dataclass(frozen=True)
class BrevoSendResult:
    provider_message_id: str


def _text_to_basic_html(text: str) -> str:
    # Minimal safe conversion: escape HTML, preserve newlines.
    return "<br>".join(html.escape(text).splitlines())


async def send_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    reply_to: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
) -> BrevoSendResult:
    """Send an email via Brevo transactional API."""
    if not settings.BREVO_API_KEY:
        raise ValueError("BREVO_API_KEY not configured")
    if not settings.OUTREACH_FROM_EMAIL:
        raise ValueError("OUTREACH_FROM_EMAIL not configured")

    payload: dict = {
        "sender": {
            "email": settings.OUTREACH_FROM_EMAIL,
            "name": settings.OUTREACH_FROM_NAME or "AI Outbound OS",
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": text_body,
        "htmlContent": _text_to_basic_html(text_body),
    }

    if reply_to or settings.OUTREACH_REPLY_TO:
        payload["replyTo"] = {"email": reply_to or settings.OUTREACH_REPLY_TO}

    if headers:
        # Brevo supports arbitrary custom headers in the payload.
        payload["headers"] = dict(headers)

    req_headers = {
        "api-key": settings.BREVO_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post("https://api.brevo.com/v3/smtp/email", json=payload, headers=req_headers)
        resp.raise_for_status()
        data = resp.json() if resp.content else {}

    provider_message_id = data.get("messageId") or data.get("message_id") or data.get("id")
    if not provider_message_id and isinstance(data.get("messageIds"), list) and data["messageIds"]:
        provider_message_id = data["messageIds"][0]
    if not provider_message_id:
        raise RuntimeError("Brevo response missing message id")

    return BrevoSendResult(provider_message_id=str(provider_message_id))
