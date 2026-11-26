"""In-person service flow without a reserved availability slot (MySQL)."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.endpoints import booking as booking_api
from app.api.v1.endpoints import platform as platform_api
from app.core.security import create_access_token
from app.models import Appointment, Barbershop, Payment, Service, Subscription, User
from app.utils.datetime import utc_now_naive


def test_walk_in_starts_service_and_uses_the_standard_payment_flow(
    client: TestClient, test_db: Session, monkeypatch
):
    now = utc_now_naive().replace(microsecond=0)
    monkeypatch.setattr(booking_api, "utc_now_naive", lambda: now)
    monkeypatch.setattr(platform_api, "utc_now_naive", lambda: now)
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=2,
        max_appointments_per_month=100, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Turnos Presenciales", slug="walk-in-test", email="walk-in-shop@example.com",
        phone="8095550501", address_line1="Calle 5", city="Santo Domingo",
        state="DN", postal_code="10101", country="DO", timezone="America/Santo_Domingo",
        currency="DOP", subscription_id=subscription.id,
    )
    test_db.add(shop)
    test_db.flush()
    barber = User(
        email="walk-in-barber@example.com", password_hash="unused", first_name="Mario",
        last_name="Presencial", role="barber", is_active=True,
        barbershop_id=shop.id,
    )
    service = Service(
        barbershop_id=shop.id, name="Corte presencial", duration_minutes=30,
        price=22000, category="haircut", is_active=True,
    )
    test_db.add_all([shop, barber, service])
    test_db.commit()

    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber.id), 'role': barber.role})}"}
    created = client.post(
        "/api/v1/barber/appointments/walk-in",
        headers=headers,
        json={"client_name": "Cliente Local", "phone": "809-555-0502", "service_id": service.id},
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["status"] == "in_progress"
    appointment = test_db.get(Appointment, payload["appointment_id"])
    assert appointment.actual_start_time is not None
    assert appointment.client.phone == "8095550502"
    assert appointment.client.is_verified is False

    duplicate = client.post(
        "/api/v1/barber/appointments/walk-in",
        headers=headers,
        json={"client_name": "Cliente Local", "phone": "8095550502", "service_id": service.id},
    )
    assert duplicate.status_code == 409

    queued = client.post(
        "/api/v1/barber/appointments/walk-in",
        headers=headers,
        json={
            "client_name": "Cliente En Espera", "phone": "809-555-0503",
            "service_id": service.id, "start_immediately": False,
        },
    )
    assert queued.status_code == 201, queued.text
    queued_payload = queued.json()
    assert queued_payload["queued"] is True
    assert queued_payload["status"] == "confirmed"
    queued_appointment = test_db.get(Appointment, queued_payload["appointment_id"])
    assert queued_appointment.checked_in_at == now
    assert queued_appointment.actual_start_time is None

    monkeypatch.setattr(platform_api, "utc_now_naive", lambda: now + timedelta(minutes=6))
    paid = client.post(
        f"/api/v1/barber/appointments/{appointment.id}/payment",
        headers=headers,
        json={"method": "cash", "tip_cents": 1000},
    )
    assert paid.status_code == 201, paid.text
    assert paid.json()["total_cents"] == 23000
    test_db.refresh(appointment)
    assert appointment.status == "completed"
    assert test_db.query(Payment).filter(Payment.appointment_id == appointment.id).count() == 1

    # A checked-in walk-in must remain startable even if their wait exceeds the
    # normal 15-minute appointment arrival window.
    monkeypatch.setattr(platform_api, "utc_now_naive", lambda: now + timedelta(minutes=30))
    started = client.put(
        f"/api/v1/barber/appointments/{queued_appointment.id}/status",
        headers=headers,
        json={"status": "in_progress"},
    )
    assert started.status_code == 200, started.text
    test_db.refresh(queued_appointment)
    assert queued_appointment.status == "in_progress"
    assert queued_appointment.actual_start_time == now + timedelta(minutes=30)
