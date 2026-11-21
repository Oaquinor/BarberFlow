"""Index tenant appointment creation times for monthly usage queries."""

from alembic import op


revision = "027_appointment_monthly_usage"
down_revision = "026_users_client_listing"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_appointments_shop_created_at"


def upgrade():
    op.create_index(INDEX_NAME, "appointments", ["barbershop_id", "created_at"])


def downgrade():
    op.drop_index(INDEX_NAME, table_name="appointments")
