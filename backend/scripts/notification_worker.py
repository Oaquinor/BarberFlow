"""Run the durable MySQL outbox and appointment reminder scheduler."""

import logging
import time

from app.core.database import SessionLocal
from app.services.notification_outbox import (
    enqueue_due_appointment_reminders,
    process_due_deliveries,
)
from app.services.style_passport_retention import purge_expired_style_passports
from app.services.waitlist_offer_service import enqueue_automatic_waitlist_offers


def run_once() -> tuple[int, int, int, int]:
    db = SessionLocal()
    try:
        reminders = enqueue_due_appointment_reminders(db)
        waitlist_offers = enqueue_automatic_waitlist_offers(db)
        delivered = process_due_deliveries(db)
        purged_style_passports = purge_expired_style_passports(db)
        return reminders, waitlist_offers, delivered, purged_style_passports
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
            reminders, waitlist_offers, delivered, purged = run_once()
            if reminders or waitlist_offers or delivered or purged:
                logging.info(
                    "Worker reminders_queued=%s waitlist_offers_queued=%s sent=%s style_passports_purged=%s",
                    reminders,
                    waitlist_offers,
                    delivered,
                    purged,
                )
        except Exception:
            pass
        time.sleep(30)


if __name__ == "__main__":
    main()
