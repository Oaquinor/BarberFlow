"""Add append-only owner operating expenses."""

from alembic import op
import sqlalchemy as sa

revision = "040_operating_expenses"
down_revision = "039_retail_sales"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cash_register_closes",
        sa.Column("opening_cash_cents", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "operating_expenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("payment_method", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("spent_at", sa.DateTime(), nullable=False),
        sa.Column("request_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("barbershop_id", "request_key_hash", name="uq_expense_shop_request"),
        sa.CheckConstraint("amount_cents > 0", name="ck_expense_amount_positive"),
        sa.CheckConstraint(
            "category IN ('rent','utilities','payroll','commission','supplies','maintenance',"
            "'marketing','administrative','internet','water','electricity','other')",
            name="ck_operating_expense_category",
        ),
        sa.CheckConstraint(
            "payment_method IN ('cash','card','transfer','other')",
            name="ck_operating_expense_method",
        ),
    )
    op.create_index("ix_expense_shop_spent", "operating_expenses", ["barbershop_id", "spent_at"])
    op.create_index(
        "ix_expense_shop_category_spent",
        "operating_expenses",
        ["barbershop_id", "category", "spent_at"],
    )


def downgrade():
    op.drop_index("ix_expense_shop_category_spent", table_name="operating_expenses")
    op.drop_index("ix_expense_shop_spent", table_name="operating_expenses")
    op.drop_table("operating_expenses")
    op.drop_column("cash_register_closes", "opening_cash_cents")
