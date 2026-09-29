from datetime import date, time

import pytest

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    LunchRule,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
    continuous_break_minutes,
)
from app.scheduler.domain.candidate_validation import (
    ValidationViolationCode,
    validate_candidate,
)
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice
from app.scheduler.domain.serialization import snapshot_from_dict, snapshot_to_dict

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)
PREFERRED = date(2026, 10, 30)
HARD_END = date(2026, 11, 30)
MONDAY = date(2026, 9, 21)

LUNCH = LunchRule(window_start=time(12, 0), window_end=time(14, 0), minimum_minutes=60)


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _period(day, start, end):
    return normalize_period(day, start, end, TZ)


def _snapshot(**overrides) -> PlanningSnapshot:
    values = {
        "strategy": SchedulingStrategy.COMPLETE_GENERATION,
        "origin": ORIGIN,
        "preferred_end_date": PREFERRED,
        "hard_end_date": HARD_END,
        "timezone_name": TZ,
        "grid_slots": (
            GridSlot(0, time(12), time(12, 50)),
            GridSlot(0, time(13), time(13, 50)),
        ),
        "assignments": (
            Assignment(
                assignment_id=1,
                class_id=1,
                subject_id=10,
                teacher_id=100,
                eligible_room_ids=frozenset({500}),
                modules=(ModuleRequirement(1, 1, 100),),
            ),
        ),
        "executed_minutes": {},
        "blocked_dates": frozenset(),
        "unavailable": (),
    }
    values.update(overrides)
    return PlanningSnapshot(**values)


def _lessons(*periods_with_credit) -> tuple[ScheduledLesson, ...]:
    lessons = []
    offset = 0
    for index, (period, credit) in enumerate(periods_with_credit, start=1):
        lessons.append(
            ScheduledLesson(
                lesson_id=index,
                assignment_id=1,
                period=period,
                room_id=500,
                credit_minutes=credit,
                slices=(ModuleSlice(index, 1, offset, credit),),
            )
        )
        offset += credit
    return tuple(lessons)


def _ten_minute_gap_candidate() -> CandidateSchedule:
    return CandidateSchedule(
        _lessons(
            (_period(MONDAY, time(12), time(12, 50)), 50),
            (_period(MONDAY, time(13), time(13, 50)), 50),
        )
    )


def test_continuous_break_rejects_short_separated_gaps():
    occupied = [
        (_minutes(time(12)), _minutes(time(12, 50))),
        (_minutes(time(13)), _minutes(time(13, 50))),
    ]

    assert continuous_break_minutes(occupied, LUNCH) == 10


def test_continuous_break_accepts_a_single_long_gap():
    occupied = [
        (_minutes(time(12)), _minutes(time(12, 30))),
        (_minutes(time(13, 30)), _minutes(time(14))),
    ]

    assert continuous_break_minutes(occupied, LUNCH) == 60


def test_continuous_break_counts_the_whole_window_when_free():
    assert continuous_break_minutes([], LUNCH) == 120


def test_lunch_rule_rejects_inconsistent_configuration():
    with pytest.raises(ValueError):
        LunchRule(window_start=time(14), window_end=time(12), minimum_minutes=60)
    with pytest.raises(ValueError):
        LunchRule(window_start=time(12), window_end=time(14), minimum_minutes=0)
    with pytest.raises(ValueError):
        LunchRule(window_start=time(12), window_end=time(13), minimum_minutes=90)


def test_validator_rejects_a_candidate_that_leaves_no_continuous_break():
    report = validate_candidate(_snapshot(lunch_rule=LUNCH), _ten_minute_gap_candidate())

    assert ValidationViolationCode.LUNCH_BREAK_VIOLATION in {
        violation.code for violation in report.violations
    }


def test_validator_reports_class_and_teacher_lunch_separately():
    report = validate_candidate(_snapshot(lunch_rule=LUNCH), _ten_minute_gap_candidate())
    kinds = {
        (violation.resource_type, violation.resource_id)
        for violation in report.violations
        if violation.code is ValidationViolationCode.LUNCH_BREAK_VIOLATION
    }

    assert kinds == {("class", 1), ("teacher", 100)}


def test_validator_accepts_when_a_continuous_break_exists():
    snapshot = _snapshot(
        lunch_rule=LUNCH,
        grid_slots=(GridSlot(0, time(9), time(10)), GridSlot(0, time(10), time(11))),
        assignments=(
            Assignment(
                assignment_id=1,
                class_id=1,
                subject_id=10,
                teacher_id=100,
                eligible_room_ids=frozenset({500}),
                modules=(ModuleRequirement(1, 1, 120),),
            ),
        ),
    )
    candidate = CandidateSchedule(
        _lessons(
            (_period(MONDAY, time(9), time(10)), 60),
            (_period(MONDAY, time(10), time(11)), 60),
        )
    )

    assert validate_candidate(snapshot, candidate).valid


def test_validator_ignores_lunch_when_no_rule_is_configured():
    assert validate_candidate(_snapshot(), _ten_minute_gap_candidate()).valid


def test_lunch_rule_survives_serialization_and_changes_the_digest():
    snapshot = _snapshot(lunch_rule=LUNCH)
    payload = snapshot_to_dict(snapshot)

    restored = snapshot_from_dict(payload)

    assert restored.lunch_rule == LUNCH
    without = snapshot_to_dict(_snapshot())
    assert without != payload
