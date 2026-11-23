"""Platform administration and support endpoints."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import get_db
from app.core.constants import CommissionStatus
from app.models import (
    Affiliate,
    Appointment,
    AuditLog,
    Barbershop,
    Commission,
    Payment,
    RefreshSession,
    Subscription,
    SubscriptionPayment,
    SupportTicket,
    User,
    UserFeatureFlag,
)
from app.schemas.platform import (
    AdminAffiliateCreateRequest,
    AdminCommissionPaymentRequest,
    AdminStatusUpdateRequest,
    AdminSubscriptionPaymentRequest,
    AdminSubscriptionResponse,
    AdminSubscriptionUpdateRequest,
    AdminSupportTicketStatusRequest,
    AdminTenantItem,
    AdminTenantsResponse,
    AdminUserFeatureFlagRequest,
    AdminUserItem,
    AdminUsersResponse,
    AdminUserSupportToggleRequest,
)
from app.services.affiliate_service import AffiliateService
from app.utils.datetime import utc_now_naive
from app.api.v1.endpoints.common import _apply_plan_limits, _audit, _get_current_user, _normalize_phone

router = APIRouter(tags=["platform"])

@router.get("/admin/support/tickets")
def admin_list_support_tickets(
    status: Optional[str] = Query(None, pattern=r"^(open|in_progress|resolved|closed)$"),
    barbershop_id: Optional[int] = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo el superadministrador puede consultar soporte")
    query = db.query(SupportTicket).filter(SupportTicket.is_deleted == False)
    if status:
        query = query.filter(SupportTicket.status == status)
    if barbershop_id is not None:
        query = query.filter(SupportTicket.barbershop_id == barbershop_id)
    total = query.order_by(None).count()
    tickets = (
        query.order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc())
        .offset(offset).limit(limit).all()
    )
    return {"items": [{
        "id": ticket.id,
        "barbershop_id": ticket.barbershop_id,
        "barbershop_name": ticket.barbershop.name if ticket.barbershop else "Plataforma",
        "name": ticket.sender_name,
        "email": ticket.sender_email,
        "phone": ticket.sender_phone,
        "message": ticket.message,
        "status": ticket.status,
        "notification_sent": ticket.notification_sent,
        "created_at": ticket.created_at.isoformat(),
    } for ticket in tickets], "total": total, "limit": limit, "offset": offset}

@router.put("/admin/support/tickets/{ticket_id}/status")
def admin_update_support_ticket_status(
    ticket_id: int,
    data: AdminSupportTicketStatusRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo el superadministrador puede gestionar soporte")
    ticket = db.query(SupportTicket).filter(
        SupportTicket.id == ticket_id,
        SupportTicket.is_deleted == False,
    ).with_for_update().first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Solicitud de soporte no encontrada")
    previous = ticket.status
    ticket.status = data.status
    _audit(db, admin, "support.ticket_status_changed", "support_ticket", ticket.id,
           ticket.barbershop_id, {"previous": previous, "status": ticket.status})
    db.commit()
    return {"success": True, "ticket_id": ticket.id, "status": ticket.status}

@router.get("/admin/overview")
def admin_overview(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    now = utc_now_naive()
    month_start = datetime(now.year, now.month, 1)
    next_month = datetime(now.year + 1, 1, 1) if now.month == 12 else datetime(now.year, now.month + 1, 1)
    tenant_count = db.query(func.count(Barbershop.id)).filter(Barbershop.is_deleted == False).scalar() or 0
    active_tenant_count = db.query(func.count(Barbershop.id)).filter(
        Barbershop.is_deleted == False, Barbershop.is_active == True,
    ).scalar() or 0
    active_user_count = db.query(func.count(User.id)).filter(
        User.is_deleted == False, User.is_active == True,
    ).scalar() or 0
    active_subscription_count = db.query(func.count(Subscription.id)).filter(
        Subscription.is_deleted == False,
        Subscription.status == "active",
        Subscription.current_period_start <= now,
        Subscription.current_period_end > now,
    ).scalar() or 0
    appointment_query = db.query(Appointment).filter(
        Appointment.created_at >= month_start,
        Appointment.created_at < next_month,
        Appointment.is_deleted == False,
    )
    appointment_count = appointment_query.count()
    completed_appointment_count = appointment_query.filter(Appointment.status == "completed").count()
    payment_totals = db.query(
        Payment.currency,
        func.sum(Payment.amount_cents + Payment.tip_cents),
    ).filter(
        Payment.received_at >= month_start,
        Payment.received_at < next_month,
        Payment.is_deleted == False,
    ).group_by(Payment.currency).order_by(Payment.currency).all()
    return {
        "period_start": month_start.date().isoformat(),
        "tenant_count": int(tenant_count),
        "active_tenant_count": int(active_tenant_count),
        "active_user_count": int(active_user_count),
        "active_subscription_count": int(active_subscription_count),
        "appointments_created_this_month": int(appointment_count),
        "appointments_completed_this_month": int(completed_appointment_count),
        "collected_this_month_by_currency": [
            {"currency": currency, "amount_cents": int(amount or 0)}
            for currency, amount in payment_totals
        ],
    }

@router.get("/admin/tenants", response_model=AdminTenantsResponse)
def admin_tenants(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    owner_email = db.query(User.email).filter(
        User.barbershop_id == Barbershop.id,
        User.role == "barbershop_owner",
        User.is_deleted == False,
    ).order_by(User.id.asc()).limit(1).correlate(Barbershop).scalar_subquery()
    tenant_rows = db.query(
        Barbershop, owner_email, Subscription.plan, Subscription.status,
    ).outerjoin(
        Subscription, Subscription.id == Barbershop.subscription_id,
    ).filter(
        Barbershop.is_deleted == False,
    ).order_by(Barbershop.id.asc()).all()

    items = [
        AdminTenantItem(
            barbershop_id=shop.id,
            barbershop_name=shop.name,
            currency=shop.currency,
            slug=shop.slug,
            owner_email=owner_email,
            plan=plan,
            subscription_status=subscription_status,
            active=shop.is_active,
        )
        for shop, owner_email, plan, subscription_status in tenant_rows
    ]

    return AdminTenantsResponse(items=items)

@router.get("/admin/affiliates")
def admin_list_affiliates(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    affiliates = db.query(Affiliate).filter(Affiliate.is_deleted == False).order_by(Affiliate.id.desc()).all()
    affiliate_ids = [affiliate.id for affiliate in affiliates]
    active_counts = {}
    commission_totals = {}
    if affiliate_ids:
        active_counts = dict(db.query(
            Barbershop.referred_by_affiliate_id, func.count(Barbershop.id)
        ).filter(
            Barbershop.referred_by_affiliate_id.in_(affiliate_ids),
            Barbershop.is_active == True,
            Barbershop.is_deleted == False,
        ).group_by(Barbershop.referred_by_affiliate_id).all())
        for affiliate_id, currency, earned, paid in db.query(
            Commission.affiliate_id, Commission.currency,
            func.sum(Commission.amount),
            func.sum(case((Commission.status == CommissionStatus.PAID, Commission.amount), else_=0)),
        ).filter(
            Commission.affiliate_id.in_(affiliate_ids),
            Commission.is_deleted == False,
        ).group_by(Commission.affiliate_id, Commission.currency).all():
            commission_totals.setdefault(affiliate_id, []).append({
                "currency": currency, "earned_cents": int(earned or 0), "paid_cents": int(paid or 0),
            })
    return {"items": [{
        "id": affiliate.id, "name": affiliate.full_name, "email": affiliate.email,
        "phone": affiliate.phone, "code": affiliate.code,
        "commission_rate": affiliate.commission_rate, "is_active": affiliate.is_active,
        "total_referrals": affiliate.total_referrals or 0,
        "active_referrals": int(active_counts.get(affiliate.id, 0)),
        "commission_totals_by_currency": commission_totals.get(affiliate.id, []),
    } for affiliate in affiliates]}

@router.post("/admin/affiliates", status_code=201)
def admin_create_affiliate(
    data: AdminAffiliateCreateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    email = str(data.email).lower()
    if db.query(Affiliate.id).filter(Affiliate.email == email, Affiliate.is_deleted == False).first():
        raise HTTPException(status_code=409, detail="El correo ya pertenece a un afiliado")
    code = secrets.token_urlsafe(8).replace("-", "").replace("_", "").upper()[:10]
    while db.query(Affiliate.id).filter(Affiliate.code == code).first():
        code = secrets.token_urlsafe(8).replace("-", "").replace("_", "").upper()[:10]
    affiliate = Affiliate(
        first_name=data.first_name.strip(), last_name=data.last_name.strip(), email=email,
        phone=_normalize_phone(data.phone or "") or None, code=code,
        commission_rate=data.commission_rate, joined_at=utc_now_naive(),
        total_referrals=0, active_referrals=0,
        total_commissions_earned=0, total_commissions_paid=0,
        is_active=True, is_verified=False,
    )
    db.add(affiliate)
    try:
        db.flush()
        _audit(db, admin, "affiliate.created", "affiliate", affiliate.id,
               details={"email": affiliate.email, "commission_rate": affiliate.commission_rate})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="No se pudo crear el afiliado") from exc
    return {"id": affiliate.id, "email": affiliate.email, "name": affiliate.full_name,
            "code": affiliate.code, "commission_rate": affiliate.commission_rate}

@router.put("/admin/affiliates/{affiliate_id}/status")
def admin_update_affiliate_status(
    affiliate_id: int,
    data: AdminStatusUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    affiliate = db.query(Affiliate).filter(
        Affiliate.id == affiliate_id,
        Affiliate.is_deleted == False,
    ).with_for_update().first()
    if not affiliate:
        raise HTTPException(status_code=404, detail="Afiliado no encontrado")
    affiliate.is_active = data.is_active
    _audit(db, admin, "affiliate.status_changed", "affiliate", affiliate.id,
           details={"is_active": affiliate.is_active})
    db.commit()
    return {"success": True, "affiliate_id": affiliate.id, "is_active": affiliate.is_active}

@router.get("/admin/affiliates/{affiliate_id}/commissions")
def admin_list_affiliate_commissions(
    affiliate_id: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    affiliate = db.query(Affiliate).filter(Affiliate.id == affiliate_id, Affiliate.is_deleted == False).first()
    if not affiliate:
        raise HTTPException(status_code=404, detail="Afiliado no encontrado")
    rows = db.query(Commission).filter(
        Commission.affiliate_id == affiliate_id,
        Commission.is_deleted == False,
    ).order_by(Commission.period_start.desc(), Commission.id.desc()).all()
    return {"items": [{
        "id": row.id, "barbershop_id": row.barbershop_id,
        "barbershop_name": row.barbershop.name if row.barbershop else None,
        "subscription_id": row.subscription_id, "amount_cents": row.amount,
        "commission_rate_percent": row.commission_rate,
        "period_start": row.period_start.isoformat(), "period_end": row.period_end.isoformat(),
        "status": row.status, "paid_at": row.paid_at.isoformat() if row.paid_at else None,
        "payment_method": row.payment_method, "payment_reference": row.payment_reference,
    } for row in rows]}

@router.post("/admin/commissions/{commission_id}/approve")
def admin_approve_commission(
    commission_id: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    commission = db.query(Commission).filter(
        Commission.id == commission_id, Commission.is_deleted == False,
    ).with_for_update().first()
    if not commission:
        raise HTTPException(status_code=404, detail="Comisión no encontrada")
    if commission.status != CommissionStatus.PENDING:
        raise HTTPException(status_code=409, detail="Solo se aprueban comisiones pendientes")
    commission.status = CommissionStatus.APPROVED
    _audit(db, admin, "affiliate.commission_approved", "commission", commission.id,
           commission.barbershop_id, {"amount_cents": commission.amount})
    db.commit()
    return {"success": True, "commission_id": commission.id, "status": commission.status}

@router.post("/admin/commissions/{commission_id}/pay")
def admin_pay_commission(
    commission_id: int,
    data: AdminCommissionPaymentRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    commission = db.query(Commission).filter(
        Commission.id == commission_id, Commission.is_deleted == False,
    ).with_for_update().first()
    if not commission:
        raise HTTPException(status_code=404, detail="Comisión no encontrada")
    if commission.status != CommissionStatus.APPROVED:
        raise HTTPException(status_code=409, detail="La comisión debe aprobarse antes de pagarla")
    affiliate = db.query(Affiliate).filter(Affiliate.id == commission.affiliate_id).with_for_update().first()
    if not affiliate:
        raise HTTPException(status_code=409, detail="Afiliado de la comisión no encontrado")
    commission.status = CommissionStatus.PAID
    commission.paid_at = utc_now_naive()
    commission.payment_method = data.payment_method.strip()
    commission.payment_reference = data.payment_reference
    commission.payment_notes = data.payment_notes
    affiliate.total_commissions_paid = (affiliate.total_commissions_paid or 0) + commission.amount
    _audit(db, admin, "affiliate.commission_paid", "commission", commission.id,
           commission.barbershop_id, {"amount_cents": commission.amount,
                                      "payment_method": commission.payment_method})
    db.commit()
    return {"success": True, "commission_id": commission.id, "status": commission.status,
            "paid_at": commission.paid_at.isoformat()}

@router.get("/admin/audit-logs")
def admin_audit_logs(
    barbershop_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Read tenant-aware audit history; only the platform super admin can query it."""
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Paginación fuera de rango")
    query = db.query(AuditLog)
    if barbershop_id is not None:
        query = query.filter(AuditLog.barbershop_id == barbershop_id)
    rows = query.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).offset(offset).limit(limit).all()
    return {"items": [{
        "id": row.id,
        "barbershop_id": row.barbershop_id,
        "actor_user_id": row.actor_user_id,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "occurred_at": row.occurred_at.isoformat(),
        "details": row.details,
    } for row in rows], "limit": limit, "offset": offset}

