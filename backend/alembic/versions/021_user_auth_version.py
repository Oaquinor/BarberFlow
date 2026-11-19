"""Allow immediate revocation of all access tokens after credential changes."""

from alembic import op
import sqlalchemy as sa


revision = "021_user_auth_version"
down_revision = "020_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    connection = op.get_bind()
    changed_accounts = connection.execute(sa.text(
        "SELECT COUNT(*) FROM users WHERE auth_version <> 0"
    )).scalar_one()
    if changed_accounts:
        raise RuntimeError(
            "Refusing to remove active auth-version revocation state; wait for access tokens to expire "
            "and reconcile all changed account versions before downgrade."
        )
    op.drop_column("users", "auth_version")
