"""Persist barber absences and block future slot creation during those ranges."""

from alembic import op
import sqlalchemy as sa


revision = "018_barber_availability_blocks"
down_revision = "017_notification_delivery_outbox"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "barber_availability_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("barber_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["barber_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("starts_at < ends_at", name="ck_availability_block_range"),
    )
    op.create_index(
        "ix_availability_blocks_barber_range", "barber_availability_blocks",
        ["barber_id", "starts_at", "ends_at"],
    )
    op.create_index(
        "ix_availability_blocks_tenant", "barber_availability_blocks",
        ["barbershop_id", "barber_id"],
    )


def downgrade():
    connection = op.get_bind()
    row_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM barber_availability_blocks")
    ).scalar_one()
    if row_count:
        raise RuntimeError(
            "Refusing to drop barber_availability_blocks because it contains absence history; "
            "archive or export those rows before reverting this migration."
        )
    op.drop_table("barber_availability_blocks")
