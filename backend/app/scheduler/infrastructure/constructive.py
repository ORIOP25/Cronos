"""Chronological construction with parallel curricular progress.

Subjects advance together at the pace allowed by shared resources.
Within that cadence, adjacent teacher and class lessons take priority.
Construction failure is inconclusive; every returned plan is independently valid.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date
from fractions import Fraction
from time import monotonic

from ortools.graph.python import min_cost_flow
from ortools.sat.python import cp_model

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
    allocate_lesson_identity,
    continuous_break_minutes,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import (
    available_rooms,
    canonical_periods,
    eligible_periods,
    residual_minutes,
    room_free,
)
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


def _progress_targets(
    snapshot: PlanningSnapshot,
    eligible: dict[int, tuple[Period, ...]],
    remaining: dict[int, int],
    occupied: dict[tuple, list[tuple[int, int]]],
) -> dict[tuple[int, date], Fraction]:
    """Estimate a shared resource pace, without stretching demand to year end.

    Independent resource groups can finish independently. Capacity is a pacing
    estimate, not proof that those resources can be allocated simultaneously.
    """
    members: dict[tuple[str, int], set[int]] = defaultdict(set)
    resources: dict[int, tuple[tuple[str, int], ...]] = {}
    availability: dict[tuple[str, int], set[Period]] = defaultdict(set)
    demand: dict[tuple[str, int], int] = defaultdict(int)
    for identity, periods in eligible.items():
        assignment = snapshot.assignment_for(identity)
        keys = (("class", assignment.class_id), ("teacher", assignment.teacher_id))
        resources[identity] = (*keys, *(("room", room) for room in assignment.eligible_room_ids))
        for key in resources[identity]:
            members[key].add(identity)
            availability[key].update(periods)
        for key in keys:
            demand[key] += remaining[identity]

    days = sorted({period.school_date for periods in eligible.values() for period in periods})
    capacity: dict[tuple[str, int], dict[date, int]] = {}
    capacity_by_calendar: dict[tuple, dict[date, int]] = {}
    for key, periods in availability.items():
        if key[0] == "room":
            periods = {period for period in periods if room_free(snapshot, key[1], period)}
        protected = tuple(
            (day, tuple(occupied[(*key, day)])) for day in days if occupied.get((*key, day))
        )
        calendar_key = (frozenset(periods), protected, key[0] != "room")
        if calendar_key in capacity_by_calendar:
            capacity[key] = capacity_by_calendar[calendar_key]
            continue
        daily: dict[date, list[tuple[int, int]]] = defaultdict(list)
        minutes: dict[date, int] = defaultdict(int)
        for period in sorted(periods, key=lambda row: (row.start_utc, row.end_utc)):
            day = period.school_date
            interval = _local_interval(period)
            intervals = [*occupied.get((*key, day), ()), *daily[day]]
            if any(interval[0] < end and start < interval[1] for start, end in intervals):
                continue
            if key[0] != "room" and snapshot.lunch_rule is not None:
                if (
                    continuous_break_minutes([*intervals, interval], snapshot.lunch_rule)
                    < snapshot.lunch_rule.minimum_minutes
                ):
                    continue
            daily[day].append(interval)
            minutes[day] += period.duration_minutes
        elapsed = 0
        capacity[key] = {}
        for day in days:
            elapsed += minutes[day]
            capacity[key][day] = elapsed
        capacity_by_calendar[calendar_key] = capacity[key]

    targets = {}
    unseen = set(eligible)
    while unseen:
        group = {min(unseen)}
        pending = list(group)
        shared: set[tuple[str, int]] = set()
        while pending:
            identity = pending.pop()
            for key in resources[identity]:
                if key in shared:
                    continue
                shared.add(key)
                additions = members[key] - group
                group.update(additions)
                pending.extend(sorted(additions))
        unseen.difference_update(group)
        room_sets = {snapshot.assignment_for(identity).eligible_room_ids for identity in group}
        room_sets.add(frozenset(key[1] for key in shared if key[0] == "room"))
        room_demands = {
            rooms: sum(
                remaining[identity]
                for identity in group
                if snapshot.assignment_for(identity).eligible_room_ids <= rooms
            )
            for rooms in room_sets
        }
        for day in days:
            pace = min(
                (Fraction(capacity[key][day], demand[key]) for key in shared if key in demand),
                default=Fraction(1),
            )
            pace = min(
                pace,
                *(
                    Fraction(sum(capacity[("room", room)][day] for room in rooms), need)
                    for rooms, need in room_demands.items()
                    if need > 0
                ),
            )
            for identity in group:
                targets[(identity, day)] = min(Fraction(1), pace)
    return targets


def _flow_selection(
    options: list[tuple[Assignment, tuple[int, ...]]],
) -> list[tuple[Assignment, int]] | None:
    """Match resources; validate each selected subject's actual room domain."""
    rooms_by_class: dict[int, tuple[int, ...]] = {}
    rooms_by_assignment = {row.assignment_id: rooms for row, rooms in options}
    for assignment, rooms in options:
        rooms_by_class[assignment.class_id] = tuple(
            dict.fromkeys((*rooms_by_class.get(assignment.class_id, ()), *rooms))
        )
    flow = min_cost_flow.SimpleMinCostFlow()
    nodes: dict[tuple, int] = {}

    def node(kind: str, identity: int = 0) -> int:
        return nodes.setdefault((kind, identity), len(nodes))

    source, sink = node("source"), node("sink")
    teachers = sorted({row.teacher_id for row, _rooms in options})
    rooms = sorted({room for _row, values in options for room in values})
    for teacher in teachers:
        flow.add_arc_with_capacity_and_unit_cost(source, node("teacher", teacher), 1, 0)
    for class_id in sorted(rooms_by_class):
        flow.add_arc_with_capacity_and_unit_cost(
            node("class", class_id), node("class_out", class_id), 1, 0
        )
    for room in rooms:
        flow.add_arc_with_capacity_and_unit_cost(node("room", room), sink, 1, 0)
    assignment_arcs = []
    for rank, (assignment, _rooms) in enumerate(options):
        arc = flow.add_arc_with_capacity_and_unit_cost(
            node("teacher", assignment.teacher_id), node("class", assignment.class_id), 1, rank
        )
        assignment_arcs.append((assignment, arc))
    room_arcs = {
        (class_id, room): flow.add_arc_with_capacity_and_unit_cost(
            node("class_out", class_id), node("room", room), 1, 0
        )
        for class_id, values in sorted(rooms_by_class.items())
        for room in values
    }
    upper = min(len(teachers), len(rooms_by_class), len(rooms))
    flow.set_node_supply(source, upper)
    flow.set_node_supply(sink, -upper)
    status = flow.solve_max_flow_with_min_cost()
    if status != flow.OPTIMAL:
        raise RuntimeError(f"Period resource matching failed: {status}.")
    selected = [
        (
            assignment,
            next(
                room
                for room in rooms_by_class[assignment.class_id]
                if flow.flow(room_arcs[(assignment.class_id, room)])
            ),
        )
        for assignment, arc in assignment_arcs
        if flow.flow(arc)
    ]
    if any(room not in rooms_by_assignment[row.assignment_id] for row, room in selected):
        # Selected classes are unique. A second flow assigns their actual rooms.
        refined = _flow_selection(
            [(row, rooms_by_assignment[row.assignment_id]) for row, _room in selected]
        )
        return refined if refined is not None and len(refined) == len(selected) else None
    return selected


