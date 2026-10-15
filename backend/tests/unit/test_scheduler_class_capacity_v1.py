"""WBS 2.4.1/2.4.2: per-class capacity deficits and class-time diagnoses."""

from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    PlanningSnapshot,
    SchedulingStrategy,
)
from app.scheduler.domain.capacity import aggregate_capacity_check
from app.scheduler.domain.diagnostics import (
    DiagnosisCode,
    EvidenceKind,
    diagnose_capacity,
)
from app.scheduler.domain.projection import ModuleRequirement
from tests.unit.test_scheduler_w04_w05_regressions_v1 import ORIGIN, TZ, period


def _snapshot(periods, assignments, executed=None):
    return PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=periods[-1].school_date,
        hard_end_date=periods[-1].school_date,
        timezone_name=TZ,
        grid_slots=tuple(
            dict.fromkeys(
                GridSlot(row.school_date.weekday(), row.start_local, row.end_local)
                for row in periods
            )
        ),
        assignments=tuple(assignments),
        executed_minutes=executed or {},
        blocked_dates=frozenset(),
        unavailable=(),
    )


def assignment(identity, class_id, teacher_id, room_id, minutes):
    return Assignment(
        identity,
        (class_id,),
        identity,
        teacher_id,
        frozenset({room_id}),
        (ModuleRequirement(identity, 1, minutes),),
    )


def test_a_class_shares_the_union_of_its_subject_periods_once():
    periods = (period(0), period(1))
    assignments = (assignment(1, 1, 1, 1, 60), assignment(2, 1, 2, 2, 120))

    check = aggregate_capacity_check(_snapshot(periods, assignments), periods)

    # Each subject fits its own 120 eligible minutes, but the class only ever
    # has 120 minutes and needs 180: the shared periods count once.
    assert check.deficits == {}
    assert check.class_deficits == {1: 60}
    assert check.proven_infeasible


def test_a_class_with_enough_free_time_has_no_deficit():
    periods = (period(0), period(1), period(2))
    assignments = (assignment(1, 1, 1, 1, 60), assignment(2, 1, 2, 2, 60))

    check = aggregate_capacity_check(_snapshot(periods, assignments), periods)

    assert check.class_deficits == {}
    assert not check.proven_infeasible


def test_a_class_with_only_completed_assignments_has_no_deficit():
    periods = (period(0),)
    assignments = (assignment(1, 1, 1, 1, 60),)

    check = aggregate_capacity_check(
        _snapshot(periods, assignments, executed={1: {1: 60}}), periods
    )

    assert check.deficits == {}
    assert check.class_deficits == {}
    assert not check.proven_infeasible


def test_diagnose_capacity_returns_a_class_time_lower_bound():
    periods = (period(0), period(1))
    assignments = (assignment(1, 1, 1, 1, 60), assignment(2, 1, 2, 2, 120))
    snapshot = _snapshot(periods, assignments)

    diagnoses = diagnose_capacity(snapshot, aggregate_capacity_check(snapshot, periods))

    class_diagnosis = next(
        row for row in diagnoses if row.code is DiagnosisCode.INSUFFICIENT_CLASS_TIME
    )
    assert class_diagnosis.evidence_kind is EvidenceKind.PROVEN_LOWER_BOUND
    assert class_diagnosis.scope == "CLASS:1"
    assert class_diagnosis.minimum_missing_minutes == 60
    assert class_diagnosis.affected_class_ids == (1,)
    assert class_diagnosis.affected_subject_id is None


def test_diagnose_capacity_records_the_affected_subject_on_intersection():
    periods = (period(0),)
    snapshot = _snapshot(periods, (assignment(1, 1, 1, 1, 120),))

    diagnoses = diagnose_capacity(snapshot, aggregate_capacity_check(snapshot, periods))

    intersection = next(
        row for row in diagnoses if row.code is DiagnosisCode.INSUFFICIENT_INTERSECTION
    )
    assert intersection.affected_subject_id == 1
