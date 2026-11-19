"""Persist failed login attempt counters and temporary locks."""

from alembic import op
import sqlalchemy as sa


revision = "009_login_attempt_limits"
down_revision = "008_payments_cash_register"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_started_at", sa.DateTime(), nullable=False),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_login_attempts_key_hash"),
    )
    op.create_index("ix_login_attempts_locked_until", "login_attempts", ["locked_until"])


def downgrade():
    op.drop_index("ix_login_attempts_locked_until", table_name="login_attempts")
    op.drop_table("login_attempts")
