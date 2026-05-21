"""Shared security utilities for the AI Outbound OS backend.

Provides helpers for:
- Log input sanitization (log injection prevention)
- URL validation (SSRF prevention)
- Path safety (path traversal prevention)
"""

import os
import re
from urllib.parse import urlparse


# ── Log sanitization ──────────────────────────────────────────────────────

# Control characters and newlines that could be used for log injection
_LOG_SANITISE_RE = re.compile(r"[\r\n\t\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_log(value: str) -> str:
    """Strip newlines and control characters from a value before logging.

    This prevents log injection attacks where user-supplied data containing
    newlines or control characters could forge additional log entries.

    Parameters
    ----------
    value : str
        The value to sanitize (will be cast to str if not already).

    Returns
    -------
    str
        The sanitized string with newlines replaced by ``\\n``/``\\r`` escapes
        and other control characters removed.
    """
    text = str(value)
    # Replace newlines with escaped versions to preserve info without injection
    text = text.replace("\r\n", "\\n")
    text = text.replace("\r", "\\n")
    text = text.replace("\n", "\\n")
    # Strip remaining control characters
    text = _LOG_SANITISE_RE.sub("", text)
    return text


# ── URL validation (SSRF prevention) ──────────────────────────────────────

_ALLOWED_SCHEMES = {"https"}
_BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "169.254.169.254",  # AWS/cloud metadata
}
_PRIVATE_NET_RE = re.compile(
    r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|fc00:|fe80:)",
)


def validate_url_for_fetch(url: str) -> str:
    """Validate and normalise a URL before making an HTTP request.

    Prevents SSRF by enforcing HTTPS, blocking private/loopback IPs,
    and rejecting obviously malformed URLs.

    Parameters
    ----------
    url : str
        The URL to validate.

    Returns
    -------
    str
        The validated, normalised URL.

    Raises
    ------
    ValueError
        If the URL is invalid, uses a blocked scheme, or targets a
        private/local network address.
    """
    parsed = urlparse(url)

    # Require a scheme
    if not parsed.scheme:
        # Default to https if no scheme provided
        url = f"https://{url}"
        parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme '{scheme}' is not allowed; only https is permitted")

    hostname = parsed.hostname or ""
    hostname_lower = hostname.lower()

    # Block known-dangerous hostnames
    if hostname_lower in _BLOCKED_HOSTS:
        raise ValueError(f"URL hostname '{hostname}' is blocked (private/reserved address)")

    # Block private network ranges
    if _PRIVATE_NET_RE.match(hostname_lower):
        raise ValueError(f"URL hostname '{hostname}' appears to be a private/local network address")

    return url


# ── Path safety (path traversal prevention) ────────────────────────────────


def safe_filename(value: str) -> str:
    """Return only the basename component of a path, stripping any directory
    traversal sequences.

    Parameters
    ----------
    value : str
        A user-supplied filename or path component.

    Returns
    -------
    str
        Just the basename, with any ``..`` segments removed.
    """
    # Take only the final component (strips directory traversal)
    base = os.path.basename(value)
    # Extra safety: reject if basename still contains path separators
    if base in ("", ".", ".."):
        raise ValueError(f"Invalid filename: {value!r}")
    return base
