"""Concurrent cash-close requests must create one immutable daily close (MySQL)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.endpoints import platform
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models import (
    Appointment, AuditLog, BarberCommission, BarberPerformance, Barbershop,
    CashRegisterClose, NotificationDelivery, Payment, User, UserAchievement,
)
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


def test_cash_close_uses_latest_mysql_state_after_waiting_for_checkout(
    mysql_test_engine, monkeypatch,
):
    """A close must reconcile a checkout committed after its initial auth read."""
    suffix = uuid4().hex
    with Session(mysql_test_engine) as db:
        shop = Barbershop(
            name="Cash Checkout Snapshot", slug=f"cash-checkout-snapshot-{suffix}",
            email=f"cash-checkout-snapshot-{suffix}@example.com", phone="8095550202",
            address_line1="Test", city="Santo Domingo", state="DN",
            postal_code="10103", country="DO", timezone="America/Santo_Domingo",
            currency="DOP",
        )
        db.add(shop)
        db.flush()
        owner = User(
            email=f"cash-checkout-owner-{suffix}@example.com", password_hash="unused",
            first_name="Owner", last_name="Snapshot", role="barbershop_owner",
            is_active=True, barbershop_id=shop.id,
        )
        barber = User(
            email=f"cash-checkout-barber-{suffix}@example.com", password_hash="unused",
            first_name="Barber", last_name="Snapshot", role="barber",
            is_active=True, barbershop_id=shop.id,
        )
        customer = User(
            email=f"cash-checkout-client-{suffix}@example.com", password_hash="unused",
            first_name="Client", last_name="Snapshot", role="client",
            is_active=True, barbershop_id=shop.id,
        )
        db.add_all([owner, barber, customer])
        db.flush()
        now = utc_now_naive()
        appointment = Appointment(
            barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
            scheduled_time=now, estimated_duration=30, service_type="Corte",
            service_price=25000, status="in_progress",
            actual_start_time=now - timedelta(minutes=6),
        )
        db.add(appointment)
        db.commit()
        shop_id, owner_id, barber_id = shop.id, owner.id, barber.id
        appointment_id = appointment.id
        business_date = now.replace(tzinfo=timezone.utc).astimezone(
            ZoneInfo(shop.timezone)
        ).date().isoformat()

    def override_get_db():
        with Session(mysql_test_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    close_has_snapshot = Event()
    release_close = Event()
    original_get_current_user = platform._get_current_user

    def pause_close_after_auth_read(db, authorization):
        user = original_get_current_user(db, authorization)
        if user.id == owner_id:
            close_has_snapshot.set()
            if not release_close.wait(timeout=10):
                raise TimeoutError("Cash close test was not released")
        return user

    monkeypatch.setattr(platform, "_get_current_user", pause_close_after_auth_read)
    owner_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner_id)})}"}
    barber_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(barber_id)})}"}
    close_payload = {"business_date": business_date, "declared_cash_cents": 25000}

    def close_cash():
        with TestClient(app) as client:
            return client.post("/api/v1/barber/cash/close", headers=owner_headers, json=close_payload)

    def checkout():
        with TestClient(app) as client:
            return client.post(
                f"/api/v1/barber/appointments/{appointment_id}/payment",
                headers=barber_headers, json={"method": "cash", "tip_cents": 0},
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            close_future = pool.submit(close_cash)
            assert close_has_snapshot.wait(timeout=10)
            checkout_response = checkout()
            release_close.set()
            close_response = close_future.result(timeout=10)

        assert checkout_response.status_code == 201
        assert close_response.status_code == 201
        assert close_response.json()["expected_cash_cents"] == 25000
        assert close_response.json()["payment_count"] == 1
    finally:
        release_close.set()
        app.dependency_overrides.clear()
        with Session(mysql_test_engine) as db:
            user_ids = db.query(User.id).filter(User.barbershop_id == shop_id)
            db.query(UserAchievement).filter(UserAchievement.user_id.in_(user_ids)).delete(
                synchronize_session=False,
            )
            db.query(NotificationDelivery).filter(
                NotificationDelivery.appointment_id == appointment_id,
            ).delete(synchronize_session=False)
            db.query(AuditLog).filter(AuditLog.barbershop_id == shop_id).delete(
                synchronize_session=False,
            )
            db.query(BarberCommission).filter(BarberCommission.barbershop_id == shop_id).delete(
                synchronize_session=False,
            )
            db.query(BarberPerformance).filter(BarberPerformance.barbershop_id == shop_id).delete(
                synchronize_session=False,
            )
            db.query(CashRegisterClose).filter(CashRegisterClose.barbershop_id == shop_id).delete(
                synchronize_session=False,
            )
            db.query(Payment).filter(Payment.barbershop_id == shop_id).delete(
                synchronize_session=False,
            )
            db.query(Appointment).filter(Appointment.barbershop_id == shop_id).delete(
                synchronize_session=False,
            )
            db.query(User).filter(User.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(Barbershop).filter(Barbershop.id == shop_id).delete(synchronize_session=False)
            db.commit()


def test_barber_cannot_close_after_owner_closes_while_barber_waits_for_shop_lock(
    mysql_test_engine, monkeypatch,
):
    suffix = uuid4().hex
    with Session(mysql_test_engine) as db:
        shop = Barbershop(
            name="Cash Close Owner Race", slug=f"cash-close-owner-race-{suffix}",
            email=f"cash-close-owner-race-{suffix}@example.com", phone="8095550201",
            address_line1="Test", city="Santo Domingo", state="DN",
            postal_code="10102", country="DO", timezone="America/Santo_Domingo",
            currency="DOP",
        )
        db.add(shop)
        db.flush()
        owner = User(
            email=f"cash-close-owner-race-owner-{suffix}@example.com", password_hash="unused",
            first_name="Owner", last_name="Race", role="barbershop_owner",
            is_active=True, barbershop_id=shop.id,
        )
        barber = User(
            email=f"cash-close-owner-race-barber-{suffix}@example.com", password_hash="unused",
            first_name="Barber", last_name="Race", role="barber",
            is_active=True, barbershop_id=shop.id,
        )
        db.add_all([owner, barber])
        db.commit()
        shop_id, owner_id, barber_id = shop.id, owner.id, barber.id
        business_date = utc_now_naive().replace(tzinfo=timezone.utc).astimezone(
            ZoneInfo(shop.timezone)
        ).date().isoformat()

    def override_get_db():
        with Session(mysql_test_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    owner_has_snapshot = Event()
    release_owner = Event()
    barber_has_snapshot = Event()
    release_barber = Event()
    original_get_current_user = platform._get_current_user

    def synchronized_get_current_user(db, authorization):
        user = original_get_current_user(db, authorization)
        if user.id == owner_id:
            owner_has_snapshot.set()
            if not release_owner.wait(timeout=10):
                raise TimeoutError("Owner close test was not released")
        elif user.id == barber_id:
            barber_has_snapshot.set()
            if not release_barber.wait(timeout=10):
                raise TimeoutError("Barber close test was not released")
        return user

    monkeypatch.setattr(platform, "_get_current_user", synchronized_get_current_user)
    owner_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(owner_id)})}",
    }
    barber_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(barber_id)})}",
    }
    payload = {"business_date": business_date, "declared_cash_cents": 0}

    def close_once(headers):
        with TestClient(app) as client:
            return client.post("/api/v1/barber/cash/close", headers=headers, json=payload)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            owner_future = pool.submit(close_once, owner_headers)
            assert owner_has_snapshot.wait(timeout=10)
            barber_future = pool.submit(close_once, barber_headers)
            assert barber_has_snapshot.wait(timeout=10)

            release_owner.set()
            owner_response = owner_future.result(timeout=10)
            release_barber.set()
            barber_response = barber_future.result(timeout=10)

        assert owner_response.status_code == 201
        assert barber_response.status_code == 409
        with Session(mysql_test_engine) as db:
            closes = db.query(CashRegisterClose).filter(
                CashRegisterClose.barbershop_id == shop_id,
                CashRegisterClose.business_date == datetime.fromisoformat(business_date),
                CashRegisterClose.is_deleted == False,
            ).all()
            assert len(closes) == 1
            assert closes[0].closed_by_user_id == owner_id
    finally:
        release_owner.set()
        release_barber.set()
        app.dependency_overrides.clear()
        with Session(mysql_test_engine) as db:
            db.query(AuditLog).filter(AuditLog.barbershop_id == shop_id).delete(
                synchronize_session=False,
            )
            db.query(CashRegisterClose).filter(
                CashRegisterClose.barbershop_id == shop_id,
            ).delete(synchronize_session=False)
            db.query(User).filter(User.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(Barbershop).filter(Barbershop.id == shop_id).delete(synchronize_session=False)
            db.commit()
