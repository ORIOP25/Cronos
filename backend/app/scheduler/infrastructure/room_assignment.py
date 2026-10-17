"""Room pass by the home-room policy (T10): only ``room_id`` of editable lessons changes.

Periods are processed in chronological order. Each period is a min-cost matching
between its editable lessons and their free eligible rooms, weighted by the
lexicographic key of ``home_rooms.room_choice_costs``. Times, identities and
credits never change, so a valid candidate stays valid.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from itertools import combinations

from ortools.graph.python import min_cost_flow

from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
)
from app.scheduler.domain.capacity import available_rooms
from app.scheduler.domain.home_rooms import (
    RoomHabits,
    foreign_home_claims,
    is_justified_room_change,
    lexicographic_weights,
    room_choice_costs,
)
from app.scheduler.domain.recovery import RecoveryPolicy

PositionKey = tuple[int, datetime, datetime]


@dataclass(frozen=True)
class _PassContext:
    snapshot: PlanningSnapshot
    assignments: Mapping[int, Assignment]
    homes: Mapping[int, int]
    published: Mapping[PositionKey, ScheduledLesson]
    policy: RecoveryPolicy | None
    prior_changes: frozenset[int]

    def published_change(
        self, lesson: ScheduledLesson, assignment: Assignment, room_id: int
    ) -> int:
        """Cost of leaving the published room; a justified change costs nothing (T09)."""
        key = (lesson.assignment_id, lesson.period.start_utc, lesson.period.end_utc)
        source = self.published.get(key)
        if self.policy is None or source is None or room_id == source.room_id:
            return 0
        if is_justified_room_change(self.snapshot, assignment.class_ids, source.room_id, room_id):
            return 0
        return self.policy.change_cost(
            self.policy.room_change_cost,
            self.snapshot,
            source,
            source.lesson_id in self.prior_changes,
        )


def assign_rooms_by_period(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
    *,
    baseline: CandidateSchedule | None = None,
    policy: RecoveryPolicy | None = None,
    prior_changes: frozenset[int] = frozenset(),
) -> CandidateSchedule:
    """Return the candidate with rooms chosen by the home-room policy.

    ``baseline`` and ``policy`` are given only in recovery: they price leaving the
    published room, and a justified change costs nothing.
    """
    if (baseline is None) != (policy is None):
        raise ValueError("Published rooms need a baseline and a recovery policy together.")
    context = _PassContext(
        snapshot=snapshot,
        assignments={row.assignment_id: row for row in snapshot.assignments},
        homes={row.class_id: row.room_id for row in snapshot.home_rooms},
        published=_published_by_position(baseline),
        policy=policy,
        prior_changes=prior_changes,
    )
    protected_ids = {row.lesson_id for row in snapshot.protected_lessons}
    partly_overlapping = _partly_overlapping_dates(candidate.lessons, protected_ids)
    rooms = {row.lesson_id: row.room_id for row in candidate.lessons}
    habits = RoomHabits()
    for (school_date, _start, _end), lessons in _periods(candidate.lessons):
        editable = [row for row in lessons if row.lesson_id not in protected_ids]
        if editable and school_date not in partly_overlapping:
            rooms.update(_choose_rooms(context, habits, lessons, editable))
        for row in lessons:
            habits.record(context.assignments[row.assignment_id], school_date, rooms[row.lesson_id])
    return CandidateSchedule(
        tuple(replace(row, room_id=rooms[row.lesson_id]) for row in candidate.lessons)
    )


def _published_by_position(
    baseline: CandidateSchedule | None,
) -> dict[PositionKey, ScheduledLesson]:
    if baseline is None:
        return {}
    return {
        (row.assignment_id, row.period.start_utc, row.period.end_utc): row
        for row in baseline.lessons
    }


def _periods(
    lessons: Iterable[ScheduledLesson],
) -> list[tuple[tuple[date, datetime, datetime], list[ScheduledLesson]]]:
    grouped: dict[tuple[date, datetime, datetime], list[ScheduledLesson]] = defaultdict(list)
    for row in lessons:
        key = (row.period.school_date, row.period.start_utc, row.period.end_utc)
        grouped[key].append(row)
    return sorted(grouped.items())


def _partly_overlapping_dates(
    lessons: Sequence[ScheduledLesson], protected_ids: set[int]
) -> frozenset[date]:
    """Dates where an editable lesson overlaps another lesson without the same period (T13)."""
    by_day: dict[date, list[ScheduledLesson]] = defaultdict(list)
    for row in lessons:
        by_day[row.period.school_date].append(row)
    return frozenset(
        day
        for day, rows in by_day.items()
        if any(
            _partly_overlaps(left, right, protected_ids) for left, right in combinations(rows, 2)
        )
    )


def _partly_overlaps(
    left: ScheduledLesson, right: ScheduledLesson, protected_ids: set[int]
) -> bool:
    editable = left.lesson_id not in protected_ids or right.lesson_id not in protected_ids
    same_period = (left.period.start_utc, left.period.end_utc) == (
        right.period.start_utc,
        right.period.end_utc,
    )
    return editable and not same_period and left.period.overlaps(right.period)


def _choose_rooms(
    context: _PassContext,
    habits: RoomHabits,
    lessons: Sequence[ScheduledLesson],
    editable: Sequence[ScheduledLesson],
) -> dict[int, int]:
    """Best rooms for the editable lessons of one period; the current room is always an option."""
    domains = {
        row.lesson_id: sorted(
            {
                *available_rooms(
                    context.snapshot, context.assignments[row.assignment_id], row.period
                ),
                row.room_id,
            }
        )
        for row in editable
    }
    components: dict[tuple[int, int], tuple[int, ...]] = {}
    for row in editable:
        assignment = context.assignments[row.assignment_id]
        others = [
            context.assignments[other.assignment_id]
            for other in lessons
            if other.lesson_id != row.lesson_id
        ]
        for room in domains[row.lesson_id]:
            components[(row.lesson_id, room)] = (
                *room_choice_costs(
                    context.homes,
                    habits,
                    assignment,
                    row.period.school_date,
                    room,
                    foreign_claims=foreign_home_claims(context.homes, assignment, room, others),
                    published_change=context.published_change(row, assignment, room),
                ),
                room,
            )
    level_count = len(next(iter(components.values())))
    maxima = [max(values[level] for values in components.values()) for level in range(level_count)]
    weights = lexicographic_weights(maxima, len(editable))
    costs = {
        key: sum(weight * value for weight, value in zip(weights, values, strict=True))
        for key, values in components.items()
    }
    return _match(domains, costs)


def _match(
    domains: Mapping[int, Sequence[int]], costs: Mapping[tuple[int, int], int]
) -> dict[int, int]:
    """Give each lesson one room, each room to one lesson, at the lowest total cost."""
    flow = min_cost_flow.SimpleMinCostFlow()
    nodes: dict[tuple[str, int], int] = {}

    def node(kind: str, identity: int) -> int:
        return nodes.setdefault((kind, identity), len(nodes))

    source = node("source", 0)
    sink = node("sink", 0)
    arcs: dict[tuple[int, int], int] = {}
    for lesson_id, rooms in domains.items():
        flow.add_arc_with_capacity_and_unit_cost(source, node("lesson", lesson_id), 1, 0)
        for room in rooms:
            arcs[(lesson_id, room)] = flow.add_arc_with_capacity_and_unit_cost(
                node("lesson", lesson_id), node("room", room), 1, costs[(lesson_id, room)]
            )
    for room in sorted({room for rooms in domains.values() for room in rooms}):
        flow.add_arc_with_capacity_and_unit_cost(node("room", room), sink, 1, 0)
    supply = len(domains)
    flow.set_node_supply(source, supply)
    flow.set_node_supply(sink, -supply)
    status = flow.solve_max_flow_with_min_cost()
    if status != flow.OPTIMAL:
        raise RuntimeError(f"Period room matching failed: {status}.")
    chosen = {lesson_id: room for (lesson_id, room), arc in arcs.items() if flow.flow(arc)}
    if len(chosen) != supply:
        raise RuntimeError("Period room matching left a lesson without a room.")
    return chosen
