"""MySQL checks for migration rollback data-retention guards."""

import pytest

from app.models import AuditLog
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
