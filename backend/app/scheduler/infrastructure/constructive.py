"""Independent constructive schedule for viable snapshots.

A greedy earliest-period placement with dynamic class/teacher/room occupancy,
followed by the independent validator. The constructor walks every assignment in
ascending scarcity and fills its residual demand from the earliest eligible
periods. It returns ``None`` when it cannot cover the demand or when the
validator rejects the result; a construction failure never declares a case
impossible.

The search uses the result as an initial incumbent. It is deliberately not a
solver: it is fast, deterministic and only ever yields a candidate already
accepted by :func:`validate_candidate`.
"""

from __future__ import annotations

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
    allocate_lesson_identity,
    continuous_break_minutes,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import available_rooms, eligible_periods, residual_minutes
from app.scheduler.domain.projection import ModuleSlice


def _local_interval(period: Period) -> tuple[int, int]:
    return (
        period.start_local.hour * 60 + period.start_local.minute,
        period.end_local.hour * 60 + period.end_local.minute,
    )


def _next_module(modules, cursor: dict[int, int]) -> int | None:
    for index, module in enumerate(modules):
        if cursor[module.module_id] < module.required_minutes:
            return index
    return None


def construct_schedule(
    snapshot: PlanningSnapshot, periods: tuple[Period, ...]
) -> CandidateSchedule | None:
    """Greedy complete plan covering the residual demand, or ``None``."""
    assignments = sorted(
        snapshot.assignments,
        key=lambda assignment: (
            len(eligible_periods(snapshot, assignment, periods)),
            assignment.assignment_id,
        ),
    )
    eligibility = {
        assignment.assignment_id: eligible_periods(snapshot, assignment, periods)
        for assignment in assignments
    }
    busy: dict[tuple, dict[str, set[int]]] = {}
    used_ids: set[int] = {lesson.lesson_id for lesson in snapshot.protected_lessons}
    lunch = snapshot.lunch_rule
    occupancy: dict[tuple, list[tuple[int, int]]] = {}
    if lunch is not None:
        for lesson in snapshot.protected_lessons:
            assignment = snapshot.assignment_for(lesson.assignment_id)
            if assignment is None:
                continue
            interval = _local_interval(lesson.period)
            teacher_id = (
                lesson.teacher_id if lesson.teacher_id is not None else assignment.teacher_id
            )
            occupancy.setdefault(
                ("class", assignment.class_id, lesson.period.school_date), []
            ).append(interval)
            occupancy.setdefault(("teacher", teacher_id, lesson.period.school_date), []).append(
                interval
            )
    lessons: list[ScheduledLesson] = []
    for assignment in assignments:
        remaining = residual_minutes(snapshot, assignment.assignment_id)
        if remaining <= 0:
            continue
        executed = snapshot.executed_minutes.get(assignment.assignment_id, {})
        modules = assignment.modules
        cursor = {module.module_id: executed.get(module.module_id, 0) for module in modules}

        rank = 0
        for period in eligibility[assignment.assignment_id]:
            if remaining <= 0:
                break
            key = (period.start_utc, period.end_utc)
            used = busy.setdefault(key, {"class": set(), "teacher": set(), "room": set()})
            if assignment.class_id in used["class"] or assignment.teacher_id in used["teacher"]:
                continue
            room_id = next(
                (
                    room
                    for room in available_rooms(snapshot, assignment, period)
                    if room not in used["room"]
                ),
                None,
            )
            if room_id is None:
                continue
            class_key = ("class", assignment.class_id, period.school_date)
            teacher_key = ("teacher", assignment.teacher_id, period.school_date)
            interval = _local_interval(period)
            if lunch is not None and (
                continuous_break_minutes([*occupancy.get(class_key, ()), interval], lunch)
                < lunch.minimum_minutes
                or continuous_break_minutes([*occupancy.get(teacher_key, ()), interval], lunch)
                < lunch.minimum_minutes
            ):
                continue
            credit = min(remaining, period.duration_minutes)
            rank += 1
            lesson_id = allocate_lesson_identity(assignment.assignment_id, rank, used_ids)
            used_ids.add(lesson_id)
            slices: list[ModuleSlice] = []
            left = credit
            while left > 0:
                index = _next_module(modules, cursor)
                if index is None:
                    return None
                module = modules[index]
                available = module.required_minutes - cursor[module.module_id]
                take = min(left, available)
                slices.append(
                    ModuleSlice(lesson_id, module.module_id, cursor[module.module_id], take)
                )
                cursor[module.module_id] += take
                left -= take
            if not slices:
                return None
            used["class"].add(assignment.class_id)
            used["teacher"].add(assignment.teacher_id)
            used["room"].add(room_id)
            lessons.append(
                ScheduledLesson(
                    lesson_id=lesson_id,
                    assignment_id=assignment.assignment_id,
                    period=period,
                    room_id=room_id,
                    credit_minutes=credit,
                    slices=tuple(slices),
                )
            )
            remaining -= credit
            if lunch is not None:
                occupancy.setdefault(class_key, []).append(interval)
                occupancy.setdefault(teacher_key, []).append(interval)
        if remaining > 0:
            return None
    candidate = CandidateSchedule((*snapshot.protected_lessons, *lessons))
    if not validate_candidate(snapshot, candidate).valid:
        return None
    return candidate
