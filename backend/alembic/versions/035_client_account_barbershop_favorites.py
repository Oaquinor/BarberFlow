"""Allow customers to save barberies as favorites."""

from alembic import op


revision = "035_shop_favorites"
down_revision = "034_client_account_favorites"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_client_account_favorites_type",
        "client_account_favorites",
        type_="check",
    )
    op.create_check_constraint(
        "ck_client_account_favorites_type",
        "client_account_favorites",
        "target_type IN ('barber', 'service', 'barbershop')",
    )


def downgrade():
    # A backward-compatible superset preserves already saved barber shops.
    pass
