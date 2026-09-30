import importlib.util
from datetime import time
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
BASELINE = VERSIONS / "0001_scheduler_v1_baseline.py"
GRID_VERSIONS = VERSIONS / "0011_grid_versions.py"
GRID_CHANGE_STRATEGY = VERSIONS / "0012_grid_change_strategy.py"
INTERNSHIP_FLOWS = VERSIONS / "0013_internship_flows.py"
FOUNDATION_INTERNSHIP_STEP = VERSIONS / "0014_foundation_internship_step.py"
SCHEDULER_V1_GRID_CHANGE = VERSIONS / "0015_scheduler_v1_grid_change.py"
RESOURCE_ARCHIVE_FLAGS = VERSIONS / "0016_resource_archive_flags.py"
ACTIVE_COURSE_ABBREVIATIONS = VERSIONS / "0017_active_course_abbreviations.py"


def _load_migration(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_history_keeps_the_consolidated_baseline_and_its_dependents():
    assert sorted(VERSIONS.glob("*.py")) == [
        BASELINE,
        GRID_VERSIONS,
        GRID_CHANGE_STRATEGY,
        INTERNSHIP_FLOWS,
        FOUNDATION_INTERNSHIP_STEP,
        SCHEDULER_V1_GRID_CHANGE,
        RESOURCE_ARCHIVE_FLAGS,
        ACTIVE_COURSE_ABBREVIATIONS,
    ]
    baseline = _load_migration(BASELINE, "baseline_migration")
    grid_versions = _load_migration(GRID_VERSIONS, "grid_versions")
    grid_change = _load_migration(GRID_CHANGE_STRATEGY, "grid_change_strategy")
    internship_flows = _load_migration(INTERNSHIP_FLOWS, "internship_flows")
    foundation_step = _load_migration(FOUNDATION_INTERNSHIP_STEP, "foundation_internship_step")
    v1_grid_change = _load_migration(SCHEDULER_V1_GRID_CHANGE, "v1_grid_change")
    resource_archive_flags = _load_migration(RESOURCE_ARCHIVE_FLAGS, "resource_archive_flags")
    active_course_abbreviations = _load_migration(
        ACTIVE_COURSE_ABBREVIATIONS, "active_course_abbreviations"
    )

    assert baseline.revision == "0001_scheduler_v1_baseline"
    assert baseline.down_revision is None
    assert grid_versions.down_revision == baseline.revision
    assert grid_change.down_revision == grid_versions.revision
    assert internship_flows.down_revision == grid_change.revision
    assert foundation_step.down_revision == internship_flows.revision
    assert v1_grid_change.down_revision == foundation_step.revision
    assert resource_archive_flags.down_revision == v1_grid_change.revision
    assert active_course_abbreviations.down_revision == resource_archive_flags.revision

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
    assert "failure_reference" in sql
    assert "trg_organization_legal_acceptance_append_only" in sql
    assert "tutorial_telemetry" not in sql


def test_downgrade_preserves_the_alembic_version_table():
    source = BASELINE.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:")[1]

    assert "alembic_version" in downgrade
    assert "DROP SCHEMA IF EXISTS app_security CASCADE" in downgrade


def test_grid_version_migration_rebuilds_regular_legacy_configuration():
    migration = _load_migration(GRID_VERSIONS, "grid_versions")

    regular = migration.derive_grid_configuration(
        [
            (0, time(9, 0), time(9, 50)),
            (0, time(10, 0), time(10, 50)),
            (4, time(9, 0), time(9, 50)),
            (4, time(10, 0), time(10, 50)),
        ]
    )
    assert regular == {
        "opening_time": "09:00",
        "closing_time": "10:50",
        "slot_duration_minutes": 50,
        "break_duration_minutes": 10,
        "break_overrides": [],
        "days_of_week": [0, 4],
    }

    irregular_duration = migration.derive_grid_configuration(
        [
            (0, time(9, 0), time(9, 50)),
            (0, time(10, 0), time(11, 30)),
        ]
    )
    assert irregular_duration is None

    irregular_sequence = migration.derive_grid_configuration(
        [
            (0, time(9, 0), time(9, 50)),
            (0, time(10, 0), time(10, 50)),
            (1, time(9, 0), time(9, 50)),
        ]
    )
    assert irregular_sequence is None

    assert migration.derive_grid_configuration([]) is None
    assert migration.derive_grid_configuration([(0, time(9, 0, 30), time(9, 50, 30))]) is None
    assert (
        migration.derive_grid_configuration(
            [
                (0, time(9, 0), time(9, 50)),
                (0, time(9, 40), time(10, 30)),
            ]
        )
        is None
    )
    assert (
        migration.derive_grid_configuration(
            [
                (0, time(9, 0), time(9, 50)),
                (0, time(10, 51), time(11, 41)),
            ]
        )
        is None
    )
