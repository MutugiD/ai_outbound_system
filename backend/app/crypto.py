"""Small crypto helpers for encrypting secrets at rest.

This intentionally focuses on:
  - server-side encryption for provider tokens/keys stored in DB
  - stable keyed hashing for lookup/dedup without storing plaintext
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class CryptoError(Exception):
    pass


def _normalize_fernet_key(raw: str) -> bytes:
    raw_bytes = raw.encode("utf-8")

    # If caller provided a valid Fernet key (urlsafe base64 -> 32 bytes), accept it.
    try:
        decoded = base64.urlsafe_b64decode(raw_bytes)
        if len(decoded) == 32:
            return raw_bytes
    except Exception:
        pass

    # Otherwise derive a stable 32-byte key from the provided string.
    digest = hashlib.sha256(raw_bytes).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    key = _normalize_fernet_key(settings.ENCRYPTION_KEY)
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    if plaintext is None or not str(plaintext).strip():
        raise CryptoError("Secret cannot be empty")
    token = _fernet().encrypt(str(plaintext).encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    if ciphertext is None or not str(ciphertext).strip():
        raise CryptoError("Ciphertext cannot be empty")
    try:
        pt = _fernet().decrypt(str(ciphertext).encode("utf-8"))
        return pt.decode("utf-8")
    except InvalidToken as exc:
        raise CryptoError("Invalid ciphertext") from exc


def keyed_hash_secret(secret: str) -> str:
    """Return an HMAC-SHA256 hex digest for stable lookup/dedup."""
    if secret is None:
        secret = ""
    key = settings.SECRET_KEY.encode("utf-8")
    msg = str(secret).encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()

