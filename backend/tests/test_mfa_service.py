import pytest
from types import SimpleNamespace

from app.services.mfa_service import (
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    hash_recovery_code,
    normalize_recovery_code,
    totp_at,
    verify_totp,
    verify_user_totp,
)


def test_totp_rfc_6238_sha1_vector_and_replay_window():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp_at(secret, 59)[0] == "287082"
    assert verify_totp(secret, "287082", now=59) == 1
    assert verify_totp(secret, "287082", now=59, last_counter=1) is None
    assert verify_totp(secret, "287082", now=90) is None


def test_totp_accepts_previous_step_but_not_future_step():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    previous, _ = totp_at(secret, 59)
    assert verify_totp(secret, previous, now=60) == 1
    next_step, _ = totp_at(secret, 90)
    assert verify_totp(secret, next_step, now=60) is None


def test_recovery_codes_are_single_hashable_values():
    codes = generate_recovery_codes()
    assert len(codes) == 10
    assert all(len(code) == 24 for code in codes)
    assert normalize_recovery_code(codes[0].lower()) == codes[0].replace("-", "")
    assert hash_recovery_code(codes[0]) == hash_recovery_code(codes[0].replace("-", " "))
    assert hash_recovery_code(codes[0]) != hash_recovery_code(codes[1])


def test_encrypted_secret_authenticates_user_and_purpose(monkeypatch):
    from app.services import mfa_service

    monkeypatch.setattr(
        mfa_service,
        "get_settings",
        lambda: SimpleNamespace(
            MFA_ENCRYPTION_KEY="test-only-independent-encryption-key",
            SECRET_KEY="test-only-signing-key",
            ENVIRONMENT="test",
        ),
    )
    encrypted = encrypt_secret("JBSWY3DPEHPK3PXP", 17)
    assert decrypt_secret(encrypted, 17) == "JBSWY3DPEHPK3PXP"
    monkeypatch.setattr(
        mfa_service,
        "get_settings",
        lambda: SimpleNamespace(
            MFA_ENCRYPTION_KEY="different-independent-test-encryption-key",
            SECRET_KEY="test-signing-key",
            ENVIRONMENT="test",
        ),
    )
    assert verify_user_totp(encrypted, 17, "000000") is None
    monkeypatch.setattr(
        mfa_service,
        "get_settings",
        lambda: SimpleNamespace(
            MFA_ENCRYPTION_KEY="test-only-independent-encryption-key",
            SECRET_KEY="test-signing-key",
            ENVIRONMENT="test",
        ),
    )
    with pytest.raises(Exception):
        decrypt_secret(encrypted, 18)
    with pytest.raises(Exception):
        decrypt_secret(encrypted, 17, "pending")
