"""Add verified customer accounts and tenant CRM links."""

from alembic import op
import sqlalchemy as sa


revision = "033_client_accounts"
down_revision = "032_cancellation_window"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_account_verifications",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_client_account_verifications_token_hash"),
    )
    op.create_index(
        "ix_client_account_verifications_user_active",
        "client_account_verifications", ["user_id", "consumed_at", "revoked_at"],
    )
    op.create_index(
        "ix_client_account_verifications_expires_at",
        "client_account_verifications", ["expires_at"],
    )

    op.create_table(
        "client_account_shop_links",
        sa.Column("account_user_id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("crm_client_user_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["crm_client_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_user_id", "barbershop_id", name="uq_client_account_shop"),
        sa.UniqueConstraint("crm_client_user_id", name="uq_client_account_crm_client"),
    )
    op.create_index(
        "ix_client_account_shop_lookup",
        "client_account_shop_links", ["barbershop_id", "account_user_id"],
    )


def downgrade():
    op.drop_index("ix_client_account_shop_lookup", table_name="client_account_shop_links")
    op.drop_table("client_account_shop_links")
    op.drop_index("ix_client_account_verifications_expires_at", table_name="client_account_verifications")
    op.drop_index("ix_client_account_verifications_user_active", table_name="client_account_verifications")
    op.drop_table("client_account_verifications")
