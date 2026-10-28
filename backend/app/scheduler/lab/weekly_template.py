"""Lab MVP3 of a weekly-template timetable: two stages rolled out on real dates.

Stage A chooses how many lessons each unit gets on each weekday of one week. A greedy plan packs
the lessons and repairs the class and teacher rules; a CP-SAT count model then improves it from
that plan as a hint, within a tick budget, and falls back to the plan if it finds nothing.
Stage B places one weekday's lessons into slots: one independent model per day. A lesson that the
day cannot place is shortfall, so every weekday has an answer and the rollout carries the shortfall
into the next weeks' targets.
A class day holds zero lessons or at least three, except a tail: one or two lessons that finish
the last remaining lessons of their units. A class has at most one internal gap slot per day.

Not wired into production (search, jobs, API). The rollout walks the calendar week by week and
solves each week against the school days that week really has. Rooms and validation reuse the
production passes, so a violation is reported, not hidden.
"""

from __future__ import annotations

import multiprocessing
import os
import time as clock
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from functools import cache
from math import ceil

from ortools.sat.python import cp_model

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    LunchRule,
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
from app.scheduler.domain.teacher_presence import (
    _lunch_choices_from_intervals,
    longest_presence_minutes,
    presence_minutes_fit,
)
from app.scheduler.infrastructure.placement_model import _module_completed
from app.scheduler.infrastructure.recovery_construction import construct_recovery
from app.scheduler.infrastructure.room_assignment import assign_rooms_by_period

SlotKey = tuple[int, time, time]  # (weekday, start_local, end_local) of a grid slot
Placement = tuple[int, int, time, time]  # (assignment_id, weekday, start_local, end_local)
TEACHER = UnavailableResource.TEACHER
CLASS = UnavailableResource.CLASS
# A lesson that a stage cannot place costs more than every preference and gap together, so the rules
# and the weekly targets win over preferences. The shortfall is reported, never hidden.
SHORTFALL_WEIGHT = 10**9
# Deterministic solver budgets (CP-SAT ticks are not seconds).
COUNT_TICKS = 2
FIX_TICKS = 60
DAY_TICKS = 24
# Core-based search proves the optimum of both stages in a few ticks, where the default search does
# not. One worker, so the result is deterministic.
CORE_SEARCH: dict[str, object] = {"optimize_with_core": True, "linearization_level": 0}
TAIL_LESSONS = 2
# A class day holds zero lessons or at least this many, unless it is a tail day.
MIN_DAY_LESSONS = 3
# Times the class-gap day cost above one teacher gap hour (round 4 priced them equal).
CLASS_GAP_WEIGHT = 20
# The rollout paces units to finish this many weeks before the target week.
TARGET_LEAD_WEEKS = 1
# The rollout re-solves the template at least this often, so units that fell behind get more lessons.
REFRESH_WEEKS = 4


