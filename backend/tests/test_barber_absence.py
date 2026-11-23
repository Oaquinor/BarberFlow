"""MySQL integration tests for barber absence blocks and existing appointments."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import (
    Appointment, BarberAvailability, BarberAvailabilityBlock, Barbershop, Service, Subscription, User,
)
from app.utils.datetime import utc_now_naive


def _setup(test_db: Session):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=2,
        max_appointments_per_month=100, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Absence Test", slug="barber-absence-test", email="absence-shop@example.com",
        phone="8095557000", address_line1="Calle 1", city="Santo Domingo", state="DN",
        postal_code="10101", country="DO", timezone="America/Santo_Domingo", currency="DOP",
        opening_time=time(9), closing_time=time(18), subscription_id=subscription.id,
    )
    test_db.add(shop)
    test_db.flush()
    barber = User(
        email="absence-barber@example.com", password_hash="unused", first_name="Barbero",
        last_name="Ausencia", role="barber", is_active=True, barbershop_id=shop.id,
    )
    client = User(
        email="absence-client@example.com", password_hash="unused", first_name="Cliente",
        last_name="Cita", role="client", is_active=True, barbershop_id=shop.id,
    )
    service = Service(
        barbershop_id=shop.id, name="Corte de prueba", duration_minutes=30,
        price=2000, category="haircut", is_active=True,
    )
    test_db.add_all([barber, client, service])
    test_db.flush()
    token = create_access_token({"sub": str(barber.id), "role": barber.role})
    target_date = (datetime.now(ZoneInfo(shop.timezone)).date() + timedelta(days=1)).isoformat()
    return shop, barber, client, service, target_date, {"Authorization": f"Bearer {token}"}


def test_absence_filters_slots_and_supports_safe_cancellation(client: TestClient, test_db: Session):
    shop, barber, _customer, service, target_date, headers = _setup(test_db)
    slots = client.post("/api/v1/barber/slots", headers=headers, json={
        "date": target_date, "start_time": "09:00", "end_time": "12:00", "slot_minutes": 30,
    })
    assert slots.status_code == 200
    assert slots.json()["created_slots"] == 6

    absence = client.post("/api/v1/barber/absences", headers=headers, json={
        "date": target_date, "start_time": "10:00", "end_time": "11:00", "reason": "Cita médica",
    })
    assert absence.status_code == 201
    assert absence.json()["affected_slots"] == 2
    assert test_db.query(BarberAvailabilityBlock).filter(
        BarberAvailabilityBlock.barbershop_id == shop.id,
        BarberAvailabilityBlock.barber_id == barber.id,
        BarberAvailabilityBlock.is_deleted == False,
    ).count() == 1
    assert test_db.query(BarberAvailability).filter(
        BarberAvailability.barbershop_id == shop.id,
        BarberAvailability.is_active == True,
        BarberAvailability.is_deleted == False,
    ).count() == 6

    public_slots = client.get(f"/api/v1/public/{shop.slug}/slots")
    assert public_slots.status_code == 200
    assert len(public_slots.json()) == 4

    local_blocked_slot = datetime.combine(
        datetime.strptime(target_date, "%Y-%m-%d").date(), time(10),
        tzinfo=ZoneInfo(shop.timezone),
    ).astimezone(timezone.utc).isoformat()
    direct_booking = client.post(f"/api/v1/public/{shop.slug}/appointments", json={
        "client_name": "Cliente Ausencia", "phone": "8095557001", "service_id": service.id,
        "scheduled_time": local_blocked_slot,
    })
    assert direct_booking.status_code == 409

    regenerated = client.post("/api/v1/barber/slots", headers=headers, json={
        "date": target_date, "start_time": "10:00", "end_time": "11:00", "slot_minutes": 30,
    })
    assert regenerated.status_code == 409
    duplicate = client.post("/api/v1/barber/absences", headers=headers, json={
        "date": target_date, "start_time": "10:30", "end_time": "11:30",
    })
    assert duplicate.status_code == 409

    listed = client.get("/api/v1/barber/absences", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    cancelled = client.delete(
        f"/api/v1/barber/absences/{absence.json()['absence_id']}", headers=headers,
    )
    assert cancelled.status_code == 200
    assert client.get("/api/v1/barber/absences", headers=headers).json() == []
    assert len(client.get(f"/api/v1/public/{shop.slug}/slots").json()) == 6


def test_absence_refuses_to_hide_existing_appointments(client: TestClient, test_db: Session):
    shop, barber, customer, _service, target_date, headers = _setup(test_db)
    local_start = datetime.combine(
        datetime.strptime(target_date, "%Y-%m-%d").date(), time(10),
        tzinfo=ZoneInfo(shop.timezone),
    )
    start_utc = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    slot = BarberAvailability(
        barbershop_id=shop.id, barber_id=barber.id, slot_start=start_utc,
        slot_end=start_utc + timedelta(minutes=30), is_active=True, is_booked=True,
    )
    appointment = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=start_utc, estimated_duration=30, service_type="Corte",
        service_price=2000, status="confirmed",
    )
    test_db.add_all([slot, appointment])
    test_db.flush()

    response = client.post("/api/v1/barber/absences", headers=headers, json={
        "date": target_date, "start_time": "09:30", "end_time": "10:30",
    })
    assert response.status_code == 409
    assert "cita" in response.json()["detail"].lower()
    assert test_db.query(BarberAvailabilityBlock).filter(
        BarberAvailabilityBlock.barbershop_id == shop.id,
    ).count() == 0
    assert test_db.get(BarberAvailability, slot.id).is_active is True


def test_owner_cannot_register_a_barbers_personal_absence(client: TestClient, test_db: Session):
    shop, _barber, _customer, _service, _target_date, _headers = _setup(test_db)
    owner = User(
        email="absence-owner@example.com", password_hash="unused", first_name="Owner",
        last_name="Test", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    test_db.add(owner)
    test_db.flush()
    token = create_access_token({"sub": str(owner.id), "role": owner.role})
    response = client.post("/api/v1/barber/absences", headers={
        "Authorization": f"Bearer {token}",
    }, json={"date": "2026-12-01", "start_time": "09:00", "end_time": "10:00"})
    assert response.status_code == 403
