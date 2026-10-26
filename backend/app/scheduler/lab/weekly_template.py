"""Lab MVP of a weekly-template timetable: one CP-SAT pattern rolled out on real dates.

Not wired into production (search, jobs, API). A template is a weekly pattern of booleans
x[unit, weekday, slot] that enforces the owner's day rules for every class: zero lessons or at
least three, at most one internal gap, lunch kept free. The rollout walks the calendar week by
week: a template lesson lands on its real date when that date is still usable, otherwise it is
skipped. Rooms and validation reuse the production passes, so a violation is reported, not hidden.
"""

from __future__ import annotations

import time as clock
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import ceil

from ortools.sat.python import cp_model

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
    UnavailableResource,
    allocate_lesson_identity,
)
from app.scheduler.domain.capacity import (
    canonical_periods,
    is_physically_protected,
    residual_minutes,
    room_free,
)
from app.scheduler.domain.priorities import (
    DEFAULT_LEVELS,
    PRIORITY_MULTIPLIERS,
    UNIT_COSTS,
    PriorityWeights,
)
from app.scheduler.domain.priority_metrics import typical_lesson_minutes
from app.scheduler.domain.projection import FutureLesson, project_module_slices
from app.scheduler.infrastructure.room_assignment import assign_rooms_by_period

SlotKey = tuple[int, time, time]  # (weekday, start_local, end_local) of a grid slot
Placement = tuple[int, int, time, time]  # (assignment_id, weekday, start_local, end_local)
TEACHER = UnavailableResource.TEACHER
CLASS = UnavailableResource.CLASS
REFRESH_WEEKS = 4
# One lesson below its weekly target costs more than any preference, so the target holds
# whenever the rules allow it; a shortfall is reported, never silently accepted.
SHORTFALL_WEIGHT = 10**6
SOLVED_STATUSES = ("OPTIMAL", "FEASIBLE")
# Deterministic solver budgets: about three minutes for the first template, about two minutes for a
# warm-started re-solve, measured on the development machine (CP-SAT ticks are not seconds).
FIRST_SOLVE_TICKS = 60
RESOLVE_TICKS = 40


@dataclass(frozen=True)
class Template:
    placements: frozenset[Placement]
    status: str
    variables: int
    shortfall: int
    seconds: float


@dataclass(frozen=True)
class MvpResult:
    candidate: CandidateSchedule | None
    status: str
    stats: dict[str, object]


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _duration(key: SlotKey) -> int:
    return _minutes(key[2]) - _minutes(key[1])


def _slot_of(period: Period) -> SlotKey:
    return (period.school_date.weekday(), period.start_local, period.end_local)


def _overlapping_slots(period: Period, slots: Iterable[SlotKey]) -> list[SlotKey]:
    return [
        key
        for key in slots
        if key[0] == period.school_date.weekday()
        and key[1] < period.end_local
        and period.start_local < key[2]
    ]


def _resources(assignment: Assignment) -> tuple[tuple[UnavailableResource, int], ...]:
    return (
        (TEACHER, assignment.teacher_id),
        *((CLASS, class_id) for class_id in assignment.class_ids),
    )


def _minute_costs(snapshot: PlanningSnapshot) -> dict[str, int]:
    """Integer cost of one measured minute per criterion, priced with the school levels (T13)."""
    weights = snapshot.priority_weights or PriorityWeights(DEFAULT_LEVELS)
    return {
        key: PRIORITY_MULTIPLIERS[getattr(weights, key)] * UNIT_COSTS[key]
        for key in (
            "teacher_gaps",
            "class_gaps",
            "teacher_single_lessons",
            "teacher_preferences",
            "class_preferences",
            "weekly_stability",
        )
    }


def _blocked_resources(
    snapshot: PlanningSnapshot, slots: list[SlotKey], occurrences: Mapping[SlotKey, int]
) -> frozenset[tuple[UnavailableResource, int, SlotKey]]:
    """Slots that a resource cannot use as a weekly pattern: hard unavailability on most dates.

    Date-specific blocks that cover only a few dates are not in the template; the rollout skips
    those dates instead.
    """
    dates = {
        (row.resource_type, row.resource_id, key, row.period.school_date)
        for row in snapshot.unavailable
        for key in _overlapping_slots(row.period, slots)
    }
    counted = Counter((kind, identity, key) for kind, identity, key, _day in dates)
    return frozenset(
        resource for resource, count in counted.items() if 2 * count > occurrences[resource[2]]
    )


