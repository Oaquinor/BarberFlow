"""Owner subscription status is derived from MySQL plan and tenant usage."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Appointment, Barbershop, Subscription, User
from app.utils.datetime import utc_now_naive


def _headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def test_owner_reads_subscription_period_and_real_limits(client: TestClient, test_db: Session):
    now = utc_now_naive()
    subscription = Subscription(
        plan="basic", status="active", current_period_start=now - timedelta(days=2),
        current_period_end=now + timedelta(days=20), max_barbers=3,
        max_appointments_per_month=100, max_clients=200, auto_renew=True,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Billing Status", slug="billing-status-test", email="billing-status@example.com",
        phone="8095555010", address_line1="Calle 50", city="Santo Domingo", state="DN",
        postal_code="10105", country="DO", timezone="America/Santo_Domingo",
        currency="DOP", subscription_id=subscription.id,
    )
    test_db.add(shop)
    test_db.flush()
    owner = User(
        email="billing-status-owner@example.com", password_hash="unused", first_name="Owner",
        last_name="Billing", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    barber = User(
        email="billing-status-barber@example.com", password_hash="unused", first_name="Barber",
        last_name="Active", role="barber", is_active=True, barbershop_id=shop.id,
    )
    inactive_barber = User(
        email="billing-status-inactive@example.com", password_hash="unused", first_name="Barber",
        last_name="Inactive", role="barber", is_active=False, barbershop_id=shop.id,
    )
    customers = [User(
        email=f"billing-status-client-{i}@example.com", password_hash="unused",
        first_name="Client", last_name=str(i), role="client", is_active=True, barbershop_id=shop.id,
    ) for i in range(2)]
    test_db.add_all([owner, barber, inactive_barber, *customers])
    test_db.flush()
    appointment = Appointment(
        barbershop_id=shop.id, client_id=customers[0].id, barber_id=barber.id,
        scheduled_time=now + timedelta(days=1), estimated_duration=30, service_type="Corte",
        service_price=1500, status="confirmed",
    )
    test_db.add(appointment)
    test_db.commit()

    result = client.get("/api/v1/billing/subscription", headers=_headers(owner))
    assert result.status_code == 200
    data = result.json()
    assert data["plan"] == "basic"
    assert data["status"] == "active"
    assert data["currency"] == "DOP"
    assert data["days_remaining"] in range(19, 22)
    assert data["auto_renew"] is True
    assert data["usage"] == {
        "barbers": {"used": 1, "limit": 3},
        "appointments": {"used": 1, "limit": 100},
        "clients": {"used": 2, "limit": 200},
    }
    assert client.get("/api/v1/billing/subscription", headers=_headers(barber)).status_code == 403

    subscription.current_period_end = now - timedelta(seconds=1)
    test_db.commit()
    expired = client.get("/api/v1/billing/subscription", headers=_headers(owner))
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"
    assert expired.json()["days_remaining"] == 0
