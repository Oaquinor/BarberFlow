"""MySQL integration tests for the tenant-private Live Chair snapshot."""

from datetime import timedelta
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import (
    Appointment, BarberAvailability, Barbershop, Subscription, User,
)
from app.utils.datetime import utc_now_naive


def _headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def test_owner_live_chair_aggregates_status_without_customer_identity(
    client: TestClient, test_db: Session,
):
    now = utc_now_naive().replace(second=0, microsecond=0)
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=3,
        max_appointments_per_month=100, max_clients=200, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Live Chair Test", slug="live-chair-test", email="live-chair@example.com",
        phone="8095554800", address_line1="Calle 10", city="Santo Domingo",
        state="DN", postal_code="10110", country="DO",
        timezone="America/Santo_Domingo", subscription_id=subscription.id,
    )
    test_db.add(shop)
    test_db.flush()
    owner = User(
        email="live-chair-owner@example.com", password_hash="unused",
        first_name="Owner", last_name="Test", role="barbershop_owner",
        is_active=True, barbershop_id=shop.id,
    )
    barber = User(
        email="live-chair-barber@example.com", password_hash="unused",
        first_name="Barber", last_name="Test", role="barber",
        is_active=True, barbershop_id=shop.id,
    )
    available_barber = User(
        email="live-chair-available@example.com", password_hash="unused",
        first_name="Available", last_name="Barber", role="barber",
        is_active=True, barbershop_id=shop.id,
    )
    customer = User(
        email="private-live-chair-client@example.com", password_hash="unused",
        first_name="PrivateCustomerName", last_name="ShouldNotLeak", role="client",
        is_active=True, barbershop_id=shop.id,
    )
    test_db.add_all([owner, barber, available_barber, customer])
    test_db.flush()
    active = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=now - timedelta(minutes=25), estimated_duration=20,
        actual_start_time=now - timedelta(minutes=25), service_type="Corte activo",
        status="in_progress",
    )
    waiting = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=now - timedelta(minutes=1), estimated_duration=35,
        service_type="Corte en espera", status="confirmed",
        checked_in_at=now - timedelta(minutes=2),
    )
    open_slot = BarberAvailability(
        barbershop_id=shop.id, barber_id=available_barber.id,
        slot_start=now - timedelta(minutes=10), slot_end=now + timedelta(minutes=50),
        is_active=True, is_booked=False,
    )
    test_db.add_all([active, waiting, open_slot])
    test_db.commit()

    response = client.get("/api/v1/owner/live-chair", headers=_headers(owner))

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["barber_id"] == barber.id
    assert payload["items"][0]["state"] == "delayed"
    assert payload["items"][0]["checked_in_count"] == 1
    assert payload["items"][0]["estimated_wait_minutes"] == 0
    assert payload["items"][0]["active_service"]["service_type"] == "Corte activo"
    assert payload["items"][1]["state"] == "available"
    assert "PrivateCustomerName" not in json.dumps(payload)
    assert client.get("/api/v1/owner/live-chair", headers=_headers(barber)).status_code == 403
    assert client.get("/api/v1/owner/live-chair").status_code == 401