@dataclass(frozen=True)
class Template:
    placements: frozenset[Placement]
    variables: int
    shortfall: int
    seconds: float
    count_seconds: float = 0.0
    day_seconds: float = 0.0


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
    lunch_rule: LunchRule | None
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
            "update_stability",
        )
    }
    # At equal levels one class 1-gap day costs one teacher gap hour (owner, round 2); the lab
    # prices it CLASS_GAP_WEIGHT times that so classes compact before teachers.
    costs["class_gap_day"] = (
        PRIORITY_MULTIPLIERS[weights.class_gaps]
        * UNIT_COSTS["teacher_gaps"]
        * 60
        * CLASS_GAP_WEIGHT
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


def _hint_all(model: cp_model.CpModel, values) -> None:
    """Replace the hints with a complete assignment: one value per variable, in index order."""
    model.clear_hints()
    for index, value in enumerate(values):
        model.add_hint(model.get_int_var_from_proto_index(index), value)


def _complete_hint(model: cp_model.CpModel) -> None:
    """Hint every variable with the value of a solve that fixes the partial hint.

    The partial hint (the counts) fixes in a fraction of a second; the complete values start the
    real search from a feasible plan instead of spending its ticks finding one.
    """
    fixer = cp_model.CpSolver()
    fixer.parameters.num_workers = 1
    fixer.parameters.fix_variables_to_their_hinted_value = True
    fixer.parameters.max_deterministic_time = FIX_TICKS
    if fixer.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        _hint_all(model, fixer.response_proto.solution)


def _minimize(
    model: cp_model.CpModel,
    cost_terms,
    *,
    ticks: int,
    seed: int,
    time_limit: float,
    complete_hint: bool = False,
    search: Mapping[str, object] | None = None,
):
    if cost_terms:
        model.minimize(
            cp_model.LinearExpr.weighted_sum(
                [var for var, _ in cost_terms], [cost for _, cost in cost_terms]
            )
        )
    if complete_hint:
        _complete_hint(model)
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = seed
    solver.parameters.max_deterministic_time = ticks
    solver.parameters.max_time_in_seconds = time_limit
    for name, value in (search or {}).items():
        setattr(solver.parameters, name, value)
    status = solver.solve(model)
    return solver, solver.status_name(status), status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def _presence_totals(
    week: _Week, day_keys: list[SlotKey], rule: TeacherPresenceRule, room: int
) -> list[int]:
    """Lesson totals (0 to room) that one teacher day can hold under the presence rule."""
    slots = [(_minutes(key[1]), _minutes(key[2])) for key in day_keys]
    longest = longest_presence_minutes(rule, slots, lunch_rule=week.lunch_rule)
    return [
        value
        for value in range(room + 1)
        if value == 0
        or presence_minutes_fit(
            value * week.lesson_minutes, minimum=rule.minimum_minutes, longest=longest
        )
    ]


def _capacity(week: _Week, kind: UnavailableResource, identity: int, day: int) -> int:
    """Most lessons a resource can hold on a day, leaving a lunch slot free when it must."""
    usable = [
        key for key in week.slots if key[0] == day and (kind, identity, key) not in week.blocked
    ]
    lunch_keys = week.lunch.get(day, frozenset())
    if week.lunch_rule is None or (kind is TEACHER and identity in week.dispensed):
        return len(usable)
    if not lunch_keys:
        return 0
    plain = sum(1 for key in usable if key not in lunch_keys)
    lunch_free = sum(1 for key in usable if key in lunch_keys)
    return plain + min(lunch_free, len(lunch_keys) - 1)


def _open_slots(week: _Week, unit: Assignment, day: int) -> int:
    """Grid slots of one weekday that none of the unit's resources blocks."""
    resources = _resources(unit)
    return sum(
        1
        for key in week.slots
        if key[0] == day
        and not any((kind, identity, key) in week.blocked for kind, identity in resources)
    )


def _total(members) -> int:
    return sum(count for _unit, count in members)


def _remove(members, amount: int, eligible) -> int:
    """Take ``amount`` lessons from the eligible rows, busiest unit first, lowest id on ties."""
    taken = 0
    ordered = sorted(
        (row for row in members if row[1] and eligible(row[0])),
        key=lambda row: (-row[1], row[0]),
    )
    for row in ordered:
        if taken == amount:
            break
        step = min(row[1], amount - taken)
        row[1] -= step
        taken += step
    return taken


def _settle_class(week: _Week, members) -> bool:
    """Class day: regular lessons need three or more, tail lessons at most two."""
    removed = 0
    regular = sum(count for unit_id, count in members if unit_id not in week.tail and count)
    if regular and _total(members) < MIN_DAY_LESSONS:
        removed += _remove(members, regular, lambda unit_id: unit_id not in week.tail)
    elif not regular and _total(members) > TAIL_LESSONS:
        removed += _remove(members, _total(members) - TAIL_LESSONS, lambda unit_id: True)
    return removed > 0


def _usable_keys(week: _Week, kind: UnavailableResource, identity: int, day: int) -> list[SlotKey]:
    """Grid slots of one weekday that the resource can use (not blocked for it)."""
    return [
        key for key in week.slots if key[0] == day and (kind, identity, key) not in week.blocked
    ]


def _settle_teacher(week: _Week, members, teacher_id: int, day: int) -> bool:
    """Teacher day: the total must be one that the presence rule can hold (zero always can)."""
    rule = week.presence.get(teacher_id)
    if rule is None or not rule.minimum_minutes:
        return False
    total = _total(members)
    allowed = _presence_totals(
        week,
        _usable_keys(week, TEACHER, teacher_id, day),
        rule,
        _capacity(week, TEACHER, teacher_id, day),
    )
    if total in allowed:
        return False
    keep = max(value for value in allowed if value < total)
    return _remove(members, total - keep, lambda unit_id: True) > 0


def _settle_day(week: _Week, rows, day: int) -> bool:
    """One sweep over the class and teacher groups of one weekday. True when it removed a lesson."""
    removed = False
    class_ids = {
        class_id for unit_id, count in rows if count for class_id in week.units[unit_id].class_ids
    }
    for class_id in sorted(class_ids):
        members = [row for row in rows if row[1] and class_id in week.units[row[0]].class_ids]
        removed |= _settle_class(week, members)
    teacher_ids = {week.units[unit_id].teacher_id for unit_id, count in rows if count}
    for teacher_id in sorted(teacher_ids):
        members = [row for row in rows if row[1] and week.units[row[0]].teacher_id == teacher_id]
        removed |= _settle_teacher(week, members, teacher_id, day)
    return removed


def _settle(week: _Week, counts: Mapping[tuple[int, int], int], days) -> dict[tuple[int, int], int]:
    """Remove lessons, never add, until every weekday obeys the class and teacher rules."""
    settled: dict[tuple[int, int], int] = {}
    for day in days:
        rows = [
            [unit_id, count]
            for (unit_id, weekday), count in counts.items()
            if weekday == day and count
        ]
        while _settle_day(week, rows, day):
            pass
        settled.update({(unit_id, day): count for unit_id, count in rows if count})
    return settled


def _spread_counts(week: _Week, targets: Mapping[int, int]) -> dict[tuple[int, int], int]:
    """Stage A plan without a solver: lessons per (unit, weekday).

    Each lesson goes to the weekday where its teacher and classes first reach the minimum day
    size, then to the least loaded one, so every day fills to three before any day grows. The
    class and teacher rules are then repaired by removing lessons only. The plan is the hint for
    the count model.
    """
    days = sorted({key[0] for key in week.slots})
    room_sets = {week.units[unit_id].eligible_room_ids for unit_id in targets}
    room_slots = {day: sum(1 for key in week.slots if key[0] == day) for day in days}
    previous = Counter((unit_id, day) for unit_id, day, _start, _end in week.previous)
    counts: Counter = Counter()
    load: Counter = Counter()
    room_load: Counter = Counter()

    @cache
    def capacity(kind: UnavailableResource, identity: int, day: int) -> int:
        return _capacity(week, kind, identity, day)

    def pressure(unit: Assignment, day: int) -> int:
        return sum(load[(kind, identity, day)] for kind, identity in _resources(unit))

    def filled(unit: Assignment, day: int) -> int:
        return sum(
            min(load[(kind, identity, day)], MIN_DAY_LESSONS) for kind, identity in _resources(unit)
        )

    def fits(unit: Assignment, day: int, open_count: int) -> bool:
        if counts[(unit.assignment_id, day)] >= open_count:
            return False
        for kind, identity in _resources(unit):
            if load[(kind, identity, day)] >= capacity(kind, identity, day):
                return False
        return all(
            room_load[(room_set, day)] < len(room_set) * room_slots[day]
            for room_set in room_sets
            if unit.eligible_room_ids <= room_set
        )

    def place(unit: Assignment, day: int) -> None:
        counts[(unit.assignment_id, day)] += 1
        for kind, identity in _resources(unit):
            load[(kind, identity, day)] += 1
        for room_set in room_sets:
            if unit.eligible_room_ids <= room_set:
                room_load[(room_set, day)] += 1

    for unit_id in sorted(targets, key=lambda unit_id: (-targets[unit_id], unit_id)):
        unit = week.units[unit_id]
        open_count = {day: _open_slots(week, unit, day) for day in days}
        for _ in range(targets[unit_id]):
            options = [day for day in days if fits(unit, day, open_count[day])]
            if not options:
                break
            place(
                unit,
                min(
                    options,
                    key=lambda day: (
                        -filled(unit, day),
                        pressure(unit, day),
                        -previous[(unit_id, day)],
                        day,
                    ),
                ),
            )
    return _settle(week, counts, days)


def _solve_counts(
    week: _Week,
    targets: Mapping[int, int],
    hint: Mapping[tuple[int, int], int],
    *,
    seed: int,
    time_limit: float,
) -> tuple[dict[tuple[int, int], int] | None, int]:
    """Stage A: lessons per (unit, weekday). Returns counts (None when no solution) and variables."""
    days = sorted({key[0] for key in week.slots})
    day_slots = {day: [key for key in week.slots if key[0] == day] for day in days}

    model = cp_model.CpModel()
    counts: dict[tuple[int, int], cp_model.IntVar] = {}
    members: dict[tuple[UnavailableResource, int, int], list[tuple[int, cp_model.IntVar]]] = (
        defaultdict(list)
    )
    cost_terms: list[tuple[cp_model.IntVar, int]] = []
    anywhere: dict[int, cp_model.IntVar] = {}
    teacher_units: dict[int, list[int]] = defaultdict(list)
    for unit_id, target in targets.items():
        unit = week.units[unit_id]
        row = []
        for day in days:
            allowed = sum(
                1
                for key in day_slots[day]
                if not any(
                    (kind, identity, key) in week.blocked for kind, identity in _resources(unit)
                )
            )
            if allowed:
                var = model.new_int_var(0, allowed, "")
                counts[(unit_id, day)] = var
                model.add_hint(var, hint.get((unit_id, day), 0))
                row.append(var)
                for kind, identity in _resources(unit):
                    members[(kind, identity, day)].append((unit_id, var))
        short = model.new_int_var(0, target, "")
        model.add(sum(row) + short == target)
        cost_terms.append((short, SHORTFALL_WEIGHT))
        anywhere[unit_id] = model.new_bool_var("")
        model.add(sum(row) <= target * anywhere[unit_id])
        for kind, identity in _resources(unit):
            if kind is TEACHER:
                teacher_units[identity].append(unit_id)

    teacher_days: list[tuple[int, int, cp_model.IntVar, frozenset[int]]] = []
    for (kind, identity, day), rows in members.items():
        total = sum(var for _unit, var in rows)
        room = _capacity(week, kind, identity, day)
        model.add(total <= room)
        if kind is CLASS:
            # A day holds zero lessons or at least three. Tail units may stand alone on a short day.
            has_regular = model.new_bool_var("")
            for unit_id, var in rows:
                if unit_id not in week.tail:
                    model.add(var <= room * has_regular)
            model.add(3 * has_regular <= total)
            model.add(total <= TAIL_LESSONS + room * has_regular)
        else:
            # single = 1 exactly when the teacher has one lesson on this day (multi: two or more).
            on = model.new_bool_var("")
            multi = model.new_bool_var("")
            single = model.new_bool_var("")
            model.add(total <= room * on)
            model.add(total >= on)
            model.add(total <= 1 + room * multi)
            model.add(total >= 2 * multi)
            model.add(single >= on - multi)
            cost_terms.append((single, week.costs["teacher_single_lessons"] * week.lesson_minutes))
            teacher_days.append((identity, day, single, frozenset(unit for unit, _ in rows)))
            rule = week.presence.get(identity)
            if rule is not None and rule.minimum_minutes:
                model.add(total >= ceil(rule.minimum_minutes / week.lesson_minutes) * on)
                # A day total must be one that the presence rule can hold (domain fit check).
                allowed = _presence_totals(
                    week, _usable_keys(week, TEACHER, identity, day), rule, room
                )
                capped = model.new_int_var(0, room, "")
                model.add(capped == total)
                model.add_allowed_assignments([capped], [(value,) for value in allowed])

    # A teacher's single-lesson day is forbidden while another of the teacher's units has lessons
    # elsewhere that week and could join that day.
    has_lesson: dict[tuple[int, int], cp_model.IntVar] = {}
    for (unit_id, day), var in counts.items():
        flag = model.new_bool_var("")
        model.add(var <= len(day_slots[day]) * flag)
        model.add(flag <= var)
        has_lesson[(unit_id, day)] = flag
    for teacher_id, day, single, present in teacher_days:
        for unit_id in teacher_units[teacher_id]:
            if unit_id in present or (unit_id, day) not in has_lesson:
                continue
            model.add(single + anywhere[unit_id] - has_lesson[(unit_id, day)] <= 1)

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
        cost_terms.append((moved, week.costs["moved_lesson"]))

    solver, _status, solved = _minimize(
        model,
        cost_terms,
        ticks=COUNT_TICKS,
        seed=seed,
        time_limit=time_limit,
        complete_hint=True,
        search=CORE_SEARCH,
    )
    variables = len(model.proto.variables)
    if not solved:
        return None, variables
    return {key: solver.value(var) for key, var in counts.items() if solver.value(var)}, variables


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


def _presence_part(
    model: cp_model.CpModel,
    occupied: Mapping[SlotKey, list[cp_model.IntVar]],
    keys: list[SlotKey],
    rule: TeacherPresenceRule,
    pick: cp_model.IntVar,
) -> None:
    """One presence of a teacher day: empty, or at least the minimum, with a gap within the maximum."""
    terms = [(var, _duration(key)) for key in keys for var in occupied[key]]
    if not terms:
        return
    nonempty = model.new_bool_var("")
    model.add(sum(var for var, _ in terms) >= nonempty)
    model.add(sum(var for var, _ in terms) <= len(terms) * nonempty)
    minutes = cp_model.LinearExpr.weighted_sum([var for var, _ in terms], [m for _, m in terms])
    model.add(minutes >= rule.minimum_minutes * nonempty).only_enforce_if(pick)
    pairs = _gap_pairs(model, occupied, keys, frozenset())
    if pairs:
        model.add(
            cp_model.LinearExpr.weighted_sum([gap for gap, _ in pairs], [m for _, m in pairs])
            <= rule.max_gap_minutes
        ).only_enforce_if(pick)


def _presence_split(
    model: cp_model.CpModel,
    occupied: Mapping[SlotKey, list[cp_model.IntVar]],
    keys: list[SlotKey],
    rule: TeacherPresenceRule,
    lunch_rule: LunchRule,
) -> bool:
    """Teacher day with a required lunch: some free lunch choice splits it into compliant presences.

    Mirrors ``teacher_day_complies``: the choice keeps the lunch window empty, and the morning
    and the afternoon presence each pass ``_presence_part``. False when no lunch choice exists.
    """
    choices = _lunch_choices_from_intervals(
        [(_minutes(key[1]), _minutes(key[2])) for key in keys], lunch_rule
    )
    if not choices:
        return False
    picks = []
    for start, end in choices:
        pick = model.new_bool_var("")
        picks.append(pick)
        in_window = [
            var
            for key in keys
            if _minutes(key[1]) < end and start < _minutes(key[2])
            for var in occupied[key]
        ]
        if in_window:
            model.add(sum(in_window) == 0).only_enforce_if(pick)
        morning = [key for key in keys if _minutes(key[2]) <= start]
        afternoon = [key for key in keys if _minutes(key[1]) >= end]
        _presence_part(model, occupied, morning, rule, pick)
        _presence_part(model, occupied, afternoon, rule, pick)
    model.add(sum(picks) >= 1)
    return True


def _solve_day(
    week: _Week,
    weekday: int,
    counts: Mapping[int, int],
    *,
    seed: int,
    time_limit: float,
) -> tuple[list[Placement], str, int]:
    """Stage B: place as many of one weekday's lessons as the rules allow. Returns rows, status, variables.

    A lesson that does not fit is shortfall at SHORTFALL_WEIGHT, so every weekday has an answer. The
    class-day rule holds for the lessons placed: zero, or three or more unless they are tail lessons.
    """
    keys = [key for key in week.slots if key[0] == weekday]
    model = cp_model.CpModel()
    x: dict[tuple[int, SlotKey], cp_model.IntVar] = {}
    on: dict[tuple[UnavailableResource, int, SlotKey], list[cp_model.IntVar]] = defaultdict(list)
    regular: dict[tuple[int, SlotKey], list[cp_model.IntVar]] = defaultdict(list)
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
            if unit_id not in week.tail:
                for class_id in unit.class_ids:
                    regular[(class_id, key)].append(var)
            evitar = sum(
                week.evitar.get((kind, identity, key), 0) for kind, identity in _resources(unit)
            )
            if evitar:
                cost_terms.append((var, evitar))
        short = model.new_int_var(0, count, "")
        model.add(sum(row) + short == count)
        cost_terms.append((short, SHORTFALL_WEIGHT))
        kept = [
            x[(unit_id, (weekday, start, end))]
            for start, end in previous_slots[unit_id]
            if (unit_id, (weekday, start, end)) in x
        ]
        if kept:
            moved = model.new_int_var(0, len(kept), "")
            model.add(moved >= len(kept) - sum(kept))
            cost_terms.append((moved, week.costs["moved_lesson"]))

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
        timed = [(_duration(key), var) for key in keys for var in occupied[key]]
        placed = [var for _, var in timed]
        if lunch_required and week.lunch_rule is not None:
            if not lunch_keys:
                # No lunch slot on this weekday: the resource takes no lesson at all.
                model.add(sum(placed) == 0)
            else:
                model.add(
                    sum(var for key in lunch_keys for var in occupied[key]) <= len(lunch_keys) - 1
                )
        pairs = _gap_pairs(model, occupied, keys, lunch_keys)
        if is_teacher:
            cost_terms.extend((gap, week.costs["teacher_gaps"] * minutes) for gap, minutes in pairs)
            rule = week.presence.get(identity)
            has_presence = rule is not None and rule.minimum_minutes is not None
            if has_presence and rule.lunch_required and week.lunch_rule is not None:
                if not _presence_split(model, occupied, keys, rule, week.lunch_rule):
                    model.add(sum(placed) == 0)
            elif has_presence:
                # Without a lunch split the whole day is one presence.
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
            # Class day: zero lessons, or three or more regular lessons (tail lessons may stand alone).
            has_regular = model.new_bool_var("")
            regular_vars = [var for key in keys for var in regular[(identity, key)]]
            model.add(sum(regular_vars) <= len(keys) * has_regular)
            model.add(MIN_DAY_LESSONS * has_regular <= sum(placed))
            model.add(sum(placed) <= TAIL_LESSONS + len(keys) * has_regular)

    solver, status, solved = _minimize(
        model, cost_terms, ticks=DAY_TICKS, seed=seed, time_limit=time_limit, search=CORE_SEARCH
    )
    if not solved:
        # Core search may not find a first plan; the default search does, and the day is never empty.
        solver, status, solved = _minimize(
            model, cost_terms, ticks=DAY_TICKS, seed=seed, time_limit=time_limit
        )
    variables = len(model.proto.variables)
    if not solved:
        return [], status, variables
    rows = [
        (unit_id, weekday, key[1], key[2]) for (unit_id, key), var in x.items() if solver.value(var)
    ]
    return rows, status, variables


def _week_inputs(
    snapshot: PlanningSnapshot,
    periods: Iterable[Period],
    *,
    remaining: Mapping[int, int],
    weeks_left: int,
    previous: frozenset[Placement],
    available: frozenset[SlotKey] | None,
    update: bool = False,
) -> tuple[_Week, dict[int, int]]:
    """What the stages read for one week, and the weekly lesson target of each unit."""
    grid = sorted(
        {(row.day_of_week, row.start_local, row.end_local) for row in snapshot.grid_slots}
    )
    slots = tuple(key for key in grid if available is None or key in available)
    occurrences = Counter(_slot_of(period) for period in periods)
    lesson_minutes = typical_lesson_minutes(snapshot.grid_slots)
    costs = _costs(snapshot)
    # Moving a lesson of a published schedule costs the owner's update stability; a rollout's own
    # moves between weeks cost the weekly stability.
    costs["moved_lesson"] = (
        costs["update_stability"] if update else costs["weekly_stability"] * lesson_minutes
    )
    targets, tail = _targets(remaining, lesson_minutes, weeks_left)
    week = _Week(
        slots=slots,
        blocked=_blocked_resources(snapshot, grid, occurrences),
        evitar=_evitar_costs(snapshot, grid, occurrences, costs),
        lunch=_lunch_slots(snapshot, list(slots)),
        lunch_rule=snapshot.lunch_rule,
        presence={rule.teacher_id: rule for rule in snapshot.teacher_presence},
        dispensed=snapshot.lunch_dispensed_teacher_ids,
        costs=costs,
        lesson_minutes=lesson_minutes,
        units={unit_id: snapshot.assignment_for(unit_id) for unit_id in remaining},
        tail=tail,
        previous=previous,
    )
    return week, targets


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
    update: bool = False,
) -> Template:
    """Solve one weekly pattern for the given units (remaining minutes per unit).

    ``available`` limits the slots a week really has (None means every grid slot). Every weekday
    is solved, so a lesson the stages cannot place is shortfall, never a failed week.
    """
    started = clock.perf_counter()
    week, targets = _week_inputs(
        snapshot,
        periods,
        remaining=remaining,
        weeks_left=weeks_left,
        previous=previous,
        available=available,
        update=update,
    )
    began = clock.perf_counter()
    planned = _spread_counts(week, targets)
    counts, count_variables = _solve_counts(
        week, targets, planned, seed=random_seed, time_limit=time_limit_seconds
    )
    if counts is None:
        counts = planned
    count_seconds = clock.perf_counter() - began

    began = clock.perf_counter()
    plan = {
        weekday: {unit_id: count for (unit_id, day), count in counts.items() if day == weekday}
        for weekday in sorted({day for _unit, day in counts})
    }
    solved = _solve_days(week, plan, seed=random_seed, time_limit=time_limit_seconds)
    day_seconds = clock.perf_counter() - began

    placements = frozenset(row for rows, _status, _variables in solved.values() for row in rows)
    variables = max(
        [count_variables, *(day_variables for _rows, _s, day_variables in solved.values())]
    )
    return Template(
        placements,
        variables,
        sum(targets.values()) - len(placements),
        clock.perf_counter() - started,
        count_seconds,
        day_seconds,
    )


