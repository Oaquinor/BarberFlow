"""TOTP, encrypted secrets, and one-time recovery codes for privileged accounts."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

from app.core.config import get_settings

TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def provisioning_uri(secret: str, email: str) -> str:
    label = quote(f"KingFlow Barber:{email}", safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer=KingFlow%20Barber&algorithm=SHA1&digits=6&period=30"


def totp_at(secret: str, timestamp: int | float) -> tuple[str, int]:
    counter = int(timestamp // TOTP_PERIOD_SECONDS)
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**TOTP_DIGITS)
    return f"{value:06d}", counter


def verify_totp(
    secret: str, code: str, *, now: int | float | None = None, last_counter: int | None = None
) -> int | None:
    supplied = "".join(character for character in code if character.isdigit())
    if len(supplied) != TOTP_DIGITS:
        return None
    timestamp = time.time() if now is None else now
    current = int(timestamp // TOTP_PERIOD_SECONDS)
    for counter in (current, current - 1):
        if counter < 0 or (last_counter is not None and counter <= last_counter):
            continue
        expected, _ = totp_at(secret, counter * TOTP_PERIOD_SECONDS)
        if hmac.compare_digest(expected, supplied):
            return counter
    return None


def _encryption_key() -> bytes:
    settings = get_settings()
    if settings.ENVIRONMENT == "production" and not settings.MFA_ENCRYPTION_KEY:
        raise RuntimeError("Production MFA requires an independent MFA_ENCRYPTION_KEY")
    material = settings.MFA_ENCRYPTION_KEY or settings.SECRET_KEY
    if len(material.encode("utf-8")) < 32:
        raise RuntimeError("MFA encryption material must contain at least 32 bytes")
    if not material or material == "your-secret-key-change-this-in-production":
        raise RuntimeError(
            "Configure MFA_ENCRYPTION_KEY or a production SECRET_KEY before enrolling MFA"
        )
    return hashlib.sha256(("kingflow-mfa-v1:" + material).encode("utf-8")).digest()


def verify_user_totp(
    encrypted_secret: str, user_id: int, code: str, last_counter: int | None = None
) -> int | None:
    """Return no TOTP match if a key is unavailable, preserving recovery access."""
    try:
        secret = decrypt_secret(encrypted_secret, user_id)
    except (RuntimeError, ValueError, InvalidTag):
        return None
    return verify_totp(secret, code, last_counter=last_counter)


def encrypt_secret(secret: str, user_id: int, purpose: str = "active") -> str:
    nonce = secrets.token_bytes(12)
    aad = f"kingflow:mfa:{user_id}:{purpose}:v1".encode("ascii")
    encrypted = AESGCM(_encryption_key()).encrypt(nonce, secret.encode("ascii"), aad)
    return "v1." + base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_secret(value: str, user_id: int, purpose: str = "active") -> str:
    version, encoded = value.split(".", 1)
    if version != "v1":
        raise ValueError("Unsupported MFA secret version")
    payload = base64.urlsafe_b64decode(encoded.encode("ascii"))
    aad = f"kingflow:mfa:{user_id}:{purpose}:v1".encode("ascii")
    return AESGCM(_encryption_key()).decrypt(payload[:12], payload[12:], aad).decode("ascii")


def generate_recovery_codes(count: int = 10) -> list[str]:
    return [
        "-".join("".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4)) for _ in range(5))
        for _ in range(count)
    ]


def normalize_recovery_code(code: str) -> str:
    return "".join(character for character in code.upper() if character in _RECOVERY_ALPHABET)


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(normalize_recovery_code(code).encode("ascii")).hexdigest()
