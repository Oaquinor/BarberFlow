"""
Appointment endpoints.

Handles appointment CRUD operations and actions.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from app.api.deps import DatabaseSession, CurrentUser
from app.schemas.common import StandardResponse
from app.services.appointment_service import AppointmentService
from app.core.security import check_barbershop_access

router = APIRouter(prefix="/appointments", tags=["Appointments"])


class AppointmentCreate(BaseModel):
    """Schema for creating appointment."""
    client_id: int = Field(..., description="Client user ID")
    barber_id: int = Field(..., description="Barber user ID")
    scheduled_time: datetime = Field(..., description="Scheduled appointment time")
    service_type: str = Field(..., description="Type of service")
    estimated_duration: int = Field(30, ge=15, le=120, description="Duration in minutes")
    client_notes: Optional[str] = Field(None, max_length=500, description="Client notes")


@router.post(
    "",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create appointment"
)
async def create_appointment(
    data: AppointmentCreate,
    current_user: CurrentUser,
    db: DatabaseSession
) -> StandardResponse:
    """Create new appointment."""
    if not current_user.barbershop_id:
        return StandardResponse(
            success=False,
            message="User must belong to a barbershop",
            errors=["No barbershop associated with user"]
        )

    service = AppointmentService(db)
    appointment = await service.create_appointment(
        barbershop_id=current_user.barbershop_id,
        client_id=data.client_id,
        barber_id=data.barber_id,
        scheduled_time=data.scheduled_time,
        service_type=data.service_type,
        estimated_duration=data.estimated_duration,
        client_notes=data.client_notes
    )

    return StandardResponse(
        success=True,
        message="Appointment created successfully",
        data={
            "id": appointment.id,
            "barbershop_id": appointment.barbershop_id,
            "scheduled_time": appointment.scheduled_time.isoformat(),
            "status": appointment.status
        }
    )


@router.get(
    "/{appointment_id}",
    response_model=StandardResponse,
    summary="Get appointment"
)
async def get_appointment(
    appointment_id: int,
    current_user: CurrentUser,
    db: DatabaseSession
) -> StandardResponse:
    """Get appointment by ID."""
    service = AppointmentService(db)
    appointment = await service.get_appointment(appointment_id)
    check_barbershop_access(current_user, appointment.barbershop_id)

    return StandardResponse(
        success=True,
        message="Appointment retrieved",
        data={
            "id": appointment.id,
            "scheduled_time": appointment.scheduled_time.isoformat(),
            "status": appointment.status
        }
    )


@router.post(
    "/{appointment_id}/start",
    response_model=StandardResponse,
    summary="Start appointment"
)
async def start_appointment(
    appointment_id: int,
    current_user: CurrentUser,
    db: DatabaseSession
) -> StandardResponse:
    """Start appointment."""
    service = AppointmentService(db)
    appointment = await service.start_appointment(appointment_id, current_user.id)

    return StandardResponse(
        success=True,
        message="Appointment started",
        data={"id": appointment.id, "status": appointment.status}
    )


@router.post(
    "/{appointment_id}/complete",
    response_model=StandardResponse,
    summary="Complete appointment"
)
async def complete_appointment(
    appointment_id: int,
    current_user: CurrentUser,
    db: DatabaseSession
) -> StandardResponse:
    """Complete appointment."""
    service = AppointmentService(db)
    appointment = await service.complete_appointment(appointment_id, current_user.id)

    return StandardResponse(
        success=True,
        message="Appointment completed",
        data={"id": appointment.id, "status": appointment.status}
    )
