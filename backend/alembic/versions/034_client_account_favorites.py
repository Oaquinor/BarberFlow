"""Add tenant-scoped customer favorites."""

from alembic import op
import sqlalchemy as sa


revision = "034_client_account_favorites"
down_revision = "033_client_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_account_favorites",
        sa.Column("account_user_id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "target_type IN ('barber', 'service')",
            name="ck_client_account_favorites_type",
        ),
        sa.ForeignKeyConstraint(["account_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_user_id", "barbershop_id", "target_type", "target_id",
            name="uq_client_account_favorite_target",
        ),
    )
    op.create_index(
        "ix_client_account_favorites_owner",
        "client_account_favorites", ["account_user_id", "is_deleted"],
    )


def downgrade():
    # Drop the table as a unit so MySQL can remove dependent indexes/constraints.
    op.drop_table("client_account_favorites")
