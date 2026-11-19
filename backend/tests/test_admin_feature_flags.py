"""MySQL integration tests for observable super-admin feature controls."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Barbershop, Subscription, User
from app.utils.datetime import utc_now_naive


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'role': user.role})}"}


def test_branding_feature_state_is_returned_and_consumed_by_user_session(
    client: TestClient, test_db: Session,
):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=2,
        max_appointments_per_month=50, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Brand Feature", slug="brand-feature-test", email="brand-shop@example.com",
        phone="8095556100", address_line1="Calle 21", city="Santo Domingo", state="DN",
        postal_code="10106", country="DO", timezone="America/Santo_Domingo", currency="DOP",
        subscription_id=subscription.id, onboarding_completed=True,
        primary_color="#123456", secondary_color="#654321",
    )
    test_db.add(shop)
    test_db.flush()
    admin = User(
        email="brand-admin@example.com", password_hash="unused", first_name="Admin",
        last_name="Platform", role="super_admin", is_active=True,
    )
    barber = User(
        email="brand-barber@example.com", password_hash="unused", first_name="Barber",
        last_name="Brand", role="barber", is_active=True, barbershop_id=shop.id,
    )
    test_db.add_all([admin, barber])
    test_db.commit()

    overview = client.get("/api/v1/admin/overview", headers=_headers(admin))
    assert overview.status_code == 200
    assert overview.json()["tenant_count"] == 1
    assert overview.json()["active_tenant_count"] == 1
    assert overview.json()["active_subscription_count"] == 1
    assert overview.json()["active_user_count"] == 2
    assert overview.json()["collected_this_month_by_currency"] == []
    assert client.get("/api/v1/admin/overview", headers=_headers(barber)).status_code == 403

    listed = client.get(f"/api/v1/admin/users?barbershop_id={shop.id}", headers=_headers(admin))
    assert listed.status_code == 200
    item = next(row for row in listed.json()["items"] if row["id"] == barber.id)
    assert item["feature_flags"] == {}

    enabled = client.put(
        f"/api/v1/admin/users/{barber.id}/features", headers=_headers(admin),
        json={"feature_key": "branding_auto", "enabled": True},
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    listed_again = client.get(f"/api/v1/admin/users?barbershop_id={shop.id}", headers=_headers(admin))
    updated = next(row for row in listed_again.json()["items"] if row["id"] == barber.id)
    assert updated["feature_flags"] == {"branding_auto": True}
    session_user = client.get("/api/v1/auth/me", headers=_headers(barber))
    assert session_user.status_code == 200
    assert session_user.json()["feature_flags"] == {"branding_auto": True}

    unsupported = client.put(
        f"/api/v1/admin/users/{barber.id}/features", headers=_headers(admin),
        json={"feature_key": "imaginary_feature", "enabled": True},
    )
    assert unsupported.status_code == 422
