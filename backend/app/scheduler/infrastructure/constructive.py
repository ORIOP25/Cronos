"""Chronological construction with parallel curricular progress.

Subjects with less progress take priority when competing for shared resources.
Repeating the weekly pattern may compensate for one lesson of progress.
Free resource combinations remain eligible even when other subjects must wait.
Construction failure is inconclusive; every returned plan is independently valid.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
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
    weekly_pattern: dict[tuple, tuple[int, int]] = {}
    used_ids = {row.lesson_id for row in snapshot.protected_lessons} | set(
        snapshot.reserved_lesson_ids
    )
    started_classes = {
        row.class_id
        for identity, row in assignments.items()
        if remaining[identity] < required[identity]
    }

    def occupy(assignment: Assignment, period: Period, room: int, teacher: int) -> None:
        weekly_pattern.setdefault(
            (
                assignment.class_id,
                period.school_date.weekday(),
                period.start_local,
                period.end_local,
            ),
            (assignment.assignment_id, room),
        )
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
    for identity, assignment in assignments.items():
        if (should_cancel is not None and should_cancel()) or (
            deadline is not None and monotonic() >= deadline
        ):
            return None
        if remaining[identity] <= 0:
            continue
        eligible = eligible_periods(snapshot, assignment, canonical)
        for period in eligible:
            options_by_period[period].append(assignment)
        class_remaining[assignment.class_id] += remaining[identity]
        teacher_remaining[assignment.teacher_id] += remaining[identity]
        for room in assignment.eligible_room_ids:
            room_pressure[room] += Fraction(remaining[identity], len(assignment.eligible_room_ids))

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
        signature = (period.school_date.weekday(), period.start_local, period.end_local)

        def priority(
            assignment: Assignment,
            current_period: Period = period,
            previous_end: int | None = preceding_end,
            current_signature: tuple = signature,
        ):
            identity = assignment.assignment_id
            preferred = weekly_pattern.get((assignment.class_id, *current_signature))
            repeats = preferred is not None and preferred[0] == identity
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
                Fraction(
                    required[identity]
                    - remaining[identity]
                    - (min(remaining[identity], current_period.duration_minutes) if repeats else 0),
                    required[identity],
                ),
                -adjacent,
                preferred is None,
                not repeats,
                -teacher_remaining[assignment.teacher_id],
                -class_remaining[assignment.class_id],
                len(assignment.eligible_room_ids),
                identity,
            )

        options = []
        for assignment in sorted(active, key=priority):
            identity = assignment.assignment_id
            preferred = weekly_pattern.get((assignment.class_id, *signature))
            preferred_room = (
                preferred[1] if preferred is not None and preferred[0] == identity else None
            )
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
                    key=lambda room: (room != preferred_room, room_pressure[room], room),
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
