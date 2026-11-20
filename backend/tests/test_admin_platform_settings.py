"""MySQL-backed behavior and authorization checks for platform settings."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import AuditLog, Barbershop, PlatformSettings, Subscription, User


def _headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def _registration_payload(email: str) -> dict:
    return {
        "owner_email": email, "owner_password": "SecureOwner2026",
        "owner_first_name": "Owner", "owner_last_name": "Settings", "owner_phone": "8095557090",
        "barbershop_name": "Settings Shop", "barbershop_email": f"shop-{email}",
        "barbershop_phone": "8095557091", "address_line1": "Calle 70",
        "city": "Santo Domingo", "state": "DN", "postal_code": "10107",
        "country": "DO", "timezone": "America/Santo_Domingo", "currency": "DOP",
    }


def test_super_admin_settings_control_registration_and_initial_period(
    client: TestClient, test_db: Session,
):
    shop = Barbershop(
        name="Existing", slug="settings-existing", email="existing-settings@example.com",
        phone="8095557080", address_line1="Calle 71", city="Santo Domingo", state="DN",
        postal_code="10108", country="DO", timezone="America/Santo_Domingo", currency="DOP",
    )
    test_db.add(shop)
    test_db.flush()
    admin = User(
        email="platform-settings-admin@example.com", password_hash="unused", first_name="Admin",
        last_name="Platform", role="super_admin", is_active=True,
    )
    owner = User(
        email="platform-settings-owner@example.com", password_hash="unused", first_name="Owner",
        last_name="Existing", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    test_db.add_all([admin, owner])
    test_db.commit()

    initial = client.get("/api/v1/admin/settings", headers=_headers(admin))
    assert initial.status_code == 200
    assert initial.json() == {"registrations_enabled": True, "free_period_days": 30}
    assert client.get("/api/v1/admin/settings", headers=_headers(owner)).status_code == 403

    disabled = client.put(
        "/api/v1/admin/settings", headers=_headers(admin),
        json={"registrations_enabled": False, "free_period_days": 45},
    )
    assert disabled.status_code == 200
    assert client.get("/api/v1/saas/registration-status").json() == {"registrations_enabled": False}
    blocked_registration = client.post(
        "/api/v1/saas/register", json=_registration_payload("blocked-register@example.com"),
    )
    assert blocked_registration.status_code == 503
    assert test_db.query(Barbershop).filter_by(email="shop-blocked-register@example.com").count() == 0

    enabled = client.put(
        "/api/v1/admin/settings", headers=_headers(admin),
        json={"registrations_enabled": True, "free_period_days": 45},
    )
    assert enabled.status_code == 200
    registered = client.post(
        "/api/v1/saas/register", json=_registration_payload("enabled-register@example.com"),
    )
    assert registered.status_code == 201
    subscription = test_db.query(Subscription).filter_by(
        id=test_db.query(Barbershop).filter_by(id=registered.json()["user"]["barbershop_id"]).one().subscription_id,
    ).one()
    assert subscription.current_period_end - subscription.current_period_start == timedelta(days=45)

    settings = test_db.get(PlatformSettings, 1)
    assert settings.updated_by_user_id == admin.id
    audit_count = test_db.query(AuditLog).filter_by(action="platform.settings_updated").count()
    assert audit_count == 2

    invalid = client.put(
        "/api/v1/admin/settings", headers=_headers(admin),
        json={"registrations_enabled": True, "free_period_days": 366},
    )
    assert invalid.status_code == 422


def test_registration_initializes_missing_platform_settings_with_defaults(
    client: TestClient, test_db: Session,
):
    assert test_db.get(PlatformSettings, 1) is None

    registered = client.post(
        "/api/v1/saas/register", json=_registration_payload("first-register@example.com"),
    )

    assert registered.status_code == 201
    settings = test_db.get(PlatformSettings, 1)
    assert settings is not None
    assert settings.registrations_enabled is True
    assert settings.free_period_days == 30
    shop = test_db.get(Barbershop, registered.json()["user"]["barbershop_id"])
    subscription = test_db.get(Subscription, shop.subscription_id)
    assert subscription.current_period_end - subscription.current_period_start == timedelta(days=30)
