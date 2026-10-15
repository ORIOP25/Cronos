import importlib.util
from pathlib import Path

import pytest

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
BASELINE = VERSIONS / "0001_scheduler_v1_baseline.py"
BASELINE_REVISION = "0001_scheduler_v1_baseline"


def _load_migration(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _revision_chain(paths) -> dict[str, object]:
    chain: dict[str, object] = {}
    for path in paths:
        migration = _load_migration(path, f"migration_{path.stem}")
        assert migration.revision not in chain, f"duplicate revision {migration.revision}"
        chain[migration.revision] = migration.down_revision
    return chain


def _assert_linear_chain(chain: dict[str, object], baseline_revision: str) -> None:
    """Require one linear chain from a frozen baseline root to a single head.

    A revision with a tuple ``down_revision`` is a merge. Two revisions that
    share the same parent are a branch. Both break the contract in
    CONTRIBUTING.md, so this raises ``AssertionError`` for them.
    """
    assert baseline_revision in chain, f"missing frozen baseline {baseline_revision}"
    assert chain[baseline_revision] is None, "the frozen baseline must be the root"
    children: dict[str, list[str]] = {}
    for revision, down_revision in chain.items():
        assert not isinstance(down_revision, (tuple, list)), f"{revision} merges multiple parents"
        if revision == baseline_revision:
            continue
        assert down_revision in chain, f"{revision} references unknown parent {down_revision!r}"
        children.setdefault(down_revision, []).append(revision)
    for parent, branches in children.items():
        assert len(branches) == 1, f"{parent} branches into {sorted(branches)}"
    assert len(children) == len(chain) - 1, "the revision graph is disconnected"


def test_migration_history_is_one_linear_chain_from_the_frozen_baseline():
    chain = _revision_chain(sorted(VERSIONS.glob("*.py")))
    _assert_linear_chain(chain, BASELINE_REVISION)


def test_linear_chain_validation_accepts_a_single_chain():
    _assert_linear_chain(
        {BASELINE_REVISION: None, "0002_class_subject_modules": BASELINE_REVISION},
        BASELINE_REVISION,
    )


def test_linear_chain_validation_rejects_a_branch():
    with pytest.raises(AssertionError, match="branches"):
        _assert_linear_chain(
            {BASELINE_REVISION: None, "a": BASELINE_REVISION, "b": BASELINE_REVISION},
            BASELINE_REVISION,
        )


def test_linear_chain_validation_rejects_a_merge():
    with pytest.raises(AssertionError, match="merges"):
        _assert_linear_chain(
            {BASELINE_REVISION: None, "a": BASELINE_REVISION, "b": (BASELINE_REVISION, "a")},
            BASELINE_REVISION,
        )


def test_frozen_baseline_is_present_and_unchanged():
    assert BASELINE.exists()
    baseline = _load_migration(BASELINE, "baseline_migration")
    assert baseline.revision == BASELINE_REVISION
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
