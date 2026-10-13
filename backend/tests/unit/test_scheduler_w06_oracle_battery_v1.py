"""R67.08 battery: repair vectors against the oracle on varied small schools."""

from dataclasses import replace
from datetime import date, time

import pytest

from app.scheduler.composition import repair_published_schedule
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import CandidateSchedule
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.oracle import enumerate_candidates
from app.scheduler.domain.recovery import recovery_vector
from app.scheduler.lab.fixtures import AssignmentSpec, build_fixture, build_snapshot
from app.scheduler.lab.recovery import apply_event, build_recovery_case
from tests.unit.test_scheduler_recovery_solver_v1 import (
    DAY0,
    DAY1,
    DAY2,
    GRID,
    POLICY,
    TZ,
    _baseline_lesson,
    _spec,
)

WEEK2 = date(2026, 10, 5)
WEEK3 = date(2026, 10, 12)


def _policy_for(snapshot):
    days = (snapshot.preferred_end_date - snapshot.origin).days
    return replace(POLICY, daily_slopes=tuple(range(1, days + 1)))


LATE_GRID = ((0, time(9), time(10)), (1, time(9), time(10)), (2, time(9), time(10)))
LATE_PERIODS = (
    (DAY0, time(9), time(10)),
    (WEEK2, time(9), time(10)),
    (WEEK3, time(9), time(10)),
)


def _single(module_minutes=(60,), **overrides):
    return _spec(assignments=(AssignmentSpec(1, 7, module_minutes, (500,)),), **overrides)


def _shared_teacher(**overrides):
    return _spec(
        assignments=(
            AssignmentSpec(1, 7, (60,), (500,)),
            AssignmentSpec(2, 7, (60,), (501,)),
        ),
        **overrides,
    )


def _scarce_room(**overrides):
    return _spec(
        assignments=(
            AssignmentSpec(1, 7, (60,), (500,)),
            AssignmentSpec(2, 8, (60,), (500,)),
        ),
        **overrides,
    )


SCENARIOS = (
    (
        "single-teacher-absence",
        lambda: build_recovery_case("b-single-abs", _single(), event_seed=1),
    ),
    ("single-cancel", lambda: build_recovery_case("b-single-cancel", _single(), event_seed=0)),
    ("single-room-closed", lambda: build_recovery_case("b-single-room", _single(), event_seed=2)),
    (
        "shared-teacher-absence",
        lambda: build_recovery_case("b-shared-abs", _shared_teacher(), event_seed=1),
    ),
    (
        "shared-teacher-cancel",
        lambda: build_recovery_case("b-shared-cancel", _shared_teacher(), event_seed=0),
    ),
    ("scarce-room-cancel", lambda: build_recovery_case("b-scarce", _scarce_room(), event_seed=4)),
    (
        "partial-credit",
        lambda: build_recovery_case("b-partial", _single(module_minutes=(90,)), event_seed=1),
    ),
    (
        "urgency-near-frontier",
        lambda: build_recovery_case(
            "b-urgency",
            _single(protected_dates=frozenset({DAY0})),
            event_seed=2,
        ),
    ),
    (
        "distant-weeks",
        lambda: build_recovery_case(
            "b-distant",
            _single(
                periods=LATE_PERIODS,
                grid_slots=LATE_GRID,
                preferred_end_date=WEEK3,
                hard_end_date=date(2026, 10, 23),
            ),
            event_seed=1,
        ),
    ),
    (
        "missed-target",
        lambda: build_recovery_case(
            "b-missed",
            _single(
                preferred_end_date=DAY1,
                periods=(
                    (DAY0, time(9), time(10)),
                    (DAY1, time(9), time(10)),
                    (DAY2, time(9), time(10)),
                ),
                grid_slots=GRID,
            ),
            event_seed=0,
        ),
    ),
)


@pytest.mark.parametrize(
    "builder", [builder for _, builder in SCENARIOS], ids=[name for name, _ in SCENARIOS]
)
def test_the_repair_matches_the_enumerated_adaptive_optimum(builder):
    case = builder()
    snapshot, periods, baseline = case.snapshot, case.periods, case.baseline
    oracle = enumerate_candidates(snapshot, periods)

    result = repair_published_schedule(
        snapshot, periods, baseline, _policy_for(snapshot), time_limit_seconds=10
    )

    if not oracle.feasible:
        assert result.outcome in {"INFEASIBLE", "INCONCLUSIVE"}
        return
    best = min(
        recovery_vector(snapshot, baseline, row, _policy_for(snapshot)) for row in oracle.candidates
    )
    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    vector = recovery_vector(snapshot, baseline, result.candidate, _policy_for(snapshot))
    assert vector == best
    if validate_candidate(snapshot, baseline).valid:
        assert vector <= recovery_vector(snapshot, baseline, baseline, _policy_for(snapshot))


