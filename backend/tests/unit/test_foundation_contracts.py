from datetime import date, time
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import CurrentMemberRead, FoundationDraftData
from app.services.foundation_service import validate_foundation_snapshot


def valid_snapshot() -> FoundationDraftData:
    return FoundationDraftData(
        school_start_date=date(2025, 9, 15),
        school_hard_end_date=date(2026, 7, 31),
        repair_stability_window_days=1,
        days_of_week=[0, 1, 2, 3, 4],
        opening_time=time(8, 30),
        closing_time=time(17, 30),
        slot_duration_minutes=50,
        break_duration_minutes=0,
        lunch_window_start=time(12, 30),
        lunch_window_end=time(14, 0),
        lunch_min_duration_minutes=60,
    )


def test_foundation_snapshot_accepts_zero_break():
    validate_foundation_snapshot(valid_snapshot())


def test_foundation_snapshot_accepts_zero_stability_window():
    validate_foundation_snapshot(
        valid_snapshot().model_copy(update={"repair_stability_window_days": 0})
    )


@pytest.mark.parametrize("payload", [{}, {"repair_stability_window_days": None}])
def test_foundation_stability_window_defaults_to_fourteen(payload):
    assert FoundationDraftData(**payload).repair_stability_window_days == 14


@pytest.mark.parametrize(
    "changes",
    [
        {"school_hard_end_date": date(2025, 9, 15)},
        {"days_of_week": [0, 0]},
        {"days_of_week": [7]},
        {"lunch_window_start": time(7, 0)},
        {"lunch_window_end": time(18, 0)},
        {"slot_duration_minutes": 0},
        {"repair_stability_window_days": -1},
        {"repair_stability_window_days": 61},
    ],
)
def test_foundation_snapshot_rejects_invalid_complete_configuration(changes):
    snapshot = valid_snapshot().model_copy(update=changes)

    with pytest.raises(ValueError):
        validate_foundation_snapshot(snapshot)


def test_current_member_requires_foundation_status():
    with pytest.raises(ValidationError):
        CurrentMemberRead(
            member_id=1,
            account_id=1,
            organization_id=1,
            capabilities=["admin"],
            access_status="active",
            lifecycle_status="active",
            default_mode="admin",
            available_modes=["admin"],
        )


def test_head_migration_has_no_legacy_bootstrap_or_backfill():
    migration = Path(__file__).parents[2] / "alembic" / "versions" / "0001_scheduler_v1_baseline.py"
    source = migration.read_text(encoding="utf-8").lower()

    assert (
        "create or replace function app_security.bootstrap_founder"
        not in source.split("def downgrade", 1)[0]
    )
    assert "backfill" not in source
