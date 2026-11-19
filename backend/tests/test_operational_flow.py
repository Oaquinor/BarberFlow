"""End-to-end operational flow using the dedicated MySQL integration database."""

from datetime import datetime, time, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.endpoints import platform as platform_api
from app.core.security import create_access_token
from app.models import (
    Appointment, BarberAvailability, BarberPerformance, Barbershop,
    NotificationDelivery, Payment, Service, Subscription, User,
)
from app.utils.datetime import utc_now_naive


def test_booking_to_checkout_updates_agenda_performance_and_cash(
    client: TestClient, test_db: Session, monkeypatch
):
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:8000")

    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=2,
        max_appointments_per_month=100, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Flujo Completo", slug="operational-flow-test", email="flow@example.com",
        phone="8095550301", address_line1="Calle Principal 1", city="Santo Domingo",
        state="DN", postal_code="10101", country="DO", timezone="America/Santo_Domingo",
        currency="DOP", subscription_id=subscription.id,
    )
    test_db.add(shop)
    test_db.flush()
    barber = User(
        email="flow-barber@example.com", password_hash="unused", first_name="Luis",
        last_name="Flujo", role="barber", is_active=True, barbershop_id=shop.id,
    )
    customer = User(
        email="flow-client@example.com", password_hash="unused", first_name="Cliente",
        last_name="Flujo", phone="8095550302", role="client", is_active=True,
        barbershop_id=shop.id,
    )
    service = Service(
        barbershop_id=shop.id, name="Corte completo", duration_minutes=30,
        price=25000, category="haircut", is_active=True,
    )
    test_db.add_all([barber, customer, service])
    test_db.flush()

    business_timezone = ZoneInfo(shop.timezone)
    local_start = datetime.combine(
        datetime.now(business_timezone).date() + timedelta(days=1),
        time(hour=10),
        tzinfo=business_timezone,
    )
    slot_start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    slot = BarberAvailability(
        barbershop_id=shop.id, barber_id=barber.id,
        slot_start=slot_start, slot_end=slot_start + timedelta(hours=1),
        is_active=True, is_booked=False,
    )
    second_slot_start = slot_start + timedelta(days=1, hours=2)
    second_slot = BarberAvailability(
        barbershop_id=shop.id, barber_id=barber.id,
        slot_start=second_slot_start, slot_end=second_slot_start + timedelta(hours=1),
        is_active=True, is_booked=False,
    )
    test_db.add_all([slot, second_slot])
    test_db.commit()

    reservation = client.post(
        f"/api/v1/public/{shop.slug}/appointments",
        json={
            "client_name": "Cliente Flujo", "phone": "8095550302",
            "service_id": service.id,
            "scheduled_time": slot_start.replace(tzinfo=timezone.utc).isoformat(),
        },
    )
    assert reservation.status_code == 200
    appointment_id = reservation.json()["appointment_id"]
    queued = test_db.query(NotificationDelivery).filter(
        NotificationDelivery.appointment_id == appointment_id,
    ).all()
    assert {item.channel for item in queued} == {"email", "whatsapp"}
    request_email = next(item for item in queued if item.channel == "email")
    assert request_email.event_type == "appointment_booking_received"
    assert "pendiente de confirmación" in request_email.body
    assert "confirmada exitosamente" not in request_email.body
    tracking_token = parse_qs(urlparse(reservation.json()["tracking_link"]).query)["track_token"][0]

    token = create_access_token({"sub": str(barber.id), "role": barber.role})
    headers = {"Authorization": f"Bearer {token}"}
    confirmed = client.put(
        f"/api/v1/barber/appointments/{appointment_id}/status",
        headers=headers, json={"status": "confirmed"},
    )
    assert confirmed.status_code == 200
    confirmation_deliveries = test_db.query(NotificationDelivery).filter(
        NotificationDelivery.appointment_id == appointment_id,
        NotificationDelivery.event_type == "appointment_confirmation",
    ).all()
    assert {item.channel for item in confirmation_deliveries} == {"email", "whatsapp"}
    assert "Cita Confirmada" in next(
        item.body for item in confirmation_deliveries if item.channel == "email"
    )

    agenda = client.get(
        "/api/v1/barber/appointments",
        params={"target_date": local_start.date().isoformat()},
        headers=headers,
    )
    assert agenda.status_code == 200
    assert any(item["id"] == appointment_id for item in agenda.json()["appointments"])

    monkeypatch.setattr(platform_api, "utc_now_naive", lambda: slot_start - timedelta(minutes=16))
    too_early = client.put(
        f"/api/v1/barber/appointments/{appointment_id}/status",
        headers=headers, json={"status": "in_progress"},
    )
    assert too_early.status_code == 409

    monkeypatch.setattr(platform_api, "utc_now_naive", lambda: slot_start)
    started = client.put(
        f"/api/v1/barber/appointments/{appointment_id}/status",
        headers=headers, json={"status": "in_progress"},
    )
    assert started.status_code == 200
    dashboard = client.get("/api/v1/barber/dashboard", headers=headers)
    assert dashboard.status_code == 200
    active_service = dashboard.json()["active_appointment"]
    assert active_service["id"] == appointment_id
    assert active_service["actual_start_time"] is not None
    assert active_service["progress_percent"] >= 0

    second_reservation = client.post(
        f"/api/v1/public/{shop.slug}/appointments",
        json={
            "client_name": "Segundo Cliente", "phone": "8095550303",
            "service_id": service.id,
            "scheduled_time": second_slot_start.replace(tzinfo=timezone.utc).isoformat(),
        },
    )
    assert second_reservation.status_code == 200
    second_appointment_id = second_reservation.json()["appointment_id"]
    monkeypatch.setattr(platform_api, "utc_now_naive", lambda: second_slot_start)
    second_start = client.put(
        f"/api/v1/barber/appointments/{second_appointment_id}/status",
        headers=headers, json={"status": "in_progress"},
    )
    assert second_start.status_code == 409
    assert test_db.get(Appointment, second_appointment_id).status == "pending"
    next_day_dashboard = client.get("/api/v1/barber/dashboard", headers=headers)
    assert next_day_dashboard.status_code == 200
    assert next_day_dashboard.json()["next_appointment"]["id"] == second_appointment_id

    monkeypatch.setattr(platform_api, "utc_now_naive", lambda: slot_start + timedelta(minutes=4))
    too_soon_to_charge = client.post(
        f"/api/v1/barber/appointments/{appointment_id}/payment",
        headers=headers, json={"method": "cash", "tip_cents": 2500},
    )
    assert too_soon_to_charge.status_code == 409

    monkeypatch.setattr(platform_api, "utc_now_naive", lambda: slot_start + timedelta(minutes=5))
    checkout = client.post(
        f"/api/v1/barber/appointments/{appointment_id}/payment",
        headers=headers, json={"method": "cash", "tip_cents": 2500},
    )
    assert checkout.status_code == 201
    completion_deliveries = test_db.query(NotificationDelivery).filter(
        NotificationDelivery.appointment_id == appointment_id,
        NotificationDelivery.event_type == "appointment_completion",
    ).all()
    assert {item.channel for item in completion_deliveries} == {"email", "whatsapp"}
    assert checkout.json()["total_cents"] == 27500
    appointment = test_db.get(Appointment, appointment_id)
    assert appointment.status == "completed"
    assert appointment.actual_start_time is not None
    assert appointment.actual_end_time is not None
    assert test_db.query(Payment).filter(Payment.appointment_id == appointment_id).count() == 1

    business_date = appointment.scheduled_time.replace(tzinfo=timezone.utc).astimezone(business_timezone).date()
    performance = test_db.query(BarberPerformance).filter(
        BarberPerformance.barbershop_id == shop.id,
        BarberPerformance.barber_id == barber.id,
        BarberPerformance.date == business_date,
    ).one()
    assert performance.appointments_completed == 1
    assert performance.total_revenue == 27500

    cash = client.get("/api/v1/barber/cash/today", headers=headers)
    assert cash.status_code == 200
    assert cash.json()["expected_cash_cents"] == 27500
    closed = client.post(
        "/api/v1/barber/cash/close", headers=headers,
        json={"business_date": cash.json()["business_date"], "declared_cash_cents": 27500},
    )
    assert closed.status_code == 201
    assert closed.json()["difference_cents"] == 0

    tracked = client.post(
        f"/api/v1/public/{shop.slug}/track", json={"token": tracking_token},
    )
    assert tracked.status_code == 200
    assert tracked.json()["items"][0]["status"] == "completed"
