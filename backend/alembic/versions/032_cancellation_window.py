"""Add a tenant-configurable public booking change window."""

from alembic import op
import sqlalchemy as sa


revision = "032_cancellation_window"
down_revision = "031_booking_questions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "barbershops",
        sa.Column("cancellation_window_hours", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("barbershops", "cancellation_window_hours")