def test_a_protected_published_lesson_is_preserved_and_the_rest_is_repaired():
    base = build_fixture("b-protected-base", _single(module_minutes=(120,)))
    baseline = base.witness
    protected = baseline.lessons[0]
    snapshot = replace(
        base.snapshot,
        baseline_lessons=baseline.lessons,
        protected_lessons=(protected,),
    )
    snapshot = apply_event(snapshot, baseline, "TEACHER_ABSENCE", 1)
    oracle = enumerate_candidates(snapshot, base.periods)

    result = repair_published_schedule(
        snapshot, base.periods, baseline, _policy_for(snapshot), time_limit_seconds=10
    )

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert any(row.lesson_id == protected.lesson_id for row in result.candidate.lessons)
    best = min(
        recovery_vector(snapshot, baseline, row, _policy_for(snapshot)) for row in oracle.candidates
    )
    assert recovery_vector(snapshot, baseline, result.candidate, _policy_for(snapshot)) == best


def _single_assignment_case(day, *, spec_extra=None):
    periods = tuple(normalize_period(row, time(9), time(10), TZ) for row in (DAY0, DAY1, DAY2))
    baseline = CandidateSchedule(
        (_baseline_lesson(1, 1, normalize_period(day, time(9), time(10), TZ), 500, 7),)
    )
    spec = _single(**(spec_extra or {}))
    snapshot = replace(build_snapshot(spec), baseline_lessons=baseline.lessons)
    return snapshot, periods, baseline


def test_open_debt_survives_a_repair_without_being_credited_as_execution():
    from app.scheduler.domain.debt import DebtClaim, RecoveryAllocation
    from app.scheduler.domain.recovery import reconcile_after_repair

    base = build_fixture("b-debt", _single(module_minutes=(120,)))
    baseline = base.witness
    snapshot = replace(
        base.snapshot,
        baseline_lessons=baseline.lessons,
        active_version_id=7,
        open_debt_minutes={4: 30},
        claim_assignments={4: 1},
    )

    result = repair_published_schedule(
        snapshot, base.periods, baseline, _policy_for(snapshot), time_limit_seconds=10
    )

    assert result.outcome == "COMPLETE"
    balances = reconcile_after_repair(
        snapshot,
        result.candidate,
        (DebtClaim(4, snapshot.origin, 30),),
        allocations=(RecoveryAllocation(9, result.candidate.lessons[0].lesson_id, 4, 30),),
    )
    assert balances[0].open_minutes == 30
    assert balances[0].reserved_minutes == 0


def test_recurrence_increases_the_cost_of_repeating_a_change():
    snapshot, periods, baseline = _single_assignment_case(
        DAY0, spec_extra={"unavailable": (("teacher", 7, (DAY0, time(9), time(10))),)}
    )

    plain = repair_published_schedule(
        snapshot, periods, baseline, _policy_for(snapshot), time_limit_seconds=10
    )
    repeated = repair_published_schedule(
        snapshot,
        periods,
        baseline,
        POLICY,
        prior_changes=frozenset({1}),
        time_limit_seconds=10,
    )

    assert plain.outcome == repeated.outcome == "COMPLETE"
    assert plain.quality is not None and repeated.quality is not None
    assert repeated.quality.disruption.total_cost == plain.quality.disruption.total_cost * (
        1 + POLICY.recurrence_penalty
    )


def test_urgency_raises_the_cost_near_the_editable_frontier():
    snapshot, periods, baseline = _single_assignment_case(
        DAY1,
        spec_extra={
            "protected_dates": frozenset({DAY0}),
            "unavailable": (("teacher", 7, (DAY1, time(9), time(10))),),
        },
    )

    result = repair_published_schedule(
        snapshot, periods, baseline, _policy_for(snapshot), time_limit_seconds=10
    )

    assert result.outcome == "COMPLETE"
    assert result.quality is not None
    assert result.quality.disruption.total_cost > POLICY.move_cost


def test_a_repair_never_exceeds_the_hard_end_even_when_the_target_is_missed():
    case = build_recovery_case(
        "b-hard-end",
        _single(
            preferred_end_date=DAY0,
            hard_end_date=DAY2,
            periods=(
                (DAY0, time(9), time(10)),
                (DAY1, time(9), time(10)),
                (DAY2, time(9), time(10)),
            ),
            grid_slots=GRID,
        ),
        event_seed=0,
    )

    result = repair_published_schedule(
        case.snapshot,
        case.periods,
        case.baseline,
        _policy_for(case.snapshot),
        time_limit_seconds=10,
    )

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert all(
        row.period.school_date <= case.snapshot.hard_end_date for row in result.candidate.lessons
    )
    assert result.summary is not None
    assert result.summary.excess_days >= 0
