"""Add private booking tokens for public appointment tracking."""

from alembic import op
import sqlalchemy as sa
from migration_safety import require_no_matching_rows


revision = "006_appointment_tracking_token"
down_revision = "005_user_support_flags"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "appointments",
        sa.Column("tracking_token_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_appointments_tracking_token_hash",
        "appointments",
        ["tracking_token_hash"],
        unique=True,
    )


def downgrade():
    require_no_matching_rows(
        op.get_bind(), 'appointments', 'tracking_token_hash IS NOT NULL', 'private appointment tracking tokens',
    )
    op.drop_index("ix_appointments_tracking_token_hash", table_name="appointments")
    op.drop_column("appointments", "tracking_token_hash")
