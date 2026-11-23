"""Persist support contact messages and admin status changes."""

from alembic import op
import sqlalchemy as sa


revision = "023_persist_support_tickets"
down_revision = "022_auth_record_retention_index"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=True),
        sa.Column("sender_name", sa.String(length=120), nullable=False),
        sa.Column("sender_email", sa.String(length=320), nullable=True),
        sa.Column("sender_phone", sa.String(length=30), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("notification_sent", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["barbershop_id"], ["barbershops.id"], ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_tickets_barbershop_id", "support_tickets", ["barbershop_id"],
    )
    op.create_index(
        "ix_support_tickets_status_created", "support_tickets", ["status", "created_at"],
    )


def downgrade():
    connection = op.get_bind()
    ticket_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM support_tickets")
    ).scalar_one()
    if ticket_count:
        raise RuntimeError(
            "Refusing to drop support_tickets because it contains support history; "
            "export or archive the tickets before reverting this migration."
        )
    # Dropping the table also removes its indexes and foreign key together.
    # MySQL refuses to drop the barbershop_id index while the FK still uses it.
    op.drop_table("support_tickets")
