from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
)
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)


def _period(day=ORIGIN, start=time(9), end=time(10)):
    return normalize_period(day, start, end, TZ)


def _assignment(**overrides) -> Assignment:
    values = {
        "assignment_id": 1,
        "class_id": 1,
        "subject_id": 10,
        "teacher_id": 100,
        "eligible_room_ids": frozenset({500}),
        "modules": (ModuleRequirement(1, 1, 60),),
    }
    values.update(overrides)
    return Assignment(**values)


def _snapshot(**overrides) -> PlanningSnapshot:
    values = {
        "strategy": SchedulingStrategy.COMPLETE_GENERATION,
        "origin": ORIGIN,
        "preferred_end_date": date(2026, 10, 30),
        "hard_end_date": date(2026, 11, 30),
        "timezone_name": TZ,
        "grid_slots": (GridSlot(0, time(9), time(10)),),
        "assignments": (_assignment(),),
        "executed_minutes": {},
        "blocked_dates": frozenset(),
        "unavailable": (),
    }
    values.update(overrides)
    return PlanningSnapshot(**values)


def test_snapshot_deep_copies_executed_minutes_so_aliases_cannot_mutate_it():
    executed = {1: {1: 0}}
    snapshot = _snapshot(executed_minutes=executed)

    executed[1][1] = 60

    assert snapshot.executed_minutes[1][1] == 0


def test_snapshot_refuses_unknown_timezone_and_date_order():
    with pytest.raises(ValueError):
        _snapshot(timezone_name="Mars/Olympus")
    with pytest.raises(ValueError):
        _snapshot(preferred_end_date=date(2026, 12, 1))


def test_snapshot_requires_unique_assignments_and_matching_debt_claims():
    with pytest.raises(ValueError):
        _snapshot(assignments=(_assignment(), _assignment()))
    with pytest.raises(ValueError):
        _snapshot(open_debt_minutes={7: 30})


def test_assignment_rejects_duplicate_modules_and_ids():
    with pytest.raises(ValueError):
        _assignment(modules=(ModuleRequirement(1, 1, 60), ModuleRequirement(1, 2, 30)))
    with pytest.raises(ValueError):
        _assignment(assignment_id=0)


def test_incoherent_period_instants_are_rejected_at_construction():
    period = _period()

    with pytest.raises(ValueError):
        replace(period, start_utc=datetime(2026, 9, 21, 6, 0, tzinfo=UTC))


def test_lesson_rejects_credit_above_physical_duration():
    with pytest.raises(ValueError):
        ScheduledLesson(
            lesson_id=1,
            assignment_id=1,
            period=_period(),
            room_id=500,
            credit_minutes=61,
            slices=(ModuleSlice(1, 1, 0, 61),),
        )


def test_grid_slot_rejects_invalid_weekday_and_duration():
    with pytest.raises(ValueError):
        GridSlot(7, time(9), time(10))
    with pytest.raises(ValueError):
        GridSlot(0, time(10), time(9))


def test_grid_weekdays_are_derived_from_concrete_slots():
    snapshot = _snapshot(
        grid_slots=(GridSlot(0, time(9), time(10)), GridSlot(2, time(9), time(10)))
    )

    assert snapshot.grid_weekdays == frozenset({0, 2})