def _solve_days(
    week: _Week,
    plan: Mapping[int, Mapping[int, int]],
    *,
    seed: int,
    time_limit: float,
) -> dict[int, tuple[list[Placement], str, int]]:
    """Solve every weekday model, in parallel processes.

    Each model is single-threaded and bounded by deterministic ticks, so the parallel result
    equals the sequential one.
    """
    if not plan:
        return {}
    workers = min(len(plan), os.cpu_count() or 1)
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        futures = {
            weekday: pool.submit(
                _solve_day, week, weekday, day_counts, seed=seed, time_limit=time_limit
            )
            for weekday, day_counts in plan.items()
        }
        return {weekday: future.result() for weekday, future in futures.items()}


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


def _published_hints(
    snapshot: PlanningSnapshot, published: CandidateSchedule, origin_monday: date
) -> dict[int, frozenset[Placement]]:
    """The published lessons that are still open, as the stability hint of each school week."""
    hints: dict[int, set[Placement]] = defaultdict(set)
    for row in published.lessons:
        if is_physically_protected(snapshot, row.period):
            continue
        week = (row.period.school_date - origin_monday).days // 7
        hints[week].add(
            (
                row.assignment_id,
                row.period.school_date.weekday(),
                row.period.start_local,
                row.period.end_local,
            )
        )
    return {week: frozenset(rows) for week, rows in hints.items()}


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


