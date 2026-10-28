"""Shared construction heuristics; no solver state or OR-Tools imports."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from datetime import date, datetime

from app.scheduler.domain.availability_priority import (
    CLASS,
    RESOURCE_KINDS,
    TEACHER,
    AvailabilityLedger,
)
from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    LunchRule,
    PlanningSnapshot,
    TeacherPresenceRule,
)
from app.scheduler.domain.class_day_gaps import class_day_excess_value, class_day_gap_worsened
from app.scheduler.domain.priorities import SCARCITY_UNIT_COST, PriorityWeights
from app.scheduler.domain.priority_value import _grid_interval, _local_interval
from app.scheduler.domain.teacher_presence import (
    PresenceLesson,
    longest_presence_minutes,
    presence_minutes_fit,
    teacher_day_complies,
)


def _scarcity(
    ledger: AvailabilityLedger, assignment: Assignment, period: Period, credit: int
) -> int:
    """T07: an empty hour in a tight calendar is not free, because the lesson must still be
    taught later. The push grows with the tightness of the calendar, up to full.
    """
    return round(SCARCITY_UNIT_COST * credit * ledger.tightness(assignment, period))


def _gives_up(ledger: AvailabilityLedger, period: Period, *, strict: bool) -> bool:
    """Whether a pass stops early because it can no longer place every missing hour.

    A strict pass waits for its first refusal: only a refusal sends the
    construction on to the relaxed pass, and a later one could still come.
    """
    return (ledger.refused > 0 or not strict) and ledger.cannot_finish(period)


def _evitar_kinds(weights: PriorityWeights | None) -> frozenset[str]:
    """The resource kinds whose Evitar blocks steer the construction (D01, I05).

    Without weights the construction keeps its availability rules for both kinds.
    """
    if weights is None:
        return RESOURCE_KINDS
    return frozenset(
        kind
        for kind, level in (
            (TEACHER, weights.teacher_preferences),
            (CLASS, weights.class_preferences),
        )
        if level > 0
    )


def _minimum_presence_teachers(snapshot: PlanningSnapshot) -> dict[int, TeacherPresenceRule]:
    """Teachers with a presence minimum, keyed by teacher id."""
    return {
        row.teacher_id: row for row in snapshot.teacher_presence if row.minimum_minutes is not None
    }


def _longest_presences(
    snapshot: PlanningSnapshot,
    rules: Mapping[int, TeacherPresenceRule],
    slots_by_day: Mapping[int, Sequence[GridSlot]],
) -> dict[int, int]:
    """The longest presence each teacher with a minimum can hold on any grid day."""
    return {
        teacher_id: max(
            (
                longest_presence_minutes(
                    rule, [_grid_interval(slot) for slot in slots], lunch_rule=snapshot.lunch_rule
                )
                for slots in slots_by_day.values()
            ),
            default=0,
        )
        for teacher_id, rule in rules.items()
    }


def _presence_left_fits(left: int, rule: TeacherPresenceRule, longest: int) -> bool:
    """Minutes left to a teacher must still split into valid presences (no stranded hours)."""
    return presence_minutes_fit(left, minimum=rule.minimum_minutes, longest=longest)


def _grid_intervals_by_day(
    slots_by_day: Mapping[int, Sequence[GridSlot]],
) -> dict[int, tuple[tuple[int, int], ...]]:
    return {
        day: tuple(_grid_interval(slot) for slot in day_slots)
        for day, day_slots in slots_by_day.items()
    }


def _presence_day_complies(
    intervals: Iterable[tuple[int, int]],
    protected: AbstractSet[tuple[int, int]],
    rule: TeacherPresenceRule,
    lunch_rule: LunchRule | None,
    grid_slots: Sequence[tuple[int, int]],
) -> bool:
    """True when a teacher's booked intervals on one day meet the presence rule."""
    lessons = [PresenceLesson(start, end, (start, end) in protected) for start, end in intervals]
    return teacher_day_complies(lessons, rule, lunch_rule=lunch_rule, grid_slots=grid_slots)


def _resource_keys(
    assignment: Assignment, room: int, teacher: int, school_date: date
) -> tuple[tuple, ...]:
    """Busy keys of one lesson: its teacher, room and classes on the date."""
    return (
        ("teacher", teacher, school_date),
        ("room", room, school_date),
        *(("class", class_id, school_date) for class_id in assignment.class_ids),
    )


def class_day_excess_option_value(
    occupancy, assignment: Assignment, period: Period, slots: Sequence[GridSlot], lunch_rule
) -> int:
    """T06 excess-gap term of an option: the excess minutes its classes shed on that date."""
    return class_day_excess_value(
        (occupancy[("class", class_id, period.school_date)] for class_id in assignment.class_ids),
        _local_interval(period),
        slots,
        lunch_rule,
    )


def class_day_gap_refused(
    occupancy, assignment: Assignment, period: Period, slots: Sequence[GridSlot], lunch_rule
) -> bool:
    """Owner rule (23 Oct 2026): the option would give one of its classes a second gap hour."""
    return class_day_gap_worsened(
        (occupancy[("class", class_id, period.school_date)] for class_id in assignment.class_ids),
        _local_interval(period),
        slots,
        lunch_rule,
    )


def _slots_by_day(snapshot: PlanningSnapshot) -> dict[int, tuple[GridSlot, ...]]:
    by_day: dict[int, list[GridSlot]] = defaultdict(list)
    for slot in snapshot.grid_slots:
        by_day[slot.day_of_week].append(slot)
    return {
        day: tuple(sorted(rows, key=lambda slot: (slot.start_local, slot.end_local)))
        for day, rows in by_day.items()
    }


def _slot_position_for_interval(slots: Sequence[GridSlot], interval: tuple[int, int]) -> int | None:
    start, end = interval
    for position, slot in enumerate(slots):
        if (
            slot.start_local.hour * 60 + slot.start_local.minute == start
            and slot.end_local.hour * 60 + slot.end_local.minute == end
        ):
            return position
    return None


def _continues_open_presence(
    slots_by_day: dict[int, tuple[GridSlot, ...]],
    occupancy: dict,
    teacher_id: int,
    period: Period,
    presence_rules: dict[int, TeacherPresenceRule],
) -> bool:
    """True when the period extends an open presence of a minimum teacher.

    Adjacency is by grid position, not by wall-clock minutes, so the default
    grid's short inter-block break still counts as continuing. The exact
    minimum/gap semantics live in ``domain/teacher_presence.py`` and the
    validator; this only prefers extending an open run so a presence reaches the
    minimum instead of fragmenting the day.
    """
    if teacher_id not in presence_rules:
        return False
    slots = slots_by_day.get(period.school_date.weekday(), ())
    position = _slot_position_for_interval(slots, _local_interval(period))
    if position is None:
        return False
    return any(
        (other := _slot_position_for_interval(slots, row)) is not None
        and abs(other - position) == 1
        for row in occupancy[("teacher", teacher_id, period.school_date)]
    )


def _next_module(modules, cursor: dict[int, int]) -> int | None:
    for index, module in enumerate(modules):
        if cursor[module.module_id] < module.required_minutes:
            return index
    return None


def _predecessors_ready(
    predecessors: Mapping[int, Sequence[int]],
    remaining: Mapping[int, int],
    last_end: Mapping[int, datetime],
    identity: int,
    period: Period,
) -> bool:
    """All predecessor units must finish before this physical period."""
    return all(
        remaining[source] <= 0 and last_end.get(source, period.start_utc) <= period.start_utc
        for source in predecessors.get(identity, ())
    )
