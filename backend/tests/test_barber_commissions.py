"""MySQL integration coverage for barber commission accrual, access and settlement."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Appointment, Barbershop, BarberCommission, Payment, User
from app.utils.datetime import utc_now_naive


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'role': user.role})}"}


def test_paid_appointment_accrues_and_owner_can_settle_tenant_commission(
    client: TestClient, test_db: Session,
):
    now = utc_now_naive()
    shop = Barbershop(
        name="Comisiones Barber", slug="barber-commissions-test", email="commissions-shop@example.com",
        phone="8095554100", address_line1="Calle 14", city="Santo Domingo", state="DN",
        postal_code="10104", country="DO", timezone="America/Santo_Domingo", currency="DOP",
    )
    other_shop = Barbershop(
        name="Otro Tenant", slug="barber-commissions-other", email="commissions-other@example.com",
        phone="8095554101", address_line1="Calle 15", city="Santo Domingo", state="DN",
        postal_code="10105", country="DO", timezone="America/Santo_Domingo", currency="DOP",
    )
    test_db.add_all([shop, other_shop])
    test_db.flush()
    owner = User(
        email="commissions-owner@example.com", password_hash="unused", first_name="Dueña",
        last_name="Tienda", role="barbershop_owner", is_active=True, barbershop_id=shop.id,
    )
    other_owner = User(
        email="commissions-other-owner@example.com", password_hash="unused", first_name="Otro",
        last_name="Dueño", role="barbershop_owner", is_active=True, barbershop_id=other_shop.id,
    )
    barber = User(
        email="commissions-barber@example.com", password_hash="unused", first_name="Luis",
        last_name="Barbero", role="barber", is_active=True, barbershop_id=shop.id,
    )
    client_user = User(
        email="commissions-client@example.com", password_hash="unused", first_name="Cliente",
        last_name="Prueba", role="client", is_active=True, barbershop_id=shop.id,
    )
    test_db.add_all([owner, other_owner, barber, client_user])
    test_db.flush()
    appointment = Appointment(
        barbershop_id=shop.id, client_id=client_user.id, barber_id=barber.id,
        scheduled_time=now - timedelta(minutes=15), estimated_duration=30,
        actual_start_time=now - timedelta(minutes=15), service_type="haircut",
        service_price=22000, status="in_progress",
    )
    test_db.add(appointment)
    test_db.commit()

    rate = client.put(
        f"/api/v1/owner/barbers/{barber.id}/commission-rate",
        headers=_headers(owner), json={"rate_basis_points": 5000},
    )
    assert rate.status_code == 200
    assert rate.json()["rate_basis_points"] == 5000

    payment = client.post(
        f"/api/v1/barber/appointments/{appointment.id}/payment",
        headers=_headers(barber), json={"method": "cash", "tip_cents": 1000},
    )
    assert payment.status_code == 201
    assert payment.json()["barber_commission_cents"] == 11000
    commission_id = payment.json()["barber_commission_id"]
    commission = test_db.get(BarberCommission, commission_id)
    assert commission.payment_id == payment.json()["payment_id"]
    assert commission.currency == "DOP"
    assert commission.rate_basis_points == 5000
    assert test_db.query(Payment).filter(Payment.appointment_id == appointment.id).count() == 1

    own_pending = client.get("/api/v1/barber/commissions", headers=_headers(barber))
    assert own_pending.status_code == 200
    assert own_pending.json()["pending_totals_by_currency"] == [{"currency": "DOP", "amount_cents": 11000}]
    assert len(own_pending.json()["items"]) == 1

    owner_list = client.get("/api/v1/owner/barber-commissions", headers=_headers(owner))
    assert owner_list.status_code == 200
    assert owner_list.json()["items"][0]["id"] == commission_id
    assert owner_list.json()["pending_totals_by_currency"] == [{"currency": "DOP", "amount_cents": 11000}]

    foreign_pay = client.post(
        f"/api/v1/owner/barber-commissions/{commission_id}/pay", headers=_headers(other_owner),
        json={"payment_method": "bank_transfer", "payment_reference": "INV-1"},
    )
    assert foreign_pay.status_code == 404

    paid = client.post(
        f"/api/v1/owner/barber-commissions/{commission_id}/pay", headers=_headers(owner),
        json={"payment_method": "cash", "payment_reference": "CAJA-456"},
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"
    test_db.refresh(commission)
    assert commission.paid_by_user_id == owner.id
    assert commission.payment_reference == "CAJA-456"

    cash_summary = client.get("/api/v1/barber/cash/today", headers=_headers(owner))
    assert cash_summary.status_code == 200
    assert cash_summary.json()["cash_commissions_paid_cents"] == 11000
    assert cash_summary.json()["expected_cash_cents"] == 12000
    close = client.post("/api/v1/barber/cash/close", headers=_headers(owner), json={
        "business_date": cash_summary.json()["business_date"],
        "declared_cash_cents": 12000,
        "notes": "Pago de comisión incluido como salida de efectivo",
    })
    assert close.status_code == 201
    assert close.json()["expected_cash_cents"] == 12000
    assert close.json()["cash_commissions_paid_cents"] == 11000

    duplicate = client.post(
        f"/api/v1/owner/barber-commissions/{commission_id}/pay", headers=_headers(owner),
        json={"payment_method": "cash"},
    )
    assert duplicate.status_code == 409
    own_paid = client.get("/api/v1/barber/commissions", headers=_headers(barber))
    assert own_paid.json()["pending_totals_by_currency"] == []
    assert own_paid.json()["paid_totals_by_currency"] == [{"currency": "DOP", "amount_cents": 11000}]