def _select_period(
    options: list[tuple[Assignment, tuple[int, ...]]],
    *,
    deadline: float | None,
) -> list[tuple[Assignment, int]]:
    """Fill a period; repair greedy resource choices with a small native model."""
    selected = []
    classes: set[int] = set()
    teachers: set[int] = set()
    rooms: set[int] = set()
    for assignment, available in options:
        room = next((value for value in available if value not in rooms), None)
        if assignment.class_id in classes or assignment.teacher_id in teachers or room is None:
            continue
        selected.append((assignment, room))
        classes.add(assignment.class_id)
        teachers.add(assignment.teacher_id)
        rooms.add(room)
    upper = min(
        len({row.class_id for row, _ in options}),
        len({row.teacher_id for row, _ in options}),
        len({room for _, available in options for room in available}),
    )
    if len(selected) == upper:
        return selected

    matched = _flow_selection(options)
    if matched is not None:
        return matched

    # ponytail: resolve only this period, without annual placement variables.
    # A construction dead end still falls back to the existing complete search.
    model = cp_model.CpModel()
    choices: dict[tuple[int, int, int], tuple[Assignment, cp_model.IntVar]] = {}
    resource_choices: dict[tuple[str, int], list] = defaultdict(list)
    preferred = {(row.assignment_id, room) for row, room in selected}
    terms = []
    count_weight = len(options) ** 2 + 1
    for rank, (assignment, available) in enumerate(options):
        for room in available:
            key = (assignment.class_id, assignment.teacher_id, room)
            # Identical resource choices retain the highest-priority subject.
            if key in choices:
                continue
            variable = model.NewBoolVar(f"choice_{assignment.assignment_id}_{room}")
            choices[key] = (assignment, variable)
            for kind, identity in zip(("class", "teacher", "room"), key, strict=True):
                resource_choices[(kind, identity)].append(variable)
            terms.append((count_weight + len(options) - rank) * variable)
            model.AddHint(variable, int((assignment.assignment_id, room) in preferred))
    for variables in resource_choices.values():
        model.AddAtMostOne(variables)
    model.Maximize(sum(terms))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 1
    # ponytail: each period gets a short repair; unresolved choices keep the
    # feasible greedy selection and final coverage still needs validation.
    solver.parameters.max_time_in_seconds = 0.1
    if deadline is not None:
        solver.parameters.max_time_in_seconds = min(0.1, max(0.0, deadline - monotonic()))
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return selected
    return [
        (assignment, key[2])
        for key, (assignment, variable) in choices.items()
        if solver.Value(variable)
    ]


