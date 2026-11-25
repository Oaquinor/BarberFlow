"""Add tenant-configurable Style Passport retention."""

from alembic import op
import sqlalchemy as sa


revision = "042_style_passport_retention"
down_revision = "041_style_passport"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "barbershops",
        sa.Column("style_passport_retention_days", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_barbershop_style_passport_retention",
        "barbershops",
        "style_passport_retention_days IS NULL OR style_passport_retention_days IN (90, 180, 365, 730)",
    )


def downgrade():
    op.drop_constraint(
        "ck_barbershop_style_passport_retention", "barbershops", type_="check"
    )
    op.drop_column("barbershops", "style_passport_retention_days")
