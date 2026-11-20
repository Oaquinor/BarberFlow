"""Store the originating tenant currency on every affiliate commission."""

from alembic import op
import sqlalchemy as sa
from migration_safety import require_empty_tables

revision = "013_commission_currency"
down_revision = "012_subscription_payments"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("commissions", sa.Column("currency", sa.String(length=3), nullable=True))
    op.execute(sa.text(
        "UPDATE commissions c JOIN barbershops b ON b.id = c.barbershop_id "
        "SET c.currency = b.currency WHERE c.currency IS NULL"
    ))
    op.alter_column("commissions", "currency", existing_type=sa.String(length=3), nullable=False)


def downgrade():
    require_empty_tables(op.get_bind(), 'commissions')
    op.drop_column("commissions", "currency")
