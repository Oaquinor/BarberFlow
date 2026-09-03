"""
Create super admin user script.

Run this script to create a super admin user.
"""

import asyncio
import sys
from getpass import getpass

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import User
from app.core.constants import UserRole

settings = get_settings()


async def create_super_admin():
    """Create super admin user interactively."""

    print("=" * 50)
    print("CREATE SUPER ADMIN USER")
    print("=" * 50)

    # Get user input
    email = input("Email: ").strip()
    if not email:
        print("❌ Email is required")
        sys.exit(1)

    first_name = input("First Name: ").strip()
    if not first_name:
        print("❌ First name is required")
        sys.exit(1)

    last_name = input("Last Name: ").strip()
    if not last_name:
        print("❌ Last name is required")
        sys.exit(1)

    phone = input("Phone (optional): ").strip() or None

    password = getpass("Password: ")
    if len(password) < 8:
        print("❌ Password must be at least 8 characters")
        sys.exit(1)

    password_confirm = getpass("Confirm Password: ")
    if password != password_confirm:
        print("❌ Passwords don't match")
        sys.exit(1)

    # Create engine and session
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            # Check if user already exists
            from sqlalchemy import select
            result = await session.execute(
                select(User).where(User.email == email)
            )
            existing_user = result.scalar_one_or_none()

            if existing_user:
                print(f"❌ User with email {email} already exists")
                sys.exit(1)

            # Create super admin
            admin = User(
                email=email,
                password_hash=hash_password(password),
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role=UserRole.SUPER_ADMIN,
                is_active=True,
                is_verified=True
            )

            session.add(admin)
            await session.commit()

            print("\n✅ Super admin created successfully!")
            print(f"Email: {email}")
            print(f"Role: {UserRole.SUPER_ADMIN}")

        except Exception as e:
            print(f"\n❌ Error creating super admin: {e}")
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_super_admin())
