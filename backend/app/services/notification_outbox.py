"""Queue and deliver idempotent SMTP and WhatsApp messages using MySQL."""

import logging
from datetime import timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.appointment import Appointment
from app.models.barbershop import Barbershop
from app.models.notification_delivery import NotificationDelivery
from app.models.user import User
from app.services.notification_service import NotificationService
from app.utils.datetime import utc_now_naive

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 8
LEASE_MINUTES = 5
REMINDER_WINDOW_HOURS = 24
REMINDER_ENQUEUE_BATCH_SIZE = 500


def enqueue_delivery(
    db: Session,
    *,
    barbershop_id: int,
    dedupe_key: str,
    channel: str,
    event_type: str,
    recipient: str,
    body: str,
    recipient_user_id: int | None = None,
    subject: str | None = None,
    appointment_id: int | None = None,
    scheduled_for=None,
) -> NotificationDelivery:
    """Persist a delivery in the same transaction as its business event."""
    if channel not in {"email", "whatsapp"}:
        raise ValueError("Unsupported notification channel")
    # These MySQL DATETIME columns use second precision, so normalize values
    # before insert to avoid rounding a due timestamp into the next second.
    now = utc_now_naive().replace(microsecond=0)
    scheduled_for = (scheduled_for or now).replace(microsecond=0)
    existing = db.query(NotificationDelivery).filter(
        NotificationDelivery.barbershop_id == barbershop_id,
        NotificationDelivery.dedupe_key == dedupe_key,
    ).first()
    if existing:
        return existing
    row = NotificationDelivery(
        barbershop_id=barbershop_id,
        appointment_id=appointment_id,
        recipient_user_id=recipient_user_id,
        dedupe_key=dedupe_key,
        channel=channel,
        event_type=event_type,
        recipient=recipient,
        subject=subject,
        body=body,
        status="pending",
        attempts=0,
        scheduled_for=scheduled_for,
        next_attempt_at=scheduled_for,
    )
    db.add(row)
    return row


def enqueue_due_appointment_reminders(db: Session, now=None) -> int:
    """Materialize reminders due within the next 24 hours in bounded batches."""
    now = (now or utc_now_naive()).replace(microsecond=0)
    last_appointment_id = 0
    total_queued = 0
    while True:
        appointments = db.query(Appointment).filter(
            Appointment.id > last_appointment_id,
            Appointment.status.in_(["pending", "confirmed"]),
            Appointment.scheduled_time > now,
            Appointment.scheduled_time <= now + timedelta(hours=24),
            Appointment.is_deleted == False,
        ).order_by(Appointment.id).limit(REMINDER_ENQUEUE_BATCH_SIZE).options(
            joinedload(Appointment.client),
            joinedload(Appointment.barber),
            joinedload(Appointment.barbershop),
        ).all()
        if not appointments:
            break

        total_queued += _enqueue_appointment_reminder_batch(db, appointments, now)
        last_appointment_id = appointments[-1].id
        # Commit each bounded batch so both memory and row locks remain bounded.
        db.commit()
        if len(appointments) < REMINDER_ENQUEUE_BATCH_SIZE:
            break

    return total_queued


