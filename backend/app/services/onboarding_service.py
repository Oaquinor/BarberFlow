"""
Onboarding service for barbershop personalization.
"""

from typing import Optional, Dict
from datetime import datetime, time, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.barbershop import Barbershop
from app.models.appointment import Appointment
from app.schemas.onboarding import (
    OnboardingComplete,
    BarbershopProfile,
    DashboardLayoutResponse,
    ContextualMessage
)


class OnboardingService:
    """Service for managing barbershop onboarding and personalization."""

    @staticmethod
    def _message_for_appointment_counts(status_counts: Dict[str, int]) -> ContextualMessage:
        total = sum(status_counts.values())
        completed = status_counts.get("completed", 0)
        cancelled = status_counts.get("cancelled", 0)
        if total == 0:
            return ContextualMessage(
                type="insight", message="Aún no hay citas en los últimos 30 días. Comparte tu enlace para recibir reservas.",
                icon="📅", priority="low",
            )
        if cancelled and (cancelled / total) >= 0.2:
            rate = round(cancelled / total * 100)
            return ContextualMessage(
                type="warning", message=f"Se cancelaron {cancelled} de {total} citas en los últimos 30 días ({rate} %). Revisa los motivos registrados.",
                icon="⚠️", priority="medium",
            )
        return ContextualMessage(
            type="celebration" if completed else "insight",
            message=f"En los últimos 30 días se completaron {completed} de {total} citas.",
            icon="⭐" if completed else "📅", priority="low",
        )

    @staticmethod
    def complete_onboarding(
        db: Session,
        barbershop_id: int,
        data: OnboardingComplete,
        commit: bool = True,
    ) -> Barbershop:
        """Complete onboarding process and update barbershop profile."""

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id, Barbershop.is_deleted == False).first()

        if not barbershop:
            raise ValueError("Barbershop not found")

        # Update barbershop with onboarding data
        barbershop.name = data.barbershop_name
        barbershop.primary_color = data.primary_color
        barbershop.secondary_color = data.secondary_color
        barbershop.style = data.style
        barbershop.primary_goal = data.primary_goal
        barbershop.team_size = data.team_size
        barbershop.avg_service_duration = data.avg_service_duration
        barbershop.personality = data.personality
        barbershop.onboarding_completed = True

        # Parse and set business hours
        opening_parts = data.opening_time.split(':')
        closing_parts = data.closing_time.split(':')
        barbershop.opening_time = time(int(opening_parts[0]), int(opening_parts[1]))
        barbershop.closing_time = time(int(closing_parts[0]), int(closing_parts[1]))

        if commit:
            db.commit()
            db.refresh(barbershop)
        else:
            db.flush()

        return barbershop

    @staticmethod
    def get_barbershop_profile(db: Session, barbershop_id: int) -> Optional[BarbershopProfile]:
        """Get barbershop profile for frontend."""

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id, Barbershop.is_deleted == False).first()

        if not barbershop:
            return None

        return BarbershopProfile.model_validate(barbershop)

    @staticmethod
    def get_dashboard_layout(db: Session, barbershop_id: int) -> DashboardLayoutResponse:
        """Get dashboard layout adapted to barbershop's primary goal."""

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id, Barbershop.is_deleted == False).first()

        if not barbershop or not barbershop.primary_goal:
            # Default layout
            return DashboardLayoutResponse(
                layout_type="default",
                priority_metrics=["appointments", "revenue", "clients"],
                widgets=["calendar", "stats", "performance"],
                greeting_message="👋 Bienvenido al sistema",
                insights=["Completa la configuración del negocio para adaptar este panel a tus objetivos."]
            )

        # Adapt layout based on primary goal
        layouts = {
            "more_clients": {
                "layout_type": "growth",
                "priority_metrics": ["new_clients", "return_rate", "cancellations", "client_satisfaction"],
                "widgets": ["growth_chart", "client_funnel", "retention_tracker", "referral_stats"],
                "greeting_message": "📈 Enfocado en crecimiento de clientes",
                "insights": [
                    "Revisa qué servicios atraen nuevos clientes antes de planificar promociones.",
                    "Consulta el historial de visitas para identificar oportunidades de seguimiento.",
                    "Mantén actualizado el catálogo y los horarios disponibles."
                ]
            },
            "organization": {
                "layout_type": "organization",
                "priority_metrics": ["upcoming_appointments", "schedule_occupancy", "gaps", "conflicts"],
                "widgets": ["calendar_view", "schedule_optimizer", "reminder_status", "booking_flow"],
                "greeting_message": "📅 Tu agenda organizada",
                "insights": [
                    "Revisa las citas pendientes y confirma los cambios de horario.",
                    "Mantén actualizada la disponibilidad de cada barbero.",
                    "Usa el cierre diario para conciliar los cobros registrados."
                ]
            },
            "reduce_cancellations": {
                "layout_type": "retention",
                "priority_metrics": ["cancellation_rate", "no_shows", "confirmation_rate", "reminder_effectiveness"],
                "widgets": ["cancellation_tracker", "reminder_dashboard", "client_communication", "penalty_stats"],
                "greeting_message": "🎯 Reduciendo cancelaciones",
                "insights": [
                    "Revisa las citas pendientes con anticipación y confirma con tus clientes.",
                    "Registra los motivos de cancelación para detectar patrones.",
                    "Mantén clara la política de cancelación en la página pública."
                ]
            },
            "save_time": {
                "layout_type": "efficiency",
                "priority_metrics": ["avg_service_time", "idle_time", "prep_time", "efficiency_score"],
                "widgets": ["time_tracker", "efficiency_meter", "automation_status", "quick_actions"],
                "greeting_message": "⚡ Ahorrando tiempo",
                "insights": [
                    "Registra el inicio y el fin de cada servicio para medir su duración.",
                    "Configura duraciones realistas en el catálogo de servicios.",
                    "Agrupa las citas para reducir espacios vacíos en la agenda."
                ]
            },
            "better_service": {
                "layout_type": "quality",
                "priority_metrics": ["client_satisfaction", "service_quality", "feedback_score", "loyalty"],
                "widgets": ["satisfaction_meter", "feedback_dashboard", "service_tracker", "vip_clients"],
                "greeting_message": "⭐ Excelencia en servicio",
                "insights": [
                    "Solicita comentarios a tus clientes después de cada visita.",
                    "Revisa las notas de citas anteriores para personalizar la atención.",
                    "Mantén registrados los servicios preferidos de cada cliente."
                ]
            },
            "productivity": {
                "layout_type": "performance",
                "priority_metrics": ["services_per_day", "revenue_per_hour", "utilization", "speed"],
                "widgets": ["performance_chart", "productivity_score", "revenue_tracker", "speed_metrics"],
                "greeting_message": "🔥 Maximizando productividad",
                "insights": [
                    "Compara servicios completados y horas trabajadas por semana.",
                    "Revisa los periodos de mayor demanda antes de ajustar horarios.",
                    "Completa los cobros al finalizar cada servicio para conciliar la caja."
                ]
            }
        }

        layout_data = layouts.get(barbershop.primary_goal, layouts["more_clients"])

        return DashboardLayoutResponse(**layout_data)

    @staticmethod
    def get_contextual_greeting(db: Session, barbershop_id: int, hour: int) -> ContextualMessage:
        """Get contextual greeting message based on time and barbershop data."""

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id, Barbershop.is_deleted == False).first()

        if not barbershop:
            return ContextualMessage(
                type="greeting",
                message="👋 Bienvenido",
                icon="👋",
                priority="low"
            )

        # Time-based greetings
        if hour < 12:
            time_greeting = "☀️ Buenos días"
        elif hour < 18:
            time_greeting = "🌤️ Buenas tardes"
        else:
            time_greeting = "🌙 Buenas noches"

        # Personalized with barbershop name
        message = f"{time_greeting}, {barbershop.name}"

        return ContextualMessage(
            type="greeting",
            message=message,
            icon=time_greeting.split()[0],
            priority="medium"
        )

    @staticmethod
    def get_motivational_message(
        db: Session,
        barbershop_id: int,
        context: Dict
    ) -> Optional[ContextualMessage]:
        """Return a short message based on appointment facts, never caller-supplied claims."""
        shop = db.query(Barbershop).filter(
            Barbershop.id == barbershop_id,
            Barbershop.is_deleted == False,
        ).first()
        if not shop:
            return None
        try:
            ZoneInfo(shop.timezone)
        except (ZoneInfoNotFoundError, TypeError):
            return ContextualMessage(
                type="warning", message="Configura una zona horaria válida para consultar tus métricas.",
                icon="⚠️", priority="medium",
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        start = now - timedelta(days=30)
        status_counts = dict(db.query(Appointment.status, func.count(Appointment.id)).filter(
            Appointment.barbershop_id == barbershop_id,
            Appointment.scheduled_time >= start,
            Appointment.scheduled_time < now,
            Appointment.is_deleted == False,
        ).group_by(Appointment.status).all())
        return OnboardingService._message_for_appointment_counts(status_counts)

    @staticmethod
    def update_barbershop_logo(
        db: Session,
        barbershop_id: int,
        logo_url: str
    ) -> Barbershop:
        """Update barbershop logo URL."""

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id, Barbershop.is_deleted == False).first()

        if not barbershop:
            raise ValueError("Barbershop not found")

        barbershop.logo_url = logo_url
        db.commit()
        db.refresh(barbershop)

        return barbershop

    @staticmethod
    def update_brand_colors(
        db: Session,
        barbershop_id: int,
        primary_color: str,
        secondary_color: str,
        commit: bool = True,
    ) -> Barbershop:
        """Update barbershop brand colors."""

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id, Barbershop.is_deleted == False).first()

        if not barbershop:
            raise ValueError("Barbershop not found")

        barbershop.primary_color = primary_color
        barbershop.secondary_color = secondary_color
        if commit:
            db.commit()
            db.refresh(barbershop)
        else:
            db.flush()

        return barbershop
