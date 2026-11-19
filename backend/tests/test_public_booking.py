"""Booking, private tracking, reschedule and cancellation tests for MySQL."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    Appointment, AuditLog, BarberAvailability, BarberAvailabilityBlock,
    Barbershop, Service, Subscription, User,
)
from app.api.v1.endpoints.platform import _slot_available_for_duration
from app.core.security import create_access_token
from app.utils.datetime import utc_now_naive


def test_public_slot_filter_uses_service_duration_for_conflicts_and_absences():
    start = datetime(2030, 5, 10, 9)
    too_short = SimpleNamespace(slot_start=start, slot_end=start + timedelta(minutes=15))
    available = SimpleNamespace(slot_start=start, slot_end=start + timedelta(hours=1))
    block_at_slot_tail = SimpleNamespace(
        starts_at=start + timedelta(minutes=45), ends_at=start + timedelta(hours=1),
    )
    appointment_overlap = SimpleNamespace(
        scheduled_time=start + timedelta(minutes=20), estimated_duration=30,
    )

    assert not _slot_available_for_duration(too_short, [], [], 30)
    assert not _slot_available_for_duration(available, [], [appointment_overlap], 30)
    assert _slot_available_for_duration(available, [block_at_slot_tail], [], 30)
    assert not _slot_available_for_duration(available, [block_at_slot_tail], [], 60)


def test_public_booking_tracking_and_cancel_are_connected(
    client: TestClient, test_db: Session, monkeypatch
):
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:8000")
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=1,
        max_appointments_per_month=50, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Barbería de Prueba",
        slug="booking-test",
        email="booking-shop@example.com",
        phone="8095550101",
        address_line1="Calle 1",
        city="Santo Domingo",
        state="DN",
        postal_code="10101",
        country="DO",
        timezone="America/Santo_Domingo",
        subscription_id=subscription.id,
    )
    test_db.add(shop)
    test_db.commit()
    test_db.refresh(shop)

    barber = User(
        email="booking-barber@example.com",
        password_hash="not-used-for-public-booking",
        first_name="Barbero",
        last_name="Prueba",
        role="barber",
        is_active=True,
        barbershop_id=shop.id,
    )
    owner = User(
        email="booking-owner@example.com",
        password_hash="not-used-for-public-booking",
        first_name="Dueña",
        last_name="Prueba",
        role="barbershop_owner",
        is_active=True,
        barbershop_id=shop.id,
    )
    service = Service(
        barbershop_id=shop.id,
        name="Corte",
        duration_minutes=30,
        price=1800,
        category="haircut",
        is_active=True,
    )
    test_db.add_all([barber, owner, service])
    test_db.commit()
    test_db.refresh(barber)
    test_db.refresh(service)

    start = utc_now_naive().replace(second=0, microsecond=0) + timedelta(days=1)
    start = start.replace(minute=0)
    slot = BarberAvailability(
        barbershop_id=shop.id,
        barber_id=barber.id,
        slot_start=start,
        slot_end=start + timedelta(hours=1),
        is_active=True,
        is_booked=False,
    )
    replacement_slot = BarberAvailability(
        barbershop_id=shop.id, barber_id=barber.id,
        slot_start=start + timedelta(hours=2), slot_end=start + timedelta(hours=3),
        is_active=True, is_booked=False,
    )
    blocked_slot = BarberAvailability(
        barbershop_id=shop.id, barber_id=barber.id,
        slot_start=start + timedelta(hours=4), slot_end=start + timedelta(hours=5),
        is_active=True, is_booked=False,
    )
    test_db.add_all([slot, replacement_slot, blocked_slot])
    test_db.add(BarberAvailabilityBlock(
        barbershop_id=shop.id, barber_id=barber.id,
        starts_at=blocked_slot.slot_start + timedelta(minutes=10),
        ends_at=blocked_slot.slot_start + timedelta(minutes=40),
        reason="Ausencia parcial",
    ))
    test_db.commit()

    payload = {
        "client_name": "Cliente Prueba",
        "phone": "809-555-0202",
        "service_id": service.id,
        "scheduled_time": start.replace(tzinfo=timezone.utc).isoformat(),
    }
    response = client.post(f"/api/v1/public/{shop.slug}/appointments", json=payload)
    assert response.status_code == 200
    booking = response.json()
    booked_appointment = test_db.get(Appointment, booking["appointment_id"])
    public_client = test_db.get(User, booked_appointment.client_id)
    assert public_client.email.endswith("@client.invalid")
    assert "8095550202" not in public_client.email
    assert test_db.query(AuditLog).filter(
        AuditLog.action == "appointment.booked",
        AuditLog.entity_id == booking["appointment_id"],
        AuditLog.barbershop_id == shop.id,
    ).count() == 1
    barber_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber.id), 'role': barber.role})}"}
    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id), 'role': owner.role})}"}
    barber_inbox = client.get("/api/v1/notifications", headers=barber_headers)
    owner_inbox = client.get("/api/v1/notifications", headers=owner_headers)
    assert barber_inbox.status_code == owner_inbox.status_code == 200
    assert barber_inbox.json()["unread_count"] == owner_inbox.json()["unread_count"] == 1
    notification_id = barber_inbox.json()["items"][0]["id"]
    assert barber_inbox.json()["items"][0]["event_type"] == "appointment_booked"
    client_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(public_client.id), 'role': public_client.role})}"}
    private_read = client.post(
        f"/api/v1/notifications/{notification_id}/read", headers=client_headers,
    )
    assert private_read.status_code == 404
    marked = client.post(f"/api/v1/notifications/{notification_id}/read", headers=barber_headers)
    assert marked.status_code == 200
    assert client.get("/api/v1/notifications?unread_only=true", headers=barber_headers).json()["items"] == []
    tracking_token = parse_qs(urlparse(booking["tracking_link"]).query)["track_token"][0]
    assert urlparse(booking["tracking_link"]).netloc == "localhost:8000"

    duplicate = client.post(f"/api/v1/public/{shop.slug}/appointments", json=payload)
    assert duplicate.status_code in {400, 409}
    tracked = client.post(
        f"/api/v1/public/{shop.slug}/track", json={"token": tracking_token}
    )
    assert tracked.status_code == 200
    assert len(tracked.json()["items"]) == 1
    assert tracked.json()["items"][0]["appointment_id"] == booking["appointment_id"]
    assert tracked.json()["items"][0]["estimated_duration"] == 30

    blocked_reschedule = client.post(
        f"/api/v1/public/{shop.slug}/appointments/reschedule",
        json={"token": tracking_token, "availability_id": blocked_slot.id},
    )
    assert blocked_reschedule.status_code == 409

    rescheduled = client.post(
        f"/api/v1/public/{shop.slug}/appointments/reschedule",
        json={"token": tracking_token, "availability_id": replacement_slot.id},
    )
    assert rescheduled.status_code == 200
    assert rescheduled.json()["scheduled_time"]
    test_db.refresh(slot)
    test_db.refresh(replacement_slot)
    assert slot.is_booked is False
    assert replacement_slot.is_booked is True

    cancelled = client.post(
        f"/api/v1/public/{shop.slug}/appointments/cancel",
        json={"token": tracking_token, "reason": "Cambio de horario"},
    )
    assert cancelled.status_code == 200
    test_db.refresh(replacement_slot)
    assert replacement_slot.is_booked is False
    assert cancelled.json()["status"] == "cancelled"
    barber_events = client.get("/api/v1/notifications", headers=barber_headers).json()["items"]
    assert {item["event_type"] for item in barber_events} >= {
        "appointment_booked", "appointment_rescheduled", "appointment_cancelled",
    }


def test_barber_slots_respect_business_hours(client: TestClient, test_db: Session):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=1,
        max_appointments_per_month=50, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Horario Test", slug="business-hours-test", email="hours@example.com",
        phone="8095550190", address_line1="Calle 1", city="Santo Domingo",
        state="DN", postal_code="10101", country="DO", timezone="America/Santo_Domingo",
        opening_time=datetime.strptime("09:00", "%H:%M").time(),
        closing_time=datetime.strptime("18:00", "%H:%M").time(),
        subscription_id=subscription.id,
    )
    test_db.add(shop)
    test_db.flush()
    barber = User(
        email="hours-barber@example.com", password_hash="unused", first_name="Barbero",
        last_name="Horario", role="barber", is_active=True, barbershop_id=shop.id,
    )
    test_db.add(barber)
    test_db.commit()

    token = create_access_token({"sub": str(barber.id), "role": "barber"})
    headers = {"Authorization": f"Bearer {token}"}
    business_date = (datetime.now(ZoneInfo(shop.timezone)).date() + timedelta(days=1)).isoformat()
    outside = client.post(
        "/api/v1/barber/slots", headers=headers,
        json={"date": business_date, "start_time": "08:30", "end_time": "09:30", "slot_minutes": 30},
    )
    assert outside.status_code == 422

    inside = client.post(
        "/api/v1/barber/slots", headers=headers,
        json={"date": business_date, "start_time": "09:00", "end_time": "10:00", "slot_minutes": 30},
    )
    assert inside.status_code == 200
    assert inside.json()["created_slots"] == 2


def test_public_slots_match_service_duration_absences_and_existing_appointments(
    client: TestClient, test_db: Session,
):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=1,
        max_appointments_per_month=50, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Disponibilidad Real", slug="availability-filter-test",
        email="availability-shop@example.com", phone="8095550191",
        address_line1="Calle 2", city="Santo Domingo", state="DN",
        postal_code="10101", country="DO", timezone="America/Santo_Domingo",
        subscription_id=subscription.id,
    )
    test_db.add(shop)
    test_db.flush()
    barber = User(
        email="availability-barber@example.com", password_hash="unused",
        first_name="Barbero", last_name="Disponibilidad", role="barber",
        is_active=True, barbershop_id=shop.id,
    )
    customer = User(
        email="availability-client@example.com", password_hash="unused",
        first_name="Cliente", last_name="Existente", role="client",
        is_active=True, barbershop_id=shop.id,
    )
    short_service = Service(
        barbershop_id=shop.id, name="Servicio corto", duration_minutes=30,
        price=1000, category="haircut", is_active=True,
    )
    long_service = Service(
        barbershop_id=shop.id, name="Servicio largo", duration_minutes=60,
        price=2000, category="combo", is_active=True,
    )
    test_db.add_all([barber, customer, short_service, long_service])
    test_db.flush()

    start = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    slots = [
        BarberAvailability(
            barbershop_id=shop.id, barber_id=barber.id,
            slot_start=start, slot_end=start + timedelta(minutes=15),
            is_active=True, is_booked=False,
        ),
        BarberAvailability(
            barbershop_id=shop.id, barber_id=barber.id,
            slot_start=start + timedelta(hours=1), slot_end=start + timedelta(hours=2),
            is_active=True, is_booked=False,
        ),
        BarberAvailability(
            barbershop_id=shop.id, barber_id=barber.id,
            slot_start=start + timedelta(hours=2), slot_end=start + timedelta(hours=3),
            is_active=True, is_booked=False,
        ),
        BarberAvailability(
            barbershop_id=shop.id, barber_id=barber.id,
            slot_start=start + timedelta(hours=3), slot_end=start + timedelta(hours=4),
            is_active=True, is_booked=False,
        ),
    ]
    test_db.add_all(slots)
    test_db.add(Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=start + timedelta(hours=1, minutes=20), estimated_duration=30,
        service_type="Cita existente", service_price=1000, status="confirmed",
    ))
    test_db.add(BarberAvailabilityBlock(
        barbershop_id=shop.id, barber_id=barber.id,
        starts_at=start + timedelta(hours=3, minutes=45),
        ends_at=start + timedelta(hours=4), reason="Fin de turno",
    ))
    test_db.commit()

    response = client.get(f"/api/v1/public/{shop.slug}/slots?duration_minutes=30")
    assert response.status_code == 200
    assert [item["slot_start"] for item in response.json()] == [
        (start + timedelta(hours=2)).replace(tzinfo=timezone.utc).isoformat(),
        (start + timedelta(hours=3)).replace(tzinfo=timezone.utc).isoformat(),
    ]

    long_service_slots = client.get(
        f"/api/v1/public/{shop.slug}/slots?duration_minutes=60",
    )
    assert long_service_slots.status_code == 200
    assert [item["slot_start"] for item in long_service_slots.json()] == [
        (start + timedelta(hours=2)).replace(tzinfo=timezone.utc).isoformat(),
    ]
