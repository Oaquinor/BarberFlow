"""
Appointment repository.

Handles data access for Appointment entities.
"""

from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.appointment import Appointment
from app.repositories.base_repository import BaseRepository
from app.core.constants import AppointmentStatus


class AppointmentRepository(BaseRepository[Appointment]):
    """Appointment data access repository."""

    def __init__(self, db: AsyncSession):
        super().__init__(Appointment, db)

    async def get_by_id_with_relations(self, appointment_id: int) -> Optional[Appointment]:
        """
        Get appointment with related entities (client, barber, barbershop).

        Args:
            appointment_id: Appointment ID

        Returns:
            Appointment with relationships loaded
        """
        result = await self.db.execute(
            select(Appointment)
            .options(
                joinedload(Appointment.client),
                joinedload(Appointment.barber),
                joinedload(Appointment.barbershop)
            )
            .where(
                Appointment.id == appointment_id,
                Appointment.is_deleted == False
            )
        )
        return result.scalar_one_or_none()

    async def get_by_barbershop(
        self,
        barbershop_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[Appointment]:
        """
        Get appointments by barbershop.

        Args:
            barbershop_id: Barbershop ID
            skip: Number to skip
            limit: Maximum to return

        Returns:
            List of appointments
        """
        result = await self.db.execute(
            select(Appointment)
            .where(
                Appointment.barbershop_id == barbershop_id,
                Appointment.is_deleted == False
            )
            .order_by(Appointment.scheduled_time.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_client(self, client_id: int) -> List[Appointment]:
        """
        Get appointments by client.

        Args:
            client_id: Client user ID

        Returns:
            List of appointments
        """
        result = await self.db.execute(
            select(Appointment)
            .where(
                Appointment.client_id == client_id,
                Appointment.is_deleted == False
            )
            .order_by(Appointment.scheduled_time.desc())
        )
        return list(result.scalars().all())

    async def get_by_barber(
        self,
        barber_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Appointment]:
        """
        Get appointments by barber with optional date filter.

        Args:
            barber_id: Barber user ID
            start_date: Start date filter
            end_date: End date filter

        Returns:
            List of appointments
        """
        query = select(Appointment).where(
            Appointment.barber_id == barber_id,
            Appointment.is_deleted == False
        )

        if start_date:
            query = query.where(Appointment.scheduled_time >= start_date)
        if end_date:
            query = query.where(Appointment.scheduled_time <= end_date)

        query = query.order_by(Appointment.scheduled_time)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_date(
        self,
        barbershop_id: int,
        target_date: date
    ) -> List[Appointment]:
        """
        Get all appointments for a specific date.

        Args:
            barbershop_id: Barbershop ID
            target_date: Target date

        Returns:
            List of appointments
        """
        start_datetime = datetime.combine(target_date, datetime.min.time())
        end_datetime = datetime.combine(target_date, datetime.max.time())

        result = await self.db.execute(
            select(Appointment)
            .where(
                and_(
                    Appointment.barbershop_id == barbershop_id,
                    Appointment.scheduled_time >= start_datetime,
                    Appointment.scheduled_time <= end_datetime,
                    Appointment.is_deleted == False
                )
            )
            .order_by(Appointment.scheduled_time)
        )
        return list(result.scalars().all())

    async def get_active_appointments(self, barbershop_id: int) -> List[Appointment]:
        """
        Get active appointments (confirmed or in progress).

        Args:
            barbershop_id: Barbershop ID

        Returns:
            List of active appointments
        """
        result = await self.db.execute(
            select(Appointment)
            .where(
                and_(
                    Appointment.barbershop_id == barbershop_id,
                    Appointment.status.in_([
                        AppointmentStatus.CONFIRMED,
                        AppointmentStatus.IN_PROGRESS
                    ]),
                    Appointment.is_deleted == False
                )
            )
            .order_by(Appointment.scheduled_time)
        )
        return list(result.scalars().all())

    async def check_barber_availability(
        self,
        barber_id: int,
        scheduled_time: datetime,
        duration: int,
        exclude_appointment_id: Optional[int] = None
    ) -> bool:
        """
        Check if barber is available at given time.

        Args:
            barber_id: Barber ID
            scheduled_time: Proposed appointment time
            duration: Appointment duration in minutes
            exclude_appointment_id: Appointment ID to exclude (for rescheduling)

        Returns:
            True if available, False otherwise
        """
        end_time = scheduled_time + timedelta(minutes=duration)

        query = select(Appointment).where(
            and_(
                Appointment.barber_id == barber_id,
                Appointment.status.in_([
                    AppointmentStatus.CONFIRMED,
                    AppointmentStatus.IN_PROGRESS
                ]),
                Appointment.scheduled_time < end_time,
                Appointment.is_deleted == False
            )
        )

        if exclude_appointment_id:
            query = query.where(Appointment.id != exclude_appointment_id)

        result = await self.db.execute(query)
        conflicting = list(result.scalars().all())

        return len(conflicting) == 0