def _evitar_costs(
    snapshot: PlanningSnapshot,
    slots: list[SlotKey],
    occurrences: Mapping[SlotKey, int],
    costs: Mapping[str, int],
) -> dict[tuple[UnavailableResource, int, SlotKey], int]:
    """Average Evitar cost of one lesson in each slot, from the soft unavailability rows."""
    totals: Counter = Counter()
    for row in snapshot.soft_unavailable:
        weight = (
            costs["teacher_preferences"]
            if row.resource_type is TEACHER
            else costs["class_preferences"]
        )
        for key in _overlapping_slots(row.period, slots):
            overlap = min(_minutes(row.period.end_local), _minutes(key[2])) - max(
                _minutes(row.period.start_local), _minutes(key[1])
            )
            totals[(row.resource_type, row.resource_id, key)] += overlap * weight
    return {
        resource: round(total / max(occurrences[resource[2]], 1))
        for resource, total in totals.items()
    }


def _lunch_slots(snapshot: PlanningSnapshot, slots: list[SlotKey]) -> dict[int, frozenset[SlotKey]]:
    """Grid slots inside the lunch window that are long enough to be the lunch break."""
    rule = snapshot.lunch_rule
    if rule is None:
        return {}
    fits: dict[int, set[SlotKey]] = defaultdict(set)
    for key in slots:
        inside = rule.window_start <= key[1] and key[2] <= rule.window_end
        if inside and _duration(key) >= rule.minimum_minutes:
            fits[key[0]].add(key)
    return {weekday: frozenset(keys) for weekday, keys in fits.items()}


