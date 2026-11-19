"""Persist externally collected SaaS subscription payments."""

from alembic import op
import sqlalchemy as sa

revision = "012_subscription_payments"
down_revision = "011_seed_achievements"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "subscription_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("method", sa.String(length=40), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", "period_start", "period_end", name="uq_subscription_payment_period"),
    )
    op.create_index("ix_subscription_payments_shop_paid", "subscription_payments", ["barbershop_id", "paid_at"])


def downgrade():
    # MySQL may use the composite index for the barbershop_id foreign key;
    # dropping the table removes its indexes and constraints safely together.
    op.drop_table("subscription_payments")
