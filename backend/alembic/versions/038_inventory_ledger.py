"""Add tenant inventory catalog and append-only stock ledger."""

from alembic import op
import sqlalchemy as sa

revision = "038_inventory_ledger"
down_revision = "037_booking_waitlist"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("barcode", sa.String(80), nullable=True),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("unit_cost_cents", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("stock_minimum", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("barbershop_id", "barcode", name="uq_inventory_shop_barcode"),
        sa.CheckConstraint("unit_cost_cents >= 0", name="ck_inventory_product_cost_nonnegative"),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_inventory_product_price_nonnegative"),
        sa.CheckConstraint("stock_quantity >= 0", name="ck_inventory_product_stock_nonnegative"),
        sa.CheckConstraint("stock_minimum >= 0", name="ck_inventory_product_minimum_nonnegative"),
    )
    op.create_index(
        "ix_inventory_shop_active_name",
        "inventory_products",
        ["barbershop_id", "is_active", "name"],
    )
    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("unit_cost_cents", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("request_key_hash", sa.String(64), nullable=False),
        sa.Column("request_payload_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["inventory_products.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "barbershop_id", "request_key_hash", name="uq_inventory_shop_request_key"
        ),
        sa.CheckConstraint("quantity_delta != 0", name="ck_inventory_movement_nonzero"),
        sa.CheckConstraint("unit_cost_cents >= 0", name="ck_inventory_movement_cost_nonnegative"),
    )
    op.create_index(
        "ix_inventory_movement_shop_created", "inventory_movements", ["barbershop_id", "created_at"]
    )
    op.create_index(
        "ix_inventory_movement_product_created", "inventory_movements", ["product_id", "created_at"]
    )


def downgrade():
    op.drop_index("ix_inventory_movement_product_created", table_name="inventory_movements")
    op.drop_index("ix_inventory_movement_shop_created", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_index("ix_inventory_shop_active_name", table_name="inventory_products")
    op.drop_table("inventory_products")
