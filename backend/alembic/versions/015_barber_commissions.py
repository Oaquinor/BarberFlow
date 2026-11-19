"""Accrue and settle barber commissions from completed service payments."""

from alembic import op
import sqlalchemy as sa

revision = "015_barber_commissions"
down_revision = "014_align_mysql_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("commission_rate_basis_points", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "barber_commissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("barber_id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("rate_basis_points", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("accrued_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("paid_by_user_id", sa.Integer(), nullable=True),
        sa.Column("payment_method", sa.String(length=20), nullable=True),
        sa.Column("payment_reference", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["barber_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["paid_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id", name="uq_barber_commissions_payment"),
    )
    op.create_index(
        "ix_barber_commissions_shop_barber_status", "barber_commissions",
        ["barbershop_id", "barber_id", "status"],
    )


def downgrade():
    op.drop_table("barber_commissions")
    op.drop_column("users", "commission_rate_basis_points")