def _overplaces(template: Template, remaining: Mapping[int, int], lesson_minutes: int) -> bool:
    """True when the template holds more slots for a unit than the unit has lessons left.

    Such a slot would be dropped inside the week, which takes a lesson out of a teacher or class
    day the template had built, so the rollout solves again first.
    """
    placed = Counter(unit_id for unit_id, _weekday, _start, _end in template.placements)
    return any(
        count > ceil(remaining[unit_id] / lesson_minutes)
        for unit_id, count in placed.items()
        if unit_id in remaining
    )


def generate_weekly_template(
    snapshot: PlanningSnapshot,
    periods: Iterable[Period],
    *,
    target_finish: date,
    time_limit_seconds: float = 600.0,
    random_seed: int = 1,
) -> MvpResult:
    """Roll the weekly template out on the calendar until every unit is complete.

    A week is solved against the slots its calendar really has, so a holiday week moves its
    lessons onto the school days. A week without any school day gets no placements.
    """
    return _roll_out(
        snapshot,
        periods,
        target_finish=target_finish,
        published=None,
        time_limit_seconds=time_limit_seconds,
        random_seed=random_seed,
    )


def update_weekly_template(
    snapshot: PlanningSnapshot,
    periods: Iterable[Period],
    published: CandidateSchedule,
    *,
    time_limit_seconds: float = 600.0,
    random_seed: int = 1,
) -> MvpResult:
    """Update a published weekly schedule: protected lessons stay, the rest is rolled out again.

    ``snapshot.protected_lessons`` and the protected dates fix the past. Demand that is left (missed
    lessons and the unplanned future) rolls out from the first unprotected week. Each week's template
    takes the published lessons of that week as its stability hint, so a week the change does not
    touch keeps its lessons.
    """
    return _roll_out(
        snapshot,
        periods,
        target_finish=max(row.period.school_date for row in published.lessons),
        published=published,
        time_limit_seconds=time_limit_seconds,
        random_seed=random_seed,
    )