def _enqueue_appointment_reminder_batch(db: Session, appointments: list[Appointment], now) -> int:
    """Refresh and queue reminders for one already-loaded appointment batch."""
    appointment_ids = [appointment.id for appointment in appointments]
    reminder_rows = db.query(NotificationDelivery).filter(
        NotificationDelivery.appointment_id.in_(appointment_ids),
        NotificationDelivery.event_type == "appointment_reminder",
        NotificationDelivery.channel.in_(["email", "whatsapp"]),
    ).with_for_update().all() if appointment_ids else []
    reminders_by_appointment_and_channel = {
        (row.appointment_id, row.channel): row for row in reminder_rows
    }
    queued = 0
    notifier = NotificationService(db)

    def add_reminder(appointment, shop, channel, recipient, body, due, subject=None):
        row = NotificationDelivery(
            barbershop_id=shop.id,
            appointment_id=appointment.id,
            recipient_user_id=client.id,
            dedupe_key=f"appointment:{appointment.id}:reminder:{channel}",
            channel=channel,
            event_type="appointment_reminder",
            recipient=recipient,
            subject=subject,
            body=body,
            status="pending",
            attempts=0,
            scheduled_for=due.replace(microsecond=0),
            next_attempt_at=due.replace(microsecond=0),
        )
        db.add(row)
        reminders_by_appointment_and_channel[(appointment.id, channel)] = row

    for appointment in appointments:
        client = appointment.client
        shop = appointment.barbershop
        barber = appointment.barber
        if not client or client.is_deleted or not shop or shop.is_deleted:
            continue
        due = max(now, appointment.scheduled_time - timedelta(hours=REMINDER_WINDOW_HOURS))
        if client.email and not client.email.endswith("@client.invalid"):
            existing = reminders_by_appointment_and_channel.get((appointment.id, "email"))
            body = notifier._get_reminder_email_template(
                client_name=client.full_name,
                barber_name=barber.full_name if barber else "Tu barbero",
                barbershop_name=shop.name,
                scheduled_time=notifier._local_scheduled_time(appointment.scheduled_time, shop),
                service_type=appointment.service_type,
                barbershop_address=shop.address_line1 or "N/A",
            )
            if existing and (
                existing.status == "pending"
                or (
                    existing.status == "failed"
                    and existing.last_error in {"recipient_unavailable", "appointment_not_upcoming"}
                )
            ):
                if existing.status == "failed":
                    existing.status = "pending"
                    existing.attempts = 0
                    existing.last_error = None
                    existing.claimed_at = None
                    existing.sent_at = None
                existing.recipient = client.email
                existing.body = body
                existing.scheduled_for = due.replace(microsecond=0)
                existing.next_attempt_at = due.replace(microsecond=0)
            elif not existing:
                add_reminder(
                    appointment, shop, "email", client.email, body, due,
                    subject=f"Recordatorio de cita - {shop.name}",
                )
                queued += 1
        if client.phone:
            existing = reminders_by_appointment_and_channel.get((appointment.id, "whatsapp"))
            body = notifier._get_sms_reminder_template(
                barbershop_name=shop.name,
                scheduled_time=notifier._local_scheduled_time(appointment.scheduled_time, shop),
            )
            if existing and (
                existing.status == "pending"
                or (
                    existing.status == "failed"
                    and existing.last_error in {"recipient_unavailable", "appointment_not_upcoming"}
                )
            ):
                if existing.status == "failed":
                    existing.status = "pending"
                    existing.attempts = 0
                    existing.last_error = None
                    existing.claimed_at = None
                    existing.sent_at = None
                existing.recipient = client.phone
                existing.body = body
                existing.scheduled_for = due.replace(microsecond=0)
                existing.next_attempt_at = due.replace(microsecond=0)
            elif not existing:
                add_reminder(appointment, shop, "whatsapp", client.phone, body, due)
                queued += 1
    return queued


def _refresh_reminder_content(db: Session, row: NotificationDelivery, appointment: Appointment) -> bool:
    """Refresh stored recipient and template after a booking is reprogrammed."""
    client = db.query(User).filter(User.id == appointment.client_id, User.is_deleted == False).first()
    shop = db.query(Barbershop).filter(
        Barbershop.id == appointment.barbershop_id,
        Barbershop.is_deleted == False,
    ).first()
    barber = db.query(User).filter(User.id == appointment.barber_id).first()
    if not client or not shop:
        return False
    if row.channel == "email":
        if not client.email or client.email.endswith("@client.invalid"):
            return False
        row.recipient = client.email
        row.body = NotificationService(db)._get_reminder_email_template(
            client_name=client.full_name,
            barber_name=barber.full_name if barber else "Tu barbero",
            barbershop_name=shop.name,
            scheduled_time=NotificationService(db)._local_scheduled_time(appointment.scheduled_time, shop),
            service_type=appointment.service_type,
            barbershop_address=shop.address_line1 or "N/A",
        )
    else:
        if not client.phone:
            return False
        row.recipient = client.phone
        row.body = NotificationService(db)._get_sms_reminder_template(
            barbershop_name=shop.name,
            scheduled_time=NotificationService(db)._local_scheduled_time(appointment.scheduled_time, shop),
        )
    return True


