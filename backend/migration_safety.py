"""Guard Alembic downgrades against deleting persisted application data."""

from sqlalchemy import text


def require_empty_tables(connection, *table_names: str) -> None:
    """Refuse to drop any named table that still contains rows."""
    for table_name in table_names:
        count = connection.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar_one()
        if count:
            raise RuntimeError(
                f"Refusing to drop {table_name}: it contains {count} row(s). "
                "Export or archive the data before reverting this migration."
            )


def require_no_matching_rows(connection, table_name: str, predicate: str, description: str) -> None:
    """Refuse to remove a column while it contains values matching a fixed SQL predicate."""
    count = connection.execute(text(
        f"SELECT COUNT(*) FROM `{table_name}` WHERE {predicate}"
    )).scalar_one()
    if count:
        raise RuntimeError(
            f"Refusing to remove {description}: {count} row(s) contain data. "
            "Export or archive the data before reverting this migration."
        )
