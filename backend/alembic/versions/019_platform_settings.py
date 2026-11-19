"""Add database-backed public registration and free period settings."""

from alembic import op
import sqlalchemy as sa


revision = "019_platform_settings"
down_revision = "018_barber_availability_blocks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "platform_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("registrations_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("free_period_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("free_period_days BETWEEN 1 AND 365", name="ck_platform_settings_period_days"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(sa.text(
        "INSERT INTO platform_settings "
        "(id, registrations_enabled, free_period_days, created_at, updated_at, is_deleted) "
        "VALUES (1, 1, 30, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)"
    ))


def downgrade():
    connection = op.get_bind()
    row = connection.execute(sa.text(
        "SELECT registrations_enabled, free_period_days FROM platform_settings WHERE id = 1"
    )).first()
    if row and (not row.registrations_enabled or row.free_period_days != 30):
        raise RuntimeError(
            "Refusing to drop customized platform settings; export or restore the default values before downgrade."
        )
    op.drop_table("platform_settings")
