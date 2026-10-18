from datetime import UTC, date, datetime, time

import pytest

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import (
    ValidationViolationCode,
    lesson_violations,
    validate_candidate,
)
from app.scheduler.domain.debt import RecoveryAllocation
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)
PREFERRED = date(2026, 10, 30)
HARD_END = date(2026, 11, 30)
MONDAY = date(2026, 9, 21)
WEDNESDAY = date(2026, 9, 23)


def _period(day, start=time(9), end=time(10)):
    return normalize_period(day, start, end, TZ)


def _assignment(**overrides) -> Assignment:
    values = {
        "assignment_id": 1,
        "class_ids": (1,),
        "subject_id": 10,
        "teacher_id": 100,
        "eligible_room_ids": frozenset({500, 501}),
        "modules": (ModuleRequirement(1, 1, 60), ModuleRequirement(2, 2, 40)),
    }
    values.update(overrides)
    return Assignment(**values)


def _lesson(**overrides) -> ScheduledLesson:
    values = {
        "lesson_id": 1,
        "assignment_id": 1,
        "period": _period(MONDAY),
        "room_id": 500,
        "credit_minutes": 60,
        "slices": (ModuleSlice(1, 1, 0, 60),),
    }
    values.update(overrides)
    return ScheduledLesson(**values)


def _second_lesson(**overrides) -> ScheduledLesson:
    values = {
        "lesson_id": 2,
        "assignment_id": 1,
        "period": _period(WEDNESDAY),
        "room_id": 501,
        "credit_minutes": 40,
        "slices": (ModuleSlice(2, 2, 0, 40),),
    }
    values.update(overrides)
    return ScheduledLesson(**values)


def _snapshot(**overrides) -> PlanningSnapshot:
    values = {
        "strategy": SchedulingStrategy.COMPLETE_GENERATION,
        "origin": ORIGIN,
        "preferred_end_date": PREFERRED,
        "hard_end_date": HARD_END,
        "timezone_name": TZ,
        "grid_slots": (GridSlot(0, time(9), time(10)), GridSlot(2, time(9), time(10))),
        "assignments": (_assignment(),),
        "executed_minutes": {},
        "blocked_dates": frozenset(),
        "unavailable": (),
    }
    values.update(overrides)
    return PlanningSnapshot(**values)


def _candidate(*lessons: ScheduledLesson) -> CandidateSchedule:
    return CandidateSchedule(tuple(lessons) if lessons else (_lesson(), _second_lesson()))


def _codes(report) -> set[ValidationViolationCode]:
    return {violation.code for violation in report.violations}


def test_valid_candidate_passes_and_reports_independent_metrics():
    report = validate_candidate(_snapshot(), _candidate())

    assert report.valid
    assert report.credited_minutes == {1: 100}
    assert report.total_credit_minutes == 100
    assert report.completion_dates == {1: WEDNESDAY}


def test_module_chronology_is_enforced_not_only_totals():
    assignment = _assignment(modules=(ModuleRequirement(1, 1, 60), ModuleRequirement(2, 2, 60)))
    snapshot = _snapshot(assignments=(assignment,))
    first = _lesson(slices=(ModuleSlice(1, 2, 0, 60),))
    second = _second_lesson(credit_minutes=60, slices=(ModuleSlice(2, 1, 0, 60),))

    report = validate_candidate(snapshot, CandidateSchedule((first, second)))

    assert ValidationViolationCode.MODULE_MISMATCH in _codes(report)


def test_non_final_partial_credit_is_rejected():
    partial = _lesson(credit_minutes=30, slices=(ModuleSlice(1, 1, 0, 30),))
    grown = _second_lesson(
        period=_period(WEDNESDAY, time(9), time(11)),
        credit_minutes=70,
        slices=(ModuleSlice(2, 1, 30, 30), ModuleSlice(2, 2, 0, 40)),
    )
    snapshot = _snapshot(
        grid_slots=(
            GridSlot(0, time(9), time(10)),
            GridSlot(2, time(9), time(10)),
            GridSlot(2, time(9), time(11)),
        )
    )

    report = validate_candidate(snapshot, CandidateSchedule((partial, grown)))

    assert ValidationViolationCode.PARTIAL_CREDIT_VIOLATION in _codes(report)


