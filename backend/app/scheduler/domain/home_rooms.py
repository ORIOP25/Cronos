"""Home-room measures of a schedule: misses and avoidable room changes.

Pure rules over a snapshot and a candidate. The proposal publishes the two
counts; they never enter the quality vector, and a justified room change costs
nothing in the adaptive disruption.
"""

from collections import defaultdict
from datetime import date
from itertools import pairwise

from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
)


def _home_room_by_class(snapshot: PlanningSnapshot) -> dict[int, int]:
    return {row.class_id: row.room_id for row in snapshot.home_rooms}


def _assignment_by_id(snapshot: PlanningSnapshot) -> dict[int, Assignment]:
    return {row.assignment_id: row for row in snapshot.assignments}


def home_room_misses(snapshot: PlanningSnapshot, candidate: CandidateSchedule) -> int:
    """Lesson/class pairs where the class home room was usable but the lesson is elsewhere.

    A joint lesson counts once for each of its classes that has a home room.
    """
    homes = _home_room_by_class(snapshot)
    assignments = _assignment_by_id(snapshot)
    misses = 0
    for lesson in candidate.lessons:
        assignment = assignments[lesson.assignment_id]
        for class_id in assignment.class_ids:
            home = homes.get(class_id)
            if home is None or home not in assignment.eligible_room_ids:
                continue
            if lesson.room_id != home:
                misses += 1
    return misses


def avoidable_room_changes(snapshot: PlanningSnapshot, candidate: CandidateSchedule) -> int:
    """Room changes between two consecutive flexible lessons of one class on one day."""
    assignments = _assignment_by_id(snapshot)
    by_class_day: dict[tuple[int, date], list[ScheduledLesson]] = defaultdict(list)
    for lesson in candidate.lessons:
        for class_id in assignments[lesson.assignment_id].class_ids:
            by_class_day[(class_id, lesson.period.school_date)].append(lesson)

    changes = 0
    for lessons in by_class_day.values():
        ordered = sorted(lessons, key=lambda row: (row.period.start_utc, row.lesson_id))
        for previous, current in pairwise(ordered):
            if (
                _is_flexible(assignments, previous)
                and _is_flexible(assignments, current)
                and previous.room_id != current.room_id
            ):
                changes += 1
    return changes


def is_justified_room_change(
    snapshot: PlanningSnapshot,
    class_ids: tuple[int, ...],
    previous_room: int,
    new_room: int,
) -> bool:
    """A lesson enters a home room of its classes, or leaves another class's home room."""
    homes = _home_room_by_class(snapshot)
    own_homes = {homes[class_id] for class_id in class_ids if class_id in homes}
    if new_room in own_homes:
        return True
    return any(
        room == previous_room for class_id, room in homes.items() if class_id not in class_ids
    )


def _is_flexible(assignments: dict[int, Assignment], lesson: ScheduledLesson) -> bool:
    return not assignments[lesson.assignment_id].needs_special_room
