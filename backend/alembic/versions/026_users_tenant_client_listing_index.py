"""Index tenant-scoped role listings and counts on users."""

from alembic import op


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
    op.drop_index(INDEX_NAME, table_name="users")