def test_protected_partial_lesson_is_allowed():
    protected_partial = _lesson(credit_minutes=30, slices=(ModuleSlice(1, 1, 0, 30),))
    completion = _second_lesson(
        period=_period(WEDNESDAY, time(9), time(11)),
        credit_minutes=70,
        slices=(ModuleSlice(2, 1, 30, 30), ModuleSlice(2, 2, 0, 40)),
    )
    snapshot = _snapshot(
        protected_lessons=(protected_partial,),
        grid_slots=(
            GridSlot(0, time(9), time(10)),
            GridSlot(2, time(9), time(10)),
            GridSlot(2, time(9), time(11)),
        ),
    )
    report = validate_candidate(snapshot, CandidateSchedule((protected_partial, completion)))

    assert report.valid


def test_period_outside_the_grid_is_rejected():
    night = _lesson(period=_period(MONDAY, time(2), time(3)))
    report = validate_candidate(_snapshot(), CandidateSchedule((night, _second_lesson())))

    assert ValidationViolationCode.NOT_IN_GRID in _codes(report)


def test_initial_generation_rejects_dates_after_preference():
    late = _second_lesson(period=_period(date(2026, 11, 2)))
    report = validate_candidate(_snapshot(), _candidate(_lesson(), late))

    assert ValidationViolationCode.OUT_OF_CALENDAR in _codes(report)


def test_adaptive_recovery_allows_dates_up_to_the_hard_end():
    late = _second_lesson(period=_period(date(2026, 11, 2)))
    snapshot = _snapshot(strategy=SchedulingStrategy.ADAPTIVE_RECOVERY)
    report = validate_candidate(snapshot, _candidate(_lesson(), late))

    assert report.valid


def test_blocked_date_is_rejected():
    report = validate_candidate(_snapshot(blocked_dates=frozenset({WEDNESDAY})), _candidate())

    assert ValidationViolationCode.OUT_OF_CALENDAR in _codes(report)


def test_overlapping_unavailability_is_rejected_but_boundary_contact_is_allowed():
    unavailable = Unavailability(
        UnavailableResource.TEACHER, 100, _period(MONDAY, time(9, 30), time(10, 30))
    )
    overlapping = validate_candidate(_snapshot(unavailable=(unavailable,)), _candidate())
    contact = Unavailability(UnavailableResource.TEACHER, 100, _period(MONDAY, time(10), time(11)))
    touching = validate_candidate(_snapshot(unavailable=(contact,)), _candidate(_lesson()))

    assert ValidationViolationCode.RESOURCE_UNAVAILABLE in _codes(overlapping)
    assert ValidationViolationCode.RESOURCE_UNAVAILABLE not in _codes(touching)


def test_protection_ignores_modular_projection_but_keeps_physical_identity():
    published = _lesson()
    updated_projection = _lesson(slices=(ModuleSlice(1, 1, 0, 60),))
    snapshot = _snapshot(protected_lessons=(published,))
    projected = validate_candidate(snapshot, _candidate(updated_projection, _second_lesson()))
    moved = validate_candidate(snapshot, _candidate(_lesson(room_id=501), _second_lesson()))

    assert projected.valid
    assert ValidationViolationCode.PROTECTED_LESSON_CHANGED in _codes(moved)


def test_new_lesson_inside_the_editable_window_is_rejected():
    snapshot = _snapshot(protected_dates=frozenset({MONDAY}))
    report = validate_candidate(snapshot, _candidate())

    assert ValidationViolationCode.EDITABLE_WINDOW_VIOLATION in _codes(report)


def test_protected_lesson_inside_the_window_is_allowed():
    published = _lesson()
    snapshot = _snapshot(protected_dates=frozenset({MONDAY}), protected_lessons=(published,))
    report = validate_candidate(snapshot, _candidate(_lesson(), _second_lesson()))

    assert report.valid


def test_availability_declared_after_a_started_protected_lesson_does_not_conflict():
    started = _lesson()
    unavailable = Unavailability(UnavailableResource.TEACHER, 100, _period(MONDAY))
    snapshot = _snapshot(
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=datetime(2026, 9, 21, 12, 0, tzinfo=UTC),
        unavailable=(unavailable,),
        protected_lessons=(started,),
    )
    protected = lesson_violations(snapshot, started, protected_ids=frozenset({started.lesson_id}))
    unprotected = lesson_violations(snapshot, started)

    assert ValidationViolationCode.RESOURCE_UNAVAILABLE not in {v.code for v in protected}
    assert ValidationViolationCode.RESOURCE_UNAVAILABLE in {v.code for v in unprotected}


def test_duplicate_identity_is_rejected():
    report = validate_candidate(
        _snapshot(),
        _candidate(_lesson(), _lesson(period=_period(WEDNESDAY), room_id=501)),
    )

    assert ValidationViolationCode.DUPLICATE_IDENTITY in _codes(report)


