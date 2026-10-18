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

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
)
from app.scheduler.domain.capacity import available_rooms
from app.scheduler.domain.home_rooms import (
    ForeignClaims,
    RoomHabits,
    avoidable_room_changes,
    home_room_misses,
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
        """Cost of leaving the published room, the last priority; a justified change costs nothing (T09)."""
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
    published room, and a justified change costs nothing. Without a baseline the pass
    returns the input when its result is lexicographically worse on (home-room misses,
    avoidable changes), unless the input shares a room in one period: such an input is
    repaired, not compared. With a baseline the guard does not apply: in recovery the
    published room is the last cost, so it only breaks ties after avoidable changes (T09,
    owner decision 2026-10-18).
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
            chosen = _choose_rooms(context, habits, lessons, editable)
            if chosen is None:
                # The period cannot give each lesson its own room, so the input is invalid
                # and the validator rejects it downstream.
                return candidate
            rooms.update(chosen)
        for row in lessons:
            habits.record(context.assignments[row.assignment_id], school_date, rooms[row.lesson_id])
    result = CandidateSchedule(
        tuple(replace(row, room_id=rooms[row.lesson_id]) for row in candidate.lessons)
    )
    guarded = baseline is None and not _shares_a_room(candidate)
    # ponytail: the guard returns the whole input when one period worsens, so the other
    # periods' gains are lost too; upgrade = guard each period's matching on its own.
    if guarded and _worse_room_plan(snapshot, result, candidate):
        return candidate
    return result


def _shares_a_room(candidate: CandidateSchedule) -> bool:
    """True when two lessons of one period hold the same room; the pass repairs that clash."""
    seen: set[tuple[date, datetime, datetime, int]] = set()
    for row in candidate.lessons:
        key = (row.period.school_date, row.period.start_utc, row.period.end_utc, row.room_id)
        if key in seen:
            return True
        seen.add(key)
    return False


def _worse_room_plan(
    snapshot: PlanningSnapshot, result: CandidateSchedule, reference: CandidateSchedule
) -> bool:
    """True when ``result`` has more home-room misses, or as many and more avoidable changes."""
    result_key = (home_room_misses(snapshot, result), avoidable_room_changes(snapshot, result))
    reference_key = (
        home_room_misses(snapshot, reference),
        avoidable_room_changes(snapshot, reference),
    )
    return result_key > reference_key


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
    """Dates where two distinct periods overlap and one of them holds an editable lesson (T13).

    Compares the distinct periods of each day, not every pair of lessons.
    """
    periods_by_day: dict[date, dict[tuple[datetime, datetime], tuple[Period, bool]]] = defaultdict(
        dict
    )
    for row in lessons:
        day_periods = periods_by_day[row.period.school_date]
        key = (row.period.start_utc, row.period.end_utc)
        _period, editable = day_periods.get(key, (row.period, False))
        day_periods[key] = (row.period, editable or row.lesson_id not in protected_ids)
    # ponytail: a date with a partial overlap keeps its construction rooms; upgrade = interval
    # matching that reassigns rooms across the overlapping periods.
    return frozenset(
        day
        for day, day_periods in periods_by_day.items()
        if any(
            left.overlaps(right) and (left_editable or right_editable)
            for (left, left_editable), (right, right_editable) in combinations(
                day_periods.values(), 2
            )
        )
    )


def _choose_rooms(
    context: _PassContext,
    habits: RoomHabits,
    lessons: Sequence[ScheduledLesson],
    editable: Sequence[ScheduledLesson],
) -> dict[int, int] | None:
    """Best rooms for the editable lessons of one period; None when they cannot all get one."""
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
    claims = ForeignClaims.of(
        context.homes, [context.assignments[row.assignment_id] for row in editable]
    )
    components: dict[tuple[int, int], tuple[int, ...]] = {}
    for row in editable:
        assignment = context.assignments[row.assignment_id]
        # I09: a flexible lesson of classes without a home room keeps its current room on a
        # tie. This level sits just above the room_id tie-break.
        # ponytail: other lessons still take the lowest room id on a tie; upgrade = extend
        # this level to every class after the owner reviews the R19 and R20 expectations.
        keeps_room = not assignment.needs_special_room and not any(
            class_id in context.homes for class_id in assignment.class_ids
        )
        for room in domains[row.lesson_id]:
            components[(row.lesson_id, room)] = (
                *room_choice_costs(
                    context.homes,
                    habits,
                    assignment,
                    row.period.school_date,
                    room,
                    foreign_claims=claims.for_lesson(assignment, room),
                    published_change=context.published_change(row, assignment, room),
                ),
                int(keeps_room and room != row.room_id),
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
) -> dict[int, int] | None:
    """Give each lesson one room, each room to one lesson, at the lowest total cost.

    None when no such matching exists; the solver must still reach an optimal flow.
    """
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
        return None
    return chosen
