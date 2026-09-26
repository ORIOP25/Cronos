"""Independent constructive witnesses for viable laboratory cases.

A greedy earliest-period placement with dynamic class/teacher/room occupancy,
followed by the independent validator. A construction failure only means no
witness was built; it is never used to declare impossibility.
"""

from __future__ import annotations

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
    allocate_lesson_identity,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import available_rooms, eligible_periods, residual_minutes
from app.scheduler.domain.projection import ModuleSlice


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
    used_ids: set[int] = set()
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
        if remaining > 0:
            return None
    candidate = CandidateSchedule(tuple(lessons))
    if not validate_candidate(snapshot, candidate).valid:
        return None
    return candidate
