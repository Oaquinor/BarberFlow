"""MySQL integration coverage for secure email password recovery."""

import re
from datetime import timedelta
from hashlib import sha256
from urllib.parse import unquote

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import AuditLog, LoginAttempt, PasswordResetToken, RefreshSession, User
from app.services.auth_record_retention import prune_expired_auth_records
from app.services.notification_service import NotificationService
from app.utils.datetime import utc_now_naive


def _user(db: Session, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("OriginalPassword123"),
        first_name="María",
        last_name="Prueba",
        role="barbershop_owner",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_password_reset_request_does_not_reveal_account_existence(
    client: TestClient, test_db: Session, monkeypatch,
):
    _user(test_db, "recovery@example.com")
    deliveries = []
    monkeypatch.setattr(
        NotificationService,
        "_send_email",
        lambda _self, recipient, subject, body: deliveries.append((recipient, subject, body)) or True,
    )
    existing = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "recovery@example.com"}
    )
    unknown = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "missing@example.com"}
    )

    assert existing.status_code == unknown.status_code == 202
    assert existing.json() == unknown.json()
    assert len(deliveries) == 1
    assert deliveries[0][0] == "recovery@example.com"
    match = re.search(r"reset-password\.html\?token=([^\"&]+)", deliveries[0][2])
    assert match
    raw_token = unquote(match.group(1))
    stored = test_db.query(PasswordResetToken).one()
    assert stored.token_hash != raw_token
    assert len(stored.token_hash) == 64


def test_password_reset_is_single_use_and_revokes_all_refresh_sessions(
    client: TestClient, test_db: Session, monkeypatch,
):
    user = _user(test_db, "recovery-once@example.com")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "OriginalPassword123"},
    )
    assert login.status_code == 200

    email_bodies = []
    monkeypatch.setattr(
        NotificationService,
        "_send_email",
        lambda _self, _recipient, _subject, body: email_bodies.append(body) or True,
    )
    requested = client.post(
        "/api/v1/auth/password-reset/request", json={"email": user.email}
    )
    assert requested.status_code == 202
    match = re.search(r"reset-password\.html\?token=([^\"&]+)", email_bodies[0])
    assert match
    raw_token = unquote(match.group(1))

    reset = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "RecoveredPassword456"},
    )
    assert reset.status_code == 200
    assert test_db.query(RefreshSession).filter(
        RefreshSession.user_id == user.id,
        RefreshSession.revoked_at.is_(None),
    ).count() == 0
    stale_access = client.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert stale_access.status_code == 401
    assert test_db.query(AuditLog).filter(
        AuditLog.actor_user_id == user.id,
        AuditLog.action == "auth.password_reset",
    ).count() == 1

    replay = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "AnotherPassword789"},
    )
    assert replay.status_code == 400
    old_password = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "OriginalPassword123"},
    )
    new_password = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "RecoveredPassword456"},
    )
    assert old_password.status_code == 401
    assert new_password.status_code == 200


def test_password_reset_rejects_weak_or_expired_credentials(
    client: TestClient, test_db: Session,
):
    assert client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "x" * 43, "new_password": "weakpassword"},
    ).status_code == 422
    expired_token = "x" * 43
    user = _user(test_db, "expired-recovery@example.com")
    test_db.add(PasswordResetToken(
        user_id=user.id,
        token_hash=sha256(expired_token.encode("utf-8")).hexdigest(),
        expires_at=utc_now_naive() - timedelta(minutes=1),
    ))
    test_db.commit()
    assert client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": expired_token, "new_password": "StrongPassword123"},
    ).status_code == 400


def test_password_reset_requests_are_rate_limited_per_email_and_ip(client: TestClient):
    payload = {"email": "rate-limited@example.com"}
    for _ in range(5):
        assert client.post("/api/v1/auth/password-reset/request", json=payload).status_code == 202
    assert client.post("/api/v1/auth/password-reset/request", json=payload).status_code == 429


def test_password_reset_requests_have_a_global_per_ip_limit(client: TestClient):
    for index in range(30):
        response = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": f"reset-{index}@example.com"},
        )
        assert response.status_code == 202
    blocked = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "reset-last@example.com"}
    )
    assert blocked.status_code == 429


def test_expired_authentication_records_are_pruned_in_bounded_batches(test_db: Session):
    now = utc_now_naive()
    user = _user(test_db, "retention@example.com")
    stale_attempt = LoginAttempt(
        key_hash="a" * 64,
        failed_count=1,
        window_started_at=now - timedelta(days=2),
        last_attempt_at=now - timedelta(days=2),
    )
    fresh_attempt = LoginAttempt(
        key_hash="b" * 64,
        failed_count=1,
        window_started_at=now,
        last_attempt_at=now,
    )
    stale_token = PasswordResetToken(
        user_id=user.id,
        token_hash=sha256(b"stale-token").hexdigest(),
        expires_at=now - timedelta(days=2),
    )
    fresh_token = PasswordResetToken(
        user_id=user.id,
        token_hash=sha256(b"fresh-token").hexdigest(),
        expires_at=now + timedelta(minutes=30),
    )
    test_db.add_all([stale_attempt, fresh_attempt, stale_token, fresh_token])
    test_db.commit()

    removed = prune_expired_auth_records(test_db, now, force=True)
    assert removed == 2
    assert test_db.query(LoginAttempt).filter(LoginAttempt.key_hash == "a" * 64).count() == 0
    assert test_db.query(LoginAttempt).filter(LoginAttempt.key_hash == "b" * 64).count() == 1
    assert test_db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == sha256(b"stale-token").hexdigest()).count() == 0
    assert test_db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == sha256(b"fresh-token").hexdigest()).count() == 1
