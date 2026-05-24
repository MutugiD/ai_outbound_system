"""Resend email provider integration (outbound sends + basic status mapping)."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings


@dataclass(frozen=True)
class ResendSendResult:
    provider_message_id: str


def _format_from_header(from_email: str, from_name: str | None) -> str:
    if from_name and from_name.strip():
        return f"{from_name.strip()} <{from_email}>"
    return from_email


def _text_to_basic_html(text: str) -> str:
    # Minimal safe conversion: escape HTML, preserve newlines.
    return "<br>".join(html.escape(text).splitlines())


async def send_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    reply_to: Optional[str] = None,
) -> ResendSendResult:
    """Send an email via Resend.

    Uses Resend's REST API: POST https://api.resend.com/emails
    """
    if not settings.RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY not configured")
    if not settings.OUTREACH_FROM_EMAIL:
        raise ValueError("OUTREACH_FROM_EMAIL not configured")

    from_header = _format_from_header(settings.OUTREACH_FROM_EMAIL, settings.OUTREACH_FROM_NAME)

    payload: dict = {
        "from": from_header,
        "to": [to_email],
        "subject": subject,
        "text": text_body,
        "html": _text_to_basic_html(text_body),
    }
    if reply_to or settings.OUTREACH_REPLY_TO:
        payload["reply_to"] = reply_to or settings.OUTREACH_REPLY_TO

    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post("https://api.resend.com/emails", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    provider_message_id = data.get("id")
    if not provider_message_id:
        raise RuntimeError("Resend response missing id")
    return ResendSendResult(provider_message_id=str(provider_message_id))

