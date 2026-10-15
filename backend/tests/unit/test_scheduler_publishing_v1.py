"""W09.3/R89: the proposal diff separates changes and recurs debt planning."""

from dataclasses import replace
from datetime import date, time

import pytest

from app.scheduler.application.publishing import (
    build_diff,
    diagnostics_summary,
    plan_recovery_allocations,
)
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
)
from app.scheduler.domain.debt import RecoveryAllocation
from app.scheduler.domain.diagnostics import Diagnosis, DiagnosisCode, EvidenceKind
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice

GRID = (GridSlot(0, time(9, 0), time(9, 50)), GridSlot(1, time(9, 0), time(9, 50)))
ASSIGNMENT = Assignment(
    assignment_id=1,
    class_ids=(1,),
    subject_id=1,
    teacher_id=1,
    eligible_room_ids=frozenset({1}),
    modules=(ModuleRequirement(1, 1, 200),),
)


def _lesson(lesson_id, day, offset=0):
    return ScheduledLesson(
        lesson_id=lesson_id,
        assignment_id=1,
        period=normalize_period(day, time(9, 0), time(9, 50), "Europe/Lisbon"),
        room_id=1,
        credit_minutes=50,
        slices=(ModuleSlice(lesson_id, 1, offset, 50),),
    )


def _snapshot(baseline):
    return PlanningSnapshot(
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        origin=date(2026, 9, 1),
        preferred_end_date=date(2026, 9, 30),
        hard_end_date=date(2026, 10, 31),
        timezone_name="Europe/Lisbon",
        grid_slots=GRID,
        assignments=(ASSIGNMENT,),
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=(),
        baseline_lessons=baseline,
    )


def test_a_moved_lesson_is_physical_and_an_insertion_is_counted():
    baseline = (_lesson(1, date(2026, 9, 7)),)
    candidate = CandidateSchedule(
        (_lesson(1, date(2026, 9, 8)), _lesson(2, date(2026, 9, 14), offset=50))
    )

    diff = build_diff(_snapshot(baseline), candidate)

    assert diff["is_first_generation"] is False
    assert diff["counts"] == {
        "added": 1,
        "removed": 0,
        "moved": 1,
        "room_changed": 0,
        "modular_updates": 0,
    }
    moved = next(row for row in diff["physical"] if row["change_type"] == "MOVED")
    assert moved["lesson_id"] == 1
    assert moved["before"]["date"] == "2026-09-07"
    assert moved["after"]["date"] == "2026-09-08"


def test_a_projection_change_at_the_same_position_is_modular_only():
    baseline = (_lesson(1, date(2026, 9, 7), offset=0),)
    candidate = CandidateSchedule((_lesson(1, date(2026, 9, 7), offset=50),))

    diff = build_diff(_snapshot(baseline), candidate)

    assert diff["physical"] == []
    assert diff["counts"]["modular_updates"] == 1
    assert diff["modular"][0]["before"] == [{"module_id": 1, "offset_minutes": 0, "minutes": 50}]
    assert diff["modular"][0]["after"] == [{"module_id": 1, "offset_minutes": 50, "minutes": 50}]


def test_a_first_generation_has_no_baseline_to_compare():
    candidate = CandidateSchedule((_lesson(1, date(2026, 9, 7)),))

    diff = build_diff(_snapshot(()), candidate)

    assert diff["is_first_generation"] is True
    assert diff["counts"]["added"] == 1
    assert diff["modular"] == []


def _credit_lesson(lesson_id, day, credit):
    return ScheduledLesson(
        lesson_id=lesson_id,
        assignment_id=1,
        period=normalize_period(day, time(9, 0), time(9, 50), "Europe/Lisbon"),
        room_id=1,
        credit_minutes=credit,
        slices=(ModuleSlice(lesson_id, 1, 0, credit),),
    )


def _adaptive_snapshot(debt, claims):
    return replace(
        _snapshot(()),
        active_version_id=1,
        open_debt_minutes=debt,
        claim_assignments=claims,
    )


