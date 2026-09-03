"""Add barber availability table

Revision ID: 004_add_barber_availability
Revises: 003_add_personalization
Create Date: 2026-06-06
"""

from alembic import op
import sqlalchemy as sa


revision = "004_add_barber_availability"
down_revision = "003_add_personalization"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "barber_availabilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("barber_id", sa.Integer(), nullable=False),
        sa.Column("slot_start", sa.DateTime(), nullable=False),
        sa.Column("slot_end", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_booked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"]),
        sa.ForeignKeyConstraint(["barber_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("barber_id", "slot_start", name="uq_barber_slot_start"),
    )

    op.create_index("ix_barber_availabilities_barbershop_id", "barber_availabilities", ["barbershop_id"], unique=False)
    op.create_index("ix_barber_availabilities_barber_id", "barber_availabilities", ["barber_id"], unique=False)
    op.create_index("ix_barber_availabilities_slot_start", "barber_availabilities", ["slot_start"], unique=False)


def downgrade():
    op.drop_index("ix_barber_availabilities_slot_start", table_name="barber_availabilities")
    op.drop_index("ix_barber_availabilities_barber_id", table_name="barber_availabilities")
    op.drop_index("ix_barber_availabilities_barbershop_id", table_name="barber_availabilities")
    op.drop_table("barber_availabilities")
