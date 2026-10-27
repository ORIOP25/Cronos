"""Lab MVP2 of a weekly-template timetable: two CP-SAT stages rolled out on real dates.

Stage A chooses how many lessons each unit gets on each weekday of one week: one small integer
model. Stage B places one weekday's lessons into slots: one independent model per day. A day that
stage B cannot place sends a cut back to stage A: one lesson fewer for the busiest class that day.
A class day holds zero lessons or at least three, except a tail: one or two lessons that finish
the last remaining lessons of their units. A class has at most one internal gap slot per day.

Not wired into production (search, jobs, API). The rollout walks the calendar week by week and
solves each week against the school days that week really has. Rooms and validation reuse the
production passes, so a violation is reported, not hidden.
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
    TeacherPresenceRule,
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
# One lesson short of its weekly target costs more than every preference and gap together, so the
# target is a hard equality whenever the rules allow it. A shortfall is reported, never hidden.
SHORTFALL_WEIGHT = 10**9
SOLVED_STATUSES = ("OPTIMAL", "FEASIBLE")
# Deterministic solver budgets (CP-SAT ticks are not seconds).
COUNT_TICKS = 40
DAY_TICKS = 5
MAX_CUT_ROUNDS = 5
TAIL_LESSONS = 2


@dataclass(frozen=True)
class Template:
    placements: frozenset[Placement]
    status: str
    variables: int
    shortfall: int
    seconds: float
    cut_rounds: int = 0


@dataclass(frozen=True)
class MvpResult:
    candidate: CandidateSchedule | None
    status: str
    stats: dict[str, object]


@dataclass(frozen=True)
class _Week:
    """What both stages read for one solve. Built once per call from the snapshot."""

    slots: tuple[SlotKey, ...]
    blocked: frozenset[tuple[UnavailableResource, int, SlotKey]]
    evitar: Mapping[tuple[UnavailableResource, int, SlotKey], int]
    lunch: Mapping[int, frozenset[SlotKey]]
    lunch_rule_present: bool
    presence: Mapping[int, TeacherPresenceRule]
    dispensed: frozenset[int]
    costs: Mapping[str, int]
    lesson_minutes: int
    units: Mapping[int, Assignment]
    tail: frozenset[int]
    previous: frozenset[Placement]


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


def _costs(snapshot: PlanningSnapshot) -> dict[str, int]:
    """Integer cost per measured minute, priced with the school levels (T13)."""
    weights = snapshot.priority_weights or PriorityWeights(DEFAULT_LEVELS)
    costs = {
        key: PRIORITY_MULTIPLIERS[getattr(weights, key)] * UNIT_COSTS[key]
        for key in (
            "teacher_gaps",
            "teacher_single_lessons",
            "teacher_preferences",
            "class_preferences",
            "weekly_stability",
        )
    }
    # At equal levels one class 1-gap day costs one teacher gap hour (owner, round 2).
    costs["class_gap_day"] = (
        PRIORITY_MULTIPLIERS[weights.class_gaps] * UNIT_COSTS["teacher_gaps"] * 60
    )
    return costs


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


def _minimize(model: cp_model.CpModel, cost_terms, *, ticks: int, seed: int, time_limit: float):
    if cost_terms:
        model.minimize(
            cp_model.LinearExpr.weighted_sum(
                [var for var, _ in cost_terms], [cost for _, cost in cost_terms]
            )
        )
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = seed
    solver.parameters.max_deterministic_time = ticks
    solver.parameters.max_time_in_seconds = time_limit
    status = solver.solve(model)
    return solver, solver.status_name(status), status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def _solve_counts(
    week: _Week,
    targets: Mapping[int, int],
    cuts: Mapping[tuple[int, int], int],
    *,
    seed: int,
    time_limit: float,
) -> tuple[dict[tuple[int, int], int] | None, str, int, int]:
    """Stage A: lessons per (unit, weekday). Returns counts, status, variables and shortfall."""
    days = sorted({key[0] for key in week.slots})
    day_slots = {day: [key for key in week.slots if key[0] == day] for day in days}

    def capacity(kind: UnavailableResource, identity: int, day: int) -> int:
        """Most lessons a resource can hold on a day, leaving a lunch slot free when it must."""
        usable = [key for key in day_slots[day] if (kind, identity, key) not in week.blocked]
        lunch_keys = week.lunch.get(day, frozenset())
        if not week.lunch_rule_present or (kind is TEACHER and identity in week.dispensed):
            return len(usable)
        if not lunch_keys:
            return 0
        plain = sum(1 for key in usable if key not in lunch_keys)
        lunch_free = sum(1 for key in usable if key in lunch_keys)
        return plain + min(lunch_free, len(lunch_keys) - 1)

    model = cp_model.CpModel()
    counts: dict[tuple[int, int], cp_model.IntVar] = {}
    members: dict[tuple[UnavailableResource, int, int], list[tuple[int, cp_model.IntVar]]] = (
        defaultdict(list)
    )
    cost_terms: list[tuple[cp_model.IntVar, int]] = []
    shorts: list[cp_model.IntVar] = []
    for unit_id, target in targets.items():
        unit = week.units[unit_id]
        row = []
        for day in days:
            allowed = sum(
                1
                for key in day_slots[day]
                if not any((kind, identity, key) in week.blocked for kind, identity in _resources(unit))
            )
            if allowed:
                var = model.new_int_var(0, allowed, "")
                counts[(unit_id, day)] = var
                row.append(var)
                for kind, identity in _resources(unit):
                    members[(kind, identity, day)].append((unit_id, var))
        short = model.new_int_var(0, target, "")
        model.add(sum(row) + short == target)
        shorts.append(short)
        cost_terms.append((short, SHORTFALL_WEIGHT))

    for (kind, identity, day), rows in members.items():
        total = sum(var for _unit, var in rows)
        room = capacity(kind, identity, day)
        model.add(total <= room)
        if kind is CLASS:
            # A day holds zero lessons or at least three. Tail units may stand alone on a short day.
            has_regular = model.new_bool_var("")
            for unit_id, var in rows:
                if unit_id not in week.tail:
                    model.add(var <= room * has_regular)
            model.add(3 * has_regular <= total)
            model.add(total <= TAIL_LESSONS + room * has_regular)
            if (identity, day) in cuts:
                model.add(total <= cuts[(identity, day)])
        else:
            single = model.new_bool_var("")
            model.add(total >= single)
            model.add(total <= 1 + room * (1 - single))
            cost_terms.append((single, week.costs["teacher_single_lessons"] * week.lesson_minutes))
            rule = week.presence.get(identity)
            if rule is not None and rule.minimum_minutes:
                used = model.new_bool_var("")
                model.add(total <= room * used)
                model.add(total >= ceil(rule.minimum_minutes / week.lesson_minutes) * used)

    for room_set in {week.units[unit_id].eligible_room_ids for unit_id in targets}:
        for day in days:
            fitting = [
                var
                for (unit_id, unit_day), var in counts.items()
                if unit_day == day and week.units[unit_id].eligible_room_ids <= room_set
            ]
            if fitting:
                model.add(sum(fitting) <= len(room_set) * len(day_slots[day]))

    previous_counts = Counter((unit_id, day) for unit_id, day, _start, _end in week.previous)
    for (unit_id, day), var in counts.items():
        moved = model.new_int_var(0, len(week.slots), "")
        model.add(moved >= var - previous_counts[(unit_id, day)])
        model.add(moved >= previous_counts[(unit_id, day)] - var)
        cost_terms.append((moved, week.costs["weekly_stability"] * week.lesson_minutes))

    solver, status, solved = _minimize(
        model, cost_terms, ticks=COUNT_TICKS, seed=seed, time_limit=time_limit
    )
    variables = len(model.proto.variables)
    if not solved:
        return None, status, variables, sum(targets.values())
    values = {key: solver.value(var) for key, var in counts.items() if solver.value(var)}
    shortfall = sum(solver.value(short) for short in shorts)
    return values, status, variables, shortfall


def _gap_pairs(
    model: cp_model.CpModel,
    occupied: Mapping[SlotKey, list[cp_model.IntVar]],
    keys: list[SlotKey],
    skip: frozenset[SlotKey],
) -> list[tuple[cp_model.IntVar, int]]:
    """Empty grid slots between a resource's first and last lesson, as (flag, minutes) pairs."""
    prefix: list[cp_model.IntVar] = []
    suffix: list[cp_model.IntVar] = []
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
    pairs = []
    for index in range(1, len(keys) - 1):
        key = keys[index]
        if key in skip:
            continue
        gap = model.new_bool_var("")
        model.add(gap >= prefix[index - 1] + suffix[index + 1] - 1 - sum(occupied[key]))
        pairs.append((gap, _duration(key)))
    return pairs