def build_weekly_template(
    snapshot: PlanningSnapshot,
    periods: Iterable[Period],
    *,
    remaining: Mapping[int, int],
    weeks_left: int,
    previous: frozenset[Placement] = frozenset(),
    ticks: float = RESOLVE_TICKS,
    time_limit_seconds: float = 600.0,
    random_seed: int = 1,
) -> Template:
    """Solve one weekly pattern for the given units (remaining minutes per unit)."""
    started = clock.perf_counter()
    slots = sorted(
        {(row.day_of_week, row.start_local, row.end_local) for row in snapshot.grid_slots}
    )
    occurrences = Counter(_slot_of(period) for period in periods)
    lesson_minutes = typical_lesson_minutes(snapshot.grid_slots)
    costs = _minute_costs(snapshot)
    blocked = _blocked_resources(snapshot, slots, occurrences)
    evitar = _evitar_costs(snapshot, slots, occurrences, costs)
    lunch = _lunch_slots(snapshot, slots)
    presence = {rule.teacher_id: rule for rule in snapshot.teacher_presence}
    dispensed = snapshot.lunch_dispensed_teacher_ids
    units = {unit_id: snapshot.assignment_for(unit_id) for unit_id in remaining}

    model = cp_model.CpModel()
    x: dict[tuple[int, SlotKey], cp_model.IntVar] = {}
    on: dict[tuple[UnavailableResource, int, SlotKey], list[cp_model.IntVar]] = defaultdict(list)
    cost_terms: list[tuple[cp_model.IntVar, int]] = []
    for unit_id, unit in units.items():
        for key in slots:
            if any((kind, identity, key) in blocked for kind, identity in _resources(unit)):
                continue
            var = model.new_bool_var("")
            x[(unit_id, key)] = var
            model.add_hint(var, (unit_id, key[0], key[1], key[2]) in previous)
            for kind, identity in _resources(unit):
                on[(kind, identity, key)].append(var)
            evitar_cost = sum(
                evitar.get((kind, identity, key), 0) for kind, identity in _resources(unit)
            )
            if evitar_cost:
                cost_terms.append((var, evitar_cost))

    for members in on.values():
        if len(members) > 1:
            model.add(sum(members) <= 1)
    for room_set in {unit.eligible_room_ids for unit in units.values()}:
        for key in slots:
            members = [
                x[(unit_id, key)]
                for unit_id, unit in units.items()
                if (unit_id, key) in x and unit.eligible_room_ids <= room_set
            ]
            if len(members) > len(room_set):
                model.add(sum(members) <= len(room_set))

    day_keys = {
        weekday: [key for key in slots if key[0] == weekday] for weekday in {k[0] for k in slots}
    }
    for kind, identity in sorted(
        {(kind, identity) for kind, identity, _key in on}, key=lambda r: (r[0].value, r[1])
    ):
        is_teacher = kind is TEACHER
        lunch_required = not (is_teacher and identity in dispensed)
        rule = presence.get(identity) if is_teacher else None
        for weekday, keys in sorted(day_keys.items()):
            occupied = {key: on.get((kind, identity, key), []) for key in keys}
            day_vars = [var for key in keys for var in occupied[key]]
            if not day_vars:
                continue
            used = model.new_bool_var("")
            for var in day_vars:
                model.add(used >= var)
            model.add(used <= sum(day_vars))
            if not is_teacher:
                model.add(3 * used <= sum(day_vars))
                model.add(sum(day_vars) <= len(keys) * used)
            lunch_keys = lunch.get(weekday, frozenset()) if lunch_required else frozenset()
            if lunch_required:
                lunch_vars = [var for key in lunch_keys for var in occupied[key]]
                model.add(sum(lunch_vars) + used <= len(lunch_keys))
            if rule is not None and rule.minimum_minutes:
                timed = [(_duration(key), var) for key in keys for var in occupied[key]]
                model.add(
                    cp_model.LinearExpr.weighted_sum([v for _, v in timed], [d for d, _ in timed])
                    >= rule.minimum_minutes * used
                )
            prefix, suffix = [], []
            for key in keys:
                flag = model.new_bool_var("")
                for var in occupied[key]:
                    model.add(flag >= var)
                if prefix:
                    model.add(flag >= prefix[-1])
                prefix.append(flag)
            for key in reversed(keys):
                flag = model.new_bool_var("")
                for var in occupied[key]:
                    model.add(flag >= var)
                if suffix:
                    model.add(flag >= suffix[-1])
                suffix.append(flag)
            suffix.reverse()
            gap_pairs = []
            for index in range(1, len(keys) - 1):
                key = keys[index]
                if key in lunch_keys:
                    continue
                gap = model.new_bool_var("")
                model.add(gap >= prefix[index - 1] + suffix[index + 1] - 1 - sum(occupied[key]))
                gap_pairs.append((gap, _duration(key)))
            if is_teacher:
                cost_terms.extend(
                    (gap, costs["teacher_gaps"] * minutes) for gap, minutes in gap_pairs
                )
            else:
                cost_terms.extend(
                    (gap, costs["class_gaps"] * minutes) for gap, minutes in gap_pairs
                )
                if gap_pairs:
                    model.add(sum(gap for gap, _ in gap_pairs) <= 1)
            if is_teacher:
                single = model.new_bool_var("")
                model.add(single >= 2 * used - sum(day_vars))
                cost_terms.append((single, costs["teacher_single_lessons"] * lesson_minutes))

    stability_units = defaultdict(list)
    for unit_id, weekday, start, end in previous:
        if unit_id in units and (unit_id, (weekday, start, end)) in x:
            stability_units[unit_id].append(x[(unit_id, (weekday, start, end))])
    for kept in stability_units.values():
        moved = model.new_int_var(0, len(kept), "")
        model.add(moved >= len(kept) - sum(kept))
        cost_terms.append((moved, costs["weekly_stability"] * lesson_minutes))

    targets = {}
    for unit_id in units:
        lessons_left = ceil(remaining[unit_id] / lesson_minutes)
        target = min(ceil(lessons_left / weeks_left), lessons_left)
        placed_vars = [x[(unit_id, key)] for key in slots if (unit_id, key) in x]
        model.add(sum(placed_vars) <= target)
        cost_terms.extend((var, -SHORTFALL_WEIGHT) for var in placed_vars)
        targets[unit_id] = target

    model.minimize(
        cp_model.LinearExpr.weighted_sum([var for var, _ in cost_terms], [c for _, c in cost_terms])
    )
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = random_seed
    solver.parameters.max_deterministic_time = ticks
    solver.parameters.max_time_in_seconds = time_limit_seconds
    status = solver.solve(model)
    seconds = clock.perf_counter() - started
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Template(
            placements=frozenset(),
            status=solver.status_name(status),
            variables=len(model.proto.variables),
            shortfall=sum(targets.values()),
            seconds=seconds,
        )
    placements = frozenset(
        (unit_id, key[0], key[1], key[2]) for (unit_id, key), var in x.items() if solver.value(var)
    )
    placed_per_unit = Counter(row[0] for row in placements)
    shortfall = sum(
        max(0, target - placed_per_unit[unit_id]) for unit_id, target in targets.items()
    )
    return Template(
        placements=placements,
        status=solver.status_name(status),
        variables=len(model.proto.variables),
        shortfall=shortfall,
        seconds=seconds,
    )


