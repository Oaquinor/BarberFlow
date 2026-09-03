"""
Onboarding service for barbershop personalization.
"""

from typing import Optional, List, Dict
from datetime import datetime, time
from sqlalchemy.orm import Session

from app.models.barbershop import Barbershop
from app.schemas.onboarding import (
    OnboardingComplete,
    BarbershopProfile,
    DashboardLayoutResponse,
    ContextualMessage
)


class OnboardingService:
    """Service for managing barbershop onboarding and personalization."""

    @staticmethod
    def complete_onboarding(
        db: Session,
        barbershop_id: int,
        data: OnboardingComplete
    ) -> Barbershop:
        """Complete onboarding process and update barbershop profile."""

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()

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

        db.commit()
        db.refresh(barbershop)

        return barbershop

    @staticmethod
    def get_barbershop_profile(db: Session, barbershop_id: int) -> Optional[BarbershopProfile]:
        """Get barbershop profile for frontend."""

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()

        if not barbershop:
            return None

        return BarbershopProfile.from_orm(barbershop)

    @staticmethod
    def get_dashboard_layout(db: Session, barbershop_id: int) -> DashboardLayoutResponse:
        """Get dashboard layout adapted to barbershop's primary goal."""

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()

        if not barbershop or not barbershop.primary_goal:
            # Default layout
            return DashboardLayoutResponse(
                layout_type="default",
                priority_metrics=["appointments", "revenue", "clients"],
                widgets=["calendar", "stats", "performance"],
                greeting_message="👋 Bienvenido al sistema",
                insights=[]
            )

        # Adapt layout based on primary goal
        layouts = {
            "more_clients": {
                "layout_type": "growth",
                "priority_metrics": ["new_clients", "return_rate", "cancellations", "client_satisfaction"],
                "widgets": ["growth_chart", "client_funnel", "retention_tracker", "referral_stats"],
                "greeting_message": "📈 Enfocado en crecimiento de clientes",
                "insights": [
                    "Tus clientes regresan con frecuencia. ¡Sigue así!",
                    "Tip: Ofrece promociones para primeras visitas",
                    "Mantén baja la tasa de cancelaciones"
                ]
            },
            "organization": {
                "layout_type": "organization",
                "priority_metrics": ["upcoming_appointments", "schedule_occupancy", "gaps", "conflicts"],
                "widgets": ["calendar_view", "schedule_optimizer", "reminder_status", "booking_flow"],
                "greeting_message": "📅 Tu agenda organizada",
                "insights": [
                    "Agenda optimizada para hoy",
                    "Todos los recordatorios enviados",
                    "Sin conflictos de horario"
                ]
            },
            "reduce_cancellations": {
                "layout_type": "retention",
                "priority_metrics": ["cancellation_rate", "no_shows", "confirmation_rate", "reminder_effectiveness"],
                "widgets": ["cancellation_tracker", "reminder_dashboard", "client_communication", "penalty_stats"],
                "greeting_message": "🎯 Reduciendo cancelaciones",
                "insights": [
                    "Tasa de cancelación: Baja",
                    "Recordatorios automáticos activos",
                    "Confirma citas 24h antes"
                ]
            },
            "save_time": {
                "layout_type": "efficiency",
                "priority_metrics": ["avg_service_time", "idle_time", "prep_time", "efficiency_score"],
                "widgets": ["time_tracker", "efficiency_meter", "automation_status", "quick_actions"],
                "greeting_message": "⚡ Ahorrando tiempo",
                "insights": [
                    "Tiempo promedio optimizado",
                    "Notificaciones automáticas activas",
                    "Procesos simplificados"
                ]
            },
            "better_service": {
                "layout_type": "quality",
                "priority_metrics": ["client_satisfaction", "service_quality", "feedback_score", "loyalty"],
                "widgets": ["satisfaction_meter", "feedback_dashboard", "service_tracker", "vip_clients"],
                "greeting_message": "⭐ Excelencia en servicio",
                "insights": [
                    "Clientes satisfechos regresan",
                    "Feedback positivo creciendo",
                    "Servicio personalizado activo"
                ]
            },
            "productivity": {
                "layout_type": "performance",
                "priority_metrics": ["services_per_day", "revenue_per_hour", "utilization", "speed"],
                "widgets": ["performance_chart", "productivity_score", "revenue_tracker", "speed_metrics"],
                "greeting_message": "🔥 Maximizando productividad",
                "insights": [
                    "Has mejorado tu velocidad",
                    "Productividad en aumento",
                    "Récord de servicios esta semana"
                ]
            }
        }

        layout_data = layouts.get(barbershop.primary_goal, layouts["more_clients"])

        return DashboardLayoutResponse(**layout_data)

    @staticmethod
    def get_contextual_greeting(db: Session, barbershop_id: int, hour: int) -> ContextualMessage:
        """Get contextual greeting message based on time and barbershop data."""

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()

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
        """Get motivational message based on performance context."""

        # Example contexts: perfect_week, improved_speed, full_schedule, etc.

        messages = {
            "perfect_week": ContextualMessage(
                type="celebration",
                message="💚 ¡Semana perfecta! Sin cancelaciones.",
                icon="💚",
                priority="high"
            ),
            "improved_speed": ContextualMessage(
                type="insight",
                message="⚡ Has mejorado tu velocidad promedio en 8%.",
                icon="⚡",
                priority="medium"
            ),
            "full_schedule": ContextualMessage(
                type="celebration",
                message="👑 Agenda 100% ocupada. ¡Eres imparable!",
                icon="👑",
                priority="high"
            ),
            "high_return_rate": ContextualMessage(
                type="insight",
                message="💙 Tus clientes regresan con frecuencia.",
                icon="💙",
                priority="medium"
            ),
            "record_day": ContextualMessage(
                type="celebration",
                message="🏆 ¡Nuevo récord! Mejor día hasta ahora.",
                icon="🏆",
                priority="high"
            ),
            "consistent": ContextualMessage(
                type="insight",
                message="⭐ Manteniéndote constante. Sigue así.",
                icon="⭐",
                priority="low"
            )
        }

        achievement_type = context.get("achievement_type")
        return messages.get(achievement_type)

    @staticmethod
    def update_barbershop_logo(
        db: Session,
        barbershop_id: int,
        logo_url: str
    ) -> Barbershop:
        """Update barbershop logo URL."""

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()

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
        secondary_color: str
    ) -> Barbershop:
        """Update barbershop brand colors."""

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()

        if not barbershop:
            raise ValueError("Barbershop not found")

        barbershop.primary_color = primary_color
        barbershop.secondary_color = secondary_color
        db.commit()
        db.refresh(barbershop)

        return barbershop
