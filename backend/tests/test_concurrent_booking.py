"""MySQL integration test for two clients racing to reserve one slot."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models import (
    AuditLog, Appointment, BarberAvailability, Barbershop, InAppNotification,
    NotificationDelivery, Service, Subscription, User,
)
from app.utils.datetime import utc_now_naive


def test_only_one_simultaneous_request_can_claim_a_booking_slot(mysql_test_engine):
    suffix = uuid4().hex
    now = utc_now_naive().replace(second=0, microsecond=0)
    slot_start = (now + timedelta(days=1)).replace(minute=0)
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=1,
        max_appointments_per_month=50, max_clients=100, auto_renew=False,
    )
    with Session(mysql_test_engine) as db:
        db.add(subscription)
        db.flush()
        shop = Barbershop(
            name="Race Test", slug=f"race-{suffix}", email=f"shop-{suffix}@example.com",
            phone="8095550000", address_line1="Test", city="Santo Domingo",
            state="DN", postal_code="10101", country="DO",
            timezone="America/Santo_Domingo", subscription_id=subscription.id,
        )
        db.add(shop)
        db.flush()
        barber = User(
            email=f"barber-{suffix}@example.com", password_hash="unused",
            first_name="Barbero", last_name="Race", role="barber", is_active=True,
            barbershop_id=shop.id,
        )
        service = Service(
            barbershop_id=shop.id, name="Corte Race", duration_minutes=30,
            price=1800, category="haircut", is_active=True,
        )
        db.add_all([barber, service])
        db.flush()
        slot = BarberAvailability(
            barbershop_id=shop.id, barber_id=barber.id, slot_start=slot_start,
            slot_end=slot_start + timedelta(minutes=30), is_active=True, is_booked=False,
        )
        db.add(slot)
        db.commit()
        shop_id, slot_id, service_id = shop.id, slot.id, service.id
        subscription_id = subscription.id
        slug = shop.slug

    def override_get_db():
        with Session(mysql_test_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    payload = {
        "client_name": "Cliente Carrera",
        "phone": "8095551234",
        "service_id": service_id,
        "scheduled_time": slot_start.replace(tzinfo=timezone.utc).isoformat(),
    }

    def book_once():
        with TestClient(app) as client:
            return client.post(f"/api/v1/public/{slug}/appointments", json=payload)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _index: book_once(), range(2)))
        assert sum(response.status_code == 200 for response in responses) == 1
        assert sum(response.status_code in {400, 409} for response in responses) == 1
        with Session(mysql_test_engine) as db:
            assert db.query(Appointment.id).filter(
                Appointment.barbershop_id == shop_id,
                Appointment.scheduled_time == slot_start,
                Appointment.is_deleted == False,
            ).count() == 1
            persisted_slot = db.get(BarberAvailability, slot_id)
            assert persisted_slot is not None and persisted_slot.is_booked is True
    finally:
        app.dependency_overrides.clear()
        with Session(mysql_test_engine) as db:
            db.query(NotificationDelivery).filter(NotificationDelivery.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(InAppNotification).filter(InAppNotification.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(AuditLog).filter(AuditLog.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(Appointment).filter(Appointment.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(BarberAvailability).filter(BarberAvailability.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(Service).filter(Service.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(User).filter(User.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(Barbershop).filter(Barbershop.id == shop_id).delete(synchronize_session=False)
            db.query(Subscription).filter(Subscription.id == subscription_id).delete(synchronize_session=False)
            db.commit()


def test_booking_and_service_start_serialize_on_the_barber(mysql_test_engine):
    """A public booking cannot deadlock with the barber starting another appointment."""
    suffix = uuid4().hex
    now = utc_now_naive().replace(second=0, microsecond=0)
    slot_start = (now + timedelta(days=1)).replace(minute=0)
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=1,
        max_appointments_per_month=50, max_clients=100, auto_renew=False,
    )
    with Session(mysql_test_engine) as db:
        db.add(subscription)
        db.flush()
        shop = Barbershop(
            name="Start Race", slug=f"start-race-{suffix}", email=f"start-race-{suffix}@example.com",
            phone="8095550001", address_line1="Test", city="Santo Domingo",
            state="DN", postal_code="10101", country="DO",
            timezone="America/Santo_Domingo", subscription_id=subscription.id,
        )
        db.add(shop)
        db.flush()
        barber = User(
            email=f"start-race-{suffix}-barber@example.com", password_hash="unused",
            first_name="Barbero", last_name="Start", role="barber", is_active=True,
            barbershop_id=shop.id,
        )
        customer = User(
            email=f"start-race-{suffix}-client@example.com", password_hash="unused",
            first_name="Cliente", last_name="Start", role="client", is_active=True,
            barbershop_id=shop.id,
        )
        service = Service(
            barbershop_id=shop.id, name="Corte Start Race", duration_minutes=30,
            price=1800, category="haircut", is_active=True,
        )
        db.add_all([barber, customer, service])
        db.flush()
        appointment = Appointment(
            barbershop_id=shop.id, client_id=customer.id, barber_id=barber.id,
            scheduled_time=now, estimated_duration=30, service_type="Corte",
            service_price=1800, status="pending",
        )
        slot = BarberAvailability(
            barbershop_id=shop.id, barber_id=barber.id, slot_start=slot_start,
            slot_end=slot_start + timedelta(minutes=30), is_active=True, is_booked=False,
        )
        db.add_all([appointment, slot])
        db.commit()
        shop_id, appointment_id, slot_id, service_id = shop.id, appointment.id, slot.id, service.id
        barber_id, subscription_id, slug = barber.id, subscription.id, shop.slug

    def override_get_db():
        with Session(mysql_test_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    barber_token = create_access_token({"sub": str(barber_id), "role": "barber"})
    headers = {"Authorization": f"Bearer {barber_token}"}
    booking_phone = f"809{int(suffix[:8], 16) % 10_000_000:07d}"

    def start_service():
        with TestClient(app) as client:
            return client.put(
                f"/api/v1/barber/appointments/{appointment_id}/status",
                headers=headers, json={"status": "in_progress"},
            )

    def book_other_slot():
        with TestClient(app) as client:
            return client.post(f"/api/v1/public/{slug}/appointments", json={
                "client_name": "Cliente Concurrente", "phone": booking_phone,
                "service_id": service_id,
                "scheduled_time": slot_start.replace(tzinfo=timezone.utc).isoformat(),
            })

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            start_future = pool.submit(start_service)
            book_future = pool.submit(book_other_slot)
            started, booked = start_future.result(), book_future.result()
        assert started.status_code == 200
        assert booked.status_code == 200
        with Session(mysql_test_engine) as db:
            assert db.get(Appointment, appointment_id).status == "in_progress"
            assert db.get(BarberAvailability, slot_id).is_booked is True
    finally:
        app.dependency_overrides.clear()
        with Session(mysql_test_engine) as db:
            db.query(NotificationDelivery).filter(NotificationDelivery.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(InAppNotification).filter(InAppNotification.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(AuditLog).filter(AuditLog.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(Appointment).filter(Appointment.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(BarberAvailability).filter(BarberAvailability.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(Service).filter(Service.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(User).filter(User.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(Barbershop).filter(Barbershop.id == shop_id).delete(synchronize_session=False)
            db.query(Subscription).filter(Subscription.id == subscription_id).delete(synchronize_session=False)
            db.commit()
