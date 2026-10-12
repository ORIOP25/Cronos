"""R10.3: independent constructive witnesses for large viable cases."""

from datetime import date, time, timedelta

import pytest

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.lab.construct import construct_schedule
from app.scheduler.lab.fixtures import (
    AssignmentSpec,
    CaseExpectation,
    FixtureSpec,
    build_snapshot,
)
from app.scheduler.lab.manifest import CaseSeeds, LabCase, case_from_dict, case_to_dict
from app.scheduler.lab.recovery import (
    build_constructed_recovery_case,
    recovery_event,
)

ORIGIN = date(2026, 9, 21)


def _spec(*, periods: int, module_minutes: tuple[int, ...] = (3000,)) -> FixtureSpec:
    days = []
    day = ORIGIN
    while len(days) < periods:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return FixtureSpec(
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        origin=ORIGIN,
        preferred_end_date=ORIGIN + timedelta(days=140),
        hard_end_date=ORIGIN + timedelta(days=160),
        timezone_name="Europe/Lisbon",
        grid_slots=tuple(dict.fromkeys((day.weekday(), time(9), time(10)) for day in days)),
        periods=tuple((day, time(9), time(10)) for day in days),
        assignments=(
            AssignmentSpec(1, 7, module_minutes, (500,)),
            AssignmentSpec(2, 8, module_minutes, (501,)),
        ),
    )


def _normalized_periods(spec: FixtureSpec):
    from app.scheduler.domain.calendar import normalize_period

    return tuple(
        normalize_period(day, start, end, spec.timezone_name) for day, start, end in spec.periods
    )


def test_a_large_viable_case_gets_a_validated_constructive_witness():
    spec = _spec(periods=110)

    snapshot = build_snapshot(spec)
    periods = _normalized_periods(spec)
    witness = construct_schedule(snapshot, periods)

    assert witness is not None
    assert validate_candidate(snapshot, witness).valid is True
    assert sum(lesson.credit_minutes for lesson in witness.lessons) == 6000


def test_constructed_recovery_has_a_witness_on_both_sides_of_the_event():
    spec = _spec(periods=110)

    case = build_constructed_recovery_case(
        "constructed-1", spec, event_seed=0, fixture_seed=1, solver_seed=1
    )

    assert case.expectation.value == "FEASIBLE_WITH_WITNESS"
    assert case.event == recovery_event(0)
    assert case.baseline.lessons
    # The published baseline is invalidated by the cancellation.
    assert validate_candidate(case.snapshot, case.baseline).valid is False


def test_construction_never_declares_impossibility():
    spec = _spec(periods=1, module_minutes=(3000,))
    snapshot = build_snapshot(spec)

    assert construct_schedule(snapshot, _normalized_periods(spec)) is None
    with pytest.raises(ValueError, match="witness"):
        build_constructed_recovery_case("constructed-impossible", spec)


def test_constructed_witness_mode_roundtrips_through_the_manifest():
    case = LabCase(
        "constructed-roundtrip",
        "C03",
        1,
        CaseExpectation.EXPLORATORY_UNKNOWN,
        _spec(periods=6),
        CaseSeeds(1, 0, 1),
        witness_mode="constructed",
    )

    restored = case_from_dict(case_to_dict(case))

    assert restored.witness_mode == "constructed"
