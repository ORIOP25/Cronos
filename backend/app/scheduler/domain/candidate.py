"""Immutable v1 snapshot and candidate values for independent verification.

Every accepted structure is copied into tuples and read-only mappings so the
caller cannot mutate a snapshot after construction. The classes here carry
philosophy-free data only; no clock, database, solver or environment access.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.scheduler.domain.calendar import Period, normalize_period
from app.scheduler.domain.debt import RecoveryAllocation
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice


class SchedulingStrategy(StrEnum):
    COMPLETE_GENERATION = "COMPLETE_GENERATION"
    ADAPTIVE_RECOVERY = "ADAPTIVE_RECOVERY"


def _frozen_flat(values: Mapping[int, int]) -> Mapping[int, int]:
    if any(type(key) is not int or type(value) is not int for key, value in values.items()):
        raise ValueError("Snapshot identifiers and minute values must be integers.")
    return MappingProxyType(dict(values))


def _frozen_nested(values: Mapping[int, Mapping[int, int]]) -> Mapping[int, Mapping[int, int]]:
    if any(type(key) is not int for key in values):
        raise ValueError("Snapshot assignment identifiers must be integers.")
    return MappingProxyType({key: _frozen_flat(row) for key, row in values.items()})


def _minute(value: time, name: str) -> None:
    if type(value) is not time or value.tzinfo is not None or value.second or value.microsecond:
        raise ValueError(f"{name} must be a naive minute-precision local time.")


def _minute_of_day(value: time) -> int:
    return value.hour * 60 + value.minute


@dataclass(frozen=True)
class LunchRule:
    """Mandatory continuous lunch break inside a local window.

    The rule is a fixed school policy, so it is an immutable snapshot value.
    School hours sit between 08:00 and 20:00 and are unaffected by local clock
    changes, so the break is measured in local minutes of the same school date.
    """

    window_start: time
    window_end: time
    minimum_minutes: int

    def __post_init__(self) -> None:
        _minute(self.window_start, "window_start")
        _minute(self.window_end, "window_end")
        if self.window_start >= self.window_end:
            raise ValueError("A lunch window must have a positive duration.")
        if type(self.minimum_minutes) is not int or self.minimum_minutes <= 0:
            raise ValueError("A lunch minimum must be a positive integer.")
        if self.minimum_minutes > _minute_of_day(self.window_end) - _minute_of_day(
            self.window_start
        ):
            raise ValueError("A lunch minimum cannot exceed its window duration.")

    @property
    def window_start_minutes(self) -> int:
        return _minute_of_day(self.window_start)

    @property
    def window_end_minutes(self) -> int:
        return _minute_of_day(self.window_end)


def continuous_break_minutes(occupied: Sequence[tuple[int, int]], rule: LunchRule) -> int:
    """Longest continuous free interval inside the window, in local minutes.

    Short separated gaps never sum: only a single uninterrupted interval can
    satisfy the rule. A resource free during the whole window returns the full
    window length.
    """
    start = rule.window_start_minutes
    end = rule.window_end_minutes
    cursor = start
    longest = 0
    for occupied_start, occupied_end in sorted(occupied):
        if occupied_end <= start:
            continue
        if occupied_start >= end:
            break
        if occupied_start > cursor:
            longest = max(longest, occupied_start - cursor)
        cursor = max(cursor, min(occupied_end, end))
    return max(longest, end - cursor)


LESSON_IDENTITY_STRIDE = 1_000_000


def allocate_lesson_identity(assignment_id: int, rank: int, used: set[int]) -> int:
    """Next free lesson identity, never reusing a published or allocated ID."""
    identity = assignment_id * LESSON_IDENTITY_STRIDE + rank
    while identity in used:
        identity += 1
    used.add(identity)
    return identity


def _validate_executed_minutes(
    assignments: Mapping[int, Assignment],
    executed: Mapping[int, Mapping[int, int]],
) -> None:
    if not isinstance(executed, Mapping):
        raise ValueError("Executed progress must be a mapping.")
    for assignment_id, modules in executed.items():
        if type(assignment_id) is not int or assignment_id not in assignments:
            raise ValueError("Executed progress references an unknown assignment.")
        if not isinstance(modules, Mapping):
            raise ValueError("Executed progress must map modules to minutes.")
        assignment = assignments[assignment_id]
        required = {module.module_id: module.required_minutes for module in assignment.modules}
        for module_id, minutes in modules.items():
            if module_id not in required:
                raise ValueError("Executed progress references an unknown module.")
            if type(minutes) is not int or not 0 <= minutes <= required[module_id]:
                raise ValueError("Executed minutes are outside the module requirement.")


def _advance_frontier(
    modules: list[ModuleRequirement], cursor: Mapping[int, int], frontier: int
) -> int:
    while (
        frontier < len(modules)
        and cursor[modules[frontier].module_id] == modules[frontier].required_minutes
    ):
        frontier += 1
    return frontier


def _validate_protected_chronology(
    protected: tuple[ScheduledLesson, ...],
    assignments: Mapping[int, Assignment],
    executed: Mapping[int, Mapping[int, int]],
) -> None:
    for assignment in assignments.values():
        lessons = sorted(
            (lesson for lesson in protected if lesson.assignment_id == assignment.assignment_id),
            key=lambda lesson: (
                lesson.period.school_date,
                lesson.period.start_utc,
                lesson.lesson_id,
            ),
        )
        if not lessons:
            continue
        modules = sorted(assignment.modules, key=lambda module: module.sequence)
        sequence = {module.module_id: module.sequence for module in modules}
        cursor = {
            module.module_id: executed.get(assignment.assignment_id, {}).get(module.module_id, 0)
            for module in modules
        }
        frontier = _advance_frontier(modules, cursor, 0)
        for lesson in lessons:
            for slice_ in sorted(
                lesson.slices,
                key=lambda row: (sequence.get(row.module_id, 0), row.offset_minutes),
            ):
                if frontier >= len(modules):
                    raise ValueError("Protected slices exceed the assignment modules.")
                module = modules[frontier]
                if (
                    slice_.module_id != module.module_id
                    or slice_.offset_minutes != cursor[module.module_id]
                ):
                    raise ValueError("Protected slices do not form a chronological prefix.")
                cursor[module.module_id] += slice_.credit_minutes
                if cursor[module.module_id] > module.required_minutes:
                    raise ValueError("Protected slices exceed the module requirement.")
                frontier = _advance_frontier(modules, cursor, frontier)


def split_consumed_lessons(
    lessons: Sequence[ScheduledLesson],
    assignments: Mapping[int, Assignment],
    executed: Mapping[int, Mapping[int, int]],
) -> tuple[tuple[ScheduledLesson, ...], tuple[ScheduledLesson, ...]]:
    """Split ``(consumed, active)`` baseline lessons against executed minutes.

    A lesson whose slices are entirely covered by executed minutes is history:
    it stays out of the plannable baseline so coverage, capacity and the
    chronological prefix remain exact. A lesson partially covered by execution
    is a genuine inconsistency and fails loudly instead of being patched.
    """
    by_assignment: dict[int, list[ScheduledLesson]] = {}
    for lesson in lessons:
        by_assignment.setdefault(lesson.assignment_id, []).append(lesson)
    consumed: list[ScheduledLesson] = []
    active: list[ScheduledLesson] = []
    for assignment_id, rows in by_assignment.items():
        assignment = assignments.get(assignment_id)
        if assignment is None:
            active.extend(rows)
            continue
        cursor = {
            module.module_id: executed.get(assignment_id, {}).get(module.module_id, 0)
            for module in assignment.modules
        }
        for lesson in sorted(
            rows,
            key=lambda row: (
                row.period.school_date,
                row.period.start_utc,
                row.lesson_id,
            ),
        ):
            if all(
                slice_.offset_minutes + slice_.credit_minutes <= cursor.get(slice_.module_id, 0)
                for slice_ in lesson.slices
            ):
                consumed.append(lesson)
                continue
            if any(
                slice_.offset_minutes < cursor.get(slice_.module_id, 0) for slice_ in lesson.slices
            ):
                raise ValueError("Executed minutes overlap a published lesson in the middle.")
            active.append(lesson)
            for slice_ in lesson.slices:
                cursor[slice_.module_id] = cursor.get(slice_.module_id, 0) + slice_.credit_minutes
    return tuple(consumed), tuple(active)


def _validate_protected_lessons(
    protected: tuple[ScheduledLesson, ...],
    assignments: Mapping[int, Assignment],
    executed: Mapping[int, Mapping[int, int]],
) -> None:
    for lesson in protected:
        assignment = assignments.get(lesson.assignment_id)
        if assignment is None:
            raise ValueError("A protected lesson references an unknown assignment.")
        if lesson.room_id not in assignment.eligible_room_ids:
            raise ValueError("A protected lesson uses a room outside its assignment.")
        modules = {module.module_id: module for module in assignment.modules}
        for slice_ in lesson.slices:
            module = modules.get(slice_.module_id)
            if slice_.lesson_id != lesson.lesson_id:
                raise ValueError("A protected slice references another lesson.")
            if module is None:
                raise ValueError("A protected slice references an unknown module.")
            if slice_.offset_minutes + slice_.credit_minutes > module.required_minutes:
                raise ValueError("A protected slice exceeds its module requirement.")
        if sum(slice_.credit_minutes for slice_ in lesson.slices) != lesson.credit_minutes:
            raise ValueError("Protected slices do not sum to the lesson credit.")
    _validate_protected_chronology(protected, assignments, executed)


def _validate_baseline_lessons(
    baseline: tuple[ScheduledLesson, ...],
    assignments: Mapping[int, Assignment],
) -> None:
    """The published baseline may be stale, so only structural facts are checked.

    Room eligibility, calendar and resource conflicts are assessed separately:
    a published baseline invalidated by new data is exactly what AdaptiveRecovery
    must detect instead of keeping.
    """
    seen: set[int] = set()
    for lesson in baseline:
        if lesson.lesson_id in seen:
            raise ValueError("Baseline lesson identities must be unique.")
        seen.add(lesson.lesson_id)
        assignment = assignments.get(lesson.assignment_id)
        if assignment is None:
            raise ValueError("A baseline lesson references an unknown assignment.")
        modules = {module.module_id: module for module in assignment.modules}
        for slice_ in lesson.slices:
            module = modules.get(slice_.module_id)
            if (
                module is None
                or slice_.lesson_id != lesson.lesson_id
                or slice_.offset_minutes + slice_.credit_minutes > module.required_minutes
            ):
                raise ValueError("A baseline slice leaves its assignment module.")
        if sum(slice_.credit_minutes for slice_ in lesson.slices) != lesson.credit_minutes:
            raise ValueError("Baseline slices do not sum to the lesson credit.")


def _validate_accountability(
    assignments: Mapping[int, Assignment],
    claim_assignments: Mapping[int, int],
    open_debt_minutes: Mapping[int, int],
    reservations: tuple[RecoveryAllocation, ...],
) -> None:
    for assignment_id in claim_assignments.values():
        if assignment_id not in assignments:
            raise ValueError("A debt claim references an unknown assignment.")
    for allocation in reservations:
        if allocation.claim_id not in open_debt_minutes:
            raise ValueError("A recovery reservation references an unknown debt claim.")


def _unavailability_days(
    rows: tuple[Unavailability, ...],
) -> Mapping[tuple[str, int, date], tuple[Unavailability, ...]]:
    """Per-day index so annual checks stay linear in the relevant rows.

    A period never crosses its school date, so indexing by date is exact and
    keeps eligibility checks cheap at school scale.
    """
    days: dict[tuple[str, int, date], list[Unavailability]] = {}
    for row in rows:
        key = (row.resource_type.value, row.resource_id, row.period.school_date)
        days.setdefault(key, []).append(row)
    return MappingProxyType({key: tuple(values) for key, values in days.items()})


@dataclass(frozen=True)
class GridSlot:
    """One recurring school period in local school time."""

    day_of_week: int
    start_local: time
    end_local: time

    def __post_init__(self) -> None:
        if type(self.day_of_week) is not int or not 0 <= self.day_of_week <= 6:
            raise ValueError("Grid weekdays must be numbers from 0 to 6.")
        _minute(self.start_local, "start_local")
        _minute(self.end_local, "end_local")
        if self.start_local >= self.end_local:
            raise ValueError("A grid slot must have a positive local duration.")

    def matches(self, period: Period) -> bool:
        return (
            self.day_of_week == period.school_date.weekday()
            and self.start_local == period.start_local
            and self.end_local == period.end_local
        )


class UnavailableResource(StrEnum):
    CLASS = "class"
    TEACHER = "teacher"
    ROOM = "room"


@dataclass(frozen=True)
class Unavailability:
    """One physical interval where a resource cannot be used."""

    resource_type: UnavailableResource
    resource_id: int
    period: Period

    def __post_init__(self) -> None:
        if type(self.resource_type) is not UnavailableResource:
            raise ValueError("Unavailability needs a known resource type.")
        if type(self.resource_id) is not int or self.resource_id <= 0:
            raise ValueError("Unavailability needs a positive resource ID.")
        if type(self.period) is not Period:
            raise ValueError("Unavailability needs a normalized Period.")

    def overlaps(self, other: Period) -> bool:
        return self.period.start_utc < other.end_utc and other.start_utc < self.period.end_utc


@dataclass(frozen=True)
class Assignment:
    assignment_id: int
    class_id: int
    subject_id: int
    teacher_id: int
    eligible_room_ids: frozenset[int]
    modules: tuple[ModuleRequirement, ...]

    def __post_init__(self) -> None:
        for name in ("assignment_id", "class_id", "subject_id", "teacher_id"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        if not self.eligible_room_ids or any(
            type(room_id) is not int or room_id <= 0 for room_id in self.eligible_room_ids
        ):
            raise ValueError("An assignment needs positive eligible room IDs.")
        if not self.modules:
            raise ValueError("An assignment needs at least one module.")
        module_ids = [module.module_id for module in self.modules]
        if len(set(module_ids)) != len(module_ids):
            raise ValueError("Module IDs must be unique within an assignment.")
        sequences = [module.sequence for module in self.modules]
        if len(set(sequences)) != len(sequences):
            raise ValueError("Module sequences must be unique within an assignment.")
        object.__setattr__(self, "eligible_room_ids", frozenset(self.eligible_room_ids))
        object.__setattr__(self, "modules", tuple(self.modules))


@dataclass(frozen=True)
class ScheduledLesson:
    lesson_id: int
    assignment_id: int
    period: Period
    room_id: int
    credit_minutes: int
    slices: tuple[ModuleSlice, ...]
    source_lesson_id: int | None = None
    teacher_id: int | None = None
    class_id: int | None = None

    def __post_init__(self) -> None:
        if type(self.lesson_id) is not int or self.lesson_id <= 0:
            raise ValueError("lesson_id must be a positive integer.")
        if type(self.assignment_id) is not int or self.assignment_id <= 0:
            raise ValueError("assignment_id must be a positive integer.")
        if type(self.period) is not Period:
            raise ValueError("period must be a normalized Period.")
        expected = normalize_period(
            self.period.school_date,
            self.period.start_local,
            self.period.end_local,
            self.period.timezone_name,
        )
        if expected.start_utc != self.period.start_utc or expected.end_utc != self.period.end_utc:
            raise ValueError("The period UTC instants do not match its local school times.")
        if type(self.room_id) is not int or self.room_id <= 0:
            raise ValueError("room_id must be a positive integer.")
        if type(self.credit_minutes) is not int or self.credit_minutes <= 0:
            raise ValueError("credit_minutes must be a positive integer.")
        if self.credit_minutes > self.period.duration_minutes:
            raise ValueError("Curricular credit cannot exceed physical duration.")
        if type(self.slices) is not tuple:
            raise ValueError("Slices must be a tuple.")
        for name in ("source_lesson_id", "teacher_id", "class_id"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(f"{name} must be a positive integer when present.")


@dataclass(frozen=True)
class PlanningSnapshot:
    strategy: SchedulingStrategy
    origin: date
    preferred_end_date: date
    hard_end_date: date
    timezone_name: str
    grid_slots: tuple[GridSlot, ...]
    assignments: tuple[Assignment, ...]
    executed_minutes: Mapping[int, Mapping[int, int]]
    blocked_dates: frozenset[date]
    unavailable: tuple[Unavailability, ...]
    soft_unavailable: tuple[Unavailability, ...] = ()
    class_blocked_dates: Mapping[int, frozenset[date]] = field(default_factory=dict)
    protected_lessons: tuple[ScheduledLesson, ...] = ()
    baseline_lessons: tuple[ScheduledLesson, ...] = ()
    protected_dates: frozenset[date] = frozenset()
    now_utc: datetime | None = None
    reservations: tuple[RecoveryAllocation, ...] = ()
    open_debt_minutes: Mapping[int, int] = field(default_factory=dict)
    claim_assignments: Mapping[int, int] = field(default_factory=dict)
    active_version_id: int | None = None
    lunch_rule: LunchRule | None = None

    def __post_init__(self) -> None:
        if type(self.strategy) is not SchedulingStrategy:
            raise ValueError("A snapshot needs an explicit scheduling strategy.")
        if type(self.origin) is not date or type(self.preferred_end_date) is not date:
            raise ValueError("Scheduling dates must be dates.")
        if type(self.hard_end_date) is not date:
            raise ValueError("The hard end date must be a date.")
        if not self.origin <= self.preferred_end_date <= self.hard_end_date:
            raise ValueError("Scheduling dates must satisfy origin <= preferred <= hard end.")
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
            raise ValueError("Unknown school timezone.") from exc
        if not self.grid_slots or type(self.grid_slots) is not tuple:
            raise ValueError("A snapshot needs at least one concrete grid slot.")
        if any(type(slot) is not GridSlot for slot in self.grid_slots):
            raise ValueError("Grid slots must be GridSlot values.")
        if not self.assignments:
            raise ValueError("A snapshot needs at least one assignment.")
        if len({row.assignment_id for row in self.assignments}) != len(self.assignments):
            raise ValueError("Assignment IDs must be unique.")
        assignments = {row.assignment_id: row for row in self.assignments}
        if any(type(row) is not ScheduledLesson for row in self.protected_lessons):
            raise ValueError("Protected lessons must be ScheduledLesson values.")
        if any(type(row) is not ScheduledLesson for row in self.baseline_lessons):
            raise ValueError("Baseline lessons must be ScheduledLesson values.")
        if any(type(row) is not RecoveryAllocation for row in self.reservations):
            raise ValueError("Reservations must be RecoveryAllocation values.")
        _validate_executed_minutes(assignments, self.executed_minutes)
        _validate_protected_lessons(self.protected_lessons, assignments, self.executed_minutes)
        _validate_baseline_lessons(self.baseline_lessons, assignments)
        if type(self.unavailable) is not tuple or any(
            type(row) is not Unavailability for row in self.unavailable
        ):
            raise ValueError("Unavailability must be a tuple of Unavailability values.")
        if type(self.soft_unavailable) is not tuple or any(
            type(row) is not Unavailability for row in self.soft_unavailable
        ):
            raise ValueError("Soft unavailability must be a tuple of Unavailability values.")
        if any(type(day) is not date for day in self.blocked_dates):
            raise ValueError("Blocked dates must be dates.")
        if any(type(class_id) is not int or class_id <= 0 for class_id in self.class_blocked_dates):
            raise ValueError("Class-blocked dates must be keyed by positive class IDs.")
        if any(
            any(type(day) is not date for day in days) for days in self.class_blocked_dates.values()
        ):
            raise ValueError("Class-blocked dates must be dates.")
        if any(type(day) is not date for day in self.protected_dates):
            raise ValueError("Protected dates must be dates.")
        if self.now_utc is not None and (
            type(self.now_utc) is not datetime or self.now_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("The reference instant must be UTC with timezone.")
        if self.active_version_id is not None and (
            type(self.active_version_id) is not int or self.active_version_id <= 0
        ):
            raise ValueError("The active version ID must be positive when present.")
        if self.lunch_rule is not None and type(self.lunch_rule) is not LunchRule:
            raise ValueError("The lunch rule must be a LunchRule when present.")
        claim_ids = {claim_id for claim_id, _ in self.open_debt_minutes.items()}
        if claim_ids != set(self.claim_assignments):
            raise ValueError("Every open debt claim needs its assignment.")
        if any(
            type(claim_id) is not int or minutes < 0
            for claim_id, minutes in self.open_debt_minutes.items()
        ):
            raise ValueError("Open debt must be nonnegative minutes keyed by claim ID.")
        _validate_accountability(
            assignments, self.claim_assignments, self.open_debt_minutes, self.reservations
        )
        object.__setattr__(self, "executed_minutes", _frozen_nested(self.executed_minutes))
        object.__setattr__(self, "open_debt_minutes", _frozen_flat(self.open_debt_minutes))
        object.__setattr__(self, "claim_assignments", _frozen_flat(self.claim_assignments))
        object.__setattr__(self, "assignments", tuple(self.assignments))
        object.__setattr__(self, "protected_lessons", tuple(self.protected_lessons))
        object.__setattr__(self, "baseline_lessons", tuple(self.baseline_lessons))
        object.__setattr__(self, "reservations", tuple(self.reservations))
        object.__setattr__(self, "blocked_dates", frozenset(self.blocked_dates))
        object.__setattr__(self, "protected_dates", frozenset(self.protected_dates))
        object.__setattr__(
            self,
            "class_blocked_dates",
            MappingProxyType(
                {class_id: frozenset(days) for class_id, days in self.class_blocked_dates.items()}
            ),
        )
        object.__setattr__(self, "_unavailable_days", _unavailability_days(self.unavailable))
        object.__setattr__(
            self, "_soft_unavailable_days", _unavailability_days(self.soft_unavailable)
        )

    @property
    def grid_weekdays(self) -> frozenset[int]:
        return frozenset(slot.day_of_week for slot in self.grid_slots)

    def blocked_on(self, class_id: int, school_date: date) -> bool:
        """True when the school or this class has no lessons on the date."""
        return school_date in self.blocked_dates or school_date in self.class_blocked_dates.get(
            class_id, ()
        )

    def executed_for(self, assignment_id: int) -> Mapping[int, int]:
        return self.executed_minutes.get(assignment_id, MappingProxyType({}))

    def assignment_for(self, assignment_id: int) -> Assignment | None:
        return next((row for row in self.assignments if row.assignment_id == assignment_id), None)

    def hard_unavailable_on(
        self, resource_type: UnavailableResource, resource_id: int, school_date: date
    ) -> tuple[Unavailability, ...]:
        return self._unavailable_days.get((resource_type.value, resource_id, school_date), ())

    def soft_unavailable_on(
        self, resource_type: UnavailableResource, resource_id: int, school_date: date
    ) -> tuple[Unavailability, ...]:
        return self._soft_unavailable_days.get((resource_type.value, resource_id, school_date), ())


@dataclass(frozen=True)
class CandidateSchedule:
    lessons: tuple[ScheduledLesson, ...]

    def __post_init__(self) -> None:
        if type(self.lessons) is not tuple:
            raise ValueError("Candidate lessons must be a tuple.")
