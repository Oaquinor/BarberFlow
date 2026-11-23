"""Index tenant-scoped role listings and counts on users."""

from alembic import op
import sqlalchemy as sa


revision = "026_users_client_listing"
down_revision = "025_perf_day_unique"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_users_tenant_role_deleted_id"


def upgrade():
    op.create_index(
        INDEX_NAME,
        "users",
        ["barbershop_id", "role", "is_deleted", "id"],
    )


def downgrade():
    indexes = sa.inspect(op.get_bind()).get_indexes("users")
    has_independent_foreign_key_index = any(
        index["name"] != INDEX_NAME
        and index.get("column_names")
        and index["column_names"][0] == "barbershop_id"
        for index in indexes
    )
    if not has_independent_foreign_key_index:
        # MySQL requires a leftmost barbershop_id index for users' tenant FK.
        # Preserve that constraint while removing this migration's wider index.
        op.create_index("ix_users_barbershop_id", "users", ["barbershop_id"])
    op.drop_index(INDEX_NAME, table_name="users")
