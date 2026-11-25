"""Tenant-scoped, explainable analytics endpoints."""

from collections import defaultdict
from datetime import date, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.ai.demand_forecast import DemandForecastService
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Barbershop, OperatingExpense, Payment, RetailSale, User
from app.schemas.analytics import (
    DemandForecastResponse,
    FinancialReportResponse,
    FinancialReportRow,
)
from app.utils.datetime import local_day_start_utc_naive

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

    start_utc = local_day_start_utc_naive(start_date, business_tz)
    end_utc = local_day_start_utc_naive(end_date + timedelta(days=1), business_tz)
    payments = db.query(Payment, User.first_name, User.last_name).join(
        User, User.id == Payment.barber_id,
    ).filter(
        Payment.barbershop_id == shop.id,
        Payment.is_deleted == False,
        Payment.received_at >= start_utc,
        Payment.received_at < end_utc,
    ).order_by(Payment.received_at.asc(), Payment.id.asc()).all()

    sales = db.query(RetailSale).filter(
        RetailSale.barbershop_id == shop.id,
        RetailSale.is_deleted == False,
        RetailSale.sold_at >= start_utc,
        RetailSale.sold_at < end_utc,
    ).order_by(RetailSale.sold_at.asc(), RetailSale.id.asc()).all()

    expenses = db.query(OperatingExpense).filter(
        OperatingExpense.barbershop_id == shop.id,
        OperatingExpense.is_deleted == False,
        OperatingExpense.spent_at >= start_utc,
        OperatingExpense.spent_at < end_utc,
    ).order_by(OperatingExpense.spent_at.asc(), OperatingExpense.id.asc()).all()

    def new_total(label: str) -> dict:
        return {"label": label, "payment_count": 0, "service_revenue_cents": 0,
                "retail_revenue_cents": 0, "retail_sale_count": 0, "tip_cents": 0,
                "expense_cents": 0}

    daily: dict[str, dict] = defaultdict(lambda: new_total(""))
    methods: dict[str, dict] = {}
    barbers: dict[str, dict] = {}
    method_labels = {"cash": "Efectivo", "card": "Tarjeta", "transfer": "Transferencia", "other": "Otro"}
    category_labels = {
        "rent": "Alquiler", "utilities": "Servicios", "payroll": "Nómina",
        "commission": "Comisiones", "supplies": "Insumos", "maintenance": "Mantenimiento",
        "marketing": "Publicidad", "administrative": "Administración", "internet": "Internet",
        "water": "Agua", "electricity": "Electricidad", "other": "Otros",
    }
    service_revenue = retail_revenue = tip_total = 0
    expense_total = 0
    expenses_by_category: dict[str, dict] = {}
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

    for sale in sales:
        local_day = sale.sold_at.replace(tzinfo=timezone.utc).astimezone(business_tz).date().isoformat()
        day_total = daily[local_day]
        day_total["label"] = local_day
        method = sale.payment_method
        methods.setdefault(method, new_total(method_labels.get(method, method)))
        for aggregate in (day_total, methods[method]):
            aggregate["payment_count"] += 1
            aggregate["retail_sale_count"] += 1
            aggregate["retail_revenue_cents"] += sale.total_cents
        retail_revenue += sale.total_cents

    for expense in expenses:
        local_day = expense.spent_at.replace(tzinfo=timezone.utc).astimezone(business_tz).date().isoformat()
        daily[local_day]["label"] = local_day
        daily[local_day]["expense_cents"] += expense.amount_cents
        method = expense.payment_method
        methods.setdefault(method, new_total(method_labels.get(method, method)))
        methods[method]["expense_cents"] += expense.amount_cents
        category = expenses_by_category.setdefault(expense.category, {
            "key": expense.category,
            "label": category_labels.get(expense.category, expense.category),
            "expense_count": 0,
            "amount_cents": 0,
        })
        category["expense_count"] += 1
        category["amount_cents"] += expense.amount_cents
        expense_total += expense.amount_cents

    def rows(values: dict[str, dict]) -> list[FinancialReportRow]:
        return [
            FinancialReportRow(
                key=key,
                **item,
                gross_cents=item["service_revenue_cents"] + item["retail_revenue_cents"] + item["tip_cents"],
                net_after_recorded_expenses_cents=(
                    item["service_revenue_cents"] + item["retail_revenue_cents"]
                    + item["tip_cents"] - item["expense_cents"]
                ),
            )
            for key, item in sorted(values.items())
        ]

    return FinancialReportResponse(
        start_date=start_date,
        end_date=end_date,
        timezone=shop.timezone,
        currency=shop.currency,
        payment_count=len(payments) + len(sales),
        service_payment_count=len(payments),
        service_revenue_cents=service_revenue,
        retail_revenue_cents=retail_revenue,
        retail_sale_count=len(sales),
        tip_cents=tip_total,
        gross_cents=service_revenue + retail_revenue + tip_total,
        expense_count=len(expenses),
        expense_total_cents=expense_total,
        balance_after_recorded_expenses_cents=service_revenue + retail_revenue + tip_total - expense_total,
        expenses_by_category=[item for _, item in sorted(expenses_by_category.items())],
        by_day=rows(daily),
        by_method=rows(methods),
        by_barber=rows(barbers),
    )
