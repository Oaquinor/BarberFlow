"""
Appointment Service - Service Mode Extension.

Handles "Modo En Servicio" (Service Mode) functionality.
Critical feature for real-time appointment tracking.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models import Appointment, BarberPerformance, User, Achievement, UserAchievement
from app.core.constants import AppointmentStatus
from app.services.performance_service import PerformanceService
from app.services.achievement_service import AchievementService


class ServiceModeService:
    """Service for managing active service mode (Modo En Servicio)."""

    @staticmethod
    def start_service(
        db: Session,
        appointment_id: int,
        barber_id: int
    ) -> Dict[str, Any]:
        """
        Initiate service mode for an appointment.

        This is the critical "Iniciar Servicio" button functionality.
        """
        # Get appointment
        appointment = db.query(Appointment).filter(
            and_(
                Appointment.id == appointment_id,
                Appointment.barber_id == barber_id,
                Appointment.is_deleted == False
            )
        ).first()

        if not appointment:
            raise ValueError("Appointment not found or you don't have permission")

        # Validate appointment can be started
        if appointment.status not in [AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING]:
            raise ValueError(f"Cannot start appointment with status: {appointment.status}")

        # Update appointment
        appointment.status = AppointmentStatus.IN_PROGRESS
        appointment.actual_start_time = datetime.utcnow()

        db.commit()
        db.refresh(appointment)

        # Get next appointment for alerts
        next_appointment = ServiceModeService.get_next_appointment(db, barber_id)

        return {
            "appointment": {
                "id": appointment.id,
                "client_name": f"{appointment.client.first_name} {appointment.client.last_name}",
                "service_type": appointment.service_type,
                "estimated_duration": appointment.estimated_duration,
                "actual_start_time": appointment.actual_start_time,
                "status": appointment.status
            },
            "timer": {
                "started_at": appointment.actual_start_time,
                "estimated_duration_minutes": appointment.estimated_duration
            },
            "next_appointment": next_appointment,
            "alerts": ServiceModeService._generate_service_alerts(appointment, next_appointment)
        }

    @staticmethod
    def finish_service(
        db: Session,
        appointment_id: int,
        barber_id: int,
        barber_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Finish service mode for an appointment.

        This is the critical "Finalizar Servicio" button functionality.
        """
        # Get appointment
        appointment = db.query(Appointment).filter(
            and_(
                Appointment.id == appointment_id,
                Appointment.barber_id == barber_id,
                Appointment.is_deleted == False
            )
        ).first()

        if not appointment:
            raise ValueError("Appointment not found or you don't have permission")

        # Validate appointment can be finished
        if appointment.status != AppointmentStatus.IN_PROGRESS:
            raise ValueError("Appointment is not in progress")

        # Update appointment
        appointment.status = AppointmentStatus.COMPLETED
        appointment.actual_end_time = datetime.utcnow()
        if barber_notes:
            appointment.barber_notes = barber_notes

        db.commit()
        db.refresh(appointment)

        # Calculate metrics
        actual_duration = appointment.actual_duration
        time_difference = actual_duration - appointment.estimated_duration if actual_duration else 0
        efficiency_percentage = (appointment.estimated_duration / actual_duration * 100) if actual_duration else 100

        # Update daily performance
        PerformanceService.calculate_daily_performance(
            db=db,
            barbershop_id=appointment.barbershop_id,
            barber_id=barber_id,
            target_date=appointment.scheduled_time.date()
        )

        # Check for new achievements
        new_achievements = AchievementService.check_and_award_achievements(
            db=db,
            user_id=barber_id,
            barbershop_id=appointment.barbershop_id,
            trigger_type='appointment_completed',
            context_data={
                "appointment_id": appointment_id,
                "date": appointment.scheduled_time.date().isoformat()
            }
        )

        return {
            "appointment": {
                "id": appointment.id,
                "status": appointment.status,
                "actual_start_time": appointment.actual_start_time,
                "actual_end_time": appointment.actual_end_time,
                "actual_duration_minutes": actual_duration
            },
            "performance": {
                "estimated_duration": appointment.estimated_duration,
                "actual_duration": actual_duration,
                "time_difference": time_difference,
                "efficiency_percentage": round(efficiency_percentage, 2),
                "status": "on_time" if time_difference <= 5 else "exceeded"
            },
            "achievements": [
                {
                    "name": db.query(Achievement).filter(Achievement.id == ua.achievement_id).first().name,
                    "icon": db.query(Achievement).filter(Achievement.id == ua.achievement_id).first().icon,
                    "description": db.query(Achievement).filter(Achievement.id == ua.achievement_id).first().description
                }
                for ua in new_achievements
            ] if new_achievements else [],
            "message": ServiceModeService._generate_completion_message(time_difference, efficiency_percentage)
        }

    @staticmethod
    def get_active_service(
        db: Session,
        barber_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get currently active service for a barber.
        """
        active_appointment = db.query(Appointment).filter(
            and_(
                Appointment.barber_id == barber_id,
                Appointment.status == AppointmentStatus.IN_PROGRESS,
                Appointment.is_deleted == False
            )
        ).first()

        if not active_appointment:
            return None

        # Calculate elapsed time
        elapsed_seconds = (datetime.utcnow() - active_appointment.actual_start_time).total_seconds()
        elapsed_minutes = int(elapsed_seconds / 60)

        # Calculate remaining time
        remaining_minutes = active_appointment.estimated_duration - elapsed_minutes

        # Check if exceeded
        is_exceeded = elapsed_minutes > active_appointment.estimated_duration
        exceeded_by = elapsed_minutes - active_appointment.estimated_duration if is_exceeded else 0

        # Get next appointment
        next_appointment = ServiceModeService.get_next_appointment(db, barber_id)

        return {
            "appointment": {
                "id": active_appointment.id,
                "client_name": f"{active_appointment.client.first_name} {active_appointment.client.last_name}",
                "service_type": active_appointment.service_type,
                "estimated_duration": active_appointment.estimated_duration,
                "actual_start_time": active_appointment.actual_start_time
            },
            "timer": {
                "elapsed_minutes": elapsed_minutes,
                "remaining_minutes": remaining_minutes if not is_exceeded else 0,
                "is_exceeded": is_exceeded,
                "exceeded_by_minutes": exceeded_by,
                "progress_percentage": min((elapsed_minutes / active_appointment.estimated_duration * 100), 100)
            },
            "next_appointment": next_appointment,
            "alerts": ServiceModeService._generate_time_alerts(
                elapsed_minutes, 
                active_appointment.estimated_duration,
                next_appointment
            )
        }

    @staticmethod
    def get_next_appointment(
        db: Session,
        barber_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get the next scheduled appointment for a barber."""
        next_appt = db.query(Appointment).filter(
            and_(
                Appointment.barber_id == barber_id,
                Appointment.scheduled_time > datetime.utcnow(),
                Appointment.status.in_([AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING]),
                Appointment.is_deleted == False
            )
        ).order_by(Appointment.scheduled_time).first()

        if not next_appt:
            return None

        time_until = next_appt.scheduled_time - datetime.utcnow()
        minutes_until = int(time_until.total_seconds() / 60)

        return {
            "id": next_appt.id,
            "client_name": f"{next_appt.client.first_name} {next_appt.client.last_name}",
            "service_type": next_appt.service_type,
            "scheduled_time": next_appt.scheduled_time,
            "minutes_until": minutes_until
        }

    @staticmethod
    def _generate_service_alerts(
        current_appointment: Appointment,
        next_appointment: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Generate alerts when starting a service."""
        alerts = []

        if next_appointment:
            minutes_until_next = next_appointment["minutes_until"]
            if minutes_until_next <= 30:
                alerts.append(f"⚠️ Tienes otra cita en {minutes_until_next} minutos")
            elif minutes_until_next <= 60:
                alerts.append(f"📅 Próxima cita en {minutes_until_next} minutos")

        return alerts

    @staticmethod
    def _generate_time_alerts(
        elapsed_minutes: int,
        estimated_duration: int,
        next_appointment: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Generate alerts during active service."""
        alerts = []

        # Time exceeded alerts
        if elapsed_minutes > estimated_duration:
            exceeded_by = elapsed_minutes - estimated_duration
            alerts.append(f"⚠️ El servicio excede el tiempo estimado por {exceeded_by} minutos")

        # Approaching time limit
        elif elapsed_minutes >= estimated_duration * 0.8:
            remaining = estimated_duration - elapsed_minutes
            alerts.append(f"⏰ {remaining} minutos restantes del tiempo estimado")

        # Next appointment alerts
        if next_appointment:
            minutes_until_next = next_appointment["minutes_until"]
            if minutes_until_next <= 10:
                alerts.append(f"🚨 URGENTE: Próxima cita en {minutes_until_next} minutos")
            elif minutes_until_next <= 20:
                alerts.append(f"⚠️ Próxima cita en {minutes_until_next} minutos")

        return alerts

    @staticmethod
    def _generate_completion_message(
        time_difference: int,
        efficiency_percentage: float
    ) -> str:
        """Generate motivational message upon completion."""
        if time_difference <= 0:
            return "🎯 ¡Excelente! Completaste el servicio antes del tiempo estimado."
        elif time_difference <= 5:
            return "✅ ¡Muy bien! Completaste el servicio en el tiempo estimado."
        elif time_difference <= 10:
            return "⏱️ Servicio completado. El tiempo excedió ligeramente lo estimado."
        else:
            return "⚠️ Servicio completado. Considera optimizar tu tiempo para la próxima cita."

    @staticmethod
    def get_daily_schedule(
        db: Session,
        barber_id: int,
        date: datetime
    ) -> Dict[str, Any]:
        """Get barber's schedule for a specific day with service status."""
        appointments = db.query(Appointment).filter(
            and_(
                Appointment.barber_id == barber_id,
                func.date(Appointment.scheduled_time) == date.date(),
                Appointment.is_deleted == False
            )
        ).order_by(Appointment.scheduled_time).all()

        completed = [a for a in appointments if a.status == AppointmentStatus.COMPLETED]
        in_progress = [a for a in appointments if a.status == AppointmentStatus.IN_PROGRESS]
        upcoming = [a for a in appointments if a.status in [AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING]]

        return {
            "date": date.date(),
            "summary": {
                "total": len(appointments),
                "completed": len(completed),
                "in_progress": len(in_progress),
                "upcoming": len(upcoming),
                "cancelled": len([a for a in appointments if a.status == AppointmentStatus.CANCELLED])
            },
            "appointments": [
                {
                    "id": a.id,
                    "client_name": f"{a.client.first_name} {a.client.last_name}",
                    "service_type": a.service_type,
                    "scheduled_time": a.scheduled_time,
                    "status": a.status,
                    "duration": a.estimated_duration,
                    "actual_duration": a.actual_duration if a.status == AppointmentStatus.COMPLETED else None
                }
                for a in appointments
            ]
        }
