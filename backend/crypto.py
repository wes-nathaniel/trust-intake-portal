"""AES-256-GCM encryption for SSN storage.

Encrypts every SSN before it hits MongoDB. Decrypts only on explicit admin
reveal. Existing plaintext SSNs are handled transparently (decrypt_ssn passes
them through), so migration is lazy: on every write the value is re-persisted
in encrypted form.

Storage format: `enc:v1:<nonce_b64>:<ciphertext_b64>`
- 12-byte random nonce (AES-GCM standard)
- Base64-urlsafe encoding (no padding issues)
- Prefix makes it trivial to detect legacy plaintext vs encrypted values
"""
from __future__ import annotations

import base64
import logging
import os
import re
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("trust-portal")

_KEY_ENV = "SSN_ENCRYPTION_KEY"
_PREFIX = "enc:v1:"
_KEY_LEN = 32  # AES-256
_NONCE_LEN = 12


def _load_or_create_key() -> bytes:
    """Load the SSN encryption key from env. If missing, generate a new one
    and log a WARN so operators know to persist it in production .env. On
    production the key MUST be set via env or every restart rotates it —
    which would make old ciphertexts unreadable."""
    raw = os.environ.get(_KEY_ENV, "").strip()
    if raw:
        try:
            key = base64.urlsafe_b64decode(raw.encode("utf-8"))
            if len(key) != _KEY_LEN:
                raise ValueError(f"expected {_KEY_LEN} bytes, got {len(key)}")
            return key
        except Exception as e:
            logger.error(
                f"{_KEY_ENV} is set but invalid ({e}); refusing to start with a "
                f"random key that would orphan existing ciphertexts."
            )
            raise RuntimeError(f"Invalid {_KEY_ENV}: {e}")
    # Not set — generate a fresh key. Only safe in dev. Production must set
    # SSN_ENCRYPTION_KEY explicitly.
    key = AESGCM.generate_key(bit_length=256)
    logger.warning(
        f"{_KEY_ENV} not set; generated an EPHEMERAL key. Set "
        f"{_KEY_ENV}={base64.urlsafe_b64encode(key).decode('ascii')} "
        f"in backend/.env to persist across restarts."
    )
    return key


_KEY = _load_or_create_key()
_AESGCM = AESGCM(_KEY)


def is_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_ssn(plaintext: str) -> str:
    """Return an encrypted representation of `plaintext`. Empty / None input
    returns empty string. Already-encrypted input is returned unchanged so
    accidental double-encryption is impossible."""
    if not plaintext:
        return ""
    if is_encrypted(plaintext):
        return plaintext
    nonce = os.urandom(_NONCE_LEN)
    ct = _AESGCM.encrypt(nonce, plaintext.encode("utf-8"), None)
    return (
        _PREFIX
        + base64.urlsafe_b64encode(nonce).decode("ascii")
        + ":"
        + base64.urlsafe_b64encode(ct).decode("ascii")
    )


def decrypt_ssn(value: str) -> str:
    """Return the plaintext SSN. Passes legacy plaintext values through
    unchanged so cases created before encryption was rolled out still work.
    Returns empty string on decryption failure — the caller can decide how
    to surface that (typically log + treat as missing)."""
    if not value:
        return ""
    if not is_encrypted(value):
        # Legacy plaintext — passthrough
        return value
    try:
        _, _, body = value.partition(_PREFIX)
        nonce_b64, _, ct_b64 = body.partition(":")
        nonce = base64.urlsafe_b64decode(nonce_b64.encode("ascii"))
        ct = base64.urlsafe_b64decode(ct_b64.encode("ascii"))
        return _AESGCM.decrypt(nonce, ct, None).decode("utf-8")
    except Exception as e:
        logger.error(f"SSN decrypt failed: {e}")
        return ""


_DIGITS = re.compile(r"\D")


def mask_ssn(value: str) -> str:
    """Return the client-safe masked form 'XXX-XX-####'. Accepts either
    encrypted or plaintext input. Empty input → empty string."""
    if not value:
        return ""
    plain = decrypt_ssn(value) if is_encrypted(value) else value
    digits = _DIGITS.sub("", plain)
    if len(digits) < 4:
        return ""
    return f"XXX-XX-{digits[-4:]}"
