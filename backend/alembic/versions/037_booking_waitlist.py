"""Persist tenant-scoped public booking waitlist requests."""

from alembic import op
import sqlalchemy as sa

revision = "037_booking_waitlist"
down_revision = "036_booking_answers"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "booking_waitlist_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("request_key_hash", sa.String(length=64), nullable=False),
        sa.Column("service_name_snapshot", sa.String(length=100), nullable=False),
        sa.Column("barber_id", sa.Integer(), nullable=True),
        sa.Column("barber_name_snapshot", sa.String(length=201), nullable=True),
        sa.Column("client_name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("preferred_date_start", sa.Date(), nullable=True),
        sa.Column("preferred_date_end", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="new", nullable=False),
        sa.Column("contacted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["barber_id"], ["users.id"]),
        sa.UniqueConstraint(
            "barbershop_id", "request_key_hash", name="uq_waitlist_shop_request_key"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('new', 'contacted', 'closed')", name="ck_waitlist_status"),
    )
    op.create_index(
        "ix_waitlist_shop_status_created",
        "booking_waitlist_entries",
        ["barbershop_id", "status", "created_at"],
    )
    op.create_index(
        "ix_waitlist_shop_phone",
        "booking_waitlist_entries",
        ["barbershop_id", "phone"],
    )


def downgrade():
    op.drop_index("ix_waitlist_shop_phone", table_name="booking_waitlist_entries")
    op.drop_index("ix_waitlist_shop_status_created", table_name="booking_waitlist_entries")
    op.drop_table("booking_waitlist_entries")
