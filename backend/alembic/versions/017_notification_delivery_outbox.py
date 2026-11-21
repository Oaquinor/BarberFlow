"""Add the durable MySQL notification delivery outbox."""

from alembic import op
import sqlalchemy as sa


revision = "017_notification_delivery_outbox"
down_revision = "016_in_app_notifications"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=191), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scheduled_for", sa.DateTime(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("barbershop_id", "dedupe_key", name="uq_notification_delivery_dedupe"),
    )
    op.create_index(
        "ix_notification_deliveries_due", "notification_deliveries",
        ["status", "next_attempt_at", "scheduled_for"],
    )
    op.create_index(
        "ix_notification_deliveries_appointment", "notification_deliveries",
        ["appointment_id", "event_type"],
    )


def downgrade():
    connection = op.get_bind()
    row_count = connection.execute(sa.text("SELECT COUNT(*) FROM notification_deliveries")).scalar_one()
    if row_count:
        raise RuntimeError(
            "Refusing to drop notification_deliveries because it contains delivery history; "
            "archive or export those rows before reverting this migration."
        )
    op.drop_table("notification_deliveries")
