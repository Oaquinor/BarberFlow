"""Durable notification queue and reminder scheduling on MySQL."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import Appointment, Barbershop, NotificationDelivery, User
from app.services.notification_outbox import (
    enqueue_delivery,
    enqueue_due_appointment_reminders,
    process_due_deliveries,
)
from app.services.notification_service import NotificationService
from app.utils.datetime import utc_now_naive


def _tenant_with_appointment(db: Session, scheduled_time):
    shop = Barbershop(
        name="Outbox Barbería", slug="outbox-test", email="shop@example.com",
        phone="8095550401", address_line1="Calle Uno", city="Santo Domingo",
        state="DN", postal_code="10101", country="DO", timezone="America/Santo_Domingo",
        currency="DOP",
    )
    db.add(shop)
    db.flush()
    barber = User(
        email="outbox-barber@example.com", password_hash="unused", first_name="Barbero",
        last_name="Uno", role="barber", is_active=True, barbershop_id=shop.id,
    )
    client = User(
        email="outbox-client@example.com", password_hash="unused", first_name="Cliente",
        last_name="Uno", phone="8095550402", role="client", is_active=True,
        barbershop_id=shop.id,
    )
    db.add_all([barber, client])
    db.flush()
    appointment = Appointment(
        barbershop_id=shop.id, client_id=client.id, barber_id=barber.id,
        scheduled_time=scheduled_time, estimated_duration=30, service_type="Corte",
        service_price=10000, status="confirmed",
    )
    db.add(appointment)
    db.flush()
    return shop, client, appointment


def test_reminders_are_due_and_idempotent(test_db: Session):
    now = utc_now_naive()
    shop, client, appointment = _tenant_with_appointment(test_db, now + timedelta(hours=1))

    first = enqueue_due_appointment_reminders(test_db, now)
    second = enqueue_due_appointment_reminders(test_db, now + timedelta(seconds=30))

    rows = test_db.query(NotificationDelivery).filter(
        NotificationDelivery.barbershop_id == shop.id,
        NotificationDelivery.appointment_id == appointment.id,
    ).all()
    assert first == 2
    assert second == 0
    assert {row.channel for row in rows} == {"email", "whatsapp"}
    assert all(row.recipient in {client.email, client.phone} for row in rows)
    assert all(row.scheduled_for <= now + timedelta(seconds=30) for row in rows)


def test_worker_sends_one_due_delivery_once(test_db: Session, monkeypatch):
    now = utc_now_naive()
    shop, _, appointment = _tenant_with_appointment(test_db, now + timedelta(hours=2))
    row = enqueue_delivery(
        test_db, barbershop_id=shop.id, appointment_id=appointment.id,
        dedupe_key="appointment:test:custom", channel="whatsapp",
        event_type="appointment_custom", recipient="8095550403", body="Mensaje de prueba",
        scheduled_for=now,
    )
    test_db.commit()
    due_count = test_db.query(NotificationDelivery.id).filter(
        NotificationDelivery.id == row.id,
        NotificationDelivery.status == "pending",
        NotificationDelivery.scheduled_for <= now,
        NotificationDelivery.next_attempt_at <= now,
        NotificationDelivery.is_deleted == False,
    ).count()
    assert due_count == 1
    monkeypatch.setattr(NotificationService, "_send_whatsapp", lambda *_args: True)

    assert process_due_deliveries(test_db, now=now) == 1
    assert process_due_deliveries(test_db, now=now + timedelta(minutes=1)) == 0
    test_db.refresh(row)
    assert row.status == "sent"
    assert row.attempts == 1
    assert row.sent_at is not None


def test_reminders_follow_rescheduled_appointments(test_db: Session, monkeypatch):
    now = utc_now_naive()
    shop, _, appointment = _tenant_with_appointment(test_db, now + timedelta(hours=23))
    assert enqueue_due_appointment_reminders(test_db, now) == 2
    appointment.scheduled_time = now + timedelta(hours=48)
    test_db.commit()

    assert process_due_deliveries(test_db, now=now) == 0
    rows = test_db.query(NotificationDelivery).filter(
        NotificationDelivery.barbershop_id == shop.id,
        NotificationDelivery.appointment_id == appointment.id,
    ).all()
    assert len(rows) == 2
    assert all(row.status == "pending" for row in rows)
    assert all(row.scheduled_for == (appointment.scheduled_time - timedelta(hours=24)).replace(microsecond=0) for row in rows)

    appointment.scheduled_time = now + timedelta(hours=20)
    test_db.commit()
    assert enqueue_due_appointment_reminders(test_db, now) == 0
    monkeypatch.setattr(NotificationService, "_send_email", lambda *_args: True)
    monkeypatch.setattr(NotificationService, "_send_whatsapp", lambda *_args: True)
    assert process_due_deliveries(test_db, now=now) == 2
    assert all(row.status == "sent" for row in rows)
