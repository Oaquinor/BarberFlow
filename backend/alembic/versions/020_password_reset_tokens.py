"""Add one-time password recovery tokens."""

from alembic import op
import sqlalchemy as sa


revision = "020_password_reset_tokens"
down_revision = "019_platform_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),
    )
    op.create_index(
        "ix_password_reset_tokens_user_active",
        "password_reset_tokens", ["user_id", "consumed_at", "revoked_at"],
    )
    op.create_index(
        "ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"],
    )


def downgrade():
    connection = op.get_bind()
    active_tokens = connection.execute(sa.text(
        "SELECT COUNT(*) FROM password_reset_tokens "
        "WHERE consumed_at IS NULL AND revoked_at IS NULL AND expires_at > CURRENT_TIMESTAMP"
    )).scalar_one()
    if active_tokens:
        raise RuntimeError(
            "Refusing to drop active password recovery tokens; allow them to expire before downgrade."
        )
    op.drop_table("password_reset_tokens")
