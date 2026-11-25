"""Add expiring single-use waitlist offers."""

from alembic import op
import sqlalchemy as sa

revision = "044_booking_waitlist_offers"
down_revision = "043_barber_live_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "booking_waitlist_offers",
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("waitlist_entry_id", sa.Integer(), nullable=False),
        sa.Column("availability_id", sa.Integer(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'expired', 'cancelled')",
            name="ck_waitlist_offer_status",
        ),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["waitlist_entry_id"], ["booking_waitlist_entries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["availability_id"], ["barber_availabilities.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_waitlist_offer_token_hash"),
        sa.UniqueConstraint("appointment_id", name="uq_waitlist_offer_appointment"),
    )
    op.create_index(
        "ix_waitlist_offer_entry_state",
        "booking_waitlist_offers",
        ["waitlist_entry_id", "status", "expires_at"],
    )
    op.create_index(
        "ix_waitlist_offer_slot_state",
        "booking_waitlist_offers",
        ["availability_id", "status", "expires_at"],
    )


def downgrade():
    op.drop_table("booking_waitlist_offers")
