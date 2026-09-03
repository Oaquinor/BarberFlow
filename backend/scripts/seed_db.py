"""
Database seeding script.

Creates initial data for development and testing.
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import User, Barbershop, Subscription
from app.core.constants import UserRole, SubscriptionPlan, SubscriptionStatus

settings = get_settings()


async def seed_database():
    """Seed database with initial data."""

    print("🌱 Starting database seeding...")

    # Create async engine
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            # Create subscription
            subscription = Subscription(
                plan=SubscriptionPlan.PROFESSIONAL,
                status=SubscriptionStatus.ACTIVE,
                current_period_start=datetime.utcnow(),
                current_period_end=datetime.utcnow() + timedelta(days=30),
                max_barbers=10,
                max_appointments_per_month=1000,
                max_clients=2000
            )
            session.add(subscription)
            await session.flush()

            # Create barbershop
            barbershop = Barbershop(
                name="King's Barbershop",
                slug="kings-barbershop",
                description="Premium barbershop in the city center",
                email="info@kingsbarbershop.com",
                phone="+1234567890",
                address_line1="123 Main Street",
                city="New York",
                state="NY",
                postal_code="10001",
                country="USA",
                is_active=True,
                is_verified=True,
                subscription_id=subscription.id
            )
            session.add(barbershop)
            await session.flush()

            # Create super admin
            super_admin = User(
                email="admin@kingflow.com",
                password_hash=hash_password("Admin123!"),
                first_name="Super",
                last_name="Admin",
                phone="+1234567890",
                role=UserRole.SUPER_ADMIN,
                is_active=True,
                is_verified=True
            )
            session.add(super_admin)

            # Create barbershop owner
            owner = User(
                email="owner@kingsbarbershop.com",
                password_hash=hash_password("Owner123!"),
                first_name="John",
                last_name="Owner",
                phone="+1234567891",
                role=UserRole.BARBERSHOP_OWNER,
                barbershop_id=barbershop.id,
                is_active=True,
                is_verified=True
            )
            session.add(owner)

            # Create barbers
            barber1 = User(
                email="mike@kingsbarbershop.com",
                password_hash=hash_password("Barber123!"),
                first_name="Mike",
                last_name="Smith",
                phone="+1234567892",
                role=UserRole.BARBER,
                barbershop_id=barbershop.id,
                is_active=True,
                is_verified=True
            )
            session.add(barber1)

            barber2 = User(
                email="david@kingsbarbershop.com",
                password_hash=hash_password("Barber123!"),
                first_name="David",
                last_name="Johnson",
                phone="+1234567893",
                role=UserRole.BARBER,
                barbershop_id=barbershop.id,
                is_active=True,
                is_verified=True
            )
            session.add(barber2)

            # Create test clients
            client1 = User(
                email="client1@example.com",
                password_hash=hash_password("Client123!"),
                first_name="James",
                last_name="Brown",
                phone="+1234567894",
                role=UserRole.CLIENT,
                barbershop_id=barbershop.id,
                is_active=True,
                is_verified=True
            )
            session.add(client1)

            client2 = User(
                email="client2@example.com",
                password_hash=hash_password("Client123!"),
                first_name="Robert",
                last_name="Davis",
                phone="+1234567895",
                role=UserRole.CLIENT,
                barbershop_id=barbershop.id,
                is_active=True,
                is_verified=True
            )
            session.add(client2)

            # Commit all changes
            await session.commit()

            print("✅ Database seeded successfully!")
            print("\n📋 Test Accounts:")
            print("=" * 50)
            print(f"Super Admin: admin@kingflow.com / Admin123!")
            print(f"Owner: owner@kingsbarbershop.com / Owner123!")
            print(f"Barber 1: mike@kingsbarbershop.com / Barber123!")
            print(f"Barber 2: david@kingsbarbershop.com / Barber123!")
            print(f"Client 1: client1@example.com / Client123!")
            print(f"Client 2: client2@example.com / Client123!")
            print("=" * 50)

        except Exception as e:
            print(f"❌ Error seeding database: {e}")
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_database())
