"""Immutable records of sensitive business and platform actions."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String

from app.models.base import BaseModel


class AuditLog(BaseModel):
    __tablename__ = "audit_logs"

    barbershop_id = Column(Integer, ForeignKey("barbershops.id"), nullable=True, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(80), nullable=False, index=True)
    entity_type = Column(String(60), nullable=False)
    entity_id = Column(Integer, nullable=True, index=True)
    occurred_at = Column(DateTime, nullable=False, index=True)
    details = Column(JSON, nullable=True)
    source_ip = Column(String(45), nullable=True)
