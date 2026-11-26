"""Cash close history stays inside a barber shop and follows role visibility."""

from datetime import datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models import Barbershop, CashRegisterClose, User
from app.utils.datetime import utc_now_naive


def test_cash_history_is_shop_scoped_and_role_scoped(mysql_test_engine):
    suffix = uuid4().hex
    with Session(mysql_test_engine) as db:
        shop = Barbershop(
            name="Cash History", slug=f"cash-history-{suffix}",
            email=f"cash-history-{suffix}@example.com", phone="8095550340",
            address_line1="Test", city="Santo Domingo", state="DN",
            postal_code="10105", country="DO", timezone="America/Santo_Domingo",
            currency="DOP",
        )
        other_shop = Barbershop(
            name="Other Cash History", slug=f"other-cash-history-{suffix}",
            email=f"other-cash-history-{suffix}@example.com", phone="8095550341",
            address_line1="Test", city="Santo Domingo", state="DN",
            postal_code="10105", country="DO", timezone="America/Santo_Domingo",
            currency="DOP",
        )
        db.add_all([shop, other_shop])
        db.flush()
        owner = User(
            email=f"cash-history-owner-{suffix}@example.com", password_hash="unused",
            first_name="History", last_name="Owner", role="barbershop_owner",
            is_active=True, barbershop_id=shop.id,
        )
        barber = User(
            email=f"cash-history-barber-{suffix}@example.com", password_hash="unused",
            first_name="History", last_name="Barber", role="barber",
            is_active=True, barbershop_id=shop.id,
        )
        other_owner = User(
            email=f"cash-history-other-{suffix}@example.com", password_hash="unused",
            first_name="Other", last_name="Owner", role="barbershop_owner",
            is_active=True, barbershop_id=other_shop.id,
        )
        db.add_all([owner, barber, other_owner])
        db.flush()
        today = utc_now_naive().replace(tzinfo=timezone.utc).astimezone(
            ZoneInfo(shop.timezone),
        ).date()
        close_date = datetime.combine(today - timedelta(days=2), time.min)
        closed_at = datetime.combine(today - timedelta(days=2), time(21, 0))
        db.add_all([
            CashRegisterClose(
                barbershop_id=shop.id, closed_by_user_id=owner.id, business_date=close_date,
                expected_cash_cents=12000, opening_cash_cents=1000,
                declared_cash_cents=11800, difference_cents=-200,
                payment_count=4, notes="private note", closed_at=closed_at,
            ),
            CashRegisterClose(
                barbershop_id=shop.id, closed_by_user_id=barber.id,
                business_date=datetime.combine(today - timedelta(days=1), time.min),
                expected_cash_cents=4000, opening_cash_cents=0,
                declared_cash_cents=4000, difference_cents=0,
                payment_count=2, closed_at=closed_at + timedelta(days=1),
            ),
            CashRegisterClose(
                barbershop_id=other_shop.id, closed_by_user_id=other_owner.id, business_date=close_date,
                expected_cash_cents=999999, opening_cash_cents=0,
                declared_cash_cents=999999, difference_cents=0,
                payment_count=1, closed_at=closed_at,
            ),
        ])
        db.commit()
        shop_id, other_shop_id = shop.id, other_shop.id
        owner_id, barber_id = owner.id, barber.id

    def override_get_db():
        with Session(mysql_test_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner_id)})}"}
    barber_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber_id)})}"}
    start_date = (today - timedelta(days=3)).isoformat()
    end_date = today.isoformat()
    try:
        with TestClient(app) as client:
            owner_response = client.get(
                "/api/v1/barber/cash/history",
                params={"start_date": start_date, "end_date": end_date},
                headers=owner_headers,
            )
            barber_response = client.get(
                "/api/v1/barber/cash/history",
                params={"start_date": start_date, "end_date": end_date},
                headers=barber_headers,
            )
            invalid_range = client.get(
                "/api/v1/barber/cash/history",
                params={"start_date": end_date, "end_date": start_date},
                headers=owner_headers,
            )

        assert owner_response.status_code == 200
        owner_items = owner_response.json()["items"]
        assert len(owner_items) == 2
        assert {item["closed_by_role"] for item in owner_items} == {"barber", "barbershop_owner"}
        assert all("notes" not in item for item in owner_items)
        assert all(item["expected_cash_cents"] != 999999 for item in owner_items)
        assert barber_response.status_code == 200
        barber_items = barber_response.json()["items"]
        assert len(barber_items) == 2
        assert {item["closed_by_role"] for item in barber_items} == {"barber", "barbershop_owner"}
        assert invalid_range.status_code == 422
    finally:
        app.dependency_overrides.clear()
        with Session(mysql_test_engine) as db:
            db.query(CashRegisterClose).filter(
                CashRegisterClose.barbershop_id.in_([shop_id, other_shop_id]),
            ).delete(synchronize_session=False)
            db.query(User).filter(User.barbershop_id.in_([shop_id, other_shop_id])).delete(
                synchronize_session=False,
            )
            db.query(Barbershop).filter(Barbershop.id.in_([shop_id, other_shop_id])).delete(
                synchronize_session=False,
            )
            db.commit()
