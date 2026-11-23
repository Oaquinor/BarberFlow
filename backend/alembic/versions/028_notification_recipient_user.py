"""Track notification recipients for send-time availability checks."""

from alembic import op
import sqlalchemy as sa


revision = "028_notification_recipient_user"
down_revision = "027_appointment_monthly_usage"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "notification_deliveries",
        sa.Column("recipient_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_notification_deliveries_recipient_user_id_users",
        "notification_deliveries",
        "users",
        ["recipient_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_notification_deliveries_recipient_user_id",
        "notification_deliveries",
        ["recipient_user_id"],
    )


def downgrade():
    op.drop_index(
        "ix_notification_deliveries_recipient_user_id",
        table_name="notification_deliveries",
    )
    op.drop_constraint(
        "fk_notification_deliveries_recipient_user_id_users",
        "notification_deliveries",
        type_="foreignkey",
    )
    op.drop_column("notification_deliveries", "recipient_user_id")
