"""Prevent duplicate daily performance rows for a barber."""

from alembic import op
import sqlalchemy as sa

revision = "025_unique_barber_performance_day"
down_revision = "024_service_name_100"
branch_labels = None
depends_on = None


CONSTRAINT_NAME = "uq_barber_performance_tenant_barber_date"


def upgrade():
    connection = op.get_bind()
    duplicate_groups = connection.execute(sa.text("""
        SELECT COUNT(*)
        FROM (
            SELECT barbershop_id, barber_id, `date`
            FROM barber_performances
            GROUP BY barbershop_id, barber_id, `date`
            HAVING COUNT(*) > 1
        ) AS duplicate_performance_days
        """)).scalar_one()
    if duplicate_groups:
        raise RuntimeError(
            "Cannot add daily performance uniqueness: barber_performances contains "
            f"{duplicate_groups} duplicate tenant/barber/date group(s). Resolve them "
            "before retrying; this migration does not delete or merge performance data."
        )

    op.create_unique_constraint(
        CONSTRAINT_NAME,
        "barber_performances",
        ["barbershop_id", "barber_id", "date"],
    )


def downgrade():
    op.drop_constraint(CONSTRAINT_NAME, "barber_performances", type_="unique")
