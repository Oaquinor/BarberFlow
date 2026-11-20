"""Concurrent cash-close requests must create one immutable daily close (MySQL)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models import AuditLog, Barbershop, CashRegisterClose, User
from app.utils.datetime import utc_now_naive


def test_only_one_simultaneous_request_can_close_the_business_date(mysql_test_engine):
    suffix = uuid4().hex
    with Session(mysql_test_engine) as db:
        shop = Barbershop(
            name="Cash Close Race", slug=f"cash-close-race-{suffix}",
            email=f"cash-close-race-{suffix}@example.com", phone="8095550200",
            address_line1="Test", city="Santo Domingo", state="DN",
            postal_code="10101", country="DO", timezone="America/Santo_Domingo",
            currency="DOP",
        )
        db.add(shop)
        db.flush()
        owner = User(
            email=f"cash-close-race-owner-{suffix}@example.com", password_hash="unused",
            first_name="Owner", last_name="Race", role="barbershop_owner",
            is_active=True, barbershop_id=shop.id,
        )
        db.add(owner)
        db.commit()
        shop_id, owner_id = shop.id, owner.id
        business_date = utc_now_naive().replace(tzinfo=timezone.utc).astimezone(
            ZoneInfo(shop.timezone)
        ).date().isoformat()

    def override_get_db():
        with Session(mysql_test_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    token = create_access_token({"sub": str(owner_id), "role": "barbershop_owner"})
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"business_date": business_date, "declared_cash_cents": 0}

    def close_once():
        with TestClient(app) as client:
            return client.post("/api/v1/barber/cash/close", headers=headers, json=payload)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _index: close_once(), range(2)))

        assert sorted(response.status_code for response in responses) == [201, 409]
        with Session(mysql_test_engine) as db:
            assert db.query(CashRegisterClose).filter(
                CashRegisterClose.barbershop_id == shop_id,
                CashRegisterClose.closed_by_user_id == owner_id,
                CashRegisterClose.is_deleted == False,
            ).count() == 1
            assert db.query(AuditLog).filter(
                AuditLog.barbershop_id == shop_id,
                AuditLog.action == "cash.closed",
            ).count() == 1
    finally:
        app.dependency_overrides.clear()
        with Session(mysql_test_engine) as db:
            db.query(AuditLog).filter(AuditLog.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(CashRegisterClose).filter(
                CashRegisterClose.barbershop_id == shop_id,
            ).delete(synchronize_session=False)
            db.query(User).filter(User.id == owner_id).delete(synchronize_session=False)
            db.query(Barbershop).filter(Barbershop.id == shop_id).delete(synchronize_session=False)
            db.commit()
