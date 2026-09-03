"""
Performance API endpoints.

Handles barber performance metrics and analytics.
"""

from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import PerformanceService
from app.core.security import get_current_user
from app.models import User

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
        target_date = date.today()

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
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
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
        today = date.today()
        start_date = today - timedelta(days=today.weekday())

    try:
        summary = PerformanceService.get_weekly_summary(
            db=db,
            barbershop_id=current_user.barbershop_id,
            barber_id=barber_id,
            start_date=start_date
        )
        return summary
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
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
        today = date.today()
        year = today.year
        month = today.month

    try:
        summary = PerformanceService.get_monthly_summary(
            db=db,
            barbershop_id=current_user.barbershop_id,
            barber_id=barber_id,
            year=year,
            month=month
        )
        return summary
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/insights/{barber_id}")
def get_performance_insights(
    barber_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get performance insights and recommendations."""
    try:
        insights = PerformanceService.get_performance_insights(
            db=db,
            barbershop_id=current_user.barbershop_id,
            barber_id=barber_id
        )
        return {"insights": insights}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
