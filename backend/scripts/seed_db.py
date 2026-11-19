"""Seed disposable demo records. This command refuses to run outside development."""

import argparse
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Barbershop, Service, Subscription, User


DEMO_SHOP = "kings-barbershop-demo"


def seed_database() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-demo-data", action="store_true")
    args = parser.parse_args()
    if settings.ENVIRONMENT.lower() != "development" or not args.allow_demo_data:
        parser.error("Demo seeding requires ENVIRONMENT=development and --allow-demo-data")
    if input(f"Type {DEMO_SHOP} to create disposable demo accounts: ").strip() != DEMO_SHOP:
        print("Cancelled.")
        return 1

    db = SessionLocal()
    try:
        if db.query(Barbershop.id).filter(Barbershop.slug == DEMO_SHOP).first():
            print("Demo barber shop already exists; refusing to modify existing records.")
            return 1

        now = datetime.utcnow()
        subscription = Subscription(
            plan="professional", status="active", current_period_start=now,
            current_period_end=now + timedelta(days=30), max_barbers=10,
            max_appointments_per_month=1000, max_clients=2000, auto_renew=False,
        )
        db.add(subscription)
        db.flush()
        shop = Barbershop(
            name="King's Barbershop Demo", slug=DEMO_SHOP,
            email="demo-shop@example.invalid", phone="8095550100",
            address_line1="Calle Demo 1", city="Santo Domingo", state="Distrito Nacional",
            postal_code="10101", country="DO", timezone="America/Santo_Domingo",
            currency="DOP", subscription_id=subscription.id, is_active=True,
        )
        db.add(shop)
        db.flush()

        users = [
            User(email="admin-demo@example.invalid", first_name="Demo", last_name="Admin", role="super_admin"),
            User(email="owner-demo@example.invalid", first_name="Demo", last_name="Owner", role="barbershop_owner", barbershop_id=shop.id),
            User(email="barber-demo@example.invalid", first_name="Demo", last_name="Barber", role="barber", barbershop_id=shop.id),
        ]
        for user in users:
            user.password_hash = hash_password("DemoOnlyChangeMe123")
            user.is_active = True
            user.is_verified = True
        db.add_all(users)
        db.add(Service(
            barbershop_id=shop.id, name="Corte Demo", description="Servicio de ejemplo",
            duration_minutes=30, price=20000, category="haircut", is_active=True,
        ))
        db.commit()
        print("Created disposable demo records in the configured development MySQL database.")
        print("Demo account password: DemoOnlyChangeMe123 (change it before any shared use).")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"Demo seeding failed ({type(exc).__name__}). Check the development MySQL database.")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(seed_database())