@router.put("/admin/tenants/{barbershop_id}/status")
def admin_update_tenant_status(
    barbershop_id: int,
    data: AdminStatusUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    shop = db.query(Barbershop).filter(
        Barbershop.id == barbershop_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    previous_status = shop.is_active
    if previous_status != data.is_active:
        now = utc_now_naive()
        tenant_user_ids = db.query(User.id).filter(
            User.barbershop_id == shop.id,
            User.is_deleted == False,
        )
        db.query(User).filter(
            User.barbershop_id == shop.id,
            User.is_deleted == False,
        ).update({User.auth_version: User.auth_version + 1}, synchronize_session=False)
        db.query(RefreshSession).filter(
            RefreshSession.user_id.in_(tenant_user_ids),
            RefreshSession.revoked_at.is_(None),
            RefreshSession.is_deleted == False,
        ).update({RefreshSession.revoked_at: now}, synchronize_session=False)
    shop.is_active = data.is_active
    _audit(db, admin, "tenant.status_changed", "barbershop", shop.id, shop.id,
           {"previous_is_active": previous_status, "is_active": data.is_active})
    db.commit()
    return {"success": True, "barbershop_id": shop.id, "is_active": shop.is_active}

@router.get("/admin/tenants/{barbershop_id}/subscription", response_model=AdminSubscriptionResponse)
def admin_get_subscription(
    barbershop_id: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    shop = db.query(Barbershop).filter(
        Barbershop.id == barbershop_id, Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

    if not shop.subscription_id:
        raise HTTPException(status_code=404, detail="La barbería no tiene una suscripción asociada")

    sub = db.query(Subscription).filter(
        Subscription.id == shop.subscription_id,
        Subscription.is_deleted == False,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")

    return AdminSubscriptionResponse(
        subscription_id=sub.id,
        barbershop_id=shop.id,
        plan=sub.plan,
        status=sub.status,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        auto_renew=sub.auto_renew,
        max_barbers=sub.max_barbers,
        max_appointments_per_month=sub.max_appointments_per_month,
        max_clients=sub.max_clients,
    )

@router.put("/admin/tenants/{barbershop_id}/subscription", response_model=AdminSubscriptionResponse)
def admin_update_subscription(
    barbershop_id: int,
    data: AdminSubscriptionUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Gestiona plan, estado y cobros (mensualidad) de una barbería afiliada."""
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    shop = db.query(Barbershop).filter(
        Barbershop.id == barbershop_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

    valid_plans = {"free", "basic", "professional", "enterprise"}
    valid_statuses = {"active", "inactive", "cancelled", "expired", "suspended"}

    if data.plan is not None and data.plan not in valid_plans:
        raise HTTPException(status_code=400, detail=f"Plan inválido. Use uno de: {sorted(valid_plans)}")

    if data.status is not None and data.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Use uno de: {sorted(valid_statuses)}")

    sub = None
    if shop.subscription_id:
        sub = db.query(Subscription).filter(
            Subscription.id == shop.subscription_id,
            Subscription.is_deleted == False,
        ).with_for_update().first()

    previous = None if sub is None else {
        "plan": sub.plan,
        "status": sub.status,
        "current_period_end": sub.current_period_end.isoformat(),
        "auto_renew": sub.auto_renew,
    }

    if not sub:
        # Crear una suscripción nueva si la barbería aún no tenía una asociada.
        now = utc_now_naive()
        period_end = data.current_period_end or (now + timedelta(days=30))
        if period_end.tzinfo is not None:
            period_end = period_end.astimezone(timezone.utc).replace(tzinfo=None)
        if period_end <= now:
            raise HTTPException(status_code=422, detail="El fin del periodo debe ser posterior al inicio")
        sub = Subscription(
            plan=data.plan or "free",
            status=data.status or "active",
            current_period_start=now,
            current_period_end=period_end,
            auto_renew=False,
        )
        _apply_plan_limits(sub, sub.plan)
        db.add(sub)
        db.flush()
        shop.subscription_id = sub.id
    else:
        if data.plan is not None:
            sub.plan = data.plan
            _apply_plan_limits(sub, sub.plan)
        if data.status is not None:
            sub.status = data.status
        if data.current_period_end is not None:
            period_end = data.current_period_end
            if period_end.tzinfo is not None:
                period_end = period_end.astimezone(timezone.utc).replace(tzinfo=None)
            if period_end <= sub.current_period_start:
                raise HTTPException(status_code=422, detail="El fin del periodo debe ser posterior al inicio")
            sub.current_period_end = period_end
    _audit(
        db, admin, "subscription.updated", "subscription", sub.id, shop.id,
        {"previous": previous, "plan": sub.plan, "status": sub.status,
         "current_period_start": sub.current_period_start.isoformat(),
         "current_period_end": sub.current_period_end.isoformat(),
         "auto_renew": sub.auto_renew},
    )
    db.commit()
    db.refresh(sub)

    return AdminSubscriptionResponse(
        subscription_id=sub.id,
        barbershop_id=shop.id,
        plan=sub.plan,
        status=sub.status,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        auto_renew=sub.auto_renew,
        max_barbers=sub.max_barbers,
        max_appointments_per_month=sub.max_appointments_per_month,
        max_clients=sub.max_clients,
    )

@router.post("/admin/tenants/{barbershop_id}/subscription/payments", status_code=201)
def admin_record_subscription_payment(
    barbershop_id: int,
    data: AdminSubscriptionPaymentRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Record an externally collected subscription charge and create its commission atomically."""
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    shop = db.query(Barbershop).filter(
        Barbershop.id == barbershop_id,
        Barbershop.is_deleted == False,
    ).first()
    if not shop or not shop.subscription_id:
        raise HTTPException(status_code=404, detail="Barbería o suscripción no encontrada")
    subscription = db.query(Subscription).filter(
        Subscription.id == shop.subscription_id,
        Subscription.is_deleted == False,
    ).with_for_update().first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")
    if subscription.plan == "free":
        raise HTTPException(status_code=409, detail="No se registra cobro para el plan gratuito")

    period_start = data.period_start
    period_end = data.period_end
    if period_start.tzinfo is not None:
        period_start = period_start.astimezone(timezone.utc).replace(tzinfo=None)
    if period_end.tzinfo is not None:
        period_end = period_end.astimezone(timezone.utc).replace(tzinfo=None)
    now = utc_now_naive()
    if period_end <= period_start or period_start > now or period_end <= now:
        raise HTTPException(status_code=422, detail="El periodo del pago debe ser válido y estar vigente")
    method = data.method.strip().lower()
    if method not in {"cash", "card", "bank_transfer", "other"}:
        raise HTTPException(status_code=422, detail="Método no válido: cash, card, bank_transfer u other")
    if db.query(SubscriptionPayment.id).filter(
        SubscriptionPayment.subscription_id == subscription.id,
        SubscriptionPayment.period_start == period_start,
        SubscriptionPayment.period_end == period_end,
        SubscriptionPayment.is_deleted == False,
    ).first():
        raise HTTPException(status_code=409, detail="Ese periodo ya tiene un pago registrado")

    payment = SubscriptionPayment(
        barbershop_id=shop.id,
        subscription_id=subscription.id,
        recorded_by_user_id=admin.id,
        amount_cents=data.amount_cents,
        currency=shop.currency,
        method=method,
        reference=data.reference,
        period_start=period_start,
        period_end=period_end,
        paid_at=now,
    )
    subscription.current_period_start = period_start
    subscription.current_period_end = period_end
    subscription.status = "active"
    db.add(payment)
    try:
        db.flush()
        commission = AffiliateService.calculate_commission(
            db=db,
            barbershop_id=shop.id,
            subscription_id=subscription.id,
            period_start=period_start,
            period_end=period_end,
            subscription_amount_cents=data.amount_cents,
            commit=False,
        )
        _audit(db, admin, "subscription.payment_recorded", "subscription_payment", payment.id,
               shop.id, {"subscription_id": subscription.id,
                         "amount_cents": data.amount_cents, "currency": shop.currency,
                         "method": method, "commission_id": commission.id if commission else None})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="El pago del periodo ya fue registrado") from exc
    return {"success": True, "payment_id": payment.id, "subscription_id": subscription.id,
            "amount_cents": payment.amount_cents, "currency": payment.currency,
            "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
            "commission_id": commission.id if commission else None,
            "subscription_status": subscription.status}

@router.get("/admin/users", response_model=AdminUsersResponse)
def admin_users(
    barbershop_id: Optional[int] = None,
    search: Optional[str] = Query(None, min_length=1, max_length=120),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    query = db.query(User).filter(User.is_deleted == False)
    if barbershop_id is not None:
        query = query.filter(User.barbershop_id == barbershop_id)
    search_term = search.strip() if search else ""
    if search_term:
        term = f"%{search_term}%"
        query = query.filter(or_(
            User.email.ilike(term),
            User.first_name.ilike(term),
            User.last_name.ilike(term),
        ))

    total = query.count()
    users = query.order_by(User.id.asc()).offset(offset).limit(limit).all()
    feature_rows = db.query(UserFeatureFlag).filter(
        UserFeatureFlag.user_id.in_([user.id for user in users]),
        UserFeatureFlag.is_deleted == False,
    ).all() if users else []
    feature_flags_by_user: dict[int, dict[str, bool]] = {}
    for feature in feature_rows:
        feature_flags_by_user.setdefault(feature.user_id, {})[feature.feature_key] = bool(feature.enabled)
    items = [
        AdminUserItem(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            barbershop_id=u.barbershop_id,
            is_active=u.is_active,
            support_contact_enabled=u.support_contact_enabled,
            feature_flags=feature_flags_by_user.get(u.id, {}),
        )
        for u in users
    ]
    return AdminUsersResponse(items=items, total=total, offset=offset, limit=limit)

@router.put("/admin/users/{user_id}/support")
def admin_toggle_user_support(
    user_id: int,
    data: AdminUserSupportToggleRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.role not in ["super_admin", "barbershop_owner", "barber"]:
        raise HTTPException(status_code=400, detail="Solo roles administrativos/barbero pueden recibir soporte")

    user.support_contact_enabled = data.support_contact_enabled
    _audit(db, admin, "user.support_contact_changed", "user", user.id, user.barbershop_id,
           {"enabled": data.support_contact_enabled})
    db.commit()
    return {"success": True, "user_id": user.id, "support_contact_enabled": user.support_contact_enabled}

@router.put("/admin/users/{user_id}/status")
def admin_update_user_status(
    user_id: int,
    data: AdminStatusUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    # Serialize last-admin checks across all concurrent administrator changes.
    active_admin_ids = db.query(User.id).filter(
        User.role == "super_admin", User.is_active == True, User.is_deleted == False,
    ).order_by(User.id.asc()).with_for_update().all()
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not data.is_active and user.id == admin.id:
        raise HTTPException(status_code=409, detail="No puedes desactivar tu propia cuenta")
    if not data.is_active and user.role == "super_admin":
        if len(active_admin_ids) <= 1:
            raise HTTPException(status_code=409, detail="No se puede desactivar el último super administrador")
    previous_status = user.is_active
    if previous_status != data.is_active:
        now = utc_now_naive()
        user.auth_version += 1
        db.query(RefreshSession).filter(
            RefreshSession.user_id == user.id,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.is_deleted == False,
        ).update({RefreshSession.revoked_at: now}, synchronize_session=False)
    user.is_active = data.is_active
    _audit(db, admin, "user.status_changed", "user", user.id, user.barbershop_id,
           {"previous_is_active": previous_status, "is_active": data.is_active})
    db.commit()
    return {"success": True, "user_id": user.id, "is_active": user.is_active}

@router.put("/admin/users/{user_id}/features")
def admin_set_user_feature(
    user_id: int,
    data: AdminUserFeatureFlagRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Regla solicitada: customización automática aplica solo a barberos/owner con onboarding.
    if data.feature_key == "branding_auto" and data.enabled:
        if user.role not in ["barber", "barbershop_owner"]:
            raise HTTPException(status_code=400, detail="branding_auto solo aplica a barbero/owner")

        if not user.barbershop_id:
            raise HTTPException(status_code=400, detail="Usuario sin barbería asignada")

        shop = db.query(Barbershop).filter(
            Barbershop.id == user.barbershop_id,
            Barbershop.is_deleted == False,
        ).first()
        if not shop or not shop.onboarding_completed:
            raise HTTPException(status_code=400, detail="El barbero debe completar onboarding para branding_auto")

    feature = (
        db.query(UserFeatureFlag)
        .filter(
            UserFeatureFlag.user_id == user.id,
            UserFeatureFlag.feature_key == data.feature_key,
            UserFeatureFlag.is_deleted == False,
        )
        .first()
    )

    if not feature:
        feature = UserFeatureFlag(user_id=user.id, feature_key=data.feature_key, enabled=data.enabled)
        db.add(feature)
    else:
        feature.enabled = data.enabled

    db.flush()
    _audit(db, admin, "user.feature_changed", "user_feature_flag", feature.id,
           user.barbershop_id, {"user_id": user.id, "feature_key": data.feature_key,
                                "enabled": data.enabled})
    db.commit()
    return {"success": True, "user_id": user.id, "feature_key": data.feature_key, "enabled": data.enabled}
