"""Allow appointment service snapshots to hold full catalog names."""

from alembic import op
import sqlalchemy as sa


revision = "024_service_name_100"
down_revision = "023_persist_support_tickets"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "appointments",
        "service_type",
        existing_type=sa.String(length=50),
        type_=sa.String(length=100),
        existing_nullable=False,
    )


def downgrade():
    connection = op.get_bind()
    long_names = connection.execute(sa.text(
        "SELECT COUNT(*) FROM appointments WHERE CHAR_LENGTH(service_type) > 50"
    )).scalar_one()
    if long_names:
        raise RuntimeError(
            "Refusing to shorten appointment service names because values exceed 50 characters; "
            "export or archive affected appointments before reverting this migration."
        )
    op.alter_column(
        "appointments",
        "service_type",
        existing_type=sa.String(length=100),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
