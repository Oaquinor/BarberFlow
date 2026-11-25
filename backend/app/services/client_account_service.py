"""Helpers that keep global customer identities separate from tenant CRM rows."""

import secrets

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security.password import hash_password
from app.models import Barbershop, ClientAccountShopLink, Subscription, User


def get_or_create_shop_client(
    db: Session,
    account: User,
    shop: Barbershop,
    subscription: Subscription,
) -> User:
    """Get the account's CRM row. Caller holds the shop and subscription locks."""
    link = db.query(ClientAccountShopLink).filter(
        ClientAccountShopLink.account_user_id == account.id,
        ClientAccountShopLink.barbershop_id == shop.id,
        ClientAccountShopLink.is_deleted == False,
    ).with_for_update().first()
    if link:
        crm_client = db.query(User).filter(
            User.id == link.crm_client_user_id,
            User.barbershop_id == shop.id,
            User.role == "client",
            User.is_deleted == False,
        ).with_for_update().first()
        if not crm_client:
            raise HTTPException(status_code=409, detail="El perfil CRM vinculado ya no está disponible")
        if not crm_client.is_active:
            raise HTTPException(status_code=409, detail="El perfil de cliente está desactivado en esta barbería")
        return crm_client

    if subscription.max_clients is not None:
        count = db.query(User.id).filter(
            User.barbershop_id == shop.id,
            User.role == "client",
            User.is_deleted == False,
        ).count()
        if count >= subscription.max_clients:
            raise HTTPException(status_code=402, detail="La barbería alcanzó el límite de clientes de su plan")

    crm_client = User(
        email=f"client-{shop.id}-{secrets.token_hex(16)}@client.invalid",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        first_name=account.first_name,
        last_name=account.last_name,
        phone=account.phone,
        role="client",
        is_active=True,
        is_verified=False,
        barbershop_id=shop.id,
    )
    db.add(crm_client)
    db.flush()
    db.add(ClientAccountShopLink(
        account_user_id=account.id,
        barbershop_id=shop.id,
        crm_client_user_id=crm_client.id,
    ))
    db.flush()
    return crm_client
