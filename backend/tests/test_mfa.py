"""MFA API integration tests require the dedicated MySQL test database."""

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import RefreshSession, User, UserMfaRecoveryCode
from app.services import mfa_service


def test_owner_mfa_enrollment_login_and_single_use_recovery(
    client: TestClient,
    test_db: Session,
    monkeypatch,
):
    monkeypatch.setattr(
        mfa_service,
        "get_settings",
        lambda: SimpleNamespace(
            MFA_ENCRYPTION_KEY="independent-test-encryption-key-value",
            SECRET_KEY="test-signing-key",
            ENVIRONMENT="test",
        ),
    )
    clock = [1_800_000_000]
    monkeypatch.setattr(mfa_service.time, "time", lambda: clock[0])
    user = User(
        email="mfa-owner@example.com",
        password_hash=hash_password("TestPassword123"),
        first_name="MFA",
        last_name="Owner",
        role="barbershop_owner",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()

    password_login = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "TestPassword123",
        },
    )
    assert password_login.status_code == 200
    bearer = {"Authorization": f"Bearer {password_login.json()['access_token']}"}

    setup = client.post(
        "/api/v1/auth/mfa/setup", headers=bearer, json={"password": "TestPassword123"}
    )
    assert setup.status_code == 200
    assert setup.headers["cache-control"] == "no-store"
    secret = setup.json()["secret"]
    enabled = client.post(
        "/api/v1/auth/mfa/enable",
        headers=bearer,
        json={"code": mfa_service.totp_at(secret, clock[0])[0]},
    )
    assert enabled.status_code == 200
    codes = enabled.json()["recovery_codes"]
    assert len(codes) == 10
    recovery_rows = test_db.query(UserMfaRecoveryCode).filter_by(user_id=user.id).all()
    assert len(recovery_rows) == 10
    assert all(row.code_hash not in codes for row in recovery_rows)

    challenge = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "TestPassword123",
        },
    )
    assert challenge.status_code == 200
    assert challenge.json()["mfa_required"] is True
    assert challenge.json()["access_token"] is None
    assert challenge.json()["refresh_token"] is None
    assert test_db.query(RefreshSession).filter_by(user_id=user.id).count() == 1

    clock[0] += 30
    verified = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "TestPassword123",
            "otp_code": mfa_service.totp_at(secret, clock[0])[0],
        },
    )
    assert verified.status_code == 200
    assert verified.json()["access_token"]

    recovery_login = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "TestPassword123",
            "otp_code": codes[0],
        },
    )
    assert recovery_login.status_code == 200
    assert recovery_login.json()["access_token"]
    replayed_recovery = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "TestPassword123",
            "otp_code": codes[0],
        },
    )
    assert replayed_recovery.status_code == 401
    assert test_db.query(RefreshSession).filter_by(user_id=user.id).count() == 3
