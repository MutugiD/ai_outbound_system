"""Svix-style webhook signature verification (used by Resend webhooks).

Resend signs webhook payloads using Svix headers:
  - svix-id
  - svix-timestamp
  - svix-signature

Signing content format:
  "{svix_id}.{svix_timestamp}.{raw_body_text}"
"""

from __future__ import annotations

import base64
import hmac
import hashlib
import time
from dataclasses import dataclass
from typing import Mapping


class WebhookVerificationError(Exception):
    pass


@dataclass(frozen=True)
class SvixHeaders:
    msg_id: str
    timestamp: str
    signature: str


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    # Headers are case-insensitive; FastAPI provides a case-insensitive mapping,
    # but we defensively normalize.
    target = name.lower()
    for k, v in headers.items():
        if k.lower() == target:
            return v
    return None


def _parse_svix_headers(headers: Mapping[str, str]) -> SvixHeaders:
    msg_id = _get_header(headers, "svix-id")
    ts = _get_header(headers, "svix-timestamp")
    sig = _get_header(headers, "svix-signature")
    if not msg_id or not ts or not sig:
        raise WebhookVerificationError("Missing svix signature headers")
    return SvixHeaders(msg_id=msg_id, timestamp=ts, signature=sig)


def _secret_to_key_bytes(secret: str) -> bytes:
    # Svix secrets are commonly formatted as: "whsec_<base64>"
    if secret.startswith("whsec_"):
        secret = secret.split("_", 1)[1]
    try:
        return base64.b64decode(secret)
    except Exception:
        return secret.encode("utf-8")


def verify_svix_webhook(
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
    secret: str,
    tolerance_seconds: int = 300,
) -> None:
    """Verify the Svix signature and timestamp. Raises on failure."""
    svix = _parse_svix_headers(headers)

    try:
        ts_int = int(svix.timestamp)
    except ValueError as exc:
        raise WebhookVerificationError("Invalid svix-timestamp") from exc

    now = int(time.time())
    if tolerance_seconds > 0 and abs(now - ts_int) > tolerance_seconds:
        raise WebhookVerificationError("svix-timestamp outside tolerance")

    body_text = raw_body.decode("utf-8")
    signed_content = f"{svix.msg_id}.{svix.timestamp}.{body_text}".encode()

    key = _secret_to_key_bytes(secret)
    digest = hmac.new(key, signed_content, hashlib.sha256).digest()
    expected_b64 = base64.b64encode(digest).decode("utf-8")

    # The signature header may contain multiple signatures (space delimited),
    # each like "v1,<base64sig>".
    parts = [p.strip() for p in svix.signature.split(" ") if p.strip()]
    for part in parts:
        if not part.startswith("v1,"):
            continue
        candidate = part.split(",", 1)[1]
        if hmac.compare_digest(candidate, expected_b64):
            return

    raise WebhookVerificationError("svix signature mismatch")
