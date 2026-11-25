"""Shared conflict checks for appointment slots."""

from datetime import timedelta

from app.models.appointment import Appointment
from app.models.barber_availability import BarberAvailability
from app.models.barber_availability_block import BarberAvailabilityBlock


def slot_available_for_duration(
    slot: BarberAvailability,
    blocks: list[BarberAvailabilityBlock],
    appointments: list[Appointment],
    duration_minutes: int,
) -> bool:
    """Return whether a service fits within a slot without schedule conflicts."""
    duration = timedelta(minutes=duration_minutes)
    if slot.slot_end - slot.slot_start < duration:
        return False
    service_end = slot.slot_start + duration
    if any(block.starts_at < service_end and block.ends_at > slot.slot_start for block in blocks):
        return False
    return not any(
        appointment.scheduled_time < service_end
        and appointment.scheduled_time + timedelta(minutes=appointment.estimated_duration)
        > slot.slot_start
        for appointment in appointments
    )
