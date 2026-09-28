"""School fixtures that follow the product's real data typology.

The structure mirrors the import templates: each class carries seven subjects,
each subject is four 15-hour modules, every course has exactly three classes so
the class count is always a multiple of three, and each teacher covers two
classes for their subject. The school year starts on 14 September, prefers to
end on 15 June and may not pass 30 July, with the Christmas and Easter breaks
blocked alongside the Portuguese national holidays.

A witness is built by the independent constructor and validated by the
independent validator, so a large case stays checkable without the minimal
oracle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from app.scheduler.domain.calendar import Period, normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    PlanningSnapshot,
    SchedulingStrategy,
)
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.infrastructure.constructive import construct_schedule

TIMEZONE = "Europe/Lisbon"
SUBJECT_COUNT = 7
MODULES_PER_SUBJECT = 4
MODULE_MINUTES = 15 * 60
LESSON_MINUTES = 60
SLOT_START_MINUTES = (9 * 60, 10 * 60, 11 * 60, 14 * 60, 15 * 60)
WEEK_DAYS = 5

SCHOOL_YEAR_START = date(2026, 9, 14)
PREFERRED_END = date(2027, 6, 15)
HARD_END = date(2027, 7, 30)

# Christmas 21 Dec - 1 Jan and Easter 12 - 23 Apr, plus national holidays.
CHRISTMAS_BREAK = (date(2026, 12, 21), date(2027, 1, 1))
EASTER_BREAK = (date(2027, 4, 12), date(2027, 4, 23))
NATIONAL_HOLIDAYS = frozenset(
    {
        date(2026, 10, 5),
        date(2026, 12, 1),
        date(2026, 12, 8),
        date(2027, 2, 16),
        date(2027, 3, 26),
        date(2027, 4, 25),
        date(2027, 5, 1),
        date(2027, 6, 10),
    }
)


@dataclass(frozen=True)
class TypologyFixture:
    class_count: int
    courses: int
    teachers: int
    rooms: int
    snapshot: PlanningSnapshot
    periods: tuple[Period, ...]
    witness: CandidateSchedule


def _slot_time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def _school_days(first: date, last: date) -> tuple[date, ...]:
    if first.weekday() != 0:
        raise ValueError("The school year must start on a Monday.")
    days = []
    day = first
    while day <= last:
        days.append(day)
        day = date.fromordinal(day.toordinal() + 1)
    return tuple(days)


def _blocked(day: date) -> bool:
    if day.weekday() >= WEEK_DAYS:
        return True
    if CHRISTMAS_BREAK[0] <= day <= CHRISTMAS_BREAK[1]:
        return True
    return EASTER_BREAK[0] <= day <= EASTER_BREAK[1] or day in NATIONAL_HOLIDAYS


def _periods(first: date, last: date) -> tuple[Period, ...]:
    return tuple(
        normalize_period(day, _slot_time(start), _slot_time(start + LESSON_MINUTES), TIMEZONE)
        for day in _school_days(first, last)
        if not _blocked(day)
        for start in SLOT_START_MINUTES
    )


def _assignment(class_id, subject_id, teacher_id, room_ids, assignment_id):
    modules = tuple(
        ModuleRequirement(module_id, module_id, MODULE_MINUTES)
        for module_id in range(1, MODULES_PER_SUBJECT + 1)
    )
    return Assignment(
        assignment_id=assignment_id,
        class_id=class_id,
        subject_id=subject_id,
        teacher_id=teacher_id,
        eligible_room_ids=frozenset(room_ids),
        modules=modules,
    )


def build_typology_fixture(
    class_count: int,
) -> TypologyFixture:
    """Build a feasible school with the product typology and a witness.

    ``class_count`` must be a multiple of three because every course has three
    classes. Each assignment shares a pair of neighbouring rooms so alternative
    room sets stay part of the case.
    """
    if class_count < 3 or class_count % 3 != 0:
        raise ValueError("Classes are always multiples of three (three per course).")
    rooms = class_count
    periods = _periods(SCHOOL_YEAR_START, PREFERRED_END)
    grid_slots = tuple(
        dict.fromkeys(
            GridSlot(day.weekday(), _slot_time(start), _slot_time(start + LESSON_MINUTES))
            for day in _school_days(SCHOOL_YEAR_START, PREFERRED_END)
            if not _blocked(day)
            for start in SLOT_START_MINUTES
        )
    )
    assignments = []
    for class_index in range(class_count):
        class_id = class_index + 1
        pair = class_index // 2
        eligible = (class_id, (class_index + 1) % rooms + 1)
        for subject_index in range(1, SUBJECT_COUNT + 1):
            teacher_id = subject_index * 1000 + pair + 1
            assignments.append(
                _assignment(
                    class_id,
                    subject_index,
                    teacher_id,
                    eligible,
                    class_id * 10 + subject_index,
                )
            )
    snapshot = PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=SCHOOL_YEAR_START,
        preferred_end_date=PREFERRED_END,
        hard_end_date=HARD_END,
        timezone_name=TIMEZONE,
        grid_slots=grid_slots,
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=frozenset(
            day
            for day in _school_days(SCHOOL_YEAR_START, HARD_END)
            if CHRISTMAS_BREAK[0] <= day <= CHRISTMAS_BREAK[1]
            or EASTER_BREAK[0] <= day <= EASTER_BREAK[1]
            or day in NATIONAL_HOLIDAYS
        ),
        unavailable=(),
    )
    witness = construct_schedule(snapshot, periods)
    if witness is None:
        raise ValueError("The typology fixture has no independent witness.")
    return TypologyFixture(
        class_count=class_count,
        courses=class_count // 3,
        teachers=SUBJECT_COUNT * ((class_count + 1) // 2),
        rooms=rooms,
        snapshot=snapshot,
        periods=periods,
        witness=witness,
    )
