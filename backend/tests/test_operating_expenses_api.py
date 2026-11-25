"""MySQL integration tests for tenant expenses and cash-flow reconciliation."""

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Barbershop, OperatingExpense, Subscription, User
from app.utils.datetime import utc_now_naive


def _tenant(db: Session, key: str):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free",
        status="active",
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29),
        max_barbers=3,
        max_appointments_per_month=100,
        max_clients=200,
        auto_renew=False,
    )
    db.add(subscription)
    db.flush()
    shop = Barbershop(
        name=f"Expense {key}",
        slug=f"expense-{key}",
        email=f"expense-{key}@example.com",
        phone="8095554010",
        address_line1="Calle 1",
        city="Santo Domingo",
        state="DN",
        postal_code="10101",
        country="DO",
        timezone="America/Santo_Domingo",
        currency="DOP",
        subscription_id=subscription.id,
    )
    db.add(shop)
    db.flush()
    owner = User(
        email=f"expense-owner-{key}@example.com",
        password_hash="unused",
        first_name="Owner",
        last_name=key,
        role="barbershop_owner",
        is_active=True,
        barbershop_id=shop.id,
    )
    barber = User(
        email=f"expense-barber-{key}@example.com",
        password_hash="unused",
        first_name="Barber",
        last_name=key,
        role="barber",
        is_active=True,
        barbershop_id=shop.id,
    )
    db.add_all([owner, barber])
    db.commit()
    return shop, owner, barber


def _headers(user: User):
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def test_expenses_are_idempotent_tenant_scoped_and_reconciled_in_cash(
    client: TestClient,
    test_db: Session,
):
    shop, owner, barber = _tenant(test_db, "ledger")
    _, other_owner, _ = _tenant(test_db, "other")
    headers = _headers(owner)
    key = str(uuid4())
    cash_expense = {
        "idempotency_key": key,
        "category": "supplies",
        "description": "Compra de navajas",
        "amount_cents": 2500,
        "payment_method": "cash",
    }
    created = client.post("/api/v1/owner/expenses", headers=headers, json=cash_expense)
    retried = client.post("/api/v1/owner/expenses", headers=headers, json=cash_expense)
    assert created.status_code == retried.status_code == 201
    assert created.json()["id"] == retried.json()["id"]
    assert created.json()["currency"] == "DOP"

    conflict = client.post(
        "/api/v1/owner/expenses",
        headers=headers,
        json={**cash_expense, "amount_cents": 2600},
    )
    assert conflict.status_code == 409
    card_expense = client.post(
        "/api/v1/owner/expenses",
        headers=headers,
        json={
            **cash_expense,
            "idempotency_key": str(uuid4()),
            "category": "maintenance",
            "description": "Servicio de máquina",
            "amount_cents": 7000,
            "payment_method": "card",
        },
    )
    assert card_expense.status_code == 201

    today = datetime.now(ZoneInfo(shop.timezone)).date().isoformat()
    # The range is interpreted in the shop's IANA zone by the API.
    listing = client.get(
        f"/api/v1/owner/expenses?start_date={today}&end_date={today}",
        headers=headers,
    )
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 2
    assert (
        test_db.query(OperatingExpense).filter_by(barbershop_id=shop.id, is_deleted=False).count()
        == 2
    )
    other_listing = client.get("/api/v1/owner/expenses", headers=_headers(other_owner))
    assert other_listing.status_code == 200
    assert other_listing.json()["items"] == []

    forbidden = client.post("/api/v1/owner/expenses", headers=_headers(barber), json=cash_expense)
    assert forbidden.status_code == 403
    summary = client.get("/api/v1/barber/cash/today", headers=headers).json()
    assert summary["expenses_total_cents"] == 9500
    assert summary["cash_expense_cents"] == 2500
    assert summary["cash_movement_net_cents"] == -2500

    business_date = summary["business_date"]
    closed = client.post(
        "/api/v1/barber/cash/close",
        headers=headers,
        json={
            "business_date": business_date,
            "opening_cash_cents": 5000,
            "declared_cash_cents": 2500,
        },
    )
    assert closed.status_code == 201, closed.text
    assert closed.json()["opening_cash_cents"] == 5000
    assert closed.json()["expected_cash_cents"] == 2500
    assert closed.json()["difference_cents"] == 0
    after_close = client.post(
        "/api/v1/owner/expenses",
        headers=headers,
        json={
            **cash_expense,
            "idempotency_key": str(uuid4()),
            "description": "Gasto tardío",
        },
    )
    assert after_close.status_code == 409
