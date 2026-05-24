"""Provider-agnostic outbound email delivery helpers."""

from __future__ import annotations

from typing import Optional

from app.config import settings
from app.services.email import brevo_service, resend_service


async def send_outbound_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    reply_to: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
) -> tuple[str, str]:
    """Send an outbound email using the best configured provider.

    Provider priority:
      1) Brevo (if `BREVO_API_KEY` configured)
      2) Resend (if `RESEND_API_KEY` configured)

    Returns: (provider, provider_message_id)
    """
    last_exc: Exception | None = None

    if settings.BREVO_API_KEY:
        try:
            result = await brevo_service.send_email(
                to_email=to_email,
                subject=subject,
                text_body=text_body,
                reply_to=reply_to,
                headers=headers,
            )
            return "brevo", result.provider_message_id
        except Exception as exc:
            last_exc = exc

    if settings.RESEND_API_KEY:
        try:
            result = await resend_service.send_email(
                to_email=to_email,
                subject=subject,
                text_body=text_body,
                reply_to=reply_to,
            )
            return "resend", result.provider_message_id
        except Exception as exc:
            last_exc = exc

    if last_exc is not None:
        raise RuntimeError("No email provider succeeded") from last_exc

    raise ValueError("No email provider configured (set BREVO_API_KEY or RESEND_API_KEY)")
