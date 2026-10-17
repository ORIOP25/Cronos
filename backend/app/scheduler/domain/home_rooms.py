"""Home-room measures of a schedule: misses and avoidable room changes.

Pure rules over a snapshot and a candidate. The proposal publishes the two
counts; they never enter the quality vector, and a justified room change costs
nothing in the adaptive disruption.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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


@dataclass
class RoomHabits:
    """Rooms each class has used so far, recorded in chronological order (D03, D07)."""

    last_on_day: dict[tuple[int, date], tuple[int, bool]] = field(default_factory=dict)
    flexible_rooms: dict[int, Counter[int]] = field(default_factory=lambda: defaultdict(Counter))
    subject_rooms: dict[tuple[int, int], Counter[int]] = field(
        default_factory=lambda: defaultdict(Counter)
    )

    def record(self, assignment: Assignment, school_date: date, room_id: int) -> None:
        flexible = not assignment.needs_special_room
        for class_id in assignment.class_ids:
            self.last_on_day[(class_id, school_date)] = (room_id, flexible)
            if flexible:
                self.flexible_rooms[class_id][room_id] += 1
            else:
                self.subject_rooms[(class_id, assignment.subject_id)][room_id] += 1


def _most_used(counter: Counter[int] | None) -> int | None:
    if not counter:
        return None
    return max(counter, key=lambda room: (counter[room], -room))


def _habitual_room(
    habits: RoomHabits, assignment: Assignment, class_id: int, homes: Mapping[int, int]
) -> int | None:
    if assignment.needs_special_room:
        return _most_used(habits.subject_rooms.get((class_id, assignment.subject_id)))
    if class_id in homes:
        return None
    return _most_used(habits.flexible_rooms.get(class_id))


@dataclass(frozen=True)
class ForeignClaims:
    """Home-room claims of the editable lessons of one period, counted once (D04).

    A claim is a class whose home room is a room the lesson may use. Claims by the
    lesson's own classes never count against it.
    """

    room_totals: Mapping[int, int]
    class_room_counts: Mapping[tuple[int, int], int]

    @classmethod
    def of(cls, homes: Mapping[int, int], assignments: Sequence[Assignment]) -> "ForeignClaims":
        room_totals: Counter[int] = Counter()
        class_room_counts: Counter[tuple[int, int]] = Counter()
        for assignment in assignments:
            for room_id in assignment.eligible_room_ids:
                for class_id in assignment.class_ids:
                    if homes.get(class_id) == room_id:
                        room_totals[room_id] += 1
                        class_room_counts[(class_id, room_id)] += 1
        return cls(room_totals, class_room_counts)

    def for_lesson(self, assignment: Assignment, room_id: int) -> int:
        """Other classes whose home room is ``room_id`` and whose lesson in the period fits it."""
        own = sum(
            self.class_room_counts.get((class_id, room_id), 0) for class_id in assignment.class_ids
        )
        return self.room_totals.get(room_id, 0) - own


def room_choice_costs(
    homes: Mapping[int, int],
    habits: RoomHabits,
    assignment: Assignment,
    school_date: date,
    room_id: int,
    *,
    foreign_claims: int,
    published_change: int,
) -> tuple[int, ...]:
    """Priority costs of putting one lesson in one room.

    1. home-room misses (D04); 2. leaving the published room, zero when justified
    (recovery only, T09); 3. avoidable change from the class's previous lesson that
    day (D03); 4. taking another class's home room (D04); 5. the habitual room of a
    flexible lesson without a home room, or of a special-room subject (D07).
    """
    misses = sum(
        1
        for class_id in assignment.class_ids
        if homes.get(class_id) in assignment.eligible_room_ids and homes[class_id] != room_id
    )
    avoidable = 0
    if not assignment.needs_special_room:
        for class_id in assignment.class_ids:
            previous = habits.last_on_day.get((class_id, school_date))
            if previous is not None and previous[1] and previous[0] != room_id:
                avoidable += 1
    habitual = sum(
        1
        for class_id in assignment.class_ids
        if _habitual_room(habits, assignment, class_id, homes) not in (None, room_id)
    )
    return (misses, published_change, avoidable, foreign_claims, habitual)


def lexicographic_weights(maxima: Sequence[int], lesson_count: int) -> tuple[int, ...]:
    """Weights that let each priority outweigh every lower priority together.

    ``maxima[k]`` bounds one lesson's component ``k``; a matching of
    ``lesson_count`` lessons adds at most ``lesson_count * maxima[k]`` to it.
    """
    weights = [0] * len(maxima)
    lower_bound = 0
    for index in reversed(range(len(maxima))):
        weights[index] = lower_bound + 1
        lower_bound += weights[index] * lesson_count * maxima[index]
    if lower_bound >= 2**62:
        raise ValueError("Room choice costs exceed the solver's integer range.")
    return tuple(weights)