def _solve_day(
    week: _Week,
    weekday: int,
    counts: Mapping[int, int],
    *,
    seed: int,
    time_limit: float,
) -> tuple[list[Placement] | None, str, int]:
    """Stage B: place one weekday's lessons into slots. Returns rows, status and variables."""
    keys = [key for key in week.slots if key[0] == weekday]
    model = cp_model.CpModel()
    x: dict[tuple[int, SlotKey], cp_model.IntVar] = {}
    on: dict[tuple[UnavailableResource, int, SlotKey], list[cp_model.IntVar]] = defaultdict(list)
    cost_terms: list[tuple[cp_model.IntVar, int]] = []
    resources: Counter = Counter()
    previous_slots: dict[int, list[tuple[time, time]]] = defaultdict(list)
    for unit_id, weekday_placed, start, end in week.previous:
        if weekday_placed == weekday:
            previous_slots[unit_id].append((start, end))

    for unit_id, count in counts.items():
        unit = week.units[unit_id]
        for resource in _resources(unit):
            resources[resource] += count
        row = []
        for key in keys:
            if any((kind, identity, key) in week.blocked for kind, identity in _resources(unit)):
                continue
            var = model.new_bool_var("")
            x[(unit_id, key)] = var
            model.add_hint(var, (unit_id, weekday, key[1], key[2]) in week.previous)
            row.append(var)
            for kind, identity in _resources(unit):
                on[(kind, identity, key)].append(var)
            evitar = sum(
                week.evitar.get((kind, identity, key), 0) for kind, identity in _resources(unit)
            )
            if evitar:
                cost_terms.append((var, evitar))
        model.add(sum(row) == count)
        kept = [x[(unit_id, (weekday, start, end))] for start, end in previous_slots[unit_id]
                if (unit_id, (weekday, start, end)) in x]
        if kept:
            moved = model.new_int_var(0, len(kept), "")
            model.add(moved >= len(kept) - sum(kept))
            cost_terms.append((moved, week.costs["weekly_stability"] * week.lesson_minutes))

    for members in on.values():
        if len(members) > 1:
            model.add(sum(members) <= 1)
    for room_set in {week.units[unit_id].eligible_room_ids for unit_id in counts}:
        for key in keys:
            fitting = [
                x[(unit_id, key)]
                for unit_id in counts
                if (unit_id, key) in x and week.units[unit_id].eligible_room_ids <= room_set
            ]
            if len(fitting) > len(room_set):
                model.add(sum(fitting) <= len(room_set))

    for kind, identity in sorted(resources, key=lambda row: (row[0].value, row[1])):
        is_teacher = kind is TEACHER
        lunch_required = not (is_teacher and identity in week.dispensed)
        lunch_keys = week.lunch.get(weekday, frozenset()) if lunch_required else frozenset()
        occupied = {key: on.get((kind, identity, key), []) for key in keys}
        if lunch_required and week.lunch_rule_present:
            if not lunch_keys:
                return None, "NO_LUNCH_SLOT", len(model.proto.variables)
            model.add(sum(var for key in lunch_keys for var in occupied[key]) <= len(lunch_keys) - 1)
        pairs = _gap_pairs(model, occupied, keys, lunch_keys)
        timed = [(_duration(key), var) for key in keys for var in occupied[key]]
        if is_teacher:
            cost_terms.extend((gap, week.costs["teacher_gaps"] * minutes) for gap, minutes in pairs)
            rule = week.presence.get(identity)
            if rule is not None and rule.minimum_minutes:
                model.add(
                    cp_model.LinearExpr.weighted_sum([v for _, v in timed], [d for d, _ in timed])
                    >= rule.minimum_minutes
                )
                if pairs:
                    model.add(
                        cp_model.LinearExpr.weighted_sum(
                            [gap for gap, _ in pairs], [minutes for _, minutes in pairs]
                        )
                        <= rule.max_gap_minutes
                    )
        else:
            cost_terms.extend((gap, week.costs["class_gap_day"]) for gap, _ in pairs)
            model.add(sum(gap for gap, _ in pairs) <= 1)

    solver, status, solved = _minimize(
        model, cost_terms, ticks=DAY_TICKS, seed=seed, time_limit=time_limit
    )
    variables = len(model.proto.variables)
    if not solved:
        return None, status, variables
    rows = [
        (unit_id, weekday, key[1], key[2])
        for (unit_id, key), var in x.items()
        if solver.value(var)
    ]
    return rows, status, variables


