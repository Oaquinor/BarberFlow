"""MySQL checks for migration rollback data-retention guards."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models import AuditLog, PlatformSettings
from app.utils.datetime import utc_now_naive
from migration_safety import require_empty_tables


def test_downgrade_guard_refuses_to_drop_audit_history(test_db):
    connection = test_db.connection()
    require_empty_tables(connection, "audit_logs")

    test_db.add(AuditLog(
        action="migration.guard_test",
        entity_type="test",
        occurred_at=utc_now_naive(),
    ))
    test_db.flush()

    with pytest.raises(RuntimeError, match="audit_logs.*contains 1 row"):
        require_empty_tables(connection, "audit_logs")


@pytest.mark.parametrize(
    "settings",
    [
        PlatformSettings(id=1, registrations_enabled=False, free_period_days=30),
        PlatformSettings(id=2, registrations_enabled=True, free_period_days=30),
    ],
    ids=["customized-singleton", "additional-row"],
)
def test_platform_settings_downgrade_refuses_to_drop_saved_settings(
    test_db, monkeypatch, settings,
):
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "019_platform_settings.py"
    spec = importlib.util.spec_from_file_location("migration_019_platform_settings", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    test_db.add(settings)
    test_db.flush()
    dropped_tables = []
    migration.op = SimpleNamespace(
        get_bind=test_db.connection,
        drop_table=dropped_tables.append,
    )

    with pytest.raises(RuntimeError, match="customized or additional platform settings"):
        migration.downgrade()
    assert dropped_tables == []
