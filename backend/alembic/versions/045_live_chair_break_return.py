"""Store the barber's expected return time from a Live Chair break."""

from alembic import op
import sqlalchemy as sa

revision = "045_live_chair_break_return"
down_revision = "044_booking_waitlist_offers"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "barber_live_states",
        sa.Column("expected_return_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column("barber_live_states", "expected_return_at")
