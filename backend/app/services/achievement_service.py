"""
Achievement Service.

Handles gamification, achievements, and badges.
"""

from datetime import datetime, date
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models import Achievement, UserAchievement, BarberPerformance


class AchievementService:
    """Service for achievement and gamification management."""

    @staticmethod
    def initialize_default_achievements(db: Session):
        """Create default achievements for the system."""
        default_achievements = [
            # Streak Achievements
            {
                "code": "FIRST_DAY",
                "name": "Primer Día",
                "description": "Completa tu primera jornada de trabajo",
                "icon": "🎉",
                "category": "streak",
                "requirement_type": "appointments",
                "requirement_value": 1,
                "points": 10,
                "rarity": "common"
            },
            {
                "code": "WEEK_WARRIOR",
                "name": "Guerrero Semanal",
                "description": "Trabaja 7 días consecutivos",
                "icon": "🔥",
                "category": "streak",
                "requirement_type": "streak",
                "requirement_value": 7,
                "points": 50,
                "rarity": "rare"
            },
            {
                "code": "MONTH_MASTER",
                "name": "Maestro del Mes",
                "description": "Trabaja 30 días consecutivos",
                "icon": "👑",
                "category": "streak",
                "requirement_type": "streak",
                "requirement_value": 30,
                "points": 200,
                "rarity": "epic"
            },
            # Productivity Achievements
            {
                "code": "BUSY_BEE",
                "name": "Abeja Ocupada",
                "description": "Completa 10 citas en un solo día",
                "icon": "🐝",
                "category": "productivity",
                "requirement_type": "daily_appointments",
                "requirement_value": 10,
                "points": 30,
                "rarity": "rare"
            },
            {
                "code": "SUPER_BARBER",
                "name": "Super Barbero",
                "description": "Completa 15 citas en un solo día",
                "icon": "⚡",
                "category": "productivity",
                "requirement_type": "daily_appointments",
                "requirement_value": 15,
                "points": 75,
                "rarity": "epic"
            },
            {
                "code": "CENTURY_CLUB",
                "name": "Club de los 100",
                "description": "Completa 100 citas en total",
                "icon": "💯",
                "category": "milestone",
                "requirement_type": "total_appointments",
                "requirement_value": 100,
                "points": 100,
                "rarity": "rare"
            },
            {
                "code": "FIVE_HUNDRED",
                "name": "Quinientos",
                "description": "Completa 500 citas en total",
                "icon": "🌟",
                "category": "milestone",
                "requirement_type": "total_appointments",
                "requirement_value": 500,
                "points": 500,
                "rarity": "epic"
            },
            {
                "code": "LEGEND",
                "name": "Leyenda",
                "description": "Completa 1000 citas en total",
                "icon": "🏆",
                "category": "milestone",
                "requirement_type": "total_appointments",
                "requirement_value": 1000,
                "points": 1000,
                "rarity": "legendary"
            },
            # Efficiency Achievements
            {
                "code": "SPEED_DEMON",
                "name": "Demonio de la Velocidad",
                "description": "Mantén 95% de eficiencia de tiempo durante una semana",
                "icon": "⚡",
                "category": "efficiency",
                "requirement_type": "weekly_efficiency",
                "requirement_value": 95,
                "points": 100,
                "rarity": "epic"
            },
            {
                "code": "PERFECT_WEEK",
                "name": "Semana Perfecta",
                "description": "Completa todas tus citas sin cancelaciones durante una semana",
                "icon": "✨",
                "category": "excellence",
                "requirement_type": "weekly_perfect",
                "requirement_value": 1,
                "points": 150,
                "rarity": "epic"
            }
        ]

        for ach_data in default_achievements:
            # Check if already exists
            existing = db.query(Achievement).filter(Achievement.code == ach_data["code"]).first()
            if not existing:
                achievement = Achievement(**ach_data)
                db.add(achievement)

        db.commit()

    @staticmethod
    def check_and_award_achievements(
        db: Session,
        user_id: int,
        barbershop_id: int,
        trigger_type: str,
        context_data: Optional[Dict[str, Any]] = None
    ) -> List[UserAchievement]:
        """
        Check if user has earned new achievements and award them.

        trigger_type: 'appointment_completed', 'daily_summary', 'weekly_summary'
        """
        newly_earned = []

        # Get all active achievements
        all_achievements = db.query(Achievement).filter(Achievement.is_active == True).all()

        # Get user's already earned achievements
        earned_achievement_ids = {
            ua.achievement_id 
            for ua in db.query(UserAchievement).filter(
                and_(
                    UserAchievement.user_id == user_id,
                    UserAchievement.barbershop_id == barbershop_id
                )
            ).all()
        }

        # Check each achievement
        for achievement in all_achievements:
            # Skip if already earned
            if achievement.id in earned_achievement_ids:
                continue

            # Check if user qualifies
            if AchievementService._check_achievement_requirement(
                db, user_id, barbershop_id, achievement, context_data
            ):
                # Award achievement
                user_achievement = UserAchievement(
                    user_id=user_id,
                    achievement_id=achievement.id,
                    barbershop_id=barbershop_id,
                    earned_at=datetime.utcnow(),
                    context_data=context_data
                )
                db.add(user_achievement)
                newly_earned.append(user_achievement)

        if newly_earned:
            db.commit()
            for ua in newly_earned:
                db.refresh(ua)

        return newly_earned

    @staticmethod
    def _check_achievement_requirement(
        db: Session,
        user_id: int,
        barbershop_id: int,
        achievement: Achievement,
        context_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Check if user meets achievement requirements."""

        if achievement.requirement_type == "appointments":
            # Simple appointment count check (for first day)
            performance = db.query(BarberPerformance).filter(
                and_(
                    BarberPerformance.barber_id == user_id,
                    BarberPerformance.barbershop_id == barbershop_id,
                    BarberPerformance.appointments_completed >= achievement.requirement_value
                )
            ).first()
            return performance is not None

        elif achievement.requirement_type == "streak":
            # Check current streak
            latest_performance = db.query(BarberPerformance).filter(
                and_(
                    BarberPerformance.barber_id == user_id,
                    BarberPerformance.barbershop_id == barbershop_id
                )
            ).order_by(BarberPerformance.date.desc()).first()

            return (latest_performance and 
                    latest_performance.current_streak >= achievement.requirement_value)

        elif achievement.requirement_type == "daily_appointments":
            # Check if any day had this many appointments
            performance = db.query(BarberPerformance).filter(
                and_(
                    BarberPerformance.barber_id == user_id,
                    BarberPerformance.barbershop_id == barbershop_id,
                    BarberPerformance.appointments_completed >= achievement.requirement_value
                )
            ).first()
            return performance is not None

        elif achievement.requirement_type == "total_appointments":
            # Check total lifetime appointments
            total = db.query(func.sum(BarberPerformance.appointments_completed)).filter(
                and_(
                    BarberPerformance.barber_id == user_id,
                    BarberPerformance.barbershop_id == barbershop_id
                )
            ).scalar() or 0

            return total >= achievement.requirement_value

        return False

    @staticmethod
    def get_user_achievements(
        db: Session,
        user_id: int,
        barbershop_id: int
    ) -> Dict[str, Any]:
        """Get all achievements for a user with progress."""
        # Get earned achievements
        earned = db.query(UserAchievement).filter(
            and_(
                UserAchievement.user_id == user_id,
                UserAchievement.barbershop_id == barbershop_id
            )
        ).all()

        # Get all achievements
        all_achievements = db.query(Achievement).filter(Achievement.is_active == True).all()

        # Calculate total points
        total_points = sum(
            db.query(Achievement).filter(Achievement.id == ua.achievement_id).first().points
            for ua in earned
        )

        return {
            "total_achievements": len(all_achievements),
            "earned_achievements": len(earned),
            "total_points": total_points,
            "earned": [
                {
                    "achievement": {
                        "code": db.query(Achievement).filter(Achievement.id == ua.achievement_id).first().code,
                        "name": db.query(Achievement).filter(Achievement.id == ua.achievement_id).first().name,
                        "description": db.query(Achievement).filter(Achievement.id == ua.achievement_id).first().description,
                        "icon": db.query(Achievement).filter(Achievement.id == ua.achievement_id).first().icon,
                        "rarity": db.query(Achievement).filter(Achievement.id == ua.achievement_id).first().rarity,
                        "points": db.query(Achievement).filter(Achievement.id == ua.achievement_id).first().points
                    },
                    "earned_at": ua.earned_at,
                    "is_viewed": ua.is_viewed
                }
                for ua in earned
            ],
            "available": [
                {
                    "code": ach.code,
                    "name": ach.name,
                    "description": ach.description,
                    "icon": ach.icon,
                    "rarity": ach.rarity,
                    "points": ach.points,
                    "requirement_type": ach.requirement_type,
                    "requirement_value": ach.requirement_value
                }
                for ach in all_achievements
                if ach.id not in {ua.achievement_id for ua in earned}
            ]
        }