def _busiest_class_cut(week: _Week, counts: Mapping[int, int], weekday: int) -> tuple[int, int, int]:
    """(class, weekday, cap): one lesson fewer than the busiest class of the day."""
    totals: Counter = Counter()
    for unit_id, count in counts.items():
        for class_id in week.units[unit_id].class_ids:
            totals[class_id] += count
    class_id = max(totals, key=lambda identity: (totals[identity], -identity))
    return class_id, weekday, totals[class_id] - 1


def build_weekly_template(
    snapshot: PlanningSnapshot,
    periods: Iterable[Period],
    *,
    remaining: Mapping[int, int],
    weeks_left: int,
    previous: frozenset[Placement] = frozenset(),
    available: frozenset[SlotKey] | None = None,
    time_limit_seconds: float = 600.0,
    random_seed: int = 1,
) -> Template:
    """Solve one weekly pattern for the given units (remaining minutes per unit).

    ``available`` limits the slots a week really has (None means every grid slot).
    """
    started = clock.perf_counter()
    grid = sorted({(row.day_of_week, row.start_local, row.end_local) for row in snapshot.grid_slots})
    slots = tuple(key for key in grid if available is None or key in available)
    occurrences = Counter(_slot_of(period) for period in periods)
    lesson_minutes = typical_lesson_minutes(snapshot.grid_slots)
    costs = _costs(snapshot)
    targets, tail = _targets(remaining, lesson_minutes, weeks_left)
    week = _Week(
        slots=slots,
        blocked=_blocked_resources(snapshot, grid, occurrences),
        evitar=_evitar_costs(snapshot, grid, occurrences, costs),
        lunch=_lunch_slots(snapshot, list(slots)),
        lunch_rule_present=snapshot.lunch_rule is not None,
        presence={rule.teacher_id: rule for rule in snapshot.teacher_presence},
        dispensed=snapshot.lunch_dispensed_teacher_ids,
        costs=costs,
        lesson_minutes=lesson_minutes,
        units={unit_id: snapshot.assignment_for(unit_id) for unit_id in remaining},
        tail=tail,
        previous=previous,
    )

    cuts: dict[tuple[int, int], int] = {}
    day_cache: dict[tuple[int, tuple[tuple[int, int], ...]], tuple] = {}
    variables = 0
    statuses: list[str] = []
    for cut_round in range(MAX_CUT_ROUNDS + 1):
        counts, count_status, count_variables, shortfall = _solve_counts(
            week, targets, cuts, seed=random_seed, time_limit=time_limit_seconds
        )
        variables = max(variables, count_variables)
        if counts is None:
            return Template(
                frozenset(), count_status, variables, sum(targets.values()),
                clock.perf_counter() - started, cut_round,
            )
        placements: set[Placement] = set()
        failed: list[int] = []
        for weekday in sorted({day for _unit, day in counts}):
            day_counts = {unit_id: count for (unit_id, day), count in counts.items() if day == weekday}
            key = (weekday, tuple(sorted(day_counts.items())))
            if key not in day_cache:
                day_cache[key] = _solve_day(
                    week, weekday, day_counts, seed=random_seed, time_limit=time_limit_seconds
                )
            rows, day_status, day_variables = day_cache[key]
            variables = max(variables, day_variables)
            statuses.append(day_status)
            if rows is None:
                failed.append(weekday)
                cut = _busiest_class_cut(week, day_counts, weekday)
                cuts[cut[0], cut[1]] = min(cuts.get((cut[0], cut[1]), cut[2]), cut[2])
            else:
                placements.update(rows)
        statuses.append(count_status)
        if not failed:
            status = "OPTIMAL" if all(s == "OPTIMAL" for s in statuses) else "FEASIBLE"
            return Template(
                frozenset(placements), status, variables, shortfall,
                clock.perf_counter() - started, cut_round,
            )
    return Template(
        frozenset(), "INFEASIBLE_DAY", variables, sum(targets.values()),
        clock.perf_counter() - started, MAX_CUT_ROUNDS,
    )


