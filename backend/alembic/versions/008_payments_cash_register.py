"""Persist appointment payments and daily cash register closes."""

from alembic import op
import sqlalchemy as sa


revision = "008_payments_cash_register"
down_revision = "007_refresh_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("barbershop_id", sa.Integer(), sa.ForeignKey("barbershops.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("barber_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("tip_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("appointment_id", name="uq_payments_appointment_id"),
    )
    op.create_index("ix_payments_shop_received", "payments", ["barbershop_id", "received_at"])
    op.create_index("ix_payments_barber_received", "payments", ["barber_id", "received_at"])

    op.create_table(
        "cash_register_closes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("barbershop_id", sa.Integer(), sa.ForeignKey("barbershops.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("closed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("business_date", sa.DateTime(), nullable=False),
        sa.Column("expected_cash_cents", sa.Integer(), nullable=False),
        sa.Column("declared_cash_cents", sa.Integer(), nullable=False),
        sa.Column("difference_cents", sa.Integer(), nullable=False),
        sa.Column("payment_count", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("barbershop_id", "closed_by_user_id", "business_date", name="uq_cash_close_scope_date"),
    )
    op.create_index("ix_cash_close_shop_date", "cash_register_closes", ["barbershop_id", "business_date"])


def downgrade():
    op.drop_table("cash_register_closes")
    op.drop_table("payments")
