"""Verified customer identities and their tenant-scoped CRM profiles."""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from app.models.base import BaseModel


class ClientAccountVerification(BaseModel):
    __tablename__ = "client_account_verifications"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_client_account_verifications_token_hash"),
        Index("ix_client_account_verifications_user_active", "user_id", "consumed_at", "revoked_at"),
        Index("ix_client_account_verifications_expires_at", "expires_at"),
    )

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)


class ClientAccountShopLink(BaseModel):
    """Connect a verified global customer identity to one shop's CRM record."""

    __tablename__ = "client_account_shop_links"
    __table_args__ = (
        UniqueConstraint("account_user_id", "barbershop_id", name="uq_client_account_shop"),
        UniqueConstraint("crm_client_user_id", name="uq_client_account_crm_client"),
        Index("ix_client_account_shop_lookup", "barbershop_id", "account_user_id"),
    )

    account_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    barbershop_id = Column(Integer, ForeignKey("barbershops.id", ondelete="CASCADE"), nullable=False)
    crm_client_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
