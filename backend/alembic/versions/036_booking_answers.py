"""Persist customer consultation answers separately from free-form notes."""

from alembic import op
import sqlalchemy as sa


revision = "036_booking_answers"
down_revision = "035_shop_favorites"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "appointments",
        sa.Column("booking_answers", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("appointments", "booking_answers")
