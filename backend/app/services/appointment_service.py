"""
Appointment service.

Handles appointment business logic.
"""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.user_repository import UserRepository
from app.models.appointment import Appointment
from app.core.exceptions import (
    AppointmentNotFoundError,
    BarberNotFoundError,
    ClientNotFoundError,
    InvalidTimeSlotError,
    AppointmentConflictError,
    InsufficientPermissionsError
)
from app.core.constants import AppointmentStatus
from app.core.logging import get_logger

logger = get_logger(__name__)


class AppointmentService:
    """Handles appointment business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.appointment_repository = AppointmentRepository(db)
        self.user_repository = UserRepository(db)

    async def create_appointment(
        self,
        barbershop_id: int,
        client_id: int,
        barber_id: int,
        scheduled_time: datetime,
        service_type: str,
        estimated_duration: int = 30,
        client_notes: Optional[str] = None
    ) -> Appointment:
        """
        Create new appointment with business validations.

        Args:
            barbershop_id: Barbershop ID
            client_id: Client user ID
            barber_id: Barber user ID
            scheduled_time: Scheduled time
            service_type: Type of service
            estimated_duration: Duration in minutes
            client_notes: Optional notes from client

        Returns:
            Created appointment

        Raises:
            ClientNotFoundError: If client doesn't exist
            BarberNotFoundError: If barber doesn't exist
            InvalidTimeSlotError: If time slot is invalid
            AppointmentConflictError: If barber already has appointment
        """
        # Validate client exists
        client = await self.user_repository.get_by_id(client_id)
        if not client:
            raise ClientNotFoundError(f"Client with ID {client_id} not found")

        # Validate barber exists
        barber = await self.user_repository.get_by_id(barber_id)
        if not barber:
            raise BarberNotFoundError(f"Barber with ID {barber_id} not found")

        # Validate time slot is in the future
        if scheduled_time <= datetime.utcnow():
            raise InvalidTimeSlotError("Appointment time must be in the future")

        # Check barber availability
        is_available = await self.appointment_repository.check_barber_availability(
            barber_id=barber_id,
            scheduled_time=scheduled_time,
            duration=estimated_duration
        )

        if not is_available:
            raise AppointmentConflictError("Barber is not available at this time")

        # Create appointment
        appointment = await self.appointment_repository.create(
            barbershop_id=barbershop_id,
            client_id=client_id,
            barber_id=barber_id,
            scheduled_time=scheduled_time,
            service_type=service_type,
            estimated_duration=estimated_duration,
            client_notes=client_notes,
            status=AppointmentStatus.CONFIRMED
        )

        logger.info(
            f"Appointment created: ID {appointment.id}",
            extra={
                "appointment_id": appointment.id,
                "barbershop_id": barbershop_id,
                "client_id": client_id,
                "barber_id": barber_id
            }
        )

        return appointment

    async def get_appointment(self, appointment_id: int) -> Appointment:
        """
        Get appointment by ID.

        Args:
            appointment_id: Appointment ID

        Returns:
            Appointment instance

        Raises:
            AppointmentNotFoundError: If appointment doesn't exist
        """
        appointment = await self.appointment_repository.get_by_id_with_relations(appointment_id)

        if not appointment:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")

        return appointment

    async def get_barbershop_appointments(
        self,
        barbershop_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[Appointment]:
        """
        Get all appointments for a barbershop.

        Args:
            barbershop_id: Barbershop ID
            skip: Number to skip
            limit: Maximum to return

        Returns:
            List of appointments
        """
        return await self.appointment_repository.get_by_barbershop(
            barbershop_id=barbershop_id,
            skip=skip,
            limit=limit
        )

    async def start_appointment(self, appointment_id: int, barber_id: int) -> Appointment:
        """
        Start an appointment (set status to IN_PROGRESS).

        Args:
            appointment_id: Appointment ID
            barber_id: Barber ID (for permission check)

        Returns:
            Updated appointment

        Raises:
            AppointmentNotFoundError: If appointment doesn't exist
            InsufficientPermissionsError: If barber doesn't own appointment
        """
        appointment = await self.get_appointment(appointment_id)

        # Check if barber owns this appointment
        if appointment.barber_id != barber_id:
            raise InsufficientPermissionsError("You can only start your own appointments")

        # Update status
        appointment = await self.appointment_repository.update(
            appointment_id,
            status=AppointmentStatus.IN_PROGRESS,
            actual_start_time=datetime.utcnow()
        )

        logger.info(f"Appointment started: ID {appointment_id}")

        return appointment

    async def complete_appointment(self, appointment_id: int, barber_id: int) -> Appointment:
        """
        Complete an appointment.

        Args:
            appointment_id: Appointment ID
            barber_id: Barber ID (for permission check)

        Returns:
            Updated appointment

        Raises:
            AppointmentNotFoundError: If appointment doesn't exist
            InsufficientPermissionsError: If barber doesn't own appointment
        """
        appointment = await self.get_appointment(appointment_id)

        # Check if barber owns this appointment
        if appointment.barber_id != barber_id:
            raise InsufficientPermissionsError("You can only complete your own appointments")

        # Update status
        appointment = await self.appointment_repository.update(
            appointment_id,
            status=AppointmentStatus.COMPLETED,
            actual_end_time=datetime.utcnow()
        )

        logger.info(f"Appointment completed: ID {appointment_id}")

        return appointment

    async def cancel_appointment(
        self,
        appointment_id: int,
        cancelled_by: int,
        reason: Optional[str] = None
    ) -> Appointment:
        """
        Cancel an appointment.

        Args:
            appointment_id: Appointment ID
            cancelled_by: User ID who cancelled
            reason: Cancellation reason

        Returns:
            Updated appointment

        Raises:
            AppointmentNotFoundError: If appointment doesn't exist
        """
        appointment = await self.get_appointment(appointment_id)

        # Update status
        appointment = await self.appointment_repository.update(
            appointment_id,
            status=AppointmentStatus.CANCELLED,
            cancelled_by=cancelled_by,
            cancellation_reason=reason
        )

        logger.info(f"Appointment cancelled: ID {appointment_id} by user {cancelled_by}")

        return appointment

    async def reschedule_appointment(
        self,
        appointment_id: int,
        new_scheduled_time: datetime,
        user_id: int
    ) -> Appointment:
        """
        Reschedule an appointment.

        Args:
            appointment_id: Appointment ID
            new_scheduled_time: New scheduled time
            user_id: User ID making the change

        Returns:
            Updated appointment

        Raises:
            AppointmentNotFoundError: If appointment doesn't exist
            InvalidTimeSlotError: If new time is invalid
            AppointmentConflictError: If barber not available
        """
        appointment = await self.get_appointment(appointment_id)

        # Validate new time is in the future
        if new_scheduled_time <= datetime.utcnow():
            raise InvalidTimeSlotError("New appointment time must be in the future")

        # Check barber availability at new time
        is_available = await self.appointment_repository.check_barber_availability(
            barber_id=appointment.barber_id,
            scheduled_time=new_scheduled_time,
            duration=appointment.estimated_duration,
            exclude_appointment_id=appointment_id
        )

        if not is_available:
            raise AppointmentConflictError("Barber is not available at the new time")

        # Update appointment
        appointment = await self.appointment_repository.update(
            appointment_id,
            scheduled_time=new_scheduled_time
        )

        logger.info(f"Appointment rescheduled: ID {appointment_id}")

        return appointment