def _calendar(
    snapshot: PlanningSnapshot, periods: Iterable[Period]
) -> dict[tuple[date, time, time], Period]:
    return {
        (period.school_date, period.start_local, period.end_local): period
        for period in canonical_periods(tuple(periods))
        if period.timezone_name == snapshot.timezone_name
        and snapshot.origin <= period.school_date <= snapshot.preferred_end_date
        and not is_physically_protected(snapshot, period)
    }


def _refusal(
    snapshot: PlanningSnapshot,
    unit: Assignment,
    period: Period | None,
    predecessors: Mapping[int, list[int]],
    remaining: Mapping[int, int],
    last_end: Mapping[int, datetime],
) -> str | None:
    """Why a template lesson cannot land on this real period, or None when it can."""
    if period is None:
        return "no_school_date"
    if any(snapshot.blocked_on(class_id, period.school_date) for class_id in unit.class_ids):
        return "blocked_day"
    for kind, identity in _resources(unit):
        if any(
            row.overlaps(period)
            for row in snapshot.hard_unavailable_on(kind, identity, period.school_date)
        ):
            return "unavailable"
    if not any(room_free(snapshot, room_id, period) for room_id in unit.eligible_room_ids):
        return "no_room"
    for source in predecessors[unit.assignment_id]:
        if source in remaining or last_end.get(source, period.start_utc) > period.start_utc:
            return "not_ready"
    return None


