"""
Achievements API endpoints.

Handles gamification, achievements, and badges.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import AchievementService
from app.api.deps import get_current_user
from app.models import User, Achievement

router = APIRouter(prefix="/achievements", tags=["Achievements"])


@router.get("/")
def get_user_achievements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all achievements for the current user.

    Returns earned and available achievements with progress.
    """
    if not current_user.barbershop_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a barbershop"
        )
    if current_user.role != "barber":
        raise HTTPException(status_code=403, detail="Los logros son personales de cada barbero")

    try:
        achievements = AchievementService.get_user_achievements(
            db=db,
            user_id=current_user.id,
            barbershop_id=current_user.barbershop_id
        )
        return achievements
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron cargar los logros"
        )


@router.post("/check")
def check_achievements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Manually trigger achievement check.

    Useful for testing or manual verification.
    """
    if not current_user.barbershop_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a barbershop"
        )
    if current_user.role != "barber":
        raise HTTPException(status_code=403, detail="Solo un barbero puede consultar sus logros")

    try:
        newly_earned = AchievementService.check_and_award_achievements(
            db=db,
            user_id=current_user.id,
            barbershop_id=current_user.barbershop_id,
            trigger_type='manual_check'
        )

        return {
            "newly_earned": len(newly_earned),
            "achievements": [
                {
                    "name": db.query(Achievement).filter(Achievement.id == ua.achievement_id).first().name,
                    "icon": db.query(Achievement).filter(Achievement.id == ua.achievement_id).first().icon,
                    "earned_at": ua.earned_at
                }
                for ua in newly_earned
            ]
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron actualizar los logros"
        )


@router.post("/mark-viewed/{achievement_id}")
def mark_achievement_viewed(
    achievement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark an achievement as viewed by the user."""
    from app.models import UserAchievement
    from sqlalchemy import and_

    if current_user.role != "barber" or not current_user.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo un barbero puede consultar sus logros")

    user_achievement = db.query(UserAchievement).filter(
        and_(
            UserAchievement.user_id == current_user.id,
            UserAchievement.achievement_id == achievement_id,
            UserAchievement.barbershop_id == current_user.barbershop_id,
            UserAchievement.is_deleted == False,
        )
    ).first()

    if not user_achievement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Achievement not found"
        )

    user_achievement.is_viewed = True
    db.commit()

    return {"success": True, "message": "Achievement marked as viewed"}
