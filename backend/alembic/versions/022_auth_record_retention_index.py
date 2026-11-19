"""Index authentication throttle cleanup timestamps."""

from alembic import op


revision = "022_auth_record_retention_index"
down_revision = "021_user_auth_version"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_login_attempts_last_attempt_at", "login_attempts", ["last_attempt_at"],
    )


def downgrade():
    op.drop_index("ix_login_attempts_last_attempt_at", table_name="login_attempts")
