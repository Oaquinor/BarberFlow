"""
User repository.

Handles data access for User entities.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    """User data access repository."""

    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email.

        Args:
            email: User email

        Returns:
            User instance or None
        """
        result = await self.db.execute(
            select(User).where(
                User.email == email,
                User.is_deleted == False
            )
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Optional[User]:
        """
        Get user by phone.

        Args:
            phone: User phone number

        Returns:
            User instance or None
        """
        result = await self.db.execute(
            select(User).where(
                User.phone == phone,
                User.is_deleted == False
            )
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        """
        Check if email already exists.

        Args:
            email: Email to check

        Returns:
            True if exists, False otherwise
        """
        user = await self.get_by_email(email)
        return user is not None

    async def get_by_barbershop(self, barbershop_id: int) -> list[User]:
        """
        Get all users in a barbershop.

        Args:
            barbershop_id: Barbershop ID

        Returns:
            List of users
        """
        result = await self.db.execute(
            select(User).where(
                User.barbershop_id == barbershop_id,
                User.is_deleted == False
            )
        )
        return list(result.scalars().all())

    async def get_barbers_by_barbershop(self, barbershop_id: int) -> list[User]:
        """
        Get all barbers in a barbershop.

        Args:
            barbershop_id: Barbershop ID

        Returns:
            List of barber users
        """
        result = await self.db.execute(
            select(User).where(
                User.barbershop_id == barbershop_id,
                User.role == "barber",
                User.is_active == True,
                User.is_deleted == False
            )
        )
        return list(result.scalars().all())
