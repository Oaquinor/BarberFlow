"""Add tenant-scoped explicit barber availability and break state."""

from alembic import op
import sqlalchemy as sa


revision = "043_barber_live_state"
down_revision = "042_style_passport_retention"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "barber_live_states",
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("barber_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), server_default="available", nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("state IN ('available', 'on_break')", name="ck_barber_live_state"),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"]),
        sa.ForeignKeyConstraint(["barber_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("barber_id", name="uq_barber_live_state_barber"),
    )
    op.create_index("ix_barber_live_states_barbershop_id", "barber_live_states", ["barbershop_id"])
    op.create_index("ix_barber_live_states_barber_id", "barber_live_states", ["barber_id"])


def downgrade():
    # MySQL treats the FK-supporting shop index as required until the
    # constraints/table are removed. DROP TABLE removes both indexes safely.
    op.drop_table("barber_live_states")
