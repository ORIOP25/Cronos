import importlib.util
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
BASELINE = VERSIONS / "0001_scheduler_v1_baseline.py"


def _load_migration(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_history_has_one_frozen_baseline():
    assert sorted(VERSIONS.glob("*.py")) == [BASELINE]
    baseline = _load_migration(BASELINE, "baseline_migration")
    assert baseline.revision == "0001_scheduler_v1_baseline"
    assert baseline.down_revision is None
    source = BASELINE.read_text(encoding="utf-8")
    for forbidden in ("app.models", "Base.metadata", "create_all", "drop_all"):
        assert forbidden not in source


def test_baseline_contains_native_tenant_integrity():
    sql = _load_migration(BASELINE, "baseline_migration").BASELINE_SQL

    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "resolve_principal" in sql
    assert "FOREIGN KEY (organization_id" in sql
    assert "UNIQUE (organization_id, id)" in sql
    assert "cronos_app" in sql
    assert "organization_membership_id integer NOT NULL" in sql
    assert "CREATE POLICY tenant_isolation" in sql


def test_baseline_installs_the_final_scheduler_v1_state():
    sql = _load_migration(BASELINE, "baseline_migration").BASELINE_SQL

    assert "list_scheduler_v1_jobs_for_executor" in sql
    assert "scheduler_v1_queue_position" in sql
    assert "scheduler_lesson_log_v1" in sql
    assert "'REVOKED'" in sql
    assert "privacy_version" in sql
    assert "result_code" in sql
    assert "withdrawn_at" in sql
    assert "trg_organization_legal_acceptance_append_only" in sql
    assert "tutorial_telemetry" not in sql


def test_downgrade_preserves_the_alembic_version_table():
    source = BASELINE.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:")[1]

    assert "alembic_version" in downgrade
    assert "DROP SCHEMA IF EXISTS app_security CASCADE" in downgrade


def test_baseline_has_no_retired_scheduler_tables():
    sql = _load_migration(BASELINE, "baseline_migration").BASELINE_SQL
    for table in (
        "schedule_generation_job",
        "schedule_drafts",
        "schedule_draft_blocks",
        "schedule_diff_entries",
        "active_schedule_blocks",
        "planned_recovery_links",
        "occurrence_operational_event",
        "teacher_endpoint_operational_event",
    ):
        assert f"CREATE TABLE public.{table} " not in sql
    assert "pending_draft_id" not in sql
