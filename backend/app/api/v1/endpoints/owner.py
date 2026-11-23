"""Owner and barber management endpoints."""

from datetime import datetime, time
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import get_db
from app.core.security.password import hash_password
from app.models.appointment import Appointment
from app.models.barber_commission import BarberCommission
from app.models.barbershop import Barbershop
from app.models.payment import Payment
from app.models.user import User
from app.schemas.platform import (
    AdminStatusUpdateRequest,
    BarberCommissionPaymentRequest,
    BarberCommissionRateRequest,
    OwnerClientCreateRequest,
    OwnerClientUpdateRequest,
    OwnerCreateBarberRequest,
    OwnerBarberUpdateRequest,
)
from app.utils.datetime import utc_now_naive
from app.api.v1.endpoints.common import (
    _audit, _cash_register_closed_for_user, _get_current_user, _get_timezone,
    _normalize_phone, _require_active_subscription, _utc_aware,
)

router = APIRouter(tags=["platform"])

@router.get("/owner/barbers")
def owner_list_barbers(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar su equipo")
    barbers = db.query(User).filter(
        User.barbershop_id == owner.barbershop_id,
        User.role == "barber",
        User.is_deleted == False,
    ).order_by(User.first_name.asc(), User.last_name.asc()).all()
    return {"items": [{"id": barber.id, "email": barber.email,
                       "first_name": barber.first_name, "last_name": barber.last_name,
                       "full_name": barber.full_name, "phone": barber.phone,
                       "is_active": barber.is_active,
                       "commission_rate_basis_points": barber.commission_rate_basis_points}
                      for barber in barbers]}

@router.post("/owner/barbers", status_code=201)
def owner_create_barber(
    data: OwnerCreateBarberRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar su equipo")
    shop = db.query(Barbershop).filter(
        Barbershop.id == owner.barbershop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=403, detail="Barbería inactiva")
    subscription = _require_active_subscription(db, shop, lock=True)
    barber_count = db.query(User.id).filter(
        User.barbershop_id == shop.id,
        User.role == "barber",
        User.is_active == True,
        User.is_deleted == False,
    ).count()
    if subscription.max_barbers is not None and barber_count >= subscription.max_barbers:
        raise HTTPException(status_code=402, detail="La barbería alcanzó el límite de barberos de su plan")
    email = str(data.email).lower()
    if db.query(User.id).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="El correo ya está registrado")
    barber = User(
        email=email,
        password_hash=hash_password(data.password),
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        phone=_normalize_phone(data.phone or "") or None,
        role="barber",
        is_active=True,
        is_verified=False,
        barbershop_id=shop.id,
    )
    db.add(barber)
    try:
        db.flush()
        _audit(db, owner, "barber.created", "user", barber.id, shop.id, {"email": barber.email})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="El correo ya está registrado") from exc
    return {"id": barber.id, "email": barber.email, "full_name": barber.full_name,
            "phone": barber.phone, "is_active": barber.is_active}

