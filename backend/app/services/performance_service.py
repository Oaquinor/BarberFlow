"""
Performance Service.

Handles barber performance tracking, metrics, and analytics.
"""

from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models import BarberPerformance, Appointment, Payment, Barbershop, User
from app.core.constants import AppointmentStatus
from app.utils.datetime import local_day_start_utc_naive


class PerformanceService:
    """Service for performance tracking and analytics."""

    @staticmethod
    def time_efficiency(appointments: list[Appointment]) -> float:
        """Compare estimated to actual time using only completed services with timings."""
        measured = [
            appointment for appointment in appointments
            if appointment.actual_duration is not None and appointment.actual_duration > 0
        ]
        total_actual = sum(appointment.actual_duration for appointment in measured)
        if total_actual <= 0:
            return 0.0
        total_estimated = sum(appointment.estimated_duration for appointment in measured)
        return total_estimated / total_actual * 100

    @staticmethod
    def calculate_daily_performance(
        db: Session,
        barbershop_id: int,
        barber_id: int,
        target_date: date,
        commit: bool = True,
    ) -> BarberPerformance:
        """
        Calculate and save daily performance metrics for a barber.

        This should be called at the end of each day or when an appointment is completed.
        """
        shop = db.query(Barbershop).filter(
            Barbershop.id == barbershop_id,
            Barbershop.is_deleted == False,
        ).first()
        if not shop:
            raise ValueError("Barbershop not found")
        # Serialize daily recomputations per barber. Two checkouts can concern
        # different appointments but still race to create the same daily row.
        barber = db.query(User.id).filter(
            User.id == barber_id,
            User.barbershop_id == barbershop_id,
            User.role == "barber",
            User.is_deleted == False,
        ).with_for_update().first()
        if not barber:
            raise ValueError("Barber not found in barbershop")
        try:
            business_timezone = ZoneInfo(shop.timezone)
        except (ZoneInfoNotFoundError, TypeError) as exc:
            raise ValueError("Barbershop timezone is invalid") from exc
        start_utc = local_day_start_utc_naive(target_date, business_timezone)
        end_utc = local_day_start_utc_naive(target_date + timedelta(days=1), business_timezone)

        # Appointments use UTC-naive timestamps in MySQL; derive business-day bounds in tenant time.
        appointments = db.query(Appointment).filter(
            and_(
                Appointment.barbershop_id == barbershop_id,
                Appointment.barber_id == barber_id,
                Appointment.scheduled_time >= start_utc,
                Appointment.scheduled_time < end_utc,
                Appointment.is_deleted == False
            )
        ).all()

        # Calculate metrics
        completed = [a for a in appointments if a.status == AppointmentStatus.COMPLETED]
        cancelled = [a for a in appointments if a.status == AppointmentStatus.CANCELLED]
        no_show = [a for a in appointments if a.status == AppointmentStatus.NO_SHOW]

        measured = [a for a in completed if a.actual_duration is not None and a.actual_duration > 0]
        total_service_time = sum(a.actual_duration for a in measured)
        avg_service_time = total_service_time / len(measured) if measured else 0
        efficiency = PerformanceService.time_efficiency(completed)

        # Revenue reflects actual collected payments (including tips), not list prices.
        appointment_ids = [appointment.id for appointment in completed]
        total_revenue = sum(
            amount + tip for amount, tip in db.query(Payment.amount_cents, Payment.tip_cents).filter(
                Payment.barbershop_id == barbershop_id,
                Payment.barber_id == barber_id,
                Payment.appointment_id.in_(appointment_ids),
                Payment.is_deleted == False,
            ).all()
        ) if appointment_ids else 0

        # Check if performance record exists
        performance = db.query(BarberPerformance).filter(
            and_(
                BarberPerformance.barbershop_id == barbershop_id,
                BarberPerformance.barber_id == barber_id,
                BarberPerformance.date == target_date
            )
        ).with_for_update().first()

        if not performance:
            performance = BarberPerformance(
                barbershop_id=barbershop_id,
                barber_id=barber_id,
                date=target_date
            )
            db.add(performance)

        # Update metrics
        performance.appointments_completed = len(completed)
        performance.appointments_cancelled = len(cancelled)
        performance.appointments_no_show = len(no_show)
        performance.total_revenue = total_revenue
        performance.total_service_time_minutes = total_service_time
        performance.average_service_time_minutes = avg_service_time
        performance.time_efficiency_percentage = efficiency

        # Update streaks
        PerformanceService._update_streaks(db, barbershop_id, barber_id, target_date, performance)

        if commit:
            db.commit()
            db.refresh(performance)
        else:
            db.flush()

        return performance

    @staticmethod
    def _update_streaks(
        db: Session,
        barbershop_id: int,
        barber_id: int,
        target_date: date,
        current_performance: BarberPerformance
    ):
        """Update streak information for the barber."""
        # Get yesterday's performance
        yesterday = target_date - timedelta(days=1)
        yesterday_performance = db.query(BarberPerformance).filter(
            and_(
                BarberPerformance.barbershop_id == barbershop_id,
                BarberPerformance.barber_id == barber_id,
                BarberPerformance.date == yesterday
            )
        ).first()

        # Check if barber worked today (completed at least 1 appointment)
        worked_today = current_performance.appointments_completed > 0

        if worked_today:
            if yesterday_performance and yesterday_performance.appointments_completed > 0:
                # Continue streak
                current_performance.current_streak = yesterday_performance.current_streak + 1
            else:
                # Start new streak
                current_performance.current_streak = 1

            # Update best streak
            if current_performance.current_streak > (yesterday_performance.best_streak if yesterday_performance else 0):
                current_performance.best_streak = current_performance.current_streak
            elif yesterday_performance:
                current_performance.best_streak = yesterday_performance.best_streak
        else:
            # Didn't work today, reset current streak
            current_performance.current_streak = 0
            if yesterday_performance:
                current_performance.best_streak = yesterday_performance.best_streak

        # Update consecutive days worked
        if yesterday_performance:
            current_performance.consecutive_days_worked = yesterday_performance.consecutive_days_worked + 1 if worked_today else 0
        else:
            current_performance.consecutive_days_worked = 1 if worked_today else 0

    @staticmethod
    def get_weekly_summary(
        db: Session,
        barbershop_id: int,
        barber_id: int,
        start_date: date
    ) -> Dict[str, Any]:
        """Get weekly performance summary."""
        end_date = start_date + timedelta(days=6)

        performances = db.query(BarberPerformance).filter(
            and_(
                BarberPerformance.barbershop_id == barbershop_id,
                BarberPerformance.barber_id == barber_id,
                BarberPerformance.date >= start_date,
                BarberPerformance.date <= end_date
            )
        ).order_by(BarberPerformance.date.asc()).all()

        total_completed = sum(p.appointments_completed for p in performances)
        total_revenue = sum(p.total_revenue for p in performances)
        worked = [p for p in performances if p.appointments_completed > 0]
        avg_efficiency = (
            sum(p.time_efficiency_percentage or 0 for p in worked) / len(worked)
            if worked else 0
        )

        return {
            "start_date": start_date,
            "end_date": end_date,
            "total_appointments": total_completed,
            "total_revenue": total_revenue,
            "average_efficiency": round(avg_efficiency, 2),
            "days_worked": len(worked),
            "current_streak": performances[-1].current_streak if performances else 0,
            "best_streak": max((p.best_streak for p in performances), default=0),
            "daily_breakdown": [
                {
                    "date": p.date,
                    "appointments": p.appointments_completed,
                    "revenue": p.total_revenue,
                    "efficiency": p.time_efficiency_percentage
                }
                for p in performances
            ]
        }

    @staticmethod
    def get_monthly_summary(
        db: Session,
        barbershop_id: int,
        barber_id: int,
        year: int,
        month: int
    ) -> Dict[str, Any]:
        """Get monthly performance summary."""
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        performances = db.query(BarberPerformance).filter(
            and_(
                BarberPerformance.barbershop_id == barbershop_id,
                BarberPerformance.barber_id == barber_id,
                BarberPerformance.date >= start_date,
                BarberPerformance.date <= end_date
            )
        ).order_by(BarberPerformance.date.asc()).all()

        total_completed = sum(p.appointments_completed for p in performances)
        total_revenue = sum(p.total_revenue for p in performances)
        total_cancelled = sum(p.appointments_cancelled for p in performances)
        total_no_show = sum(p.appointments_no_show for p in performances)
        worked = [p for p in performances if p.appointments_completed > 0]

        return {
            "year": year,
            "month": month,
            "total_appointments": total_completed,
            "total_revenue": total_revenue,
            "total_cancelled": total_cancelled,
            "total_no_show": total_no_show,
            "days_worked": len(worked),
            "best_streak": max((p.best_streak for p in performances), default=0),
            "average_daily_appointments": round(total_completed / len(worked), 2) if worked else 0,
        }

    @staticmethod
    def get_performance_insights(
        db: Session,
        barbershop_id: int,
        barber_id: int,
        as_of_date: Optional[date] = None,
    ) -> List[str]:
        """
        Generate performance insights and recommendations.

        Returns motivational messages and actionable insights.
        """
        insights = []

        # Get last 30 days of data
        today = as_of_date or date.today()
        thirty_days_ago = today - timedelta(days=30)
        recent_performances = db.query(BarberPerformance).filter(
            and_(
                BarberPerformance.barbershop_id == barbershop_id,
                BarberPerformance.barber_id == barber_id,
                BarberPerformance.date >= thirty_days_ago,
                BarberPerformance.date <= today,
            )
        ).order_by(BarberPerformance.date.asc()).all()

        if not recent_performances:
            return ["¡Comienza tu viaje! Completa tu primera cita para ver tus estadísticas."]

        # Current streak
        current_streak = recent_performances[-1].current_streak if recent_performances else 0
        if current_streak >= 7:
            insights.append(f"🔥 ¡Increíble! Llevas {current_streak} días consecutivos trabajando.")
        elif current_streak >= 3:
            insights.append(f"💪 Llevas {current_streak} días consecutivos. ¡Sigue así!")

        # Best performance day
        best_day = max(recent_performances, key=lambda p: p.appointments_completed, default=None)
        if best_day and best_day.appointments_completed > 0:
            insights.append(f"⭐ Tu mejor día fue el {best_day.date.strftime('%d/%m')}: {best_day.appointments_completed} citas completadas.")

        # Efficiency trend
        recent_work_days = [p for p in recent_performances if p.appointments_completed > 0][-7:]
        if recent_work_days:
            avg_efficiency = sum(p.time_efficiency_percentage or 0 for p in recent_work_days) / len(recent_work_days)
            if avg_efficiency >= 90:
                insights.append("🎯 Tu eficiencia de tiempo es excelente. ¡Sigue optimizando!")
            elif avg_efficiency < 70:
                insights.append("⏱️ Hay oportunidad de mejorar tu tiempo promedio de servicio.")

        # Revenue insight
        total_revenue = sum(p.total_revenue for p in recent_performances)
        if total_revenue > 0:
            currency = db.query(Barbershop.currency).filter(Barbershop.id == barbershop_id).scalar() or "USD"
            insights.append(f"💰 Has generado {currency} {total_revenue / 100:.2f} en los últimos 30 días.")

        # Cancellation rate
        total_completed = sum(p.appointments_completed for p in recent_performances)
        total_cancelled = sum(p.appointments_cancelled for p in recent_performances)
        if total_completed + total_cancelled > 0:
            cancellation_rate = (total_cancelled / (total_completed + total_cancelled)) * 100
            if cancellation_rate > 20:
                insights.append(f"⚠️ Tu tasa de cancelación es del {cancellation_rate:.1f}%. Considera implementar confirmaciones.")

        return insights if insights else ["✨ ¡Todo marcha bien! Sigue brindando excelente servicio."]