def construct_schedule(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    *,
    deadline: float | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> CandidateSchedule | None:
    """Construct one complete plan, preserving hard rules and protected credit."""
    canonical = canonical_periods(periods)
    slots = sorted(
        snapshot.grid_slots, key=lambda slot: (slot.day_of_week, slot.start_local, slot.end_local)
    )
    preceding_ends = {
        (right.day_of_week, right.start_local, right.end_local): left.end_local.hour * 60
        + left.end_local.minute
        for left, right in zip(slots, slots[1:], strict=False)
        if left.day_of_week == right.day_of_week and left.end_local <= right.start_local
    }
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    required = {
        identity: sum(module.required_minutes for module in row.modules)
        for identity, row in assignments.items()
    }
    remaining = {identity: residual_minutes(snapshot, identity) for identity in assignments}
    initial_remaining = dict(remaining)
    cursor = {
        identity: {
            module.module_id: snapshot.executed_minutes.get(identity, {}).get(module.module_id, 0)
            for module in row.modules
        }
        for identity, row in assignments.items()
    }
    busy: dict[tuple, list[Period]] = defaultdict(list)
    occupancy: dict[tuple, list[tuple[int, int]]] = defaultdict(list)
    used_ids = {row.lesson_id for row in snapshot.protected_lessons} | set(
        snapshot.reserved_lesson_ids
    )
    started_classes = {
        row.class_id
        for identity, row in assignments.items()
        if remaining[identity] < required[identity]
    }

    def occupy(assignment: Assignment, period: Period, room: int, teacher: int) -> None:
        for kind, identity in (
            ("class", assignment.class_id),
            ("teacher", teacher),
            ("room", room),
        ):
            busy[(kind, identity, period.school_date)].append(period)
            if kind != "room":
                occupancy[(kind, identity, period.school_date)].append(_local_interval(period))

    for lesson in snapshot.protected_lessons:
        assignment = assignments[lesson.assignment_id]
        occupy(
            assignment, lesson.period, lesson.room_id, lesson.teacher_id or assignment.teacher_id
        )
        for module_slice in lesson.slices:
            cursor[lesson.assignment_id][module_slice.module_id] += module_slice.credit_minutes

    options_by_period: dict[Period, list[Assignment]] = defaultdict(list)
    room_pressure: dict[int, Fraction] = defaultdict(Fraction)
    class_remaining: dict[int, int] = defaultdict(int)
    teacher_remaining: dict[int, int] = defaultdict(int)
    eligible_by_assignment: dict[int, tuple[Period, ...]] = {}
    for identity, assignment in assignments.items():
        if (should_cancel is not None and should_cancel()) or (
            deadline is not None and monotonic() >= deadline
        ):
            return None
        if remaining[identity] <= 0:
            continue
        eligible = eligible_periods(snapshot, assignment, canonical)
        eligible_by_assignment[identity] = eligible
        for period in eligible:
            options_by_period[period].append(assignment)
        class_remaining[assignment.class_id] += remaining[identity]
        teacher_remaining[assignment.teacher_id] += remaining[identity]
        for room in assignment.eligible_room_ids:
            room_pressure[room] += Fraction(remaining[identity], len(assignment.eligible_room_ids))

    targets = _progress_targets(snapshot, eligible_by_assignment, initial_remaining, occupancy)
    ranks: dict[int, int] = defaultdict(int)
    lessons: list[ScheduledLesson] = []
    for period in canonical:
        if (should_cancel is not None and should_cancel()) or (
            deadline is not None and monotonic() >= deadline
        ):
            return None
        active = [row for row in options_by_period[period] if remaining[row.assignment_id] > 0]
        if not active:
            continue
        preceding_end = preceding_ends.get(
            (period.school_date.weekday(), period.start_local, period.end_local)
        )

        def priority(
            assignment: Assignment,
            current_period: Period = period,
            previous_end: int | None = preceding_end,
        ):
            identity = assignment.assignment_id
            adjacent = sum(
                any(
                    end == previous_end
                    for _start, end in occupancy[(kind, resource, current_period.school_date)]
                )
                for kind, resource in (
                    ("class", assignment.class_id),
                    ("teacher", assignment.teacher_id),
                )
            )
            return (
                assignment.class_id in started_classes,
                initial_remaining[identity] != remaining[identity],
                -adjacent,
                Fraction(required[identity] - remaining[identity], required[identity]),
                -teacher_remaining[assignment.teacher_id],
                -class_remaining[assignment.class_id],
                len(assignment.eligible_room_ids),
                identity,
            )

        options = []
        for assignment in sorted(active, key=priority):
            identity = assignment.assignment_id
            placed = initial_remaining[identity] - remaining[identity]
            if placed >= initial_remaining[identity] * targets[(identity, period.school_date)]:
                continue
            keys = (
                ("class", assignment.class_id, period.school_date),
                ("teacher", assignment.teacher_id, period.school_date),
            )
            if any(period.overlaps(occupied) for key in keys for occupied in busy[key]):
                continue
            if snapshot.lunch_rule is not None and any(
                continuous_break_minutes(
                    [*occupancy[key], _local_interval(period)], snapshot.lunch_rule
                )
                < snapshot.lunch_rule.minimum_minutes
                for key in keys
            ):
                continue
            rooms = tuple(
                sorted(
                    (
                        room
                        for room in available_rooms(snapshot, assignment, period)
                        if not any(
                            period.overlaps(occupied)
                            for occupied in busy[("room", room, period.school_date)]
                        )
                    ),
                    key=lambda room: (room_pressure[room], room),
                )
            )
            if rooms:
                options.append((assignment, rooms))
        for assignment, room in _select_period(options, deadline=deadline):
            identity = assignment.assignment_id
            credit = min(remaining[identity], period.duration_minutes)
            ranks[identity] += 1
            lesson_id = allocate_lesson_identity(identity, ranks[identity], used_ids)
            slices = []
            unallocated = credit
            while unallocated > 0:
                module_index = _next_module(assignment.modules, cursor[identity])
                if module_index is None:
                    return None
                module = assignment.modules[module_index]
                offset = cursor[identity][module.module_id]
                take = min(unallocated, module.required_minutes - offset)
                slices.append(ModuleSlice(lesson_id, module.module_id, offset, take))
                cursor[identity][module.module_id] += take
                unallocated -= take
            lessons.append(
                ScheduledLesson(lesson_id, identity, period, room, credit, tuple(slices))
            )
            remaining[identity] -= credit
            class_remaining[assignment.class_id] -= credit
            teacher_remaining[assignment.teacher_id] -= credit
            started_classes.add(assignment.class_id)
            occupy(assignment, period, room, assignment.teacher_id)
        if not any(remaining.values()):
            break
    if any(remaining.values()):
        return None
    candidate = CandidateSchedule((*snapshot.protected_lessons, *lessons))
    return candidate if validate_candidate(snapshot, candidate).valid else None