def generate_weekly_template(
    snapshot: PlanningSnapshot,
    periods: Iterable[Period],
    *,
    target_finish: date,
    time_limit_seconds: float = 600.0,
    random_seed: int = 1,
    refresh_weeks: int = REFRESH_WEEKS,
) -> MvpResult:
    """Roll the weekly template out on the calendar until every unit is complete."""
    origin_monday = snapshot.origin - timedelta(days=snapshot.origin.weekday())
    target_week = (target_finish - origin_monday).days // 7
    calendar = _calendar(snapshot, periods)
    calendar_periods = tuple(calendar.values())
    remaining = {
        assignment.assignment_id: residual_minutes(snapshot, assignment.assignment_id)
        for assignment in snapshot.assignments
    }
    remaining = {unit_id: minutes for unit_id, minutes in remaining.items() if minutes > 0}
    predecessors: dict[int, list[int]] = defaultdict(list)
    for source, target in snapshot.precedences:
        predecessors[target].append(source)
    placed: dict[int, list[tuple[Period, int]]] = defaultdict(list)
    last_end: dict[int, datetime] = {}
    skipped: Counter = Counter()
    solves = []
    template: Template | None = None
    solved_units: frozenset[int] = frozenset()
    previous: frozenset[Placement] = frozenset()
    changes = 0
    weeks_with_dates = [(day - origin_monday).days // 7 for day, _start, _end in calendar]
    first_week, last_calendar_week = (
        min(weeks_with_dates, default=0),
        max(weeks_with_dates, default=0),
    )
    solved_week = last_lesson_week = week = first_week
    while remaining and week <= last_calendar_week:
        monday = origin_monday + timedelta(weeks=week)
        ready = frozenset(
            unit_id
            for unit_id in remaining
            if all(source not in remaining for source in predecessors[unit_id])
        )
        if ready and (
            template is None or ready != solved_units or week - solved_week >= refresh_weeks
        ):
            template = build_weekly_template(
                snapshot,
                calendar_periods,
                remaining={unit_id: remaining[unit_id] for unit_id in ready},
                weeks_left=max(1, target_week - week + 1),
                previous=previous,
                ticks=RESOLVE_TICKS if template is not None else FIRST_SOLVE_TICKS,
                time_limit_seconds=time_limit_seconds,
                random_seed=random_seed,
            )
            if template.status not in SOLVED_STATUSES:
                # No pattern inside the budget: keep the last one for the units still ready.
                template = Template(
                    placements=frozenset(row for row in previous if row[0] in ready),
                    status="REUSED_PREVIOUS",
                    variables=template.variables,
                    shortfall=template.shortfall,
                    seconds=template.seconds,
                )
            solves.append(template)
            changes += len(template.placements - previous)
            previous = template.placements
            solved_units, solved_week = ready, week
        if template is not None:
            for unit_id, weekday, start, end in sorted(
                template.placements, key=lambda row: (row[1], row[2], row[0])
            ):
                if unit_id not in remaining:
                    continue
                unit = snapshot.assignment_for(unit_id)
                period = calendar.get((monday + timedelta(days=weekday), start, end))
                reason = _refusal(snapshot, unit, period, predecessors, remaining, last_end)
                if reason is not None:
                    skipped[reason] += 1
                    continue
                credit = min(period.duration_minutes, remaining[unit_id])
                placed[unit_id].append((period, credit))
                remaining[unit_id] -= credit
                last_end[unit_id] = period.end_utc
                last_lesson_week = week
                if remaining[unit_id] == 0:
                    del remaining[unit_id]
        week += 1

    candidate = _materialize(snapshot, placed, remaining)
    stats = {
        "template_solves": len(solves),
        "template_statuses": dict(Counter(t.status for t in solves)),
        "largest_model_variables": max((t.variables for t in solves), default=0),
        "solve_seconds": round(sum(t.seconds for t in solves), 1),
        "shortfall_lessons_in_templates": sum(t.shortfall for t in solves),
        "template_changes": changes,
        "skipped_placements": dict(skipped),
        "target_week": target_week,
        "last_lesson_week": last_lesson_week,
        "extra_weeks_after_target": max(0, last_lesson_week - target_week),
        "units_unfinished": len(remaining),
    }
    return MvpResult(candidate, "COMPLETE" if not remaining else "INCOMPLETE", stats)


def _materialize(
    snapshot: PlanningSnapshot,
    placed: Mapping[int, list[tuple[Period, int]]],
    remaining: Mapping[int, int],
) -> CandidateSchedule:
    """Lessons with identities and module slices, then the production room pass."""
    used_ids: set[int] = set()
    lessons: list[ScheduledLesson] = []
    for unit_id in sorted(placed):
        unit = snapshot.assignment_for(unit_id)
        rows = [
            (allocate_lesson_identity(unit_id, rank, used_ids), period, credit)
            for rank, (period, credit) in enumerate(placed[unit_id], start=1)
        ]
        future = [
            FutureLesson(
                lesson_id,
                period.school_date,
                _minutes(period.start_local),
                period.duration_minutes,
                credit,
            )
            for lesson_id, period, credit in rows
        ]
        slices = project_module_slices(
            unit.modules,
            completed_minutes=snapshot.executed_for(unit_id),
            lessons=future,
            require_complete=unit_id not in remaining,
        )
        for lesson_id, period, credit in rows:
            lessons.append(
                ScheduledLesson(
                    lesson_id,
                    unit_id,
                    period,
                    min(unit.eligible_room_ids),
                    credit,
                    tuple(row for row in slices if row.lesson_id == lesson_id),
                )
            )
    return assign_rooms_by_period(snapshot, CandidateSchedule(tuple(lessons)))
