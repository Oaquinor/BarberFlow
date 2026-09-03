"""Add support flag and user feature flags

Revision ID: 005_user_support_flags
Revises: 004_add_barber_availability
Create Date: 2026-06-06
"""

from alembic import op
import sqlalchemy as sa


revision = "005_user_support_flags"
down_revision = "004_add_barber_availability"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    if "support_contact_enabled" not in user_columns:
        op.add_column("users", sa.Column("support_contact_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    tables = set(inspector.get_table_names())
    if "user_feature_flags" not in tables:
        op.create_table(
            "user_feature_flags",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("feature_key", sa.String(length=100), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("user_feature_flags")}
    if "ix_user_feature_flags_user_id" not in indexes:
        op.create_index("ix_user_feature_flags_user_id", "user_feature_flags", ["user_id"], unique=False)
    if "ix_user_feature_flags_feature_key" not in indexes:
        op.create_index("ix_user_feature_flags_feature_key", "user_feature_flags", ["feature_key"], unique=False)


def downgrade():
    op.drop_index("ix_user_feature_flags_feature_key", table_name="user_feature_flags")
    op.drop_index("ix_user_feature_flags_user_id", table_name="user_feature_flags")
    op.drop_table("user_feature_flags")
    op.drop_column("users", "support_contact_enabled")
