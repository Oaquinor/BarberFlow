"""Queue and deliver idempotent SMTP and WhatsApp messages using MySQL."""

import logging
from datetime import timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

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


def enqueue_delivery(
    db: Session,
    *,
    barbershop_id: int,
    dedupe_key: str,
    channel: str,
    event_type: str,
    recipient: str,
    body: str,
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
    """Materialize reminders due within the next 24 hours, once per channel."""
    now = (now or utc_now_naive()).replace(microsecond=0)
    appointments = db.query(Appointment).filter(
        Appointment.status.in_(["pending", "confirmed"]),
        Appointment.scheduled_time > now,
        Appointment.scheduled_time <= now + timedelta(hours=24),
        Appointment.is_deleted == False,
    ).all()
    queued = 0
    notifier = NotificationService(db)
    for appointment in appointments:
        client = db.query(User).filter(
            User.id == appointment.client_id,
            User.is_deleted == False,
        ).first()
        shop = db.query(Barbershop).filter(
            Barbershop.id == appointment.barbershop_id,
            Barbershop.is_deleted == False,
        ).first()
        barber = db.query(User).filter(User.id == appointment.barber_id).first()
        if not client or not shop:
            continue
        due = max(now, appointment.scheduled_time - timedelta(hours=REMINDER_WINDOW_HOURS))
        event = "appointment_reminder"
        if client.email and not client.email.endswith("@client.invalid"):
            dedupe_key = f"appointment:{appointment.id}:reminder:email"
            existing = db.query(NotificationDelivery).filter(
                NotificationDelivery.barbershop_id == shop.id,
                NotificationDelivery.dedupe_key == dedupe_key,
            ).with_for_update().first()
            body = notifier._get_reminder_email_template(
                client_name=client.full_name,
                barber_name=barber.full_name if barber else "Tu barbero",
                barbershop_name=shop.name,
                scheduled_time=notifier._local_scheduled_time(appointment.scheduled_time, shop),
                service_type=appointment.service_type,
                barbershop_address=shop.address_line1 or "N/A",
            )
            if existing and existing.status == "pending":
                existing.recipient = client.email
                existing.body = body
                existing.scheduled_for = due.replace(microsecond=0)
                existing.next_attempt_at = due.replace(microsecond=0)
            elif not existing:
                enqueue_delivery(
                    db, barbershop_id=shop.id, appointment_id=appointment.id,
                    dedupe_key=dedupe_key,
                    channel="email", event_type=event, recipient=client.email,
                    subject=f"Recordatorio de cita - {shop.name}", body=body,
                    scheduled_for=due,
                )
                queued += 1
        if client.phone:
            dedupe_key = f"appointment:{appointment.id}:reminder:whatsapp"
            existing = db.query(NotificationDelivery).filter(
                NotificationDelivery.barbershop_id == shop.id,
                NotificationDelivery.dedupe_key == dedupe_key,
            ).with_for_update().first()
            body = notifier._get_sms_reminder_template(
                barbershop_name=shop.name,
                scheduled_time=notifier._local_scheduled_time(appointment.scheduled_time, shop),
            )
            if existing and existing.status == "pending":
                existing.recipient = client.phone
                existing.body = body
                existing.scheduled_for = due.replace(microsecond=0)
                existing.next_attempt_at = due.replace(microsecond=0)
            elif not existing:
                enqueue_delivery(
                    db, barbershop_id=shop.id, appointment_id=appointment.id,
                    dedupe_key=dedupe_key,
                    channel="whatsapp", event_type=event, recipient=client.phone,
                    body=body, scheduled_for=due,
                )
                queued += 1
    if queued:
        db.commit()
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
