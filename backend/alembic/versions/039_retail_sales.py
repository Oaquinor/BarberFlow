"""Add appointment-free retail sales and link stock movements."""

from alembic import op
import sqlalchemy as sa

revision = "039_retail_sales"
down_revision = "038_inventory_ledger"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "retail_sales",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("sold_by_user_id", sa.Integer(), nullable=False),
        sa.Column("payment_method", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("cost_total_cents", sa.Integer(), nullable=False),
        sa.Column("sold_at", sa.DateTime(), nullable=False),
        sa.Column("request_key_hash", sa.String(64), nullable=False),
        sa.Column("request_payload_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sold_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "barbershop_id", "request_key_hash", name="uq_retail_sale_shop_request"
        ),
        sa.CheckConstraint("subtotal_cents > 0", name="ck_retail_sale_subtotal_positive"),
        sa.CheckConstraint(
            "total_cents = subtotal_cents", name="ck_retail_sale_total_matches_subtotal"
        ),
        sa.CheckConstraint("cost_total_cents >= 0", name="ck_retail_sale_cost_nonnegative"),
    )
    op.create_index("ix_retail_sale_shop_sold", "retail_sales", ["barbershop_id", "sold_at"])
    op.create_index(
        "ix_retail_sale_shop_method_sold",
        "retail_sales",
        ["barbershop_id", "payment_method", "sold_at"],
    )
    op.create_table(
        "retail_sale_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_name_snapshot", sa.String(120), nullable=False),
        sa.Column("barcode_snapshot", sa.String(80), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("unit_cost_cents", sa.Integer(), nullable=False),
        sa.Column("line_total_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["sale_id"], ["retail_sales.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["inventory_products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity > 0", name="ck_retail_sale_line_quantity_positive"),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_retail_sale_line_price_nonnegative"),
        sa.CheckConstraint("unit_cost_cents >= 0", name="ck_retail_sale_line_cost_nonnegative"),
        sa.CheckConstraint("line_total_cents >= 0", name="ck_retail_sale_line_total_nonnegative"),
    )
    op.create_index("ix_retail_sale_line_product", "retail_sale_lines", ["product_id"])
    op.add_column("inventory_movements", sa.Column("retail_sale_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_inventory_movement_retail_sale",
        "inventory_movements",
        "retail_sales",
        ["retail_sale_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_inventory_movement_retail_sale", "inventory_movements", ["retail_sale_id"])


def downgrade():
    op.drop_index("ix_inventory_movement_retail_sale", table_name="inventory_movements")
    op.drop_constraint(
        "fk_inventory_movement_retail_sale", "inventory_movements", type_="foreignkey"
    )
    op.drop_column("inventory_movements", "retail_sale_id")
    op.drop_table("retail_sale_lines")
    op.drop_table("retail_sales")
