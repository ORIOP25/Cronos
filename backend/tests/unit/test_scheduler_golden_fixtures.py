import pytest

from app.scheduler.domain.constraints import SchedulerConstraintPolicy
from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder
from tests.scheduler_golden_fixtures import (
    constrained_scheduler_fixture,
    large_scheduler_fixture,
    medium_scheduler_fixture,
    small_scheduler_fixture,
)


@pytest.mark.parametrize(
    ("factory", "expected_name"),
    (
        (small_scheduler_fixture, "small"),
        (medium_scheduler_fixture, "medium"),
        (large_scheduler_fixture, "large"),
    ),
)
def test_golden_scheduler_fixtures_are_complete_and_reusable(factory, expected_name):
    fixture = factory()
    snapshot = fixture.snapshot
    ledger = CompleteDemandLedgerBuilder().build(snapshot)

    assert fixture.name == expected_name
    assert ledger.is_complete, ledger.blockers
    assert snapshot["scheduler_state_version"] > snapshot["approved_scheduler_state_version"]
    assert snapshot["calendar_events"]
    assert snapshot["lunch_rules"]["minimum_minutes"] > 0
    assert any(row["score"] == -1 for row in snapshot["teacher_availability"])
    assert {room["type"] for room in snapshot["rooms"]} == {"normal", "lab"}
    assert snapshot["active_schedule"]
    assert fixture.debt_basis["items"][0]["unresolved_debt_minutes"] > 0


def test_golden_fixture_profiles_increase_in_representative_scale():
    fixtures = [
        small_scheduler_fixture(),
        medium_scheduler_fixture(),
        large_scheduler_fixture(),
    ]

    assert [len(item.snapshot["classes"]) for item in fixtures] == [3, 12, 30]
    assert [len(item.snapshot["class_subject_requirements"]) for item in fixtures] == [9, 48, 120]


def test_constrained_golden_fixture_covers_every_supported_custom_rule():
    fixture = constrained_scheduler_fixture()
    rows = fixture.snapshot["constraints"]

    assert {row["rule_type"] for row in rows} == {
        "specific_room",
        "lock_time",
        "teacher_unavailable",
        "teacher_preferred",
    }
    assert not SchedulerConstraintPolicy.from_snapshot(fixture.snapshot).configuration_violations
