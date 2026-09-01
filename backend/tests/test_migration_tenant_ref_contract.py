import importlib.util
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
INITIAL = VERSIONS / "0001_initial.py"
SECURITY = VERSIONS / "0002_security_hardening.py"
REMOVE_AUTO_CONFIRM = VERSIONS / "0003_remove_auto_confirm_settings.py"
FOUNDATION_TELEMETRY = VERSIONS / "0004_foundation_telemetry.py"
RECLAIM_DELETED_IDENTITY = VERSIONS / "0005_reclaim_deleted_clerk_identity.py"
FIX_BOOTSTRAP_MEMBERSHIP_AUDIT = VERSIONS / "0006_fix_bootstrap_membership_audit.py"
QUALIFY_USER_RLS_POLICY = VERSIONS / "0007_qualify_user_rls_policy.py"


def _load_initial():
    spec = importlib.util.spec_from_file_location("initial_migration", INITIAL)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_history_has_expected_revisions():
    revisions = sorted(VERSIONS.glob("*.py"))
    assert revisions == [
        INITIAL,
        SECURITY,
        REMOVE_AUTO_CONFIRM,
        FOUNDATION_TELEMETRY,
        RECLAIM_DELETED_IDENTITY,
        FIX_BOOTSTRAP_MEMBERSHIP_AUDIT,
        QUALIFY_USER_RLS_POLICY,
    ]
    source = INITIAL.read_text(encoding="utf-8")
    assert _load_initial().down_revision is None
    for forbidden in ("app.models", "Base.metadata", "create_all", "drop_all", "CREATE TRIGGER"):
        assert forbidden not in source


def test_initial_revision_contains_native_tenant_integrity():
    sql = "\n".join(_load_initial().UPGRADE_SQL)
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "resolve_principal" in sql
    assert "FOREIGN KEY (organization_id" in sql
    assert "UNIQUE (organization_id, id)" in sql
    assert "cronos_app" in sql
    assert "organization_membership_id INTEGER NOT NULL" in sql
