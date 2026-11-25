"""Shared business rules for customer appointment cancellation."""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Appointment, Barbershop, BarberAvailability
from app.services.booking_policy import enforce_public_change_window


def cancel_customer_appointment(
    db: Session,
    shop: Barbershop,
    appointment: Appointment,
    reason: str | None,
    now: datetime,
) -> None:
    """Apply cancellation rules and free the matching slot inside caller transaction."""
    if appointment.barbershop_id != shop.id:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if appointment.status not in {"pending", "confirmed"}:
        raise HTTPException(status_code=409, detail="La cita ya no se puede cancelar")
    if appointment.scheduled_time <= now:
        raise HTTPException(status_code=409, detail="No se puede cancelar una cita que ya comenzó")
    enforce_public_change_window(shop, appointment.scheduled_time, now)

    appointment.status = "cancelled"
    appointment.cancelled_by = appointment.client_id
    appointment.cancellation_reason = reason
    db.query(BarberAvailability).filter(
        BarberAvailability.barbershop_id == shop.id,
        BarberAvailability.barber_id == appointment.barber_id,
        BarberAvailability.slot_start == appointment.scheduled_time,
        BarberAvailability.is_booked == True,
        BarberAvailability.is_deleted == False,
    ).update({BarberAvailability.is_booked: False}, synchronize_session=False)
