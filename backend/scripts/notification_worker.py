"""Run the durable MySQL outbox and appointment reminder scheduler."""

import logging
import time

from app.core.database import SessionLocal
from app.services.notification_outbox import enqueue_due_appointment_reminders, process_due_deliveries
from app.services.style_passport_retention import purge_expired_style_passports


def run_once() -> tuple[int, int, int]:
    db = SessionLocal()
    try:
        reminders = enqueue_due_appointment_reminders(db)
        delivered = process_due_deliveries(db)
        purged_style_passports = purge_expired_style_passports(db)
        return reminders, delivered, purged_style_passports
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
            reminders, delivered, purged = run_once()
            if reminders or delivered or purged:
                logging.info(
                    "Worker queued=%s sent=%s style_passports_purged=%s",
                    reminders, delivered, purged,
                )
        except Exception:
            pass
        time.sleep(30)


if __name__ == "__main__":
    main()
