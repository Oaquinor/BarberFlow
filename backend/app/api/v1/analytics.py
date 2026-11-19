"""Tenant-scoped, explainable analytics endpoints."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.ai.demand_forecast import DemandForecastService
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Barbershop, Payment, User
from app.schemas.analytics import (
    DemandForecastResponse,
    FinancialReportResponse,
    FinancialReportRow,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/demand-forecast", response_model=DemandForecastResponse)
def get_demand_forecast(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forecast next-week completed service demand for the authenticated tenant."""
    if current_user.role != "barbershop_owner" or not current_user.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede consultar este pronóstico")
    try:
        return DemandForecastService.forecast(db, current_user.barbershop_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/financial-report", response_model=FinancialReportResponse)
def get_financial_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Summarize actually received payments for the authenticated owner's tenant."""
    if current_user.role != "barbershop_owner" or not current_user.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede consultar este reporte")
    if end_date < start_date or end_date - start_date > timedelta(days=365):
        raise HTTPException(status_code=422, detail="El rango debe ser válido y no superar 366 días")

    shop = db.query(Barbershop).filter(
        Barbershop.id == current_user.barbershop_id,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    try:
        business_tz = ZoneInfo(shop.timezone)
    except (ZoneInfoNotFoundError, TypeError) as exc:
        raise HTTPException(status_code=500, detail="La zona horaria del negocio no es válida") from exc

    start_utc = datetime.combine(start_date, time.min, tzinfo=business_tz).astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=business_tz).astimezone(timezone.utc).replace(tzinfo=None)
    payments = db.query(Payment, User.first_name, User.last_name).join(
        User, User.id == Payment.barber_id,
    ).filter(
        Payment.barbershop_id == shop.id,
        Payment.is_deleted == False,
        Payment.received_at >= start_utc,
        Payment.received_at < end_utc,
    ).order_by(Payment.received_at.asc(), Payment.id.asc()).all()

    def new_total(label: str) -> dict:
        return {"label": label, "payment_count": 0, "service_revenue_cents": 0, "tip_cents": 0}

    daily: dict[str, dict] = defaultdict(lambda: new_total(""))
    methods: dict[str, dict] = {}
    barbers: dict[str, dict] = {}
    method_labels = {"cash": "Efectivo", "card": "Tarjeta", "transfer": "Transferencia", "other": "Otro"}
    service_revenue = tip_total = 0
    for payment, first_name, last_name in payments:
        local_day = payment.received_at.replace(tzinfo=timezone.utc).astimezone(business_tz).date().isoformat()
        day_total = daily[local_day]
        day_total["label"] = local_day
        method = payment.method
        methods.setdefault(method, new_total(method_labels.get(method, method)))
        barber_key = str(payment.barber_id)
        barbers.setdefault(barber_key, new_total(f"{first_name} {last_name}".strip()))
        for aggregate in (day_total, methods[method], barbers[barber_key]):
            aggregate["payment_count"] += 1
            aggregate["service_revenue_cents"] += payment.amount_cents
            aggregate["tip_cents"] += payment.tip_cents
        service_revenue += payment.amount_cents
        tip_total += payment.tip_cents

    def rows(values: dict[str, dict]) -> list[FinancialReportRow]:
        return [
            FinancialReportRow(key=key, **item, gross_cents=item["service_revenue_cents"] + item["tip_cents"])
            for key, item in sorted(values.items())
        ]

    return FinancialReportResponse(
        start_date=start_date,
        end_date=end_date,
        timezone=shop.timezone,
        currency=shop.currency,
        payment_count=len(payments),
        service_revenue_cents=service_revenue,
        tip_cents=tip_total,
        gross_cents=service_revenue + tip_total,
        by_day=rows(daily),
        by_method=rows(methods),
        by_barber=rows(barbers),
    )