def process_due_deliveries(db: Session, limit: int = 25, now=None) -> int:
    """Claim and send one bounded batch; failures retry with capped exponential backoff."""
    now = now or utc_now_naive()
    rows = db.query(NotificationDelivery).filter(
        NotificationDelivery.is_deleted == False,
        NotificationDelivery.status.in_(["pending", "processing"]),
        NotificationDelivery.scheduled_for <= now,
        NotificationDelivery.next_attempt_at <= now,
        or_(
            NotificationDelivery.status == "pending",
            NotificationDelivery.claimed_at.is_(None),
            NotificationDelivery.claimed_at <= now - timedelta(minutes=LEASE_MINUTES),
        ),
    ).order_by(NotificationDelivery.scheduled_for, NotificationDelivery.id).limit(limit).with_for_update(skip_locked=True).all()
    if not rows:
        return 0
    for row in rows:
        row.status = "processing"
        row.claimed_at = now
        row.attempts += 1
    db.commit()

    sent_count = 0
    notifier = NotificationService(None)
    for row_id in [item.id for item in rows]:
        row = db.query(NotificationDelivery).filter(NotificationDelivery.id == row_id).with_for_update().first()
        if not row or row.status != "processing":
            continue
        # Scheduled reminders are invalid once the appointment was cancelled or completed.
        if row.event_type == "appointment_reminder" and row.appointment_id:
            appointment = db.query(Appointment).filter(
                Appointment.id == row.appointment_id,
                Appointment.barbershop_id == row.barbershop_id,
                Appointment.status.in_(["pending", "confirmed"]),
                Appointment.is_deleted == False,
            ).first()
            if not appointment:
                row.status = "failed"
                row.last_error = "appointment_not_active"
                row.claimed_at = None
                db.commit()
                continue
            if appointment.scheduled_time <= now:
                row.status = "failed"
                row.last_error = "appointment_not_upcoming"
                row.claimed_at = None
                db.commit()
                continue
            if not _refresh_reminder_content(db, row, appointment):
                row.status = "failed"
                row.last_error = "recipient_unavailable"
                row.claimed_at = None
                db.commit()
                continue
            if appointment.scheduled_time > now + timedelta(hours=REMINDER_WINDOW_HOURS):
                rescheduled_for = (appointment.scheduled_time - timedelta(hours=REMINDER_WINDOW_HOURS)).replace(microsecond=0)
                row.status = "pending"
                row.scheduled_for = rescheduled_for
                row.next_attempt_at = rescheduled_for
                row.attempts = max(0, row.attempts - 1)
                row.claimed_at = None
                db.commit()
                continue
        if row.recipient_user_id:
            recipient_user = db.query(User).filter(
                User.id == row.recipient_user_id,
                User.is_deleted == False,
                User.is_active == True,
            ).with_for_update().first()
            contact = (recipient_user.email if row.channel == "email" else recipient_user.phone) if recipient_user else None
            if not contact or contact != row.recipient or (row.channel == "email" and contact.endswith("@client.invalid")):
                row.status = "failed"
                row.last_error = "recipient_unavailable"
                row.claimed_at = None
                db.commit()
                continue
        if row.channel == "email":
            delivered = notifier._send_email(row.recipient, row.subject or "KingFlow Barber", row.body)
        else:
            delivered = notifier._send_whatsapp(row.recipient, row.body)
        if delivered:
            row.status = "sent"
            row.sent_at = utc_now_naive().replace(microsecond=0)
            row.last_error = None
            sent_count += 1
        elif row.attempts >= MAX_ATTEMPTS:
            row.status = "failed"
            row.last_error = "delivery_failed_max_attempts"
        else:
            row.status = "pending"
            row.next_attempt_at = (utc_now_naive() + timedelta(minutes=min(60, 2 ** row.attempts))).replace(microsecond=0)
            row.last_error = "delivery_failed"
        row.claimed_at = None
        db.commit()
    return sent_count
