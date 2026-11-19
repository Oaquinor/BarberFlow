"""Align MySQL constraints and indexes with SQLAlchemy models.

Backfill legacy NULLs before enforcing non-null model invariants and remove
redundant non-unique indexes beside existing unique constraints.
"""

from alembic import op
import sqlalchemy as sa


revision = "014_align_mysql_schema"
down_revision = "013_commission_currency"
branch_labels = None
depends_on = None


NON_NULL_COLUMNS = (
    ("achievements", "created_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("achievements", "updated_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("achievements", "is_deleted", sa.Boolean(), "0"),
    ("affiliates", "created_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("affiliates", "updated_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("affiliates", "is_deleted", sa.Boolean(), "0"),
    ("appointments", "created_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("appointments", "updated_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("appointments", "is_deleted", sa.Boolean(), "0"),
    ("barber_performances", "created_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("barber_performances", "updated_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("barber_performances", "is_deleted", sa.Boolean(), "0"),
    ("barbershops", "is_active", sa.Boolean(), "1"),
    ("barbershops", "is_verified", sa.Boolean(), "0"),
    ("barbershops", "created_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("barbershops", "updated_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("barbershops", "is_deleted", sa.Boolean(), "0"),
    ("commissions", "created_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("commissions", "updated_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("commissions", "is_deleted", sa.Boolean(), "0"),
    ("services", "created_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("services", "updated_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("services", "is_deleted", sa.Boolean(), "0"),
    ("subscriptions", "created_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("subscriptions", "updated_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("subscriptions", "is_deleted", sa.Boolean(), "0"),
    ("user_achievements", "created_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("user_achievements", "updated_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("user_achievements", "is_deleted", sa.Boolean(), "0"),
    ("users", "is_active", sa.Boolean(), "1"),
    ("users", "is_verified", sa.Boolean(), "0"),
    ("users", "created_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("users", "updated_at", sa.DateTime(), "CURRENT_TIMESTAMP"),
    ("users", "is_deleted", sa.Boolean(), "0"),
)

REDUNDANT_INDEXES = (
    ("achievements", "ix_achievements_code"),
    ("affiliates", "ix_affiliates_email"),
    ("affiliates", "ix_affiliates_code"),
    ("barbershops", "ix_barbershops_slug"),
    ("users", "ix_users_email"),
    ("refresh_sessions", "ix_refresh_sessions_id"),
)

FOREIGN_KEY_INDEXES = (
    ("commissions", "ix_commissions_barbershop_id", "barbershop_id", "commissions_ibfk_2"),
    (
        "user_achievements",
        "ix_user_achievements_barbershop_id",
        "barbershop_id",
        "user_achievements_ibfk_3",
    ),
)


def _create_index_if_missing(table: str, index: str, columns: list[str]) -> None:
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
    if index not in existing:
        op.create_index(index, table, columns)


def upgrade() -> None:
    for table, column, column_type, fallback in NON_NULL_COLUMNS:
        op.execute(sa.text(
            f"UPDATE `{table}` SET `{column}` = {fallback} WHERE `{column}` IS NULL"
        ))
        op.alter_column(
            table,
            column,
            existing_type=column_type,
            existing_nullable=True,
            nullable=False,
        )

    for table, index in REDUNDANT_INDEXES:
        op.drop_index(index, table_name=table)

    _create_index_if_missing("commissions", "ix_commissions_barbershop_id", ["barbershop_id"])
    _create_index_if_missing(
        "user_achievements", "ix_user_achievements_barbershop_id", ["barbershop_id"]
    )


def downgrade() -> None:
    for table, index, column, constraint in FOREIGN_KEY_INDEXES:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.drop_index(index, table_name=table)
        op.create_foreign_key(None, table, "barbershops", [column], ["id"])

    for table, index in REDUNDANT_INDEXES:
        op.create_index(index, table, [index.removeprefix(f"ix_{table}_")])

    for table, column, column_type, _fallback in reversed(NON_NULL_COLUMNS):
        op.alter_column(
            table,
            column,
            existing_type=column_type,
            existing_nullable=False,
            nullable=True,
        )
