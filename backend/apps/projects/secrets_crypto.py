"""Encryption at rest for project secrets (spec §11).

Secret-flagged environment values are stored as ciphertext in the database — real
symmetric encryption (Fernet / AES-128-CBC + HMAC), not a reversible obfuscation
dressed up as "encryption".

The encryption key comes from the ENVIRONMENT only (never committed, never stored
in the DB): `BOLDRON_ENV_SECRET_KEY` if set (a urlsafe-base64 32-byte Fernet key),
otherwise one derived deterministically from Django's SECRET_KEY so encryption is on
by default in every deployment. Rotating the key makes existing secrets unreadable —
the standard tradeoff, stated honestly.

Ciphertext is tagged with a version prefix so a value that predates encryption (a
plaintext secret stored before this shipped) is still readable: decrypt() returns
such a value unchanged rather than failing.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    key = os.environ.get("BOLDRON_ENV_SECRET_KEY", "").strip()
    if key:
        return Fernet(key.encode())
    # Derive a stable Fernet key from the Django SECRET_KEY (urlsafe base64 of a
    # 32-byte SHA-256 digest). Deterministic, so the same deployment can always
    # decrypt what it encrypted.
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    """Return a tagged ciphertext string for a secret value. Empty stays empty."""
    if not plaintext:
        return ""
    token = _fernet().encrypt(plaintext.encode()).decode()
    return _PREFIX + token


def decrypt_secret(stored: str) -> str:
    """Return the plaintext for a stored secret value. A value without the version
    prefix (written before encryption shipped) is returned unchanged."""
    if not stored or not stored.startswith(_PREFIX):
        return stored or ""
    token = stored[len(_PREFIX):]
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        # Key changed or value corrupted — never crash the app; surface nothing.
        return ""


def is_encrypted(stored: str) -> bool:
    return bool(stored) and stored.startswith(_PREFIX)