def _targets(
    remaining: Mapping[int, int], lesson_minutes: int, weeks_left: int
) -> tuple[dict[int, int], frozenset[int]]:
    """Weekly lesson target per unit, and the tail units that finish their last lessons now."""
    targets: dict[int, int] = {}
    tail: set[int] = set()
    for unit_id, minutes in remaining.items():
        lessons_left = ceil(minutes / lesson_minutes)
        if lessons_left <= TAIL_LESSONS:
            tail.add(unit_id)
            targets[unit_id] = lessons_left
        else:
            targets[unit_id] = ceil(lessons_left / weeks_left)
    return targets, frozenset(tail)


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
    """Roll the weekly template out on the calendar until every unit is complete.

    A week is solved against the slots its calendar really has, so a holiday week moves its
    lessons onto the school days. A week without any school day gets no placements.
    """
    origin_monday = snapshot.origin - timedelta(days=snapshot.origin.weekday())
    target_week = (target_finish - origin_monday).days // 7
    calendar = _calendar(snapshot, periods)
    calendar_periods = tuple(calendar.values())
    open_slots: dict[int, set[SlotKey]] = defaultdict(set)
    for school_date, start, end in calendar:
        open_slots[(school_date - origin_monday).days // 7].add((school_date.weekday(), start, end))
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
    solved_available: frozenset[SlotKey] = frozenset()
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
        available = frozenset(open_slots.get(week, ()))
        ready = frozenset(
            unit_id
            for unit_id in remaining
            if all(source not in remaining for source in predecessors[unit_id])
        )
        if ready and available and (
            template is None
            or ready != solved_units
            or available != solved_available
            or week - solved_week >= refresh_weeks
        ):
            template = build_weekly_template(
                snapshot,
                calendar_periods,
                remaining={unit_id: remaining[unit_id] for unit_id in ready},
                weeks_left=max(1, target_week - week + 1),
                previous=previous,
                available=available,
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
                    cut_rounds=template.cut_rounds,
                )
            solves.append(template)
            changes += len(template.placements - previous)
            previous = template.placements
            solved_units, solved_week, solved_available = ready, week, available
        if template is not None and available:
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
        "cut_rounds": sum(t.cut_rounds for t in solves),
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