def _roll_out(
    snapshot: PlanningSnapshot,
    periods: Iterable[Period],
    *,
    target_finish: date,
    published: CandidateSchedule | None,
    time_limit_seconds: float,
    random_seed: int,
) -> MvpResult:
    """The rollout shared by generation (``published`` None) and update."""
    periods = tuple(periods)
    origin_monday = snapshot.origin - timedelta(days=snapshot.origin.weekday())
    hints = None if published is None else _published_hints(snapshot, published, origin_monday)
    target_week = (target_finish - origin_monday).days // 7 - TARGET_LEAD_WEEKS
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
    lesson_minutes = typical_lesson_minutes(snapshot.grid_slots)
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
    solved_week = 0
    previous: frozenset[Placement] = frozenset()
    changes = 0
    weeks_with_dates = [(day - origin_monday).days // 7 for day, _start, _end in calendar]
    first_week, last_calendar_week = (
        min(weeks_with_dates, default=0),
        max(weeks_with_dates, default=0),
    )
    last_lesson_week = week = first_week
    while remaining and week <= last_calendar_week:
        monday = origin_monday + timedelta(weeks=week)
        available = frozenset(open_slots.get(week, ()))
        ready = frozenset(
            unit_id
            for unit_id in remaining
            if all(source not in remaining for source in predecessors[unit_id])
        )
        if (
            ready
            and available
            and (
                template is None
                or ready != solved_units
                or available != solved_available
                or week - solved_week >= REFRESH_WEEKS
                or _overplaces(template, remaining, lesson_minutes)
            )
        ):
            template = build_weekly_template(
                snapshot,
                calendar_periods,
                remaining={unit_id: remaining[unit_id] for unit_id in ready},
                weeks_left=max(1, target_week - week + 1),
                previous=previous if hints is None else hints.get(week, frozenset()),
                available=available,
                time_limit_seconds=time_limit_seconds,
                random_seed=random_seed,
                update=published is not None,
            )
            solves.append(template)
            changes += len(template.placements - previous)
            previous = template.placements
            solved_units, solved_available, solved_week = ready, available, week
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

    rollout_unfinished = len(remaining)
    candidate = _materialize(snapshot, placed, remaining)
    if remaining:
        filled = _fill_leftover(snapshot, periods, candidate, time_limit_seconds=time_limit_seconds)
        if filled is not None:
            candidate, remaining = filled, {}
    stats = {
        "template_solves": len(solves),
        "rollout_units_unfinished": rollout_unfinished,
        "largest_model_variables": max((t.variables for t in solves), default=0),
        "solve_seconds": round(sum(t.seconds for t in solves), 1),
        "count_seconds": round(sum(t.count_seconds for t in solves), 1),
        "day_seconds": round(sum(t.day_seconds for t in solves), 1),
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
    """Lessons with identities and module slices, then the production room pass.

    The protected lessons stay in the candidate: their identities and module progress are taken as
    given, so new lessons continue each module after them.
    """
    used_ids: set[int] = {row.lesson_id for row in snapshot.protected_lessons} | set(
        snapshot.reserved_lesson_ids
    )
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
            completed_minutes=_module_completed(snapshot, unit_id),
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
    combined = CandidateSchedule((*snapshot.protected_lessons, *lessons))
    return assign_rooms_by_period(snapshot, combined)


def _fill_leftover(
    snapshot: PlanningSnapshot,
    periods: Iterable[Period],
    candidate: CandidateSchedule,
    *,
    time_limit_seconds: float,
) -> CandidateSchedule | None:
    """Place the demand the rollout left with the engine's recovery fill.

    The rollout's lessons become the published baseline of ``construct_recovery``: each one keeps
    its place when it is still valid, and the missing credit goes to the earliest free capacity.
    """
    protected = {row.lesson_id for row in snapshot.protected_lessons}
    planning = replace(
        snapshot,
        baseline_lessons=tuple(row for row in candidate.lessons if row.lesson_id not in protected),
    )
    return construct_recovery(
        planning,
        tuple(periods),
        deadline=clock.monotonic() + time_limit_seconds,
        weights=snapshot.priority_weights,
    )
