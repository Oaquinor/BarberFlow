"""
Affiliate Service.

Handles affiliate program, referrals, and commissions.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
import secrets
import string

from app.models import Affiliate, Commission, Barbershop, Subscription
from app.core.constants import CommissionStatus


class AffiliateService:
    """Service for affiliate program management."""

    @staticmethod
    def generate_affiliate_code(length: int = 8) -> str:
        """Generate a unique affiliate code."""
        characters = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(characters) for _ in range(length))

    @staticmethod
    def create_affiliate(
        db: Session,
        first_name: str,
        last_name: str,
        email: str,
        phone: Optional[str] = None,
        commission_rate: float = 0.15
    ) -> Affiliate:
        """Create a new affiliate."""
        # Generate unique code
        code = AffiliateService.generate_affiliate_code()

        # Ensure code is unique
        while db.query(Affiliate).filter(Affiliate.code == code).first():
            code = AffiliateService.generate_affiliate_code()

        affiliate = Affiliate(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            code=code,
            commission_rate=commission_rate,
            joined_at=datetime.utcnow()
        )

        db.add(affiliate)
        db.commit()
        db.refresh(affiliate)

        return affiliate

    @staticmethod
    def get_affiliate_by_code(
        db: Session,
        code: str
    ) -> Optional[Affiliate]:
        """Get affiliate by their unique code."""
        return db.query(Affiliate).filter(
            and_(
                Affiliate.code == code,
                Affiliate.is_active == True,
                Affiliate.is_deleted == False
            )
        ).first()

    @staticmethod
    def get_affiliate_by_email(
        db: Session,
        email: str
    ) -> Optional[Affiliate]:
        """Get affiliate by email."""
        return db.query(Affiliate).filter(
            and_(
                Affiliate.email == email,
                Affiliate.is_deleted == False
            )
        ).first()

    @staticmethod
    def register_referral(
        db: Session,
        barbershop_id: int,
        affiliate_code: str
    ) -> bool:
        """Register a barbershop as referred by an affiliate."""
        affiliate = AffiliateService.get_affiliate_by_code(db, affiliate_code)

        if not affiliate:
            return False

        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()

        if not barbershop:
            return False

        barbershop.referred_by_affiliate_id = affiliate.id
        affiliate.total_referrals += 1
        affiliate.active_referrals += 1

        db.commit()

        return True

    @staticmethod
    def calculate_commission(
        db: Session,
        barbershop_id: int,
        subscription_id: int,
        period_start: datetime,
        period_end: datetime
    ) -> Optional[Commission]:
        """Calculate and create commission for a subscription period."""
        barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()

        if not barbershop or not barbershop.referred_by_affiliate_id:
            return None

        affiliate = db.query(Affiliate).filter(Affiliate.id == barbershop.referred_by_affiliate_id).first()

        if not affiliate:
            return None

        subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()

        if not subscription:
            return None

        # Get subscription amount (you'll need to add pricing logic)
        # For now, using placeholder
        subscription_amount = 30000  # $300.00 in cents (example)

        commission_amount = int(subscription_amount * affiliate.commission_rate)

        # Create commission record
        commission = Commission(
            affiliate_id=affiliate.id,
            barbershop_id=barbershop_id,
            subscription_id=subscription_id,
            amount=commission_amount,
            commission_rate=int(affiliate.commission_rate * 100),
            period_start=period_start,
            period_end=period_end,
            status=CommissionStatus.PENDING
        )

        db.add(commission)

        # Update affiliate stats
        affiliate.total_commissions_earned += commission_amount

        db.commit()
        db.refresh(commission)

        return commission

    @staticmethod
    def approve_commission(
        db: Session,
        commission_id: int
    ) -> Optional[Commission]:
        """Approve a pending commission."""
        commission = db.query(Commission).filter(Commission.id == commission_id).first()

        if not commission or commission.status != CommissionStatus.PENDING:
            return None

        commission.status = CommissionStatus.APPROVED
        db.commit()
        db.refresh(commission)

        return commission

    @staticmethod
    def pay_commission(
        db: Session,
        commission_id: int,
        payment_method: str,
        payment_reference: Optional[str] = None,
        payment_notes: Optional[str] = None
    ) -> Optional[Commission]:
        """Mark a commission as paid."""
        commission = db.query(Commission).filter(Commission.id == commission_id).first()

        if not commission or commission.status != CommissionStatus.APPROVED:
            return None

        commission.status = CommissionStatus.PAID
        commission.paid_at = datetime.utcnow()
        commission.payment_method = payment_method
        commission.payment_reference = payment_reference
        commission.payment_notes = payment_notes

        # Update affiliate stats
        affiliate = db.query(Affiliate).filter(Affiliate.id == commission.affiliate_id).first()
        if affiliate:
            affiliate.total_commissions_paid += commission.amount

        db.commit()
        db.refresh(commission)

        return commission

    @staticmethod
    def get_affiliate_dashboard(
        db: Session,
        affiliate_id: int
    ) -> Dict[str, Any]:
        """Get affiliate dashboard statistics."""
        affiliate = db.query(Affiliate).filter(Affiliate.id == affiliate_id).first()

        if not affiliate:
            return {}

        # Get commissions
        pending_commissions = db.query(Commission).filter(
            and_(
                Commission.affiliate_id == affiliate_id,
                Commission.status == CommissionStatus.PENDING
            )
        ).all()

        paid_commissions = db.query(Commission).filter(
            and_(
                Commission.affiliate_id == affiliate_id,
                Commission.status == CommissionStatus.PAID
            )
        ).all()

        # Get active referrals
        active_referrals = db.query(Barbershop).filter(
            and_(
                Barbershop.referred_by_affiliate_id == affiliate_id,
                Barbershop.is_active == True
            )
        ).all()

        return {
            "affiliate": {
                "id": affiliate.id,
                "name": affiliate.full_name,
                "code": affiliate.code,
                "email": affiliate.email,
                "commission_rate": affiliate.commission_rate
            },
            "stats": {
                "total_referrals": affiliate.total_referrals,
                "active_referrals": len(active_referrals),
                "total_earned": affiliate.total_commissions_earned,
                "total_paid": affiliate.total_commissions_paid,
                "pending_amount": sum(c.amount for c in pending_commissions)
            },
            "recent_commissions": [
                {
                    "id": c.id,
                    "amount": c.amount,
                    "status": c.status,
                    "period_start": c.period_start,
                    "period_end": c.period_end,
                    "paid_at": c.paid_at
                }
                for c in (pending_commissions + paid_commissions)[-10:]  # Last 10
            ],
            "active_barbershops": [
                {
                    "id": b.id,
                    "name": b.name,
                    "joined": b.created_at
                }
                for b in active_referrals
            ]
        }
