"""Seed disposable demo records in a development environment only."""

import argparse
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Barbershop, Service, Subscription, User
from app.models.barber_availability import BarberAvailability


DEMO_SHOP = "kings-barbershop-demo"


def seed_database() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-demo-data", action="store_true")
    args = parser.parse_args()
    development_only = settings.ENVIRONMENT.lower() == "development"
    if not development_only or not args.allow_demo_data:
        parser.error(
            "Demo seeding requires ENVIRONMENT=development and "
            "--allow-demo-data"
        )
    confirmation = input(
        f"Type {DEMO_SHOP} to create disposable demo accounts: "
    ).strip()
    if confirmation != DEMO_SHOP:
        print("Cancelled.")
        return 1

    db = SessionLocal()
    try:
        existing_shop = db.query(Barbershop.id).filter(
            Barbershop.slug == DEMO_SHOP
        ).first()
        if existing_shop:
            print(
                "Demo barber shop already exists; refusing to modify "
                "existing records."
            )
            return 1

        now = datetime.utcnow()
        subscription = Subscription(
            plan="professional", status="active", current_period_start=now,
            current_period_end=now + timedelta(days=30), max_barbers=10,
            max_appointments_per_month=1000, max_clients=2000,
            auto_renew=False,
        )
        db.add(subscription)
        db.flush()
        shop = Barbershop(
            name="King's Barbershop Demo", slug=DEMO_SHOP,
            email="demo-shop@example.com", phone="8095550100",
            description=(
                "Una barbería de demostración para probar reservas, servicios "
                "y la experiencia pública de KingFlow."
            ),
            address_line1="Calle Demo 1", city="Santo Domingo",
            state="Distrito Nacional", postal_code="10101", country="DO",
            timezone="America/Santo_Domingo",
            currency="DOP", subscription_id=subscription.id, is_active=True,
            is_verified=True, onboarding_completed=True,
            primary_color="#9A6A3A", secondary_color="#292521",
            public_theme="light",
            style="modern", personality="professional",
            primary_goal="more_clients",
            team_size=1, avg_service_duration=40,
            opening_time=time(9, 0), closing_time=time(18, 0),
            booking_questions=["Estilo buscado", "Acabado preferido"],
        )
        db.add(shop)
        db.flush()

        barber = User(
            email="barber-demo@example.com", first_name="Demo",
            last_name="Barber",
            role="barber", barbershop_id=shop.id,
        )
        users = [
            User(
                email="admin-demo@example.com", first_name="Demo",
                last_name="Admin", role="super_admin",
            ),
            User(
                email="owner-demo@example.com", first_name="Demo",
                last_name="Owner", role="barbershop_owner",
                barbershop_id=shop.id,
            ),
            barber,
        ]
        for user in users:
            user.password_hash = hash_password("DemoOnlyChangeMe123")
            user.is_active = True
            user.is_verified = True
        db.add_all(users)
        db.flush()
        db.add_all([
            Service(
                barbershop_id=shop.id, name="Corte clásico",
                description="Corte personalizado con acabado y peinado.",
                duration_minutes=30, price=80000, category="haircut",
                display_order=1, is_active=True,
            ),
            Service(
                barbershop_id=shop.id, name="Perfilado de barba",
                description="Diseño, perfilado y cuidado de barba.",
                duration_minutes=30, price=50000, category="beard",
                display_order=2, is_active=True,
            ),
            Service(
                barbershop_id=shop.id, name="Corte y barba",
                description="Un servicio completo de corte y barba.",
                duration_minutes=60, price=120000, category="combo",
                display_order=3, is_active=True,
            ),
        ])
        db.flush()

        # Create real future booking slots in the barber shop's timezone. They
        # are persisted in UTC-naive form, matching the MySQL scheduling model.
        business_timezone = ZoneInfo(shop.timezone)
        local_now = datetime.now(business_timezone)
        availability = []
        for day_offset in range(31):
            local_day = (local_now + timedelta(days=day_offset)).date()
            if local_day.weekday() == 6:  # The demo shop closes on Sundays.
                continue
            for hour in range(9, 18):
                for minute in (0, 30):
                    local_start = datetime.combine(
                        local_day, time(hour, minute), business_timezone
                    )
                    if local_start <= local_now:
                        continue
                    slot_start = local_start.astimezone(
                        timezone.utc
                    ).replace(tzinfo=None)
                    closing = datetime.combine(
                        local_day, time(18, 0), business_timezone
                    )
                    local_end = min(
                        local_start + timedelta(minutes=60), closing
                    )
                    slot_end = local_end.astimezone(
                        timezone.utc
                    ).replace(tzinfo=None)
                    availability.append(BarberAvailability(
                        barbershop_id=shop.id, barber_id=barber.id,
                        slot_start=slot_start, slot_end=slot_end,
                    ))
        db.add_all(availability)
        db.commit()
        print(
            "Created disposable demo records in development MySQL "
            f"({len(availability)} future slots)."
        )
        print("Owner login: owner-demo@example.com")
        print("Barber login: barber-demo@example.com")
        print("Super admin login: admin-demo@example.com")
        print(
            "Password for all demo accounts: DemoOnlyChangeMe123 "
            "(change before shared use)."
        )
        return 0
    except Exception as exc:
        db.rollback()
        print(
            f"Demo seeding failed ({type(exc).__name__}). "
            "Check the development MySQL database."
        )
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(seed_database())
