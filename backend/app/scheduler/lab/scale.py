"""Large fixtures with witnesses built by construction, not enumeration.

The seed changes the problem topology, not only the witness position: it sets
how many classes share a teacher, whether teacher groups share a room and the
weekly offset. Lessons of one teacher are placed in disjoint weekly blocks, so
the witness stays valid by construction. The minimal oracle is never called.
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
    ScheduledLesson,
    SchedulingStrategy,
)
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice

TIMEZONE = "Europe/Lisbon"
START_TIMES = (time(9), time(10), time(11), time(12))
SLOTS_PER_DAY = len(START_TIMES)
WEEK_DAYS = 5
WEEK_SLOTS = WEEK_DAYS * SLOTS_PER_DAY
LESSON_MINUTES = 60
MAX_LESSONS_PER_CLASS = WEEK_SLOTS // 5


@dataclass(frozen=True)
class ScaleFixture:
    class_count: int
    snapshot: PlanningSnapshot
    periods: tuple[Period, ...]
    witness: CandidateSchedule


def build_scale_fixture(
    class_count: int,
    *,
    seed: int = 1,
    module_minutes: int = 240,
    origin: date = date(2026, 9, 21),
) -> ScaleFixture:
    if class_count < 1:
        raise ValueError("A scale fixture needs at least one class.")
    if module_minutes < 1:
        raise ValueError("Module minutes must be positive.")
    lessons = (module_minutes + LESSON_MINUTES - 1) // LESSON_MINUTES
    if lessons > MAX_LESSONS_PER_CLASS:
        raise ValueError("Module minutes do not fit the weekly scale fixture.")
    days = tuple(date.fromordinal(origin.toordinal() + offset) for offset in range(WEEK_DAYS))
    grid_slots = tuple(
        GridSlot(day.weekday(), start, time(start.hour + 1))
        for day in days
        for start in START_TIMES
    )
    periods = tuple(
        normalize_period(day, start, time(start.hour + 1), TIMEZONE)
        for day in days
        for start in START_TIMES
    )
    group_size = 2 + (seed % 4)
    if group_size * lessons > WEEK_SLOTS:
        raise ValueError("The module does not fit a shared-teacher block.")
    shared_rooms = seed % 2 == 0
    offset = seed % (WEEK_SLOTS - group_size * lessons + 1)
    credits = [LESSON_MINUTES] * (lessons - 1) + [module_minutes - LESSON_MINUTES * (lessons - 1)]

    assignments = []
    scheduled = []
    for index in range(class_count):
        class_id = index + 1
        group = index // group_size
        teacher_id = group + 1
        room_id = 1000 + group + 1 if shared_rooms else 1000 + class_id
        assignments.append(
            Assignment(
                assignment_id=class_id,
                class_ids=(class_id,),
                subject_id=1000 + class_id,
                teacher_id=teacher_id,
                eligible_room_ids=frozenset({room_id}),
                modules=(ModuleRequirement(1, 1, module_minutes),),
            )
        )
        position = index % group_size
        for step in range(lessons):
            slot = position * lessons + step + offset
            scheduled.append(
                ScheduledLesson(
                    lesson_id=class_id * 100 + step + 1,
                    assignment_id=class_id,
                    period=periods[slot],
                    room_id=room_id,
                    credit_minutes=credits[step],
                    slices=(
                        ModuleSlice(
                            class_id * 100 + step + 1,
                            1,
                            step * LESSON_MINUTES,
                            credits[step],
                        ),
                    ),
                )
            )

    snapshot = PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=origin,
        preferred_end_date=days[-1],
        hard_end_date=date.fromordinal(days[-1].toordinal() + 30),
        timezone_name=TIMEZONE,
        grid_slots=grid_slots,
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=(),
    )
    return ScaleFixture(
        class_count=class_count,
        snapshot=snapshot,
        periods=periods,
        witness=CandidateSchedule(tuple(sorted(scheduled, key=lambda lesson: lesson.lesson_id))),
    )
