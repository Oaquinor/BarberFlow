"""Run the durable MySQL outbox and appointment reminder scheduler."""

import logging
import time

from app.core.database import SessionLocal
from app.services.notification_outbox import enqueue_due_appointment_reminders, process_due_deliveries


def run_once() -> tuple[int, int]:
    db = SessionLocal()
    try:
        reminders = enqueue_due_appointment_reminders(db)
        delivered = process_due_deliveries(db)
        return reminders, delivered
    except Exception:
        db.rollback()
        logging.exception("Notification worker cycle failed")
        raise
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    while True:
        try:
            reminders, delivered = run_once()
            if reminders or delivered:
                logging.info("Notification worker queued=%s sent=%s", reminders, delivered)
        except Exception:
            pass
        time.sleep(30)


if __name__ == "__main__":
    main()