@router.put("/owner/barbers/{barber_id}/status")
def owner_update_barber_status(
    barber_id: int,
    data: AdminStatusUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar su equipo")
    shop = db.query(Barbershop).filter(
        Barbershop.id == owner.barbershop_id,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    # Serialize activations with barber creation so simultaneous changes cannot
    # exceed the subscription's seat limit.
    subscription = None
    if data.is_active:
        subscription = _require_active_subscription(db, shop, lock=True)
    barber = db.query(User).filter(
        User.id == barber_id,
        User.barbershop_id == owner.barbershop_id,
        User.role == "barber",
        User.is_deleted == False,
    ).with_for_update().first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barbero no encontrado")
    if data.is_active and not barber.is_active:
        active_count = db.query(User.id).filter(
            User.barbershop_id == shop.id,
            User.role == "barber",
            User.is_active == True,
            User.is_deleted == False,
        ).count()
        if subscription.max_barbers is not None and active_count >= subscription.max_barbers:
            raise HTTPException(status_code=402, detail="La barbería alcanzó el límite de barberos de su plan")
    barber.is_active = data.is_active
    _audit(db, owner, "barber.status_changed", "user", barber.id, owner.barbershop_id,
           {"is_active": data.is_active})
    db.commit()
    return {"success": True, "barber_id": barber.id, "is_active": barber.is_active}

@router.put("/owner/barbers/{barber_id}")
def owner_update_barber(
    barber_id: int,
    data: OwnerBarberUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar su equipo")
    barber = db.query(User).filter(
        User.id == barber_id,
        User.barbershop_id == owner.barbershop_id,
        User.role == "barber",
        User.is_deleted == False,
    ).with_for_update().first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barbero no encontrado")
    barber.first_name = data.first_name
    barber.last_name = data.last_name
    barber.phone = _normalize_phone(data.phone or "") or None
    _audit(db, owner, "barber.profile_updated", "user", barber.id, owner.barbershop_id,
           {"updated_fields": ["first_name", "last_name", "phone"]})
    db.commit()
    return {"id": barber.id, "full_name": barber.full_name, "phone": barber.phone}

@router.put("/owner/barbers/{barber_id}/commission-rate")
def owner_update_barber_commission_rate(
    barber_id: int,
    data: BarberCommissionRateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede configurar comisiones")
    barber = db.query(User).filter(
        User.id == barber_id,
        User.barbershop_id == owner.barbershop_id,
        User.role == "barber",
        User.is_deleted == False,
    ).with_for_update().first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barbero no encontrado")
    previous_rate = barber.commission_rate_basis_points
    barber.commission_rate_basis_points = data.rate_basis_points
    _audit(db, owner, "barber.commission_rate_changed", "user", barber.id, owner.barbershop_id,
           {"previous_rate_basis_points": previous_rate,
            "rate_basis_points": data.rate_basis_points})
    db.commit()
    return {"success": True, "barber_id": barber.id,
            "rate_basis_points": barber.commission_rate_basis_points}

def _commission_item(row: BarberCommission, barber: User) -> dict:
    return {
        "id": row.id,
        "barber_id": row.barber_id,
        "barber_name": barber.full_name,
        "payment_id": row.payment_id,
        "amount_cents": row.amount_cents,
        "currency": row.currency,
        "rate_basis_points": row.rate_basis_points,
        "status": row.status,
        "accrued_at": row.accrued_at.isoformat(),
        "paid_at": row.paid_at.isoformat() if row.paid_at else None,
        "payment_method": row.payment_method,
        "payment_reference": row.payment_reference,
    }

@router.get("/owner/barber-commissions")
def owner_list_barber_commissions(
    status: Optional[str] = None,
    barber_id: Optional[int] = None,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede consultar las comisiones")
    if status is not None and status not in {"pending", "paid"}:
        raise HTTPException(status_code=422, detail="Estado de comisión no válido")
    base = db.query(BarberCommission).filter(
        BarberCommission.barbershop_id == owner.barbershop_id,
        BarberCommission.is_deleted == False,
    )
    pending_totals = _commission_totals_for_scope(db, owner.barbershop_id, "pending")
    paid_totals = _commission_totals_for_scope(db, owner.barbershop_id, "paid")
    query = base
    if status:
        query = query.filter(BarberCommission.status == status)
    if barber_id:
        query = query.filter(BarberCommission.barber_id == barber_id)
    rows = query.order_by(BarberCommission.accrued_at.desc(), BarberCommission.id.desc()).limit(200).all()
    barber_ids = {row.barber_id for row in rows}
    barbers = {item.id: item for item in db.query(User).filter(User.id.in_(barber_ids)).all()} if barber_ids else {}
    return {
        "pending_totals_by_currency": pending_totals,
        "paid_totals_by_currency": paid_totals,
        "items": [_commission_item(row, barbers[row.barber_id]) for row in rows if row.barber_id in barbers],
    }

@router.get("/barber/commissions")
def barber_list_own_commissions(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    barber = _get_current_user(db, authorization)
    if barber.role != "barber" or not barber.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo un barbero puede consultar sus comisiones")
    rows = db.query(BarberCommission).filter(
        BarberCommission.barbershop_id == barber.barbershop_id,
        BarberCommission.barber_id == barber.id,
        BarberCommission.is_deleted == False,
    ).order_by(BarberCommission.accrued_at.desc(), BarberCommission.id.desc()).limit(200).all()
    return {
        "pending_totals_by_currency": _commission_totals_for_scope(
            db, barber.barbershop_id, "pending", barber_id=barber.id,
        ),
        "paid_totals_by_currency": _commission_totals_for_scope(
            db, barber.barbershop_id, "paid", barber_id=barber.id,
        ),
        "items": [_commission_item(row, barber) for row in rows],
    }

def _commission_totals_for_scope(
    db: Session, barbershop_id: int, status: str, barber_id: Optional[int] = None,
) -> list[dict]:
    query = db.query(
        BarberCommission.currency,
        func.coalesce(func.sum(BarberCommission.amount_cents), 0),
    ).filter(
        BarberCommission.barbershop_id == barbershop_id,
        BarberCommission.status == status,
        BarberCommission.is_deleted == False,
    )
    if barber_id is not None:
        query = query.filter(BarberCommission.barber_id == barber_id)
    return [{"currency": currency, "amount_cents": int(amount)}
            for currency, amount in query.group_by(BarberCommission.currency).order_by(BarberCommission.currency).all()]

@router.post("/owner/barber-commissions/{commission_id}/pay")
def owner_pay_barber_commission(
    commission_id: int,
    data: BarberCommissionPaymentRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede liquidar comisiones")
    shop = db.query(Barbershop).filter(
        Barbershop.id == owner.barbershop_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    if data.payment_method == "cash":
        business_date = _utc_aware(utc_now_naive()).astimezone(_get_timezone(shop)).date()
        if _cash_register_closed_for_user(
            db, owner, shop.id, datetime.combine(business_date, time.min),
        ):
            raise HTTPException(status_code=409, detail="La caja de hoy está cerrada; no se puede registrar un pago en efectivo")
    commission = db.query(BarberCommission).filter(
        BarberCommission.id == commission_id,
        BarberCommission.barbershop_id == owner.barbershop_id,
        BarberCommission.is_deleted == False,
    ).with_for_update().first()
    if not commission:
        raise HTTPException(status_code=404, detail="Comisión no encontrada")
    if commission.status != "pending":
        raise HTTPException(status_code=409, detail="La comisión ya fue liquidada")
    commission.status = "paid"
    commission.paid_at = utc_now_naive()
    commission.paid_by_user_id = owner.id
    commission.payment_method = data.payment_method
    commission.payment_reference = data.payment_reference.strip() if data.payment_reference else None
    _audit(db, owner, "barber.commission_paid", "barber_commission", commission.id,
           owner.barbershop_id, {"barber_id": commission.barber_id,
                                 "amount_cents": commission.amount_cents,
                                 "currency": commission.currency,
                                 "payment_method": commission.payment_method})
    db.commit()
    return {"success": True, "commission_id": commission.id, "status": commission.status,
            "paid_at": commission.paid_at.isoformat()}

@router.get("/owner/clients")
def owner_list_clients(
    limit: int = 50,
    offset: int = 0,
    search: str = Query(default="", max_length=100),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede consultar sus clientes")
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Paginación fuera de rango")
    client_query = db.query(User).filter(
        User.barbershop_id == owner.barbershop_id,
        User.role == "client",
        User.is_deleted == False,
    )
    search_term = search.strip()
    if search_term:
        pattern = f"%{search_term}%"
        client_query = client_query.filter(or_(
            User.first_name.ilike(pattern),
            User.last_name.ilike(pattern),
            User.email.ilike(pattern),
            User.phone.ilike(pattern),
            func.concat(User.first_name, " ", User.last_name).ilike(pattern),
        ))
    total = client_query.count()
    clients = client_query.order_by(User.id.desc()).offset(offset).limit(limit).all()
    client_ids = [client.id for client in clients]
    appointments = {}
    payments = {}
    if client_ids:
        appointment_rows = db.query(
            Appointment.client_id,
            func.count(Appointment.id),
            func.sum(case((Appointment.status == "completed", 1), else_=0)),
            func.max(case((Appointment.status == "completed", Appointment.scheduled_time), else_=None)),
        ).filter(
            Appointment.barbershop_id == owner.barbershop_id,
            Appointment.client_id.in_(client_ids),
            Appointment.is_deleted == False,
        ).group_by(Appointment.client_id).all()
        appointments = {row[0]: {"count": int(row[1] or 0), "completed": int(row[2] or 0), "last_visit": row[3]}
                        for row in appointment_rows}
        payment_rows = db.query(
            Appointment.client_id,
            func.sum(Payment.amount_cents + Payment.tip_cents),
        ).join(Payment, Payment.appointment_id == Appointment.id).filter(
            Appointment.barbershop_id == owner.barbershop_id,
            Appointment.client_id.in_(client_ids),
            Appointment.is_deleted == False,
            Payment.is_deleted == False,
        ).group_by(Appointment.client_id).all()
        payments = {row[0]: int(row[1] or 0) for row in payment_rows}
    return {"items": [{
        "id": client.id, "full_name": client.full_name, "first_name": client.first_name,
        "last_name": client.last_name, "phone": client.phone, "is_active": client.is_active,
        "created_at": client.created_at.isoformat(),
        "appointment_count": appointments.get(client.id, {}).get("count", 0),
        "completed_count": appointments.get(client.id, {}).get("completed", 0),
        "last_visit": appointments.get(client.id, {}).get("last_visit"),
        "total_paid_cents": payments.get(client.id, 0),
    } for client in clients], "limit": limit, "offset": offset, "total": total}

@router.get("/owner/clients/{client_id}/appointments")
def owner_list_client_appointment_history(
    client_id: int,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede consultar el historial")
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Paginación fuera de rango")
    client = db.query(User).filter(
        User.id == client_id,
        User.barbershop_id == owner.barbershop_id,
        User.role == "client",
        User.is_deleted == False,
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    appointment_query = db.query(Appointment).filter(
        Appointment.barbershop_id == owner.barbershop_id,
        Appointment.client_id == client.id,
        Appointment.is_deleted == False,
    )
    total = appointment_query.count()
    appointments = appointment_query.order_by(
        Appointment.scheduled_time.desc(), Appointment.id.desc(),
    ).offset(offset).limit(limit).all()
    appointment_ids = [appointment.id for appointment in appointments]
    payments = db.query(Payment).filter(
        Payment.barbershop_id == owner.barbershop_id,
        Payment.appointment_id.in_(appointment_ids),
        Payment.is_deleted == False,
    ).all() if appointment_ids else []
    payments_by_appointment = {payment.appointment_id: payment for payment in payments}
    barber_ids = {appointment.barber_id for appointment in appointments}
    barbers = db.query(User).filter(
        User.id.in_(barber_ids),
        User.barbershop_id == owner.barbershop_id,
        User.role == "barber",
    ).all() if barber_ids else []
    barber_names = {barber.id: barber.full_name for barber in barbers}

    def utc_iso(value: Optional[datetime]) -> Optional[str]:
        return f"{value.isoformat()}Z" if value else None

    items = []
    for appointment in appointments:
        payment = payments_by_appointment.get(appointment.id)
        actual_duration = None
        if appointment.actual_start_time and appointment.actual_end_time:
            actual_duration = max(
                0,
                int((appointment.actual_end_time - appointment.actual_start_time).total_seconds() / 60),
            )
        items.append({
            "id": appointment.id,
            "scheduled_time": utc_iso(appointment.scheduled_time),
            "status": appointment.status,
            "service_type": appointment.service_type,
            "estimated_duration": appointment.estimated_duration,
            "actual_duration": actual_duration,
            "service_price_cents": appointment.service_price,
            "barber_name": barber_names.get(appointment.barber_id),
            "payment": {
                "amount_cents": payment.amount_cents,
                "tip_cents": payment.tip_cents,
                "currency": payment.currency,
                "method": payment.method,
                "received_at": utc_iso(payment.received_at),
            } if payment else None,
        })
    return {"items": items, "limit": limit, "offset": offset, "total": total}

@router.post("/owner/clients", status_code=201)
def owner_create_client(
    data: OwnerClientCreateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar sus clientes")
    shop = db.query(Barbershop).filter(
        Barbershop.id == owner.barbershop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=403, detail="Barbería inactiva")
    subscription = _require_active_subscription(db, shop, lock=True)
    phone = _normalize_phone(data.phone)
    existing = db.query(User).filter(
        User.phone == phone,
        User.barbershop_id == shop.id,
        User.role == "client",
        User.is_deleted == False,
    ).with_for_update().first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Ya existe un cliente con ese teléfono en esta barbería",
        )
    if subscription.max_clients is not None:
        client_count = db.query(User.id).filter(
            User.barbershop_id == shop.id,
            User.role == "client",
            User.is_deleted == False,
        ).count()
        if client_count >= subscription.max_clients:
            raise HTTPException(status_code=402, detail="La barbería alcanzó el límite de clientes de su plan")

    client = User(
        email=f"client-{shop.id}-{secrets.token_hex(16)}@client.invalid",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        first_name=data.first_name,
        last_name=data.last_name,
        phone=phone,
        role="client",
        is_active=True,
        is_verified=True,
        barbershop_id=shop.id,
    )
    db.add(client)
    try:
        db.flush()
        _audit(db, owner, "client.created", "user", client.id, shop.id,
               {"phone_last4": phone[-4:], "source": "owner_manual"})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="No se pudo registrar el cliente") from exc
    return {
        "id": client.id,
        "full_name": client.full_name,
        "first_name": client.first_name,
        "last_name": client.last_name,
        "phone": client.phone,
        "is_active": client.is_active,
    }

@router.put("/owner/clients/{client_id}")
def owner_update_client(
    client_id: int,
    data: OwnerClientUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar sus clientes")
    shop = db.query(Barbershop).filter(
        Barbershop.id == owner.barbershop_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    phone = _normalize_phone(data.phone or "") or None
    client = db.query(User).filter(
        User.id == client_id,
        User.barbershop_id == owner.barbershop_id,
        User.role == "client",
        User.is_deleted == False,
    ).with_for_update().first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if phone and db.query(User.id).filter(
        User.barbershop_id == owner.barbershop_id,
        User.role == "client",
        User.phone == phone,
        User.id != client.id,
        User.is_deleted == False,
    ).with_for_update().first():
        raise HTTPException(status_code=409, detail="Ya existe un cliente con ese teléfono en esta barbería")
    client.first_name = data.first_name
    client.last_name = data.last_name
    client.phone = phone
    _audit(db, owner, "client.profile_updated", "user", client.id, owner.barbershop_id,
           {"updated_fields": ["first_name", "last_name", "phone"]})
    db.commit()
    return {"id": client.id, "full_name": client.full_name, "phone": client.phone}

@router.put("/owner/clients/{client_id}/status")
def owner_update_client_status(
    client_id: int,
    data: AdminStatusUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar sus clientes")
    client = db.query(User).filter(
        User.id == client_id,
        User.barbershop_id == owner.barbershop_id,
        User.role == "client",
        User.is_deleted == False,
    ).with_for_update().first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    previous = client.is_active
    client.is_active = data.is_active
    _audit(db, owner, "client.status_changed", "user", client.id, owner.barbershop_id,
           {"previous": previous, "is_active": data.is_active})
    db.commit()
    return {"success": True, "id": client.id, "is_active": client.is_active}