def test_unknown_assignment_is_rejected():
    report = validate_candidate(
        _snapshot(), _candidate(_lesson(assignment_id=99), _second_lesson())
    )

    assert ValidationViolationCode.UNKNOWN_ASSIGNMENT in _codes(report)


def test_ineligible_room_is_rejected():
    report = validate_candidate(_snapshot(), _candidate(_lesson(room_id=999), _second_lesson()))

    assert ValidationViolationCode.INELIGIBLE_ROOM in _codes(report)


def test_resource_overlap_is_rejected():
    report = validate_candidate(
        _snapshot(),
        _candidate(_lesson(), _second_lesson(period=_period(MONDAY), room_id=500)),
    )

    assert ValidationViolationCode.RESOURCE_CONFLICT in _codes(report)


def test_missing_coverage_is_rejected():
    report = validate_candidate(_snapshot(), _candidate(_lesson()))

    assert ValidationViolationCode.COVERAGE_MISMATCH in _codes(report)


def test_modular_gap_is_rejected():
    first = _lesson(slices=(ModuleSlice(1, 1, 0, 50),))
    second = _second_lesson(
        credit_minutes=50,
        slices=(ModuleSlice(2, 1, 60, 10), ModuleSlice(2, 2, 0, 40)),
    )
    report = validate_candidate(_snapshot(), _candidate(first, second))

    assert ValidationViolationCode.MODULE_MISMATCH in _codes(report)


def test_slice_sum_mismatch_is_rejected():
    broken = _lesson(credit_minutes=60, slices=(ModuleSlice(1, 1, 0, 50),))
    report = validate_candidate(_snapshot(), _candidate(broken, _second_lesson(credit_minutes=40)))

    assert ValidationViolationCode.SLICE_MISMATCH in _codes(report)


def test_reservation_version_mismatch_is_rejected():
    reservation = RecoveryAllocation(6, 2, 31, 30)
    snapshot = _snapshot(
        active_version_id=5,
        reservations=(reservation,),
        open_debt_minutes={31: 30},
        claim_assignments={31: 1},
    )
    report = validate_candidate(snapshot, _candidate())

    assert ValidationViolationCode.RESERVATION_VERSION_MISMATCH in _codes(report)


def test_reservation_assignment_mismatch_is_rejected():
    reservation = RecoveryAllocation(5, 2, 31, 30)
    snapshot = _snapshot(
        assignments=(
            _assignment(),
            _assignment(assignment_id=2, class_ids=(2,), teacher_id=101),
        ),
        active_version_id=5,
        reservations=(reservation,),
        open_debt_minutes={31: 30},
        claim_assignments={31: 2},
    )
    report = validate_candidate(snapshot, _candidate())

    assert ValidationViolationCode.RESERVATION_ASSIGNMENT_MISMATCH in _codes(report)


def test_duplicate_reservation_is_rejected():
    reservation = RecoveryAllocation(5, 2, 31, 30)
    snapshot = _snapshot(
        active_version_id=5,
        reservations=(reservation, reservation),
        open_debt_minutes={31: 30},
        claim_assignments={31: 1},
    )
    report = validate_candidate(snapshot, _candidate())

    assert ValidationViolationCode.RESERVATION_DUPLICATE in _codes(report)


def test_reservation_overflow_is_rejected():
    reservation = RecoveryAllocation(5, 2, 31, 50)
    snapshot = _snapshot(
        active_version_id=5,
        reservations=(reservation,),
        open_debt_minutes={31: 50},
        claim_assignments={31: 1},
    )
    report = validate_candidate(snapshot, _candidate())

    assert ValidationViolationCode.RESERVATION_OVERFLOW in _codes(report)


def test_debt_overflow_is_rejected():
    reservation = RecoveryAllocation(5, 2, 31, 30)
    snapshot = _snapshot(
        active_version_id=5,
        reservations=(reservation,),
        open_debt_minutes={31: 10},
        claim_assignments={31: 1},
    )
    report = validate_candidate(snapshot, _candidate())

    assert ValidationViolationCode.DEBT_OVERFLOW in _codes(report)


def test_projection_is_recomputed_from_residual_after_execution():
    snapshot = _snapshot(executed_minutes={1: {1: 60}})
    report = validate_candidate(snapshot, _candidate(_second_lesson()))

    assert report.valid
    assert report.credited_minutes == {1: 40}


def test_validator_rejects_wrong_argument_types():
    with pytest.raises(ValueError):
        validate_candidate(_snapshot(), _lesson())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        validate_candidate(_snapshot(), "candidate")  # type: ignore[arg-type]


