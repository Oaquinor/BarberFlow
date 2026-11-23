"""Durable notification queue and reminder scheduling on MySQL."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import event
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


def test_reminder_materialization_uses_bounded_selects_for_many_appointments(test_db: Session):
    now = utc_now_naive().replace(microsecond=0)
    shop, client, first = _tenant_with_appointment(test_db, now + timedelta(hours=2))
    appointments = [first]
    for offset in range(2, 12):
        appointment = Appointment(
            barbershop_id=shop.id,
            client_id=client.id,
            barber_id=first.barber_id,
            scheduled_time=now + timedelta(hours=offset),
            estimated_duration=30,
            service_type="Corte",
            service_price=10000,
            status="confirmed",
        )
        test_db.add(appointment)
        appointments.append(appointment)
    test_db.commit()

    selects = []

    def count_selects(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(test_db.bind, "before_cursor_execute", count_selects)
    try:
        queued = enqueue_due_appointment_reminders(test_db, now)
    finally:
        event.remove(test_db.bind, "before_cursor_execute", count_selects)

    assert queued == len(appointments) * 2
    assert len(selects) <= 2


def test_reminder_materialization_pages_appointments_and_commits_each_batch(
    test_db: Session, monkeypatch,
):
    now = utc_now_naive().replace(microsecond=0)
    shop, client, first = _tenant_with_appointment(test_db, now + timedelta(hours=2))
    for offset in range(3, 9):
        test_db.add(Appointment(
            barbershop_id=shop.id,
            client_id=client.id,
            barber_id=first.barber_id,
            scheduled_time=now + timedelta(hours=offset),
            estimated_duration=30,
            service_type="Corte",
            service_price=10000,
            status="confirmed",
        ))
    test_db.commit()
    monkeypatch.setattr(
        "app.services.notification_outbox.REMINDER_ENQUEUE_BATCH_SIZE", 3,
    )

    selects = []
    commits = []

    def count_selects(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    def count_commits(_session):
        commits.append(True)

    event.listen(test_db.bind, "before_cursor_execute", count_selects)
    event.listen(test_db, "after_commit", count_commits)
    try:
        queued = enqueue_due_appointment_reminders(test_db, now)
    finally:
        event.remove(test_db.bind, "before_cursor_execute", count_selects)
        event.remove(test_db, "after_commit", count_commits)

    assert queued == 14
    assert len(commits) == 3
    # Each nonempty page loads appointments and existing reminders. The last
    # partial page proves the keyset scan is complete without an empty query.
    assert len(selects) == 6


def test_refreshing_existing_reminders_commits_updates_for_other_workers(mysql_test_engine):
    suffix = uuid4().hex
    now = utc_now_naive().replace(microsecond=0)
    with Session(mysql_test_engine) as db:
        shop = Barbershop(
            name="Outbox reschedule", slug=f"outbox-reschedule-{suffix}",
            email=f"outbox-reschedule-shop-{suffix}@example.com", phone="8095550404",
            address_line1="Calle Dos", city="Santo Domingo", state="DN", postal_code="10102",
            country="DO", timezone="America/Santo_Domingo", currency="DOP",
        )
        db.add(shop)
        db.flush()
        barber = User(
            email=f"outbox-reschedule-barber-{suffix}@example.com", password_hash="unused",
            first_name="Barbero", last_name="Dos", role="barber", is_active=True,
            barbershop_id=shop.id,
        )
        client = User(
            email=f"outbox-reschedule-client-{suffix}@example.com", password_hash="unused",
            first_name="Cliente", last_name="Dos", phone="8095550405", role="client",
            is_active=True, barbershop_id=shop.id,
        )
        db.add_all([barber, client])
        db.flush()
        appointment = Appointment(
            barbershop_id=shop.id, client_id=client.id, barber_id=barber.id,
            scheduled_time=now + timedelta(hours=2), estimated_duration=30,
            service_type="Corte", service_price=10000, status="confirmed",
        )
        db.add(appointment)
        db.commit()
        shop_id, appointment_id, client_id = shop.id, appointment.id, client.id

    with Session(mysql_test_engine) as db:
        assert enqueue_due_appointment_reminders(db, now) == 2

    with Session(mysql_test_engine) as db:
        appointment = db.get(Appointment, appointment_id)
        appointment.scheduled_time = now + timedelta(hours=20)
        client = db.get(User, client_id)
        client.email = f"restored-{suffix}@example.com"
        existing_rows = db.query(NotificationDelivery).filter(
            NotificationDelivery.barbershop_id == shop_id,
            NotificationDelivery.appointment_id == appointment_id,
        ).all()
        previous_email_body = next(row.body for row in existing_rows if row.channel == "email")
        for row in existing_rows:
            row.next_attempt_at = now + timedelta(minutes=30)
        db.commit()

    with Session(mysql_test_engine) as db:
        assert enqueue_due_appointment_reminders(db, now + timedelta(minutes=1)) == 0

    try:
        with Session(mysql_test_engine) as db:
            rows = db.query(NotificationDelivery).filter(
                NotificationDelivery.barbershop_id == shop_id,
                NotificationDelivery.appointment_id == appointment_id,
            ).all()
            assert len(rows) == 2
            email_row = next(row for row in rows if row.channel == "email")
            assert email_row.recipient == f"restored-{suffix}@example.com"
            assert email_row.body != previous_email_body
            assert all(row.scheduled_for == now + timedelta(minutes=1) for row in rows)
            assert all(row.next_attempt_at == now + timedelta(minutes=1) for row in rows)
    finally:
        with Session(mysql_test_engine) as db:
            db.query(NotificationDelivery).filter(
                NotificationDelivery.barbershop_id == shop_id,
            ).delete(synchronize_session=False)
            db.query(Appointment).filter(Appointment.id == appointment_id).delete(
                synchronize_session=False,
            )
            db.query(User).filter(User.barbershop_id == shop_id).delete(synchronize_session=False)
            db.query(Barbershop).filter(Barbershop.id == shop_id).delete(synchronize_session=False)
            db.commit()


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


def test_worker_suppresses_queued_delivery_when_recipient_is_deleted(test_db: Session, monkeypatch):
    now = utc_now_naive()
    shop, client, appointment = _tenant_with_appointment(test_db, now + timedelta(hours=2))
    row = enqueue_delivery(
        test_db, barbershop_id=shop.id, appointment_id=appointment.id,
        recipient_user_id=client.id,
        dedupe_key="appointment:test:deleted-recipient", channel="whatsapp",
        event_type="appointment_custom", recipient=client.phone, body="Mensaje de prueba",
        scheduled_for=now,
    )
    client.is_deleted = True
    test_db.commit()
    sends = []
    monkeypatch.setattr(NotificationService, "_send_whatsapp", lambda *_args: sends.append(True) or True)

    assert process_due_deliveries(test_db, now=now) == 0
    test_db.refresh(row)
    assert sends == []
    assert row.status == "failed"
    assert row.last_error == "recipient_unavailable"


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


def test_reminder_recovers_when_recipient_becomes_available(test_db: Session, monkeypatch):
    now = utc_now_naive()
    shop, client, appointment = _tenant_with_appointment(test_db, now + timedelta(hours=2))
    assert enqueue_due_appointment_reminders(test_db, now) == 2
    email_row = test_db.query(NotificationDelivery).filter(
        NotificationDelivery.barbershop_id == shop.id,
        NotificationDelivery.appointment_id == appointment.id,
        NotificationDelivery.channel == "email",
    ).one()

    client.email = "temporarily@client.invalid"
    test_db.commit()
    monkeypatch.setattr(NotificationService, "_send_whatsapp", lambda *_args: True)
    assert process_due_deliveries(test_db, now=now) == 1
    test_db.refresh(email_row)
    assert email_row.status == "failed"
    assert email_row.last_error == "recipient_unavailable"

    client.email = "restored@example.com"
    test_db.commit()
    assert enqueue_due_appointment_reminders(test_db, now + timedelta(minutes=1)) == 0
    test_db.refresh(email_row)
    assert email_row.status == "pending"
    assert email_row.recipient == client.email
    assert email_row.attempts == 0
    assert email_row.last_error is None
    assert email_row.next_attempt_at == (now + timedelta(minutes=1)).replace(microsecond=0)
    monkeypatch.setattr(NotificationService, "_send_email", lambda *_args: True)
    assert process_due_deliveries(test_db, now=now + timedelta(minutes=1)) == 1
    assert email_row.status == "sent"
