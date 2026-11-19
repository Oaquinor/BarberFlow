"""MySQL integration coverage for appointment checkout and daily cash close."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Appointment, AuditLog, BarberPerformance, Barbershop, NotificationDelivery, Payment, User
from app.utils.datetime import utc_now_naive


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
    appointment = Appointment(
        barbershop_id=shop.id, client_id=client_user.id, barber_id=barber.id,
        scheduled_time=utc_now_naive(), estimated_duration=30, service_type="haircut",
        service_price=25000, status="in_progress",
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
    appointment = Appointment(
        barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
        scheduled_time=utc_now_naive(), estimated_duration=30, service_type="haircut",
        service_price=20000, status="in_progress",
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
