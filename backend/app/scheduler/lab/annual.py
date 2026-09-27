"""Annual fixtures with constructed witnesses and seed-dependent topology.

Each class carries several subjects and modules, the demand spans the school
year and holiday weeks are blocked. Three problem profiles share resources
differently: dedicated rooms with paired teachers, critical shared teachers, or
scarce shared rooms. The witness is built by construction and validated
independently; the minimal oracle is never called.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time, timedelta

from app.scheduler.domain.calendar import Period, normalize_period
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
from app.scheduler.domain.projection import (
    FutureLesson,
    ModuleRequirement,
    ModuleSlice,
    project_module_slices,
)

TIMEZONE = "Europe/Lisbon"
SLOT_MINUTES = 50
WEEK_DAYS = 5
SLOTS_PER_DAY = 6
WEEK_SLOTS = WEEK_DAYS * SLOTS_PER_DAY
SLOT_START_MINUTES = (9 * 60, 9 * 60 + 50, 11 * 60, 11 * 60 + 50, 14 * 60, 14 * 60 + 50)

PROFILE_LOOSE = "loose"
PROFILE_SHARED_TEACHER = "shared-teacher"
PROFILE_SCARCE_ROOMS = "scarce-rooms"
PROFILE_CONNECTED = "connected"
PROFILES = (PROFILE_LOOSE, PROFILE_SHARED_TEACHER, PROFILE_SCARCE_ROOMS, PROFILE_CONNECTED)

PROFILE_SUBJECT_LESSONS = {
    PROFILE_LOOSE: (2, 2, 2),
    PROFILE_SHARED_TEACHER: (3, 2, 2),
    PROFILE_SCARCE_ROOMS: (2, 2, 2),
    PROFILE_CONNECTED: (2, 2, 2),
}
PROFILE_TEACHERS_PER_CLASS = {
    PROFILE_LOOSE: 0.5,
    PROFILE_SHARED_TEACHER: 0.25,
    PROFILE_SCARCE_ROOMS: 0.5,
    PROFILE_CONNECTED: 0.5,
}
HOLIDAY_WEEKS = frozenset({13, 14, 21, 30})
FIRST_HOLIDAY_YEAR_END = date(2027, 6, 11)


@dataclass(frozen=True)
class AnnualFixture:
    class_count: int
    profile: str
    seed: int
    snapshot: PlanningSnapshot
    periods: tuple[Period, ...]
    witness: CandidateSchedule


def _slot_time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def _school_dates(origin: date, preferred_end_date: date) -> tuple[date, ...]:
    days = []
    day = origin
    while day <= preferred_end_date:
        if day.weekday() < WEEK_DAYS:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


def _group_sizes(profile: str, seed: int) -> tuple[int, int]:
    if profile == PROFILE_LOOSE:
        return 2 + (seed % 2), 1
    if profile == PROFILE_SHARED_TEACHER:
        return 3 + (seed % 2), 1
    if profile == PROFILE_CONNECTED:
        return 3 + (seed % 2), 2
    return 2 + (seed % 2), 2 + ((seed // 2) % 2)


def _weekly_slots(
    profile: str, class_index: int, teacher_group: int, room_group: int
) -> tuple[int, ...]:
    """Disjoint slot sets inside the group that shares a resource."""
    lessons = sum(PROFILE_SUBJECT_LESSONS[profile])
    group = teacher_group if profile != PROFILE_SCARCE_ROOMS else room_group
    block = WEEK_SLOTS // group
    if block < lessons:
        raise ValueError("The profile demand does not fit its resource group.")
    if profile == PROFILE_SCARCE_ROOMS:
        view = class_index % group
        return tuple(view + offset * group for offset in range(lessons))
    start = (class_index % group) * block
    return tuple(start + offset for offset in range(lessons))


def _resource_ids(
    profile: str, class_index: int, subject_index: int, teacher_group: int, room_group: int
) -> tuple[int, tuple[int, ...]]:
    if profile == PROFILE_LOOSE:
        return class_index // teacher_group + 1, (1000 + class_index,)
    if profile == PROFILE_SHARED_TEACHER:
        return class_index // teacher_group + 1, (1000 + class_index,)
    if profile == PROFILE_SCARCE_ROOMS:
        return class_index // room_group + 1, (1000 + class_index // room_group,)
    teacher_id = 1 + (subject_index - 1) * 4 + class_index // teacher_group
    base = 2000 + class_index * 2
    return teacher_id, (base, base + 1)


def build_annual_fixture(
    class_count: int,
    *,
    profile: str = PROFILE_LOOSE,
    seed: int = 1,
    origin: date = date(2026, 9, 21),
    preferred_end_date: date = FIRST_HOLIDAY_YEAR_END,
) -> AnnualFixture:
    if class_count < 1:
        raise ValueError("An annual fixture needs at least one class.")
    if profile not in PROFILES:
        raise ValueError("Unknown annual fixture profile.")
    if preferred_end_date <= origin:
        raise ValueError("The annual horizon must be positive.")

    days = _school_dates(origin, preferred_end_date)
    grid_slots = tuple(
        dict.fromkeys(
            GridSlot(day.weekday(), _slot_time(start), _slot_time(start + SLOT_MINUTES))
            for day in days
            for start in SLOT_START_MINUTES
        )
    )
    blocked = frozenset(day for day in days if (day - origin).days // 7 in HOLIDAY_WEEKS)
    available_days = tuple(day for day in days if day not in blocked)
    periods = tuple(
        normalize_period(day, _slot_time(start), _slot_time(start + SLOT_MINUTES), TIMEZONE)
        for day in available_days
        for start in SLOT_START_MINUTES
    )
    week_periods: dict[int, list[Period]] = defaultdict(list)
    for period in periods:
        week_periods[(period.school_date - origin).days // 7].append(period)

    weeks = sorted(week_periods)
    lessons_per_week = PROFILE_SUBJECT_LESSONS[profile]
    teacher_group, room_group = _group_sizes(profile, seed)
    assignments: list[Assignment] = []
    scheduled: list[ScheduledLesson] = []
    unavailable: list[Unavailability] = []
    if profile == PROFILE_CONNECTED:
        for group_index in range(0, class_count, 2):
            base = 2000 + group_index * 2
            unavailable.append(
                Unavailability(UnavailableResource.ROOM, base + 1, week_periods[2][0])
            )
    for index in range(class_count):
        class_id = index + 1
        slots = _weekly_slots(profile, index, teacher_group, room_group)
        module_plans: list[tuple[ModuleRequirement, ...]] = []
        subject_rows: list[list[tuple[Period, int]]] = []
        cursor = 0
        for weekly in lessons_per_week:
            subject_slots = slots[cursor : cursor + weekly]
            cursor += weekly
            total_lessons = weekly * len(weeks)
            first_module = (total_lessons + 1) // 2
            module_plans.append(
                (
                    ModuleRequirement(1, 1, first_module * SLOT_MINUTES),
                    ModuleRequirement(2, 2, (total_lessons - first_module) * SLOT_MINUTES),
                )
            )
            subject_rows.append(
                [
                    (week_periods[week][slot], SLOT_MINUTES)
                    for week in weeks
                    for slot in subject_slots
                ]
            )
        for subject_index, rows in enumerate(subject_rows, start=1):
            assignment_id = class_id * 10 + subject_index
            module = module_plans[subject_index - 1]
            teacher_id, rooms = _resource_ids(
                profile, index, subject_index, teacher_group, room_group
            )
            room_id = rooms[0]
            assignments.append(
                Assignment(
                    assignment_id=assignment_id,
                    class_id=class_id,
                    subject_id=1000 + subject_index,
                    teacher_id=teacher_id,
                    eligible_room_ids=frozenset(rooms),
                    modules=module,
                )
            )
            futures = tuple(
                FutureLesson(
                    assignment_id * 1_000_000 + rank,
                    period.school_date,
                    period.start_local.hour * 60 + period.start_local.minute,
                    SLOT_MINUTES,
                    SLOT_MINUTES,
                )
                for rank, (period, _) in enumerate(rows, start=1)
            )
            slices = project_module_slices(module, completed_minutes={}, lessons=futures)
            by_lesson: dict[int, list[ModuleSlice]] = defaultdict(list)
            for slice_ in slices:
                by_lesson[slice_.lesson_id].append(slice_)
            for rank, ((period, credit), future) in enumerate(
                zip(rows, futures, strict=True), start=1
            ):
                scheduled.append(
                    ScheduledLesson(
                        lesson_id=assignment_id * 1_000_000 + rank,
                        assignment_id=assignment_id,
                        period=period,
                        room_id=room_id,
                        credit_minutes=credit,
                        slices=tuple(by_lesson.get(future.lesson_id, ())),
                    )
                )
    snapshot = PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=origin,
        preferred_end_date=preferred_end_date,
        hard_end_date=date.fromordinal(preferred_end_date.toordinal() + 19),
        timezone_name=TIMEZONE,
        grid_slots=grid_slots,
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=blocked,
        unavailable=tuple(unavailable),
    )
    return AnnualFixture(
        class_count=class_count,
        profile=profile,
        seed=seed,
        snapshot=snapshot,
        periods=periods,
        witness=CandidateSchedule(tuple(sorted(scheduled, key=lambda lesson: lesson.lesson_id))),
    )


def annual_topology(snapshot: PlanningSnapshot) -> dict[str, int]:
    """Observable connectivity, alternatives and pressure of an annual snapshot."""
    classes_by_teacher: dict[int, set[int]] = defaultdict(set)
    classes: dict[int, set[int]] = defaultdict(set)
    rooms_in_use: set[int] = set()
    alternatives = 0
    for assignment in snapshot.assignments:
        classes_by_teacher[assignment.teacher_id].add(assignment.class_id)
        classes[assignment.class_id].add(assignment.teacher_id)
        rooms_in_use.update(assignment.eligible_room_ids)
        if len(assignment.eligible_room_ids) > 1:
            alternatives += 1
    return {
        "classes": len(classes),
        "teachers": len(classes_by_teacher),
        "shared_teachers": sum(1 for members in classes_by_teacher.values() if len(members) > 1),
        "teachers_with_transversal_classes": sum(
            1 for members in classes.values() if len(members) > 1
        ),
        "rooms": len(rooms_in_use),
        "assignments_with_room_alternatives": alternatives,
        "unavailable_intervals": len(snapshot.unavailable),
    }