def test_diagnostics_summary_keeps_the_affected_subject():
    diagnosis = Diagnosis(
        code=DiagnosisCode.INSUFFICIENT_INTERSECTION,
        evidence_kind=EvidenceKind.PROVEN_LOWER_BOUND,
        message="Missing minutes.",
        scope="ASSIGNMENT:1",
        minimum_missing_minutes=30,
        affected_class_ids=(2,),
        affected_subject_id=3,
    )

    assert diagnostics_summary((diagnosis,)) == [
        {
            "code": "INSUFFICIENT_INTERSECTION",
            "message": "Missing minutes.",
            "suggestions": [],
            "minimum_missing_minutes": 30,
            "affected_class_ids": [2],
            "affected_subject_id": 3,
        }
    ]


def test_allocations_split_a_claim_across_lessons_in_chronological_order():
    snapshot = _adaptive_snapshot({7: 50}, {7: 1})
    candidate = CandidateSchedule(
        (_credit_lesson(1, date(2026, 9, 7), 30), _credit_lesson(2, date(2026, 9, 8), 40))
    )

    allocations = plan_recovery_allocations(snapshot, candidate)

    assert [(row.lesson_id, row.claim_id, row.minutes) for row in allocations] == [
        (1, 7, 30),
        (2, 7, 20),
    ]


def test_allocations_follow_the_claim_order_from_the_caller():
    snapshot = _adaptive_snapshot({1: 30, 2: 40}, {1: 1, 2: 1})
    candidate = CandidateSchedule(
        (_credit_lesson(1, date(2026, 9, 7), 50), _credit_lesson(2, date(2026, 9, 8), 50))
    )

    allocations = plan_recovery_allocations(snapshot, candidate, claim_order=[2, 1])

    assert allocations[0].claim_id == 2
    assert allocations[0].minutes == 40


def test_recovery_debt_is_reserved_only_after_the_stability_window():
    frozen = _credit_lesson(1, date(2026, 9, 7), 50)
    snapshot = replace(
        _adaptive_snapshot({7: 50}, {7: 1}),
        protected_dates=frozenset({frozen.period.school_date}),
        protected_lessons=(frozen,),
    )
    candidate = CandidateSchedule((frozen, _credit_lesson(2, date(2026, 9, 8), 50)))

    allocations = plan_recovery_allocations(snapshot, candidate)

    assert [(row.lesson_id, row.minutes) for row in allocations] == [(2, 50)]


def test_an_approved_recovery_that_enters_the_window_keeps_its_reservation():
    frozen = _credit_lesson(1, date(2026, 9, 7), 50)
    snapshot = replace(
        _adaptive_snapshot({7: 50, 8: 50}, {7: 1, 8: 1}),
        protected_dates=frozenset({frozen.period.school_date}),
        protected_lessons=(frozen,),
        reservations=(RecoveryAllocation(1, frozen.lesson_id, 7, 50),),
    )
    candidate = CandidateSchedule((frozen, _credit_lesson(2, date(2026, 9, 8), 50)))

    allocations = plan_recovery_allocations(snapshot, candidate, claim_order=[8, 7])

    assert [(row.claim_id, row.lesson_id, row.minutes) for row in allocations] == [
        (8, 2, 50),
        (7, 1, 50),
    ]


def test_allocations_never_exceed_a_lesson_credit():
    snapshot = _adaptive_snapshot({1: 40, 2: 10}, {1: 1, 2: 1})
    candidate = CandidateSchedule((_credit_lesson(1, date(2026, 9, 7), 50),))

    allocations = plan_recovery_allocations(snapshot, candidate)

    assert sum(row.minutes for row in allocations) == 50
    assert all(row.minutes <= 50 for row in allocations)
    assert [(row.claim_id, row.minutes) for row in allocations] == [(1, 40), (2, 10)]


def test_allocations_reject_open_debt_beyond_the_candidate_credit():
    snapshot = _adaptive_snapshot({1: 80}, {1: 1})
    candidate = CandidateSchedule((_credit_lesson(1, date(2026, 9, 7), 50),))

    with pytest.raises(ValueError, match="exceeds the candidate credit"):
        plan_recovery_allocations(snapshot, candidate)
