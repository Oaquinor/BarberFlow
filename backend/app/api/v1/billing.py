"""Authenticated owner views of plan status and real tenant usage."""

from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Barbershop, Subscription, SupportTicket, User
from app.schemas.billing import OwnerSubscriptionResponse, SubscriptionUsage
from app.services.audit_service import record_audit
from app.services.subscription_service import count_monthly_appointments
from app.utils.datetime import utc_now_naive
from zoneinfo import ZoneInfoNotFoundError

router = APIRouter(prefix="/billing", tags=["Billing"])
RENEWAL_REQUEST_PREFIX = "[Solicitud de renovación]"


@router.get("/subscription", response_model=OwnerSubscriptionResponse)
def get_owner_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "barbershop_owner" or not current_user.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede consultar la suscripción")
    shop = db.query(Barbershop).filter(
        Barbershop.id == current_user.barbershop_id,
        Barbershop.is_deleted == False,
    ).first()
    if not shop or not shop.subscription_id:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")
    subscription = db.query(Subscription).filter(
        Subscription.id == shop.subscription_id,
        Subscription.is_deleted == False,
    ).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")

    now = utc_now_naive()
    status = subscription.status
    if status == "active" and subscription.current_period_end <= now:
        status = "expired"
    remaining = max(0, ceil((subscription.current_period_end - now).total_seconds() / 86400))
    barber_count = db.query(func.count(User.id)).filter(
        User.barbershop_id == shop.id, User.role == "barber",
        User.is_active == True, User.is_deleted == False,
    ).scalar() or 0
    client_count = db.query(func.count(User.id)).filter(
        User.barbershop_id == shop.id, User.role == "client", User.is_deleted == False,
    ).scalar() or 0
    try:
        appointment_count = count_monthly_appointments(db, shop, now)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise HTTPException(status_code=500, detail="La zona horaria de la barbería no es válida")

    return OwnerSubscriptionResponse(
        plan=subscription.plan,
        status=status,
        currency=shop.currency,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        days_remaining=remaining,
        auto_renew=subscription.auto_renew,
        usage={
            "barbers": SubscriptionUsage(used=int(barber_count), limit=subscription.max_barbers),
            "appointments": SubscriptionUsage(
                used=int(appointment_count), limit=subscription.max_appointments_per_month,
            ),
            "clients": SubscriptionUsage(used=int(client_count), limit=subscription.max_clients),
        },
    )


@router.post("/renewal-request", status_code=201)
def request_subscription_renewal(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create an idempotent support request; never charge or reactivate a tenant."""
    if current_user.role != "barbershop_owner" or not current_user.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede solicitar una renovación")
    shop = db.query(Barbershop).filter(
        Barbershop.id == current_user.barbershop_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop or not shop.subscription_id:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")
    subscription = db.query(Subscription).filter(
        Subscription.id == shop.subscription_id,
        Subscription.is_deleted == False,
    ).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")

    existing = db.query(SupportTicket).filter(
        SupportTicket.barbershop_id == shop.id,
        SupportTicket.message.startswith(RENEWAL_REQUEST_PREFIX),
        SupportTicket.status.in_({"open", "in_progress"}),
        SupportTicket.is_deleted == False,
    ).order_by(SupportTicket.id.desc()).first()
    if existing:
        response.status_code = 200
        return {"success": True, "created": False, "ticket_id": existing.id}

    status = subscription.status
    if status == "active" and subscription.current_period_end <= utc_now_naive():
        status = "expired"
    ticket = SupportTicket(
        barbershop_id=shop.id,
        sender_name=(current_user.full_name or current_user.email)[:120],
        sender_email=current_user.email,
        sender_phone=current_user.phone,
        message=(
            f"{RENEWAL_REQUEST_PREFIX} {shop.name} (ID {shop.id}) solicita información "
            f"para continuar. Plan: {subscription.plan}; estado: {status}; "
            f"fin del periodo: {subscription.current_period_end.isoformat()}. "
            "No se ha recibido ni procesado ningún pago."
        ),
    )
    db.add(ticket)
    db.flush()
    record_audit(
        db, current_user, "subscription.renewal_requested", "support_ticket", ticket.id,
        shop.id, {"plan": subscription.plan, "status": status},
    )
    db.commit()
    return {"success": True, "created": True, "ticket_id": ticket.id}
