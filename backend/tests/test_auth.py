"""Authentication and tenant boundary integration tests (MySQL test DB)."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Appointment, Barbershop, User
from app.utils.datetime import utc_now_naive


def _shop(db: Session, slug: str) -> Barbershop:
    shop = Barbershop(
        name=f"Tienda {slug}",
        slug=slug,
        email=f"{slug}@example.com",
        phone="8095551111",
        address_line1="Calle Principal 1",
        city="Santo Domingo",
        state="Distrito Nacional",
        postal_code="10101",
        country="DO",
    )
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return shop


def _user(db: Session, email: str, role: str, shop_id=None, active=True) -> User:
    user = User(
        email=email,
        password_hash=hash_password("TestPassword123"),
        first_name="Prueba",
        last_name="Usuario",
        role=role,
        is_active=active,
        barbershop_id=shop_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_login_returns_tokens_for_active_user(client: TestClient, test_db: Session):
    _user(test_db, "active@example.com", "barbershop_owner")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ACTIVE@EXAMPLE.COM", "password": "TestPassword123"},
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]

    old_refresh_token = response.json()["refresh_token"]
    rotated = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != old_refresh_token
    replay = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert replay.status_code == 401

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": rotated.json()["refresh_token"]},
    )
    assert logout.status_code == 200
    after_logout = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated.json()["refresh_token"]},
    )
    assert after_logout.status_code == 401


def test_inactive_user_cannot_login(client: TestClient, test_db: Session):
    _user(test_db, "inactive@example.com", "barbershop_owner", active=False)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "TestPassword123"},
    )
    assert response.status_code == 401


def test_password_change_revokes_refresh_sessions_and_requires_new_password(
    client: TestClient, test_db: Session,
):
    from app.models import RefreshSession

    user = _user(test_db, "password-change@example.com", "barbershop_owner")
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "TestPassword123"},
    )
    assert logged_in.status_code == 200
    tokens = logged_in.json()

    changed = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "current_password": "TestPassword123",
            "new_password": "UpdatedPassword456",
        },
    )
    assert changed.status_code == 200
    assert test_db.query(RefreshSession).filter(
        RefreshSession.user_id == user.id,
        RefreshSession.revoked_at.is_(None),
    ).count() == 0
    stale_access = client.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert stale_access.status_code == 401

    old_session = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert old_session.status_code == 401
    old_password = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "TestPassword123"},
    )
    assert old_password.status_code == 401
    new_password = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "UpdatedPassword456"},
    )
    assert new_password.status_code == 200
    rotated = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_password.json()["refresh_token"]},
    )
    assert rotated.status_code == 200


def test_repeated_bad_passwords_lock_the_account_and_ip_bucket(client: TestClient, test_db: Session):
    _user(test_db, "throttle@example.com", "barbershop_owner")
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "throttle@example.com", "password": "WrongPassword123"},
        )
        assert response.status_code == 401
    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "throttle@example.com", "password": "TestPassword123"},
    )
    assert blocked.status_code == 429


def test_support_contact_is_rate_limited_per_hashed_client_ip(
    client: TestClient, test_db: Session, monkeypatch
):
    import app.api.v1.endpoints.platform as platform
    from app.models import LoginAttempt

    monkeypatch.setattr(platform, "_send_email", lambda *_args, **_kwargs: True)
    recipient = User(
        email="support-admin@example.com", password_hash="unused", first_name="Support",
        last_name="Admin", role="super_admin", is_active=True,
        support_contact_enabled=True,
    )
    test_db.add(recipient)
    test_db.commit()
    payload = {"name": "Visitante", "email": "visitor@example.com", "message": "Necesito ayuda"}

    for _ in range(platform.SUPPORT_MESSAGE_LIMIT):
        assert client.post("/api/v1/support/contact", json=payload).status_code == 200
    blocked = client.post("/api/v1/support/contact", json=payload)
    assert blocked.status_code == 429

    bucket = platform._login_bucket_hash("support-ip", "testclient")
    assert bucket not in "testclient"
    assert test_db.query(LoginAttempt).filter(LoginAttempt.key_hash == bucket).count() == 1


def test_owner_cannot_read_another_tenant(client: TestClient, test_db: Session):
    first = _shop(test_db, "tenant-one")
    second = _shop(test_db, "tenant-two")
    owner = _user(test_db, "owner-one@example.com", "barbershop_owner", first.id)
    token = create_access_token({"sub": str(owner.id), "role": owner.role})

    response = client.get(
        f"/api/v1/onboarding/profile?barbershop_id={second.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_barber_cannot_change_another_barbers_appointment(client: TestClient, test_db: Session):
    shop = _shop(test_db, "appointment-tenant")
    barber_a = _user(test_db, "barber-a@example.com", "barber", shop.id)
    barber_b = _user(test_db, "barber-b@example.com", "barber", shop.id)
    client_user = _user(test_db, "client@example.com", "client", shop.id)
    appointment = Appointment(
        barbershop_id=shop.id,
        client_id=client_user.id,
        barber_id=barber_b.id,
        scheduled_time=utc_now_naive() + timedelta(days=1),
        estimated_duration=30,
        service_type="haircut",
        service_price=1500,
        status="pending",
    )
    test_db.add(appointment)
    test_db.commit()
    test_db.refresh(appointment)
    token = create_access_token({"sub": str(barber_a.id), "role": barber_a.role})

    response = client.put(
        f"/api/v1/barber/appointments/{appointment.id}/status",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
