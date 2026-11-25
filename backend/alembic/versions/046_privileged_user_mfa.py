"""Add optional TOTP MFA and one-time recovery codes."""

from alembic import op
import sqlalchemy as sa

revision = "046_privileged_user_mfa"
down_revision = "045_live_chair_break_return"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("users", sa.Column("mfa_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("mfa_pending_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("mfa_pending_expires_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("mfa_last_counter", sa.BigInteger(), nullable=True))
    op.create_table(
        "user_mfa_recovery_codes",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
    )
    op.create_index(
        "uq_user_mfa_recovery_codes_user_hash",
        "user_mfa_recovery_codes",
        ["user_id", "code_hash"],
        unique=True,
    )
    op.create_index(
        "ix_user_mfa_recovery_codes_user_unused",
        "user_mfa_recovery_codes",
        ["user_id", "used_at", "is_deleted"],
    )


def downgrade():
    op.drop_index("uq_user_mfa_recovery_codes_user_hash", table_name="user_mfa_recovery_codes")
    op.drop_index("ix_user_mfa_recovery_codes_user_unused", table_name="user_mfa_recovery_codes")
    op.drop_table("user_mfa_recovery_codes")
    op.drop_column("users", "mfa_last_counter")
    op.drop_column("users", "mfa_pending_expires_at")
    op.drop_column("users", "mfa_pending_secret_encrypted")
    op.drop_column("users", "mfa_secret_encrypted")
    op.drop_column("users", "mfa_enabled")