def test_a_joint_lesson_conflicts_with_a_lesson_of_any_member_class():
    joint = _assignment(class_ids=(1, 2))
    other = _assignment(
        assignment_id=2,
        class_ids=(1,),
        modules=(ModuleRequirement(3, 1, 60),),
    )
    snapshot = _snapshot(assignments=(joint, other))
    joint_lesson = _lesson(slices=(ModuleSlice(1, 1, 0, 60),))
    member_lesson = _lesson(
        lesson_id=2,
        assignment_id=2,
        room_id=501,
        slices=(ModuleSlice(3, 1, 0, 60),),
    )

    report = validate_candidate(snapshot, CandidateSchedule((joint_lesson, member_lesson)))

    assert ValidationViolationCode.RESOURCE_CONFLICT in _codes(report)


def test_completion_dates_cover_every_member_class_of_a_joint_lesson():
    snapshot = _snapshot(assignments=(_assignment(class_ids=(1, 2)),))

    report = validate_candidate(snapshot, _candidate())

    assert report.completion_dates == {1: WEDNESDAY, 2: WEDNESDAY}


def test_precedence_violation_flags_a_new_target_before_its_source():
    source = _assignment(assignment_id=1, class_ids=(1,))
    target = _assignment(
        assignment_id=2,
        class_ids=(2,),
        teacher_id=101,
        modules=(ModuleRequirement(1, 1, 60),),
    )
    snapshot = _snapshot(assignments=(source, target), precedences=((1, 2),))
    source_lesson = _second_lesson()
    target_lesson = _lesson(
        lesson_id=3,
        assignment_id=2,
        room_id=501,
        slices=(ModuleSlice(3, 1, 0, 60),),
    )

    report = validate_candidate(snapshot, CandidateSchedule((source_lesson, target_lesson)))

    assert ValidationViolationCode.PRECEDENCE_VIOLATION in _codes(report)


def test_precedence_violation_exempts_a_protected_target_lesson():
    source = _assignment(assignment_id=1, class_ids=(1,))
    target = _assignment(
        assignment_id=2,
        class_ids=(2,),
        teacher_id=101,
        modules=(ModuleRequirement(1, 1, 60),),
    )
    target_lesson = _lesson(
        lesson_id=3,
        assignment_id=2,
        room_id=501,
        slices=(ModuleSlice(3, 1, 0, 60),),
    )
    snapshot = _snapshot(
        assignments=(source, target),
        precedences=((1, 2),),
        protected_lessons=(target_lesson,),
    )

    report = validate_candidate(snapshot, CandidateSchedule((_second_lesson(), target_lesson)))

    assert ValidationViolationCode.PRECEDENCE_VIOLATION not in _codes(report)


def test_reservations_are_limited_per_lesson_and_class():
    snapshot = _snapshot(
        assignments=(_assignment(class_ids=(1, 2)),),
        active_version_id=5,
        open_debt_minutes={7: 50, 8: 50},
        claim_assignments={7: 1, 8: 1},
        claim_classes={7: 1, 8: 2},
        reservations=(
            RecoveryAllocation(5, 1, 7, 50),
            RecoveryAllocation(5, 1, 8, 50),
        ),
    )

    report = validate_candidate(snapshot, _candidate())

    assert ValidationViolationCode.RESERVATION_OVERFLOW not in _codes(report)


def test_one_class_reservation_above_the_lesson_credit_overflows():
    snapshot = _snapshot(
        assignments=(_assignment(class_ids=(1, 2)),),
        active_version_id=5,
        open_debt_minutes={7: 70},
        claim_assignments={7: 1},
        claim_classes={7: 1},
        reservations=(RecoveryAllocation(5, 1, 7, 70),),
    )

    report = validate_candidate(snapshot, _candidate())

    assert ValidationViolationCode.RESERVATION_OVERFLOW in _codes(report)


def test_a_claim_class_outside_the_lesson_is_a_mismatch():
    snapshot = _snapshot(
        assignments=(_assignment(class_ids=(1, 2)),),
        active_version_id=5,
        open_debt_minutes={7: 50},
        claim_assignments={7: 1},
        claim_classes={7: 2},
        reservations=(RecoveryAllocation(5, 1, 7, 50),),
    )

    report = validate_candidate(snapshot, _candidate(_lesson(class_ids=(1,))))

    assert ValidationViolationCode.RESERVATION_ASSIGNMENT_MISMATCH in _codes(report)
