import importlib.util
import inspect
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
INITIAL = VERSIONS / "0001_initial.py"
SECURITY = VERSIONS / "0002_security_hardening.py"
REMOVE_AUTO_CONFIRM = VERSIONS / "0003_remove_auto_confirm_settings.py"
FOUNDATION_TELEMETRY = VERSIONS / "0004_foundation_telemetry.py"
AUTOMATIC_HOLIDAYS = VERSIONS / "0005_automatic_holidays.py"
NON_MUTATING_ENSURE_USER = VERSIONS / "0006_non_mutating_ensure_user.py"
LEGACY_REVISION_ALIAS = VERSIONS / "0007_legacy_revision_alias.py"
LEGACY_REVISION_REPAIR = VERSIONS / "0007_legacy_revision_repair.py"
LEGAL_ACCEPTANCE = VERSIONS / "0007_legal_acceptance.py"
REMOVE_TUTORIAL_TELEMETRY = VERSIONS / "0008_remove_tutorial_telemetry.py"
INTEGRATED_LEGAL_ACCEPTANCE = VERSIONS / "0009_integrated_legal_acceptance.py"
SCHEDULER_FAILURE_REFERENCE = VERSIONS / "0010_scheduler_failure_reference.py"


def _load_initial():
    spec = importlib.util.spec_from_file_location("initial_migration", INITIAL)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _load_migration(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
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
        AUTOMATIC_HOLIDAYS,
        NON_MUTATING_ENSURE_USER,
        LEGACY_REVISION_ALIAS,
        LEGACY_REVISION_REPAIR,
        LEGAL_ACCEPTANCE,
        REMOVE_TUTORIAL_TELEMETRY,
        INTEGRATED_LEGAL_ACCEPTANCE,
        SCHEDULER_FAILURE_REFERENCE,
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


def test_legacy_revision_path_reaches_legal_acceptance():
    alias = _load_migration(LEGACY_REVISION_ALIAS, "legacy_revision_alias")
    repair = _load_migration(LEGACY_REVISION_REPAIR, "legacy_revision_repair")
    legal = _load_migration(LEGAL_ACCEPTANCE, "legal_acceptance")

    assert alias.revision == "0007_qualify_user_rls_policy"
    assert alias.down_revision == NON_MUTATING_ENSURE_USER.stem
    assert repair.down_revision == alias.revision
    assert legal.down_revision == repair.revision
    assert "IF NOT EXISTS" in inspect.getsource(repair.upgrade)


def test_integrated_legal_acceptance_downgrade_is_data_preserving():
    source = (VERSIONS / "0009_integrated_legal_acceptance.py").read_text(encoding="utf-8")

    assert "incompatible" in source
    assert "no evidence was changed" in source
    assert "drop_column" in source
