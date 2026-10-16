"""Pure teacher presence rules for one school day (D03, D04, D06, T03).

The day splits into one or two presences: the whole day without a lunch break, or
the morning and the afternoon separated by a free lunch choice inside the
configured window. Each presence is either empty or at least the minimum hours,
and its gap is the sum of empty grid blocks between its first and last lesson.
A presence made only of protected lessons is exempt; a presence with at least one
editable lesson counts every lesson, protected included.

No clock, database, solver or environment access lives here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    LunchRule,
    PlanningSnapshot,
    TeacherPresenceRule,
    UnavailableResource,
)
from app.scheduler.domain.capacity import canonical_periods, residual_minutes


@dataclass(frozen=True)
class PresenceLesson:
    """One lesson of a teacher on a school day, measured in local minutes."""

    start_minute: int
    end_minute: int
    protected: bool

    def __post_init__(self) -> None:
        for name in ("start_minute", "end_minute"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer.")
        if self.start_minute >= self.end_minute:
            raise ValueError("A presence lesson must have a positive duration.")
        if type(self.protected) is not bool:
            raise ValueError("The protected flag must be a boolean.")


@dataclass(frozen=True)
class PresenceSlot:
    """One visible grid block of a day and whether the teacher can teach it."""

    start_minute: int
    end_minute: int
    possible: bool

    def __post_init__(self) -> None:
        for name in ("start_minute", "end_minute"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer.")
        if self.start_minute >= self.end_minute:
            raise ValueError("A presence slot must have a positive duration.")
        if type(self.possible) is not bool:
            raise ValueError("The possible flag must be a boolean.")


def lunch_options(
    boundaries: Sequence[int], window_end: int, minimum: int
) -> list[tuple[int, int]]:
    """Minimal windows of at least the minimum length, anchored at a boundary.

    A maximal free run always starts at a boundary. Its first boundary at or
    after ``origin + minimum`` lies inside the run, so requiring one of these
    minimal anchors to stay free is exact and keeps the option count linear.
    """
    options: list[tuple[int, int]] = []
    for origin in boundaries:
        if origin + minimum > window_end:
            continue
        closing = next(value for value in boundaries if value >= origin + minimum)
        options.append((origin, closing))
    return options


def _lunch_choices_from_intervals(
    intervals: Sequence[tuple[int, int]], rule: LunchRule
) -> list[tuple[int, int]]:
    start = rule.window_start_minutes
    end = rule.window_end_minutes
    boundaries = {start, end}
    for interval_start, interval_end in intervals:
        if start < interval_start < end:
            boundaries.add(interval_start)
        if start < interval_end < end:
            boundaries.add(interval_end)
    return lunch_options(sorted(boundaries), end, rule.minimum_minutes)


def _lunch_choices(lessons: Sequence[PresenceLesson], rule: LunchRule) -> list[tuple[int, int]]:
    return _lunch_choices_from_intervals(
        ((lesson.start_minute, lesson.end_minute) for lesson in lessons), rule
    )


def _free(lessons: Sequence[PresenceLesson], start: int, end: int) -> bool:
    return all(not (lesson.start_minute < end and start < lesson.end_minute) for lesson in lessons)


def _gap_minutes(lessons: Sequence[PresenceLesson], grid_slots: Sequence[tuple[int, int]]) -> int:
    first = min(lesson.start_minute for lesson in lessons)
    last = max(lesson.end_minute for lesson in lessons)
    gap = 0
    for slot_start, slot_end in grid_slots:
        if slot_end <= first or slot_start >= last:
            continue
        if any(
            lesson.start_minute < slot_end and slot_start < lesson.end_minute for lesson in lessons
        ):
            continue
        gap += slot_end - slot_start
    return gap


def _presence_complies(
    lessons: Sequence[PresenceLesson],
    rule: TeacherPresenceRule,
    grid_slots: Sequence[tuple[int, int]],
) -> bool:
    if not lessons:
        return True
    if all(lesson.protected for lesson in lessons):
        return True
    minutes = sum(lesson.end_minute - lesson.start_minute for lesson in lessons)
    if minutes < rule.minimum_minutes:
        return False
    return _gap_minutes(lessons, grid_slots) <= rule.max_gap_minutes


def teacher_day_complies(
    lessons: Sequence[PresenceLesson],
    rule: TeacherPresenceRule,
    *,
    lunch_rule: LunchRule | None,
    grid_slots: Sequence[tuple[int, int]] = (),
) -> bool:
    """True when some valid lunch split keeps every non-exempt presence compliant.

    Without a minimum the presence rule imposes nothing. With a required lunch
    and a configured window there must be a free lunch choice that splits the day
    into compliant presences; otherwise the whole day is a single presence.
    """
    if rule.minimum_minutes is None:
        return True
    if not rule.lunch_required or lunch_rule is None:
        return _presence_complies(tuple(lessons), rule, grid_slots)
    for start, end in _lunch_choices(lessons, lunch_rule):
        if not _free(lessons, start, end):
            continue
        morning = [lesson for lesson in lessons if lesson.end_minute <= start]
        afternoon = [lesson for lesson in lessons if lesson.start_minute >= end]
        if _presence_complies(morning, rule, grid_slots) and _presence_complies(
            afternoon, rule, grid_slots
        ):
            return True
    return False


def _span_reaches_minimum(slots: Sequence[PresenceSlot], minimum: int, max_gap: int) -> bool:
    """True when a contiguous span of slots can host a presence of the minimum.

    The span starts and ends on a possible slot; the impossible slots inside it
    are the presence holes and may not exceed the maximum gap. An impossible run
    longer than the gap ends the search from that possible slot.
    """
    for index, slot in enumerate(slots):
        if not slot.possible:
            continue
        possible = 0
        impossible = 0
        for candidate in slots[index:]:
            duration = candidate.end_minute - candidate.start_minute
            if candidate.possible:
                possible += duration
            else:
                impossible += duration
            if impossible > max_gap:
                break
            if candidate.possible and possible >= minimum:
                return True
    return False


def teacher_can_have_presence(
    rule: TeacherPresenceRule,
    slots_by_weekday: Mapping[int, Sequence[PresenceSlot]],
    *,
    lunch_rule: LunchRule | None,
) -> bool:
    """True when some visible day can host a presence of the minimum (D08).

    The pure pre-check uses the visible grid and the teacher's impossible blocks.
    A rule without a minimum imposes nothing. With a required lunch and a
    configured window, the span must lie on one side of a free lunch option, so
    the break can be taken without overlapping the presence.
    """
    if rule.minimum_minutes is None:
        return True
    minimum = rule.minimum_minutes
    max_gap = rule.max_gap_minutes or 0
    for slots in slots_by_weekday.values():
        if not slots:
            continue
        if not rule.lunch_required or lunch_rule is None:
            if _span_reaches_minimum(slots, minimum, max_gap):
                return True
            continue
        for start, end in _lunch_choices_from_intervals(
            ((slot.start_minute, slot.end_minute) for slot in slots), lunch_rule
        ):
            morning = [slot for slot in slots if slot.end_minute <= start]
            afternoon = [slot for slot in slots if slot.start_minute >= end]
            if _span_reaches_minimum(morning, minimum, max_gap) or _span_reaches_minimum(
                afternoon, minimum, max_gap
            ):
                return True
    return False


def impossible_presence_teacher_ids(
    snapshot: PlanningSnapshot, periods: tuple[Period, ...]
) -> tuple[int, ...]:
    """Prove a minimum cannot fit, using optimistic physical daily capacity.

    Ignore competing classes, rooms and protected dates: excluding those here
    could reject a mixed presence that legitimately counts protected lessons.
    Teachers with no editable demand retain the protected-only exemption.
    """
    teachers_with_demand = {
        row.teacher_id
        for row in snapshot.assignments
        if residual_minutes(snapshot, row.assignment_id) > 0
    }
    rules = [
        rule
        for rule in snapshot.teacher_presence
        if rule.minimum_minutes is not None and rule.teacher_id in teachers_with_demand
    ]
    if not rules:
        return ()
    ordered = tuple(
        period
        for period in canonical_periods(periods)
        if any(slot.matches(period) for slot in snapshot.grid_slots)
    )
    impossible = []
    for rule in rules:
        days: dict[int, list[PresenceSlot]] = {}
        for period in ordered:
            possible = not any(
                row.overlaps(period)
                for row in snapshot.hard_unavailable_on(
                    UnavailableResource.TEACHER, rule.teacher_id, period.school_date
                )
            )
            days.setdefault(period.school_date.toordinal(), []).append(
                PresenceSlot(
                    period.start_local.hour * 60 + period.start_local.minute,
                    period.end_local.hour * 60 + period.end_local.minute,
                    possible,
                )
            )
        if not teacher_can_have_presence(rule, days, lunch_rule=snapshot.lunch_rule):
            impossible.append(rule.teacher_id)
    return tuple(sorted(impossible))
