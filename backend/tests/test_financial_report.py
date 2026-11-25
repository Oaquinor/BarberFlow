"""Tenant and local-business-date coverage for financial reports on MySQL."""

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Appointment, Barbershop, OperatingExpense, Payment, RetailSale, User


def _user(email: str, role: str, shop_id: int) -> User:
    return User(
        email=email, password_hash="unused", first_name="Test", last_name=role,
        role=role, is_active=True, barbershop_id=shop_id,
    )


def test_financial_report_uses_business_date_and_is_tenant_scoped(
    client: TestClient, test_db: Session,
):
    shop = Barbershop(
        name="Reporte", slug="financial-report-shop", email="report@example.com",
        phone="8095554010", address_line1="Calle 1", city="Santo Domingo", state="DN",
        postal_code="10101", country="DO", timezone="America/Santo_Domingo", currency="DOP",
    )
    other_shop = Barbershop(
        name="Otro tenant", slug="financial-report-other", email="report-other@example.com",
        phone="8095554011", address_line1="Calle 2", city="Santo Domingo", state="DN",
        postal_code="10102", country="DO", timezone="America/Santo_Domingo", currency="DOP",
    )
    test_db.add_all([shop, other_shop])
    test_db.flush()
    owner = _user("report-owner@example.com", "barbershop_owner", shop.id)
    barber = _user("report-barber@example.com", "barber", shop.id)
    client_user = _user("report-client@example.com", "client", shop.id)
    other_barber = _user("report-other-barber@example.com", "barber", other_shop.id)
    other_client = _user("report-other-client@example.com", "client", other_shop.id)
    test_db.add_all([owner, barber, client_user, other_barber, other_client])
    test_db.flush()

    appointments = [
        Appointment(
            barbershop_id=shop.id, client_id=client_user.id, barber_id=barber.id,
            scheduled_time=datetime(2026, 1, 10, 12), estimated_duration=30,
            service_type="cut", service_price=2000, status="completed",
        ),
        Appointment(
            barbershop_id=shop.id, client_id=client_user.id, barber_id=barber.id,
            scheduled_time=datetime(2026, 1, 10, 13), estimated_duration=30,
            service_type="beard", service_price=1500, status="completed",
        ),
        Appointment(
            barbershop_id=other_shop.id, client_id=other_client.id, barber_id=other_barber.id,
            scheduled_time=datetime(2026, 1, 10, 12), estimated_duration=30,
            service_type="cut", service_price=9900, status="completed",
        ),
    ]
    test_db.add_all(appointments)
    test_db.flush()
    test_db.add_all([
        Payment(
            barbershop_id=shop.id, appointment_id=appointments[0].id, barber_id=barber.id,
            amount_cents=2000, tip_cents=200, method="cash", currency="DOP",
            received_at=datetime(2026, 1, 10, 4, 0), recorded_by_user_id=barber.id,
        ),
        Payment(
            barbershop_id=shop.id, appointment_id=appointments[1].id, barber_id=barber.id,
            amount_cents=1500, tip_cents=0, method="card", currency="DOP",
            received_at=datetime(2026, 1, 11, 3, 59, 59), recorded_by_user_id=barber.id,
        ),
        Payment(
            barbershop_id=other_shop.id, appointment_id=appointments[2].id, barber_id=other_barber.id,
            amount_cents=9900, tip_cents=0, method="cash", currency="DOP",
            received_at=datetime(2026, 1, 10, 15), recorded_by_user_id=other_barber.id,
        ),
    ])
    test_db.add(RetailSale(
        barbershop_id=shop.id, sold_by_user_id=owner.id, payment_method="cash", currency="DOP",
        subtotal_cents=600, total_cents=600, cost_total_cents=250,
        sold_at=datetime(2026, 1, 10, 5), request_key_hash="a" * 64, request_payload_hash="b" * 64,
    ))
    test_db.add(OperatingExpense(
        barbershop_id=shop.id, created_by_user_id=owner.id, category="supplies",
        description="Insumos", amount_cents=500, payment_method="cash", currency="DOP",
        spent_at=datetime(2026, 1, 10, 6), request_key_hash="c" * 64,
        request_payload_hash="d" * 64,
    ))
    test_db.commit()

    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id), 'role': owner.role})}"}
    barber_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber.id), 'role': barber.role})}"}
    report = client.get(
        "/api/v1/analytics/financial-report?start_date=2026-01-10&end_date=2026-01-10",
        headers=owner_headers,
    )
    assert report.status_code == 200
    data = report.json()
    assert data["timezone"] == "America/Santo_Domingo"
    assert data["currency"] == "DOP"
    assert data["payment_count"] == 3
    assert data["service_payment_count"] == 2
    assert data["service_revenue_cents"] == 3500
    assert data["retail_revenue_cents"] == 600
    assert data["retail_sale_count"] == 1
    assert data["tip_cents"] == 200
    assert data["gross_cents"] == 4300
    assert data["expense_count"] == 1
    assert data["expense_total_cents"] == 500
    assert data["balance_after_recorded_expenses_cents"] == 3800
    assert data["expenses_by_category"] == [{
        "key": "supplies", "label": "Insumos", "expense_count": 1, "amount_cents": 500,
    }]
    assert data["by_day"] == [{
        "key": "2026-01-10", "label": "2026-01-10", "payment_count": 3,
        "service_revenue_cents": 3500, "retail_revenue_cents": 600, "retail_sale_count": 1,
        "tip_cents": 200, "gross_cents": 4300, "expense_cents": 500,
        "net_after_recorded_expenses_cents": 3800,
    }]
    assert {row["key"] for row in data["by_method"]} == {"cash", "card"}
    assert data["by_barber"][0]["key"] == str(barber.id)

    forbidden = client.get(
        "/api/v1/analytics/financial-report?start_date=2026-01-10&end_date=2026-01-10",
        headers=barber_headers,
    )
    assert forbidden.status_code == 403
    invalid_range = client.get(
        "/api/v1/analytics/financial-report?start_date=2026-01-11&end_date=2026-01-10",
        headers=owner_headers,
    )
    assert invalid_range.status_code == 422
