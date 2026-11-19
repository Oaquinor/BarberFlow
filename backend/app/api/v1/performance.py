"""
Performance API endpoints.

Handles barber performance metrics and analytics.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import PerformanceService
from app.api.deps import get_current_user
from app.models import User, Barbershop


def _tenant_today(current_user: User, db: Session) -> date:
    shop = db.query(Barbershop).filter(
        Barbershop.id == current_user.barbershop_id,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    try:
        return datetime.now(timezone.utc).astimezone(ZoneInfo(shop.timezone)).date()
    except (ZoneInfoNotFoundError, TypeError) as exc:
        raise HTTPException(status_code=500, detail="Zona horaria de barbería inválida") from exc


def _authorize_barber_metrics(current_user: User, barber_id: int, db: Session) -> None:
    """Keep performance queries within the authenticated tenant and role."""
    if current_user.role not in {"barber", "barbershop_owner"} or not current_user.barbershop_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    if current_user.role == "barber" and current_user.id != barber_id:
        raise HTTPException(status_code=403, detail="Solo puedes consultar tu rendimiento")
    barber = db.query(User.id).filter(
        User.id == barber_id,
        User.barbershop_id == current_user.barbershop_id,
        User.role == "barber",
        User.is_active == True,
        User.is_deleted == False,
    ).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barbero no encontrado")

router = APIRouter(prefix="/performance", tags=["Performance"])


@router.get("/daily/{barber_id}")
def get_daily_performance(
    barber_id: int,
    target_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get daily performance metrics for a barber."""
    if not target_date:
        target_date = _tenant_today(current_user, db)

    _authorize_barber_metrics(current_user, barber_id, db)

    try:
        performance = PerformanceService.calculate_daily_performance(
            db=db,
            barbershop_id=current_user.barbershop_id,
            barber_id=barber_id,
            target_date=target_date
        )

        return {
            "date": performance.date,
            "appointments_completed": performance.appointments_completed,
            "appointments_cancelled": performance.appointments_cancelled,
            "appointments_no_show": performance.appointments_no_show,
            "total_revenue": performance.total_revenue,
            "total_service_time_minutes": performance.total_service_time_minutes,
            "average_service_time_minutes": performance.average_service_time_minutes,
            "time_efficiency_percentage": performance.time_efficiency_percentage,
            "current_streak": performance.current_streak,
            "best_streak": performance.best_streak
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo calcular el rendimiento diario"
        )


@router.get("/weekly/{barber_id}")
def get_weekly_summary(
    barber_id: int,
    start_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get weekly performance summary."""
    if not start_date:
        # Get current week start (Monday)
        today = _tenant_today(current_user, db)
        start_date = today - timedelta(days=today.weekday())

    _authorize_barber_metrics(current_user, barber_id, db)

    try:
        summary = PerformanceService.get_weekly_summary(
            db=db,
            barbershop_id=current_user.barbershop_id,
            barber_id=barber_id,
            start_date=start_date
        )
        return summary
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo calcular el resumen semanal"
        )


@router.get("/monthly/{barber_id}")
def get_monthly_summary(
    barber_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get monthly performance summary."""
    if not year or not month:
        today = _tenant_today(current_user, db)
        year = today.year
        month = today.month

    if month < 1 or month > 12 or year < 2000 or year > _tenant_today(current_user, db).year + 1:
        raise HTTPException(status_code=422, detail="Periodo no válido")
    _authorize_barber_metrics(current_user, barber_id, db)

    try:
        summary = PerformanceService.get_monthly_summary(
            db=db,
            barbershop_id=current_user.barbershop_id,
            barber_id=barber_id,
            year=year,
            month=month
        )
        return summary
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo calcular el resumen mensual"
        )


@router.get("/insights/{barber_id}")
def get_performance_insights(
    barber_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get performance insights and recommendations."""
    _authorize_barber_metrics(current_user, barber_id, db)
    try:
        insights = PerformanceService.get_performance_insights(
            db=db,
            barbershop_id=current_user.barbershop_id,
            barber_id=barber_id,
            as_of_date=_tenant_today(current_user, db),
        )
        return {"insights": insights}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron generar las recomendaciones"
        )
