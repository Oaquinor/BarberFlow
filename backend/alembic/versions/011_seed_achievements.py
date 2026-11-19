"""Seed the achievement catalog used by the barber portal."""

from alembic import op
import sqlalchemy as sa

revision = "011_seed_achievements"
down_revision = "010_audit_logs"
branch_labels = None
depends_on = None


ACHIEVEMENTS = [
    {"code": "FIRST_DAY", "name": "Primer servicio", "description": "Completa tu primer servicio.", "icon": "🎉", "category": "milestone", "requirement_type": "appointments", "requirement_value": 1, "points": 10, "rarity": "common", "is_active": True},
    {"code": "WEEK_WARRIOR", "name": "Guerrero semanal", "description": "Trabaja 7 días consecutivos.", "icon": "🔥", "category": "streak", "requirement_type": "streak", "requirement_value": 7, "points": 50, "rarity": "rare", "is_active": True},
    {"code": "MONTH_MASTER", "name": "Maestro del mes", "description": "Trabaja 30 días consecutivos.", "icon": "👑", "category": "streak", "requirement_type": "streak", "requirement_value": 30, "points": 200, "rarity": "epic", "is_active": True},
    {"code": "BUSY_BEE", "name": "Abeja ocupada", "description": "Completa 10 citas en un día.", "icon": "🐝", "category": "productivity", "requirement_type": "daily_appointments", "requirement_value": 10, "points": 30, "rarity": "rare", "is_active": True},
    {"code": "SUPER_BARBER", "name": "Super barbero", "description": "Completa 15 citas en un día.", "icon": "⚡", "category": "productivity", "requirement_type": "daily_appointments", "requirement_value": 15, "points": 75, "rarity": "epic", "is_active": True},
    {"code": "CENTURY_CLUB", "name": "Club de los 100", "description": "Completa 100 citas.", "icon": "💯", "category": "milestone", "requirement_type": "total_appointments", "requirement_value": 100, "points": 100, "rarity": "rare", "is_active": True},
    {"code": "FIVE_HUNDRED", "name": "Quinientos", "description": "Completa 500 citas.", "icon": "🌟", "category": "milestone", "requirement_type": "total_appointments", "requirement_value": 500, "points": 500, "rarity": "epic", "is_active": True},
    {"code": "LEGEND", "name": "Leyenda", "description": "Completa 1,000 citas.", "icon": "🏆", "category": "milestone", "requirement_type": "total_appointments", "requirement_value": 1000, "points": 1000, "rarity": "legendary", "is_active": True},
]


def upgrade():
    achievements = sa.table(
        "achievements",
        sa.column("code", sa.String), sa.column("name", sa.String),
        sa.column("description", sa.String), sa.column("icon", sa.String),
        sa.column("category", sa.String), sa.column("requirement_type", sa.String),
        sa.column("requirement_value", sa.Integer), sa.column("points", sa.Integer),
        sa.column("rarity", sa.String), sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(achievements, ACHIEVEMENTS)


def downgrade():
    codes = [item["code"] for item in ACHIEVEMENTS]
    quoted_codes = ",".join(f"'{code}'" for code in codes)
    op.execute(sa.text(
        "DELETE FROM achievements WHERE code IN (" + quoted_codes + ") "
        "AND id NOT IN (SELECT achievement_id FROM user_achievements)"
    ))
