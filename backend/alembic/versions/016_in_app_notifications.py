"""Persist tenant scoped inbox notifications."""

from alembic import op
import sqlalchemy as sa

revision = "016_in_app_notifications"
down_revision = "015_barber_commissions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "in_app_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=191), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recipient_user_id", "dedupe_key", name="uq_in_app_notification_recipient_key"),
    )
    op.create_index(
        "ix_in_app_notifications_recipient_unread", "in_app_notifications",
        ["recipient_user_id", "read_at", "created_at"],
    )
    op.create_index(
        "ix_in_app_notifications_shop_created", "in_app_notifications",
        ["barbershop_id", "created_at"],
    )


def downgrade():
    op.drop_table("in_app_notifications")
