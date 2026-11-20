"""MySQL integration coverage for appointment checkout and daily cash close."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Appointment, AuditLog, BarberPerformance, Barbershop, NotificationDelivery, Payment, User
from app.utils.datetime import utc_now_naive


def test_historical_cash_close_requires_resolving_scheduled_appointments(
    client: TestClient, test_db: Session,
):
    shop = Barbershop(
        name="Cierre histórico", slug="historical-cash-close-test",
        email="historical-cash-close@example.com", phone="8095551099",
        address_line1="Calle 10", city="Santo Domingo", state="DN",
        postal_code="10101", country="DO", timezone="America/Santo_Domingo",
        currency="DOP",
    )
    test_db.add(shop)
    test_db.flush()
    owner = User(
        email="historical-cash-owner@example.com", password_hash="unused",
        first_name="Dueño", last_name="Histórico", role="barbershop_owner",
        is_active=True, barbershop_id=shop.id,
    )
    barber = User(
        email="historical-cash-barber@example.com", password_hash="unused",
        first_name="Barbero", last_name="Histórico", role="barber",
        is_active=True, barbershop_id=shop.id,
    )
    customer = User(
        email="historical-cash-client@example.com", password_hash="unused",
        first_name="Cliente", last_name="Histórico", role="client",
        is_active=True, barbershop_id=shop.id,
    )
    test_db.add_all([owner, barber, customer])
    test_db.flush()
    scheduled_local = datetime.now(ZoneInfo(shop.timezone)).replace(
        hour=10, minute=0, second=0, microsecond=0,
    ) - timedelta(days=1)
    scheduled_utc = scheduled_local.astimezone(timezone.utc).replace(tzinfo=None)
    appointment = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=scheduled_utc, estimated_duration=30,
        service_type="Corte", service_price=18000, status="confirmed",
    )
    test_db.add(appointment)
    test_db.commit()

    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"}
    barber_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber.id)})}"}
    payload = {"business_date": scheduled_local.date().isoformat(), "declared_cash_cents": 0}
    refused = client.post("/api/v1/barber/cash/close", headers=owner_headers, json=payload)
    assert refused.status_code == 409

    cancelled = client.put(
        f"/api/v1/barber/appointments/{appointment.id}/status",
        headers=barber_headers, json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200
    closed = client.post("/api/v1/barber/cash/close", headers=owner_headers, json=payload)
    assert closed.status_code == 201


def test_service_requires_payment_and_cash_close_reconciles(client: TestClient, test_db: Session):
    shop = Barbershop(
        name="Caja de Prueba", slug="cash-test", email="cash-shop@example.com",
        phone="8095551000", address_line1="Calle 10", city="Santo Domingo",
        state="DN", postal_code="10101", country="DO", timezone="America/Santo_Domingo",
        currency="DOP",
    )
    test_db.add(shop)
    test_db.flush()
    barber = User(
        email="cash-barber@example.com", password_hash="unused", first_name="Carlos",
        last_name="Prueba", role="barber", is_active=True, barbershop_id=shop.id,
    )
    client_user = User(
        email="cash-client@example.com", password_hash="unused", first_name="Ana",
        last_name="Cliente", role="client", is_active=True, barbershop_id=shop.id,
    )
    test_db.add_all([barber, client_user])
    test_db.flush()
    now = utc_now_naive()
    appointment = Appointment(
        barbershop_id=shop.id, client_id=client_user.id, barber_id=barber.id,
        scheduled_time=now, estimated_duration=30, service_type="haircut",
        service_price=25000, status="in_progress", actual_start_time=now - timedelta(minutes=5),
    )
    test_db.add(appointment)
    test_db.commit()

    token = create_access_token({"sub": str(barber.id), "role": "barber"})
    headers = {"Authorization": f"Bearer {token}"}
    cannot_skip_payment = client.put(
        f"/api/v1/barber/appointments/{appointment.id}/status",
        headers=headers,
        json={"status": "completed"},
    )
    assert cannot_skip_payment.status_code == 409

    cash_summary = client.get("/api/v1/barber/cash/today", headers=headers)
    premature_close = client.post("/api/v1/barber/cash/close", headers=headers, json={
        "business_date": cash_summary.json()["business_date"], "declared_cash_cents": 0,
    })
    assert premature_close.status_code == 409

    paid = client.post(
        f"/api/v1/barber/appointments/{appointment.id}/payment",
        headers=headers,
        json={"method": "cash", "tip_cents": 5000},
    )
    assert paid.status_code == 201
    assert paid.json()["total_cents"] == 30000
    test_db.refresh(appointment)
    assert appointment.status == "completed"

    summary = client.get("/api/v1/barber/cash/today", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["expected_cash_cents"] == 30000
    assert summary.json()["payment_count"] == 1

    closed = client.post(
        "/api/v1/barber/cash/close",
        headers=headers,
        json={"business_date": summary.json()["business_date"], "declared_cash_cents": 29000},
    )
    assert closed.status_code == 201
    assert closed.json()["difference_cents"] == -1000
    duplicate_close = client.post(
        "/api/v1/barber/cash/close",
        headers=headers,
        json={"business_date": summary.json()["business_date"], "declared_cash_cents": 30000},
    )
    assert duplicate_close.status_code == 409

    later_appointment = Appointment(
        barbershop_id=shop.id, client_id=client_user.id, barber_id=barber.id,
        scheduled_time=utc_now_naive(), estimated_duration=30, service_type="beard",
        service_price=12000, status="in_progress",
        actual_start_time=utc_now_naive() - timedelta(minutes=5),
    )
    test_db.add(later_appointment)
    test_db.commit()
    test_db.refresh(later_appointment)
    after_close = client.post(
        f"/api/v1/barber/appointments/{later_appointment.id}/payment",
        headers=headers,
        json={"method": "cash", "tip_cents": 0},
    )
    assert after_close.status_code == 409

    duplicate_payment = client.post(
        f"/api/v1/barber/appointments/{appointment.id}/payment",
        headers=headers,
        json={"method": "cash", "tip_cents": 0},
    )
    assert duplicate_payment.status_code == 409

    audit_actions = {row.action for row in test_db.query(AuditLog).all()}
    assert "appointment.payment_recorded" in audit_actions
    assert "cash.closed" in audit_actions


def test_owner_close_blocks_barber_checkout_for_the_same_business_day(
    client: TestClient, test_db: Session,
):
    shop = Barbershop(
        name="Caja General", slug="owner-close-cash-test", email="owner-close@example.com",
        phone="8095551010", address_line1="Calle 20", city="Santo Domingo",
        state="DN", postal_code="10110", country="DO", timezone="America/Santo_Domingo",
        currency="DOP",
    )
    test_db.add(shop)
    test_db.flush()
    owner = User(
        email="owner-close-owner@example.com", password_hash="unused", first_name="Dueño",
        last_name="Caja", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    barber = User(
        email="owner-close-barber@example.com", password_hash="unused", first_name="Barbero",
        last_name="Caja", role="barber", is_active=True, barbershop_id=shop.id,
    )
    customer = User(
        email="owner-close-client@example.com", password_hash="unused", first_name="Cliente",
        last_name="Caja", role="client", is_active=True, barbershop_id=shop.id,
    )
    test_db.add_all([owner, barber, customer])
    test_db.flush()
    now = utc_now_naive()
    appointment = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=now, estimated_duration=30, service_type="Corte",
        service_price=18000, status="in_progress", actual_start_time=now - timedelta(minutes=10),
    )
    test_db.add(appointment)
    test_db.commit()

    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id), 'role': owner.role})}"}
    barber_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber.id), 'role': barber.role})}"}
    summary = client.get("/api/v1/barber/cash/today", headers=owner_headers)
    assert summary.status_code == 200
    premature_close = client.post("/api/v1/barber/cash/close", headers=owner_headers, json={
        "business_date": summary.json()["business_date"], "declared_cash_cents": 0,
    })
    assert premature_close.status_code == 409
    assert test_db.query(Payment).filter(Payment.appointment_id == appointment.id).count() == 0

    paid = client.post(
        f"/api/v1/barber/appointments/{appointment.id}/payment",
        headers=barber_headers, json={"method": "card", "tip_cents": 0},
    )
    assert paid.status_code == 201
    closed = client.post("/api/v1/barber/cash/close", headers=owner_headers, json={
        "business_date": summary.json()["business_date"], "declared_cash_cents": 0,
    })
    assert closed.status_code == 201

    checkout = client.post(
        f"/api/v1/barber/appointments/{appointment.id}/payment",
        headers=barber_headers, json={"method": "card", "tip_cents": 0},
    )
    assert checkout.status_code == 409
    assert test_db.query(Payment).filter(Payment.appointment_id == appointment.id).count() == 1
    test_db.refresh(appointment)
    assert appointment.status == "completed"

    later_appointment = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=utc_now_naive(), estimated_duration=30, service_type="Corte posterior",
        service_price=18000, status="confirmed",
    )
    test_db.add(later_appointment)
    test_db.commit()
    started_after_close = client.put(
        f"/api/v1/barber/appointments/{later_appointment.id}/status",
        headers=barber_headers, json={"status": "in_progress"},
    )
    assert started_after_close.status_code == 409
    test_db.refresh(later_appointment)
    assert later_appointment.status == "confirmed"


def test_cash_close_waits_for_remaining_same_day_appointments(
    client: TestClient, test_db: Session, monkeypatch,
):
    import app.api.v1.endpoints.platform as platform

    now = datetime(2026, 11, 20, 15, 0)
    monkeypatch.setattr(platform, "utc_now_naive", lambda: now)
    shop = Barbershop(
        name="Caja con agenda", slug="cash-close-agenda-test", email="cash-agenda@example.com",
        phone="8095551020", address_line1="Calle 30", city="Santo Domingo",
        state="DN", postal_code="10120", country="DO", timezone="America/Santo_Domingo",
        currency="DOP",
    )
    test_db.add(shop)
    test_db.flush()
    owner = User(
        email="cash-agenda-owner@example.com", password_hash="unused", first_name="Dueño",
        last_name="Agenda", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    barber = User(
        email="cash-agenda-barber@example.com", password_hash="unused", first_name="Barbero",
        last_name="Agenda", role="barber", is_active=True, barbershop_id=shop.id,
    )
    customer = User(
        email="cash-agenda-client@example.com", password_hash="unused", first_name="Cliente",
        last_name="Agenda", role="client", is_active=True, barbershop_id=shop.id,
    )
    test_db.add_all([owner, barber, customer])
    test_db.flush()
    appointment = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=now + timedelta(hours=1), estimated_duration=30,
        service_type="Corte", service_price=18000, status="confirmed",
    )
    test_db.add(appointment)
    test_db.commit()

    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"}
    barber_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber.id)})}"}
    payload = {"business_date": "2026-11-20", "declared_cash_cents": 0}
    refused = client.post("/api/v1/barber/cash/close", headers=owner_headers, json=payload)
    assert refused.status_code == 409

    cancelled = client.put(
        f"/api/v1/barber/appointments/{appointment.id}/status",
        headers=barber_headers, json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200
    closed = client.post("/api/v1/barber/cash/close", headers=owner_headers, json=payload)
    assert closed.status_code == 201


def test_future_appointment_cannot_be_marked_no_show(client: TestClient, test_db: Session):
    shop = Barbershop(
        name="No Show Test", slug="no-show-test", email="noshow-shop@example.com",
        phone="8095551001", address_line1="Calle 11", city="Santo Domingo",
        state="DN", postal_code="10102", country="DO", timezone="America/Santo_Domingo",
        currency="DOP",
    )
    test_db.add(shop)
    test_db.flush()
    barber = User(
        email="noshow-barber@example.com", password_hash="unused", first_name="Luis",
        last_name="Prueba", role="barber", is_active=True, barbershop_id=shop.id,
    )
    customer = User(
        email="noshow-client@example.com", password_hash="unused", first_name="Eva",
        last_name="Cliente", role="client", is_active=True, barbershop_id=shop.id,
    )
    test_db.add_all([barber, customer])
    test_db.flush()
    appointment = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=utc_now_naive() + timedelta(hours=2), estimated_duration=30,
        service_type="haircut", service_price=15000, status="confirmed",
    )
    test_db.add(appointment)
    test_db.commit()

    token = create_access_token({"sub": str(barber.id), "role": "barber"})
    response = client.put(
        f"/api/v1/barber/appointments/{appointment.id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "no_show"},
    )
    assert response.status_code == 409


@pytest.mark.parametrize("failure_point", ["performance", "achievements"])
def test_checkout_rolls_back_if_performance_or_achievements_cannot_be_persisted(
    client: TestClient, test_db: Session, monkeypatch, failure_point: str,
):
    from app.services.achievement_service import AchievementService
    from app.services.performance_service import PerformanceService

    shop = Barbershop(
        name="Checkout Atomic", slug="checkout-atomic-test", email="atomic-shop@example.com",
        phone="8095551002", address_line1="Calle 12", city="Santo Domingo",
        state="DN", postal_code="10103", country="DO", timezone="America/Santo_Domingo",
        currency="DOP",
    )
    test_db.add(shop)
    test_db.flush()
    barber = User(
        email="atomic-barber@example.com", password_hash="unused", first_name="Atomic",
        last_name="Barber", role="barber", is_active=True, barbershop_id=shop.id,
    )
    customer = User(
        email="atomic-client@example.com", password_hash="unused", first_name="Atomic",
        last_name="Client", role="client", is_active=True, barbershop_id=shop.id,
    )
    test_db.add_all([barber, customer])
    test_db.flush()
    now = utc_now_naive()
    appointment = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=now, estimated_duration=30, service_type="haircut",
        service_price=20000, status="in_progress", actual_start_time=now - timedelta(minutes=5),
    )
    test_db.add(appointment)
    test_db.commit()

    def fail_consequence(**_kwargs):
        raise RuntimeError(f"{failure_point} storage unavailable")

    if failure_point == "performance":
        monkeypatch.setattr(PerformanceService, "calculate_daily_performance", fail_consequence)
    else:
        monkeypatch.setattr(AchievementService, "check_and_award_achievements", fail_consequence)
    token = create_access_token({"sub": str(barber.id), "role": barber.role})
    response = client.post(
        f"/api/v1/barber/appointments/{appointment.id}/payment",
        headers={"Authorization": f"Bearer {token}"},
        json={"method": "cash", "tip_cents": 0},
    )

    assert response.status_code == 503
    test_db.expire_all()
    assert test_db.get(Appointment, appointment.id).status == "in_progress"
    assert test_db.query(Payment).filter(Payment.appointment_id == appointment.id).count() == 0
    assert test_db.query(NotificationDelivery).filter(
        NotificationDelivery.appointment_id == appointment.id,
    ).count() == 0
    assert test_db.query(AuditLog).filter_by(action="appointment.payment_recorded").count() == 0
    assert test_db.query(BarberPerformance).filter_by(
        barbershop_id=shop.id, barber_id=barber.id,
    ).count() == 0
