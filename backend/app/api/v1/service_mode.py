"""
Service Mode API endpoints.

Handles "Modo En Servicio" - critical real-time appointment tracking.
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.services import ServiceModeService
from app.core.security import get_current_user
from app.models import User

router = APIRouter(prefix="/service-mode", tags=["Service Mode"])


class StartServiceRequest(BaseModel):
    """Request to start a service."""
    appointment_id: int


class FinishServiceRequest(BaseModel):
    """Request to finish a service."""
    appointment_id: int
    barber_notes: Optional[str] = None


@router.post("/start")
def start_service(
    request: StartServiceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Start service mode for an appointment.

    **Critical Functionality: "Iniciar Servicio" button**
    """
    try:
        result = ServiceModeService.start_service(
            db=db,
            appointment_id=request.appointment_id,
            barber_id=current_user.id
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/finish")
def finish_service(
    request: FinishServiceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Finish service mode for an appointment.

    **Critical Functionality: "Finalizar Servicio" button**
    """
    try:
        result = ServiceModeService.finish_service(
            db=db,
            appointment_id=request.appointment_id,
            barber_id=current_user.id,
            barber_notes=request.barber_notes
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/active")
def get_active_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get currently active service for the current barber.

    Returns real-time timer, progress, and alerts.
    """
    try:
        active_service = ServiceModeService.get_active_service(
            db=db,
            barber_id=current_user.id
        )

        if not active_service:
            return {"active": False, "message": "No hay servicio activo"}

        return {"active": True, **active_service}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/next")
def get_next_appointment(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get next scheduled appointment for the current barber."""
    try:
        next_appt = ServiceModeService.get_next_appointment(
            db=db,
            barber_id=current_user.id
        )

        if not next_appt:
            return {"has_next": False, "message": "No hay citas próximas"}

        return {"has_next": True, **next_appt}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/schedule/today")
def get_today_schedule(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get barber's schedule for today with service status."""
    try:
        schedule = ServiceModeService.get_daily_schedule(
            db=db,
            barber_id=current_user.id,
            date=datetime.now()
        )
        return schedule
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/schedule/{date}")
def get_schedule_by_date(
    date: str,  # Format: YYYY-MM-DD
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get barber's schedule for a specific date."""
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
        schedule = ServiceModeService.get_daily_schedule(
            db=db,
            barber_id=current_user.id,
            date=target_date
        )
        return schedule
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
