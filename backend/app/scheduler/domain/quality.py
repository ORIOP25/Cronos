from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, time
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    PlanningSnapshot,
    ScheduledLesson,
    UnavailableResource,
)

QUALITY_POLICY_VERSION = "baseline-v1"


@dataclass(frozen=True, order=True)
class InitialQualityVector:
    completion_days_desc: tuple[int, ...]
    teacher_gap_minutes: int
    class_gap_minutes: int
    preference_cost: int
    room_change_cost: int


def _completion_days_desc(
    completion_dates: Mapping[int, date], class_ids: Sequence[int], origin: date, end: date
) -> tuple[int, ...]:
    if type(origin) is not date or type(end) is not date or origin > end:
        raise ValueError("Scheduling dates are invalid.")
    if (
        not class_ids
        or len(set(class_ids)) != len(class_ids)
        or set(completion_dates) != set(class_ids)
    ):
        raise ValueError("Every expected class needs one completion date.")
    days = []
    for completion in completion_dates.values():
        if type(completion) is not date or not origin <= completion <= end:
            raise ValueError("Class completion is outside the scheduling dates.")
        days.append((completion - origin).days)
    return tuple(sorted(days, reverse=True))


def initial_quality_vector(
    completion_dates: Mapping[int, date],
    *,
    class_ids: Sequence[int],
    origin: date,
    preferred_end_date: date,
    teacher_gap_minutes: int,
    class_gap_minutes: int,
    preference_cost: int,
    room_change_cost: int,
) -> InitialQualityVector:
    """Compare only complete initial schedules under the preferred end date."""
    days = _completion_days_desc(completion_dates, class_ids, origin, preferred_end_date)
    costs = (teacher_gap_minutes, class_gap_minutes, preference_cost, room_change_cost)
    if any(type(cost) is not int or cost < 0 for cost in costs):
        raise ValueError("Initial quality costs must be nonnegative integer values.")
    return InitialQualityVector(days, *costs)


@dataclass(frozen=True)
class StageEvidence:
    """One optimized quality component with the scope of its proof."""

    stage: str
    value: int
    proven: bool
    reused: bool = False

    def __post_init__(self) -> None:
        if not self.stage or type(self.value) is not int or self.value < 0:
            raise ValueError("Stage evidence needs a name and a nonnegative integer value.")


@dataclass(frozen=True)
class SearchEvidence:
    """Objective, certified prefix, bounds and stop reason of one search."""

    objective_scope: str
    stages: tuple[StageEvidence, ...]
    certified_stages: int
    stop_reason: str
    rounds: int = 1
    proposals_excluded: int = 0
    relaxation_bound: int | None = None
    relaxation_incumbent: int | None = None
    relaxation_proven: bool = False
    relaxation_scope: str | None = None

    def __post_init__(self) -> None:
        if not self.objective_scope or not self.stop_reason:
            raise ValueError("Search evidence needs an objective scope and a stop reason.")
        if not 0 <= self.certified_stages <= len(self.stages):
            raise ValueError("The certified prefix cannot exceed the recorded stages.")
        if any(not stage.proven for stage in self.stages[: self.certified_stages]):
            raise ValueError("A certified prefix only contains proven stages.")
        if self.certified_stages < len(self.stages):
            if self.stages[self.certified_stages].proven:
                raise ValueError("The certified prefix must be contiguous.")
        if self.rounds < 1 or self.proposals_excluded < 0:
            raise ValueError("Search evidence needs a positive round count.")
        if (
            self.relaxation_bound is not None
            and self.relaxation_incumbent is not None
            and self.relaxation_bound > self.relaxation_incumbent
        ):
            raise ValueError("A relaxation lower bound cannot exceed its incumbent.")


@dataclass(frozen=True)
class InitialQualityMetrics:
    """Recalculated quality components of a materialized initial schedule."""

    completion_dates: Mapping[int, date]
    teacher_gap_minutes: int
    class_gap_minutes: int
    preference_cost_minutes: int
    room_change_cost: int

    def vector(self, *, origin: date, preferred_end_date: date) -> InitialQualityVector:
        return initial_quality_vector(
            self.completion_dates,
            class_ids=tuple(sorted(self.completion_dates)),
            origin=origin,
            preferred_end_date=preferred_end_date,
            teacher_gap_minutes=self.teacher_gap_minutes,
            class_gap_minutes=self.class_gap_minutes,
            preference_cost=self.preference_cost_minutes,
            room_change_cost=self.room_change_cost,
        )


def _slot_position(grid_slots: Sequence[GridSlot], period) -> int | None:
    slots = sorted(
        (slot for slot in grid_slots if slot.day_of_week == period.school_date.weekday()),
        key=lambda slot: (slot.start_local, slot.end_local),
    )
    for position, slot in enumerate(slots):
        if slot.matches(period):
            return position
    return None


def _gap_minutes(
    grid_slots: Sequence[GridSlot],
    occupied: Mapping[tuple[int, date], set[int]],
) -> int:
    total = 0
    for (_resource_id, school_date), positions in occupied.items():
        if len(positions) < 2:
            continue
        slots = sorted(
            (slot for slot in grid_slots if slot.day_of_week == school_date.weekday()),
            key=lambda slot: (slot.start_local, slot.end_local),
        )
        first, last = min(positions), max(positions)
        total += sum(
            (slots[position].end_local.hour * 60 + slots[position].end_local.minute)
            - (slots[position].start_local.hour * 60 + slots[position].start_local.minute)
            for position in range(first + 1, last)
            if position not in positions
        )
    return total


def _teacher_for(lesson: ScheduledLesson, assignment: Assignment) -> int:
    return lesson.teacher_id if lesson.teacher_id is not None else assignment.teacher_id


def _is_dispreferred(
    snapshot: PlanningSnapshot, assignment: Assignment, lesson: ScheduledLesson
) -> bool:
    for resource_type, resource_id in (
        (UnavailableResource.CLASS, assignment.class_id),
        (UnavailableResource.TEACHER, _teacher_for(lesson, assignment)),
        (UnavailableResource.ROOM, lesson.room_id),
    ):
        if any(
            row.overlaps(lesson.period)
            for row in snapshot.soft_unavailable_on(
                resource_type, resource_id, lesson.period.school_date
            )
        ):
            return True
    return False


def measure_initial_quality(
    snapshot: PlanningSnapshot, candidate: CandidateSchedule
) -> InitialQualityMetrics:
    """Recalculate the initial quality components without consulting the solver."""
    if type(snapshot) is not PlanningSnapshot or type(candidate) is not CandidateSchedule:
        raise ValueError("Quality measurement needs a snapshot and a candidate schedule.")
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    completion_dates = {row.class_id: snapshot.origin for row in snapshot.assignments}
    teacher_days: dict[tuple[int, date], set[int]] = defaultdict(set)
    class_days: dict[tuple[int, date], set[int]] = defaultdict(set)
    rooms: dict[tuple[int, int], set[int]] = defaultdict(set)
    preference_cost = 0
    for lesson in candidate.lessons:
        assignment = assignments.get(lesson.assignment_id)
        if assignment is None:
            raise ValueError("The candidate references an assignment outside the snapshot.")
        previous = completion_dates.get(assignment.class_id, lesson.period.school_date)
        completion_dates[assignment.class_id] = max(previous, lesson.period.school_date)
        position = _slot_position(snapshot.grid_slots, lesson.period)
        if position is not None:
            teacher_days[(_teacher_for(lesson, assignment), lesson.period.school_date)].add(
                position
            )
            class_days[(assignment.class_id, lesson.period.school_date)].add(position)
        if _is_dispreferred(snapshot, assignment, lesson):
            preference_cost += lesson.period.duration_minutes
        rooms[(assignment.class_id, assignment.subject_id)].add(lesson.room_id)
    return InitialQualityMetrics(
        completion_dates=MappingProxyType(dict(sorted(completion_dates.items()))),
        teacher_gap_minutes=_gap_minutes(snapshot.grid_slots, teacher_days),
        class_gap_minutes=_gap_minutes(snapshot.grid_slots, class_days),
        preference_cost_minutes=preference_cost,
        room_change_cost=sum(max(0, len(room_ids) - 1) for room_ids in rooms.values()),
    )


@dataclass(frozen=True)
class AdaptiveQualityPolicy:
    version: str
    daily_slopes: tuple[int, ...]
    disruption_weight: int

    def __post_init__(self) -> None:
        if (
            not self.version
            or type(self.disruption_weight) is not int
            or self.disruption_weight <= 0
        ):
            raise ValueError("Adaptive quality needs a version and positive disruption weight.")
        if type(self.daily_slopes) is not tuple or any(
            type(slope) is not int or slope <= 0 for slope in self.daily_slopes
        ):
            raise ValueError("Margin slopes must be positive integers.")
        if any(
            left >= right
            for left, right in zip(self.daily_slopes, self.daily_slopes[1:], strict=False)
        ):
            raise ValueError("Margin slopes must increase toward the preferred end date.")


@dataclass(frozen=True, order=True)
class AdaptiveQualityVector:
    excess_days_desc: tuple[int, ...]
    progressive_cost_desc: tuple[int, ...]
    completion_days_desc: tuple[int, ...]
    disruption_cost: int
    teacher_gap_minutes: int
    class_gap_minutes: int
    preference_cost: int
    room_change_cost: int


def adaptive_quality_vector(
    completion_dates: Mapping[int, date],
    *,
    class_ids: Sequence[int],
    origin: date,
    preferred_end_date: date,
    hard_end_date: date,
    disruption_cost: int,
    teacher_gap_minutes: int,
    class_gap_minutes: int,
    preference_cost: int,
    room_change_cost: int,
    policy: AdaptiveQualityPolicy,
) -> AdaptiveQualityVector:
    """Compare complete repairs using explicit experimental policy parameters."""
    if (
        type(origin) is not date
        or type(preferred_end_date) is not date
        or type(hard_end_date) is not date
        or not origin <= preferred_end_date <= hard_end_date
    ):
        raise ValueError("Adaptive scheduling dates are invalid.")
    days = _completion_days_desc(completion_dates, class_ids, origin, hard_end_date)
    preferred_day = (preferred_end_date - origin).days
    if len(policy.daily_slopes) != preferred_day:
        raise ValueError("Margin slopes must cover every day before the preference.")
    costs = (
        disruption_cost,
        teacher_gap_minutes,
        class_gap_minutes,
        preference_cost,
        room_change_cost,
    )
    if any(type(cost) is not int or cost < 0 for cost in costs):
        raise ValueError("Adaptive quality costs must be nonnegative integer values.")
    margin_cost = [0]
    for slope in policy.daily_slopes:
        margin_cost.append(margin_cost[-1] + slope)
    excess = tuple(max(0, day - preferred_day) for day in days)
    progressive = tuple(
        margin_cost[min(day, preferred_day)] + policy.disruption_weight * disruption_cost
        for day in days
    )
    return AdaptiveQualityVector(excess, progressive, days, *costs)


class SolveWorkloadMode(StrEnum):
    QUALITY_ONLY = "QUALITY_ONLY"
    PROTECT_COMFORT = "PROTECT_COMFORT"
    DEADLINE_RESCUE = "DEADLINE_RESCUE"


class AvailabilityTier(StrEnum):
    PREFERRED = "PREFERRED"
    NEUTRAL = "NEUTRAL"
    AVOID = "AVOID"
    IMPOSSIBLE = "IMPOSSIBLE"


@dataclass(frozen=True)
class SchedulerQualityPolicy:
    standard_block_minutes: int
    version: str = QUALITY_POLICY_VERSION

    @classmethod
    def from_durations(cls, durations: Iterable[int]) -> SchedulerQualityPolicy:
        ordered = sorted(int(value) for value in durations if int(value) > 0)
        if not ordered:
            raise ValueError("At least one positive timeslot duration is required.")
        return cls(standard_block_minutes=ordered[(len(ordered) - 1) // 2])

    @property
    def healthy_class_daily_minutes(self) -> int:
        return 4 * self.standard_block_minutes

    @property
    def healthy_teacher_daily_minutes(self) -> int:
        return 4 * self.standard_block_minutes

    @property
    def healthy_consecutive_minutes(self) -> int:
        return 3 * self.standard_block_minutes

    @property
    def healthy_recovery_daily_minutes(self) -> int:
        return 2 * self.standard_block_minutes


@dataclass(frozen=True)
class QualitySlot:
    id: int
    day_of_week: int
    start_minute: int
    end_minute: int

    @property
    def duration_minutes(self) -> int:
        return self.end_minute - self.start_minute


@dataclass(frozen=True)
class QualityBlock:
    class_id: int
    subject_id: int
    teacher_id: int
    room_id: int
    output_date: date
    timeslot_id: int
    duration_minutes: int
    availability_tier: AvailabilityTier | str | int = AvailabilityTier.NEUTRAL
    is_recovery_block: bool = False


@dataclass(frozen=True)
class ScheduleQualityMetrics:
    quality_policy_version: str
    workload_cost_minutes: int = 0
    class_completion_spread_days: int = 0
    class_high_load_days: int = 0
    teacher_high_load_days: int = 0
    class_gap_minutes: int = 0
    teacher_gap_minutes: int = 0
    availability_disutility_minutes: int = 0
    consecutive_excess_minutes: int = 0
    recovery_stack_excess_minutes: int = 0
    late_slot_minutes: int = 0
    repeated_heavy_penalty_minutes: int = 0
    class_daily_excess_minutes: int = 0
    teacher_daily_excess_minutes: int = 0
    room_inconsistency_count: int = 0
    minimum_class_progress_per_mille: int = 0
    class_progress_spread_per_mille: int = 0
    class_progress_per_mille: Mapping[int, int] = field(default_factory=dict)

    @property
    def gap_and_availability_cost_minutes(self) -> int:
        return (
            self.class_gap_minutes + self.teacher_gap_minutes + self.availability_disutility_minutes
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            key: value for key, value in self.__dict__.items() if key != "class_progress_per_mille"
        } | {"class_progress_per_mille": dict(self.class_progress_per_mille)}


class ScheduleQualityEvaluator:
    def __init__(
        self,
        policy: SchedulerQualityPolicy,
        slots: Sequence[QualitySlot],
        lunch_rule: Mapping[str, Any] | None = None,
    ):
        self.policy = policy
        self.slots = tuple(
            sorted(slots, key=lambda row: (row.day_of_week, row.start_minute, row.id))
        )
        self.slots_by_id = {row.id: row for row in self.slots}
        self.slots_by_day: dict[int, tuple[QualitySlot, ...]] = {
            weekday: tuple(row for row in self.slots if row.day_of_week == weekday)
            for weekday in range(7)
        }
        self.lunch_rule = lunch_rule

    def evaluate(
        self,
        blocks: Iterable[QualityBlock],
        *,
        required_minutes_by_class: Mapping[int, int] | None = None,
    ) -> ScheduleQualityMetrics:
        ordered = tuple(sorted(blocks, key=self._block_order))
        class_daily = self._daily(ordered, "class_id")
        teacher_daily = self._daily(ordered, "teacher_id")
        class_excess = sum(
            max(0, value - self.policy.healthy_class_daily_minutes)
            for value in class_daily.values()
        )
        teacher_excess = sum(
            max(0, value - self.policy.healthy_teacher_daily_minutes)
            for value in teacher_daily.values()
        )
        class_heavy = {
            key
            for key, value in class_daily.items()
            if value > self.policy.healthy_class_daily_minutes
        }
        teacher_heavy = {
            key
            for key, value in teacher_daily.items()
            if value > self.policy.healthy_teacher_daily_minutes
        }
        repeated_heavy_count = self._repeated_heavy(class_heavy) + self._repeated_heavy(
            teacher_heavy
        )
        repeated_heavy_penalty = repeated_heavy_count * self.policy.standard_block_minutes
        consecutive = self._consecutive_excess(ordered, "class_id") + self._consecutive_excess(
            ordered, "teacher_id"
        )
        late = sum(block.duration_minutes for block in ordered if self._is_late(block))
        recovery_daily: dict[tuple[int, date], int] = defaultdict(int)
        for block in ordered:
            if block.is_recovery_block:
                recovery_daily[(block.class_id, block.output_date)] += block.duration_minutes
        recovery_stack = sum(
            max(0, value - self.policy.healthy_recovery_daily_minutes)
            for value in recovery_daily.values()
        )
        class_gaps = self._gap_minutes(ordered, "class_id")
        teacher_gaps = self._gap_minutes(ordered, "teacher_id")
        availability = sum(
            self._availability_multiplier(block.availability_tier) * block.duration_minutes
            for block in ordered
        )
        rooms: dict[tuple[int, int], set[int]] = defaultdict(set)
        for block in ordered:
            rooms[(block.class_id, block.subject_id)].add(block.room_id)
        room_inconsistency = sum(max(0, len(values) - 1) for values in rooms.values())
        completion_dates: dict[int, date] = {}
        for block in ordered:
            completion_dates[block.class_id] = max(
                completion_dates.get(block.class_id, block.output_date),
                block.output_date,
            )
        completion_spread = (
            (max(completion_dates.values()) - min(completion_dates.values())).days
            if len(completion_dates) > 1
            else 0
        )
        progress: dict[int, int] = {}
        if required_minutes_by_class:
            credited: dict[int, int] = defaultdict(int)
            for block in ordered:
                credited[block.class_id] += block.duration_minutes
            progress = {
                class_id: min(1000, (1000 * credited.get(class_id, 0)) // required)
                for class_id, required in sorted(required_minutes_by_class.items())
                if required > 0
            }
        min_progress = min(progress.values(), default=0)
        progress_spread = max(progress.values(), default=0) - min_progress
        workload = (
            class_excess
            + teacher_excess
            + consecutive
            + late
            + repeated_heavy_penalty
            + recovery_stack
        )
        return ScheduleQualityMetrics(
            quality_policy_version=self.policy.version,
            workload_cost_minutes=workload,
            class_completion_spread_days=completion_spread,
            class_high_load_days=len(class_heavy),
            teacher_high_load_days=len(teacher_heavy),
            class_gap_minutes=class_gaps,
            teacher_gap_minutes=teacher_gaps,
            availability_disutility_minutes=availability,
            consecutive_excess_minutes=consecutive,
            recovery_stack_excess_minutes=recovery_stack,
            late_slot_minutes=late,
            repeated_heavy_penalty_minutes=repeated_heavy_penalty,
            class_daily_excess_minutes=class_excess,
            teacher_daily_excess_minutes=teacher_excess,
            room_inconsistency_count=room_inconsistency,
            minimum_class_progress_per_mille=min_progress,
            class_progress_spread_per_mille=progress_spread,
            class_progress_per_mille=progress,
        )

    @staticmethod
    def _daily(blocks: Sequence[QualityBlock], attribute: str) -> dict[tuple[int, date], int]:
        result: dict[tuple[int, date], int] = defaultdict(int)
        for block in blocks:
            result[(getattr(block, attribute), block.output_date)] += block.duration_minutes
        return result

    @staticmethod
    def _repeated_heavy(keys: set[tuple[int, date]]) -> int:
        weekly: dict[tuple[int, int, int], int] = defaultdict(int)
        for resource_id, output_date in keys:
            iso_year, iso_week, _ = output_date.isocalendar()
            weekly[(resource_id, iso_year, iso_week)] += 1
        return sum(max(0, count - 2) for count in weekly.values())

    def _consecutive_excess(self, blocks: Sequence[QualityBlock], attribute: str) -> int:
        grouped: dict[tuple[int, date], list[QualityBlock]] = defaultdict(list)
        for block in blocks:
            grouped[(getattr(block, attribute), block.output_date)].append(block)
        excess = 0
        for rows in grouped.values():
            run = 0
            previous_end: int | None = None
            for block in sorted(rows, key=self._block_order):
                slot = self.slots_by_id.get(block.timeslot_id)
                if slot is None:
                    continue
                if previous_end != slot.start_minute:
                    run = 0
                before = max(0, run - self.policy.healthy_consecutive_minutes)
                run += block.duration_minutes
                excess += max(0, run - self.policy.healthy_consecutive_minutes) - before
                previous_end = slot.end_minute
        return excess

    def _is_late(self, block: QualityBlock) -> bool:
        slots = self.slots_by_day.get(block.output_date.weekday(), ())
        return len(slots) >= 3 and slots[-1].id == block.timeslot_id

    def _gap_minutes(self, blocks: Sequence[QualityBlock], attribute: str) -> int:
        occupied: dict[tuple[int, date], set[int]] = defaultdict(set)
        for block in blocks:
            occupied[(getattr(block, attribute), block.output_date)].add(block.timeslot_id)
        total = 0
        for (_resource_id, output_date), occupied_ids in occupied.items():
            slots = self.slots_by_day.get(output_date.weekday(), ())
            indexes = [index for index, slot in enumerate(slots) if slot.id in occupied_ids]
            if len(indexes) < 2:
                continue
            internal = [
                slot
                for index, slot in enumerate(slots)
                if min(indexes) < index < max(indexes) and slot.id not in occupied_ids
            ]
            gap = sum(slot.duration_minutes for slot in internal)
            if gap and self.lunch_rule:
                lunch_start = self._minute(self.lunch_rule.get("window_start"))
                lunch_end = self._minute(self.lunch_rule.get("window_end"))
                lunch_gap = sum(
                    max(0, min(slot.end_minute, lunch_end) - max(slot.start_minute, lunch_start))
                    for slot in internal
                )
                gap -= min(lunch_gap, int(self.lunch_rule.get("minimum_minutes") or 0))
            total += max(0, gap)
        return total

    @staticmethod
    def _availability_multiplier(value: AvailabilityTier | str | int) -> int:
        if isinstance(value, int):
            return {2: 0, 1: 1, 0: 2, -1: 10_000}.get(value, 1)
        tier = AvailabilityTier(str(getattr(value, "value", value)).upper())
        return {
            AvailabilityTier.PREFERRED: 0,
            AvailabilityTier.NEUTRAL: 1,
            AvailabilityTier.AVOID: 2,
            AvailabilityTier.IMPOSSIBLE: 10_000,
        }[tier]

    @staticmethod
    def _minute(value: str | time | None) -> int:
        if value is None:
            return 0
        parsed = value if isinstance(value, time) else time.fromisoformat(value)
        return parsed.hour * 60 + parsed.minute

    def _block_order(self, block: QualityBlock) -> tuple[Any, ...]:
        slot = self.slots_by_id.get(block.timeslot_id)
        return (
            block.output_date,
            0 if slot is None else slot.start_minute,
            block.class_id,
            block.teacher_id,
            block.subject_id,
            block.room_id,
            block.timeslot_id,
        )


class IncrementalQualityState:
    def __init__(
        self,
        evaluator: ScheduleQualityEvaluator,
        blocks: Iterable[QualityBlock] = (),
    ):
        self.evaluator = evaluator
        self._blocks = list(blocks)

    @property
    def metrics(self) -> ScheduleQualityMetrics:
        return self.evaluator.evaluate(self._blocks)

    def incremental_vector(self, block: QualityBlock) -> tuple[int, int, int]:
        before = self.metrics
        after = self.evaluator.evaluate((*self._blocks, block))
        return (
            after.workload_cost_minutes - before.workload_cost_minutes,
            after.gap_and_availability_cost_minutes - before.gap_and_availability_cost_minutes,
            after.room_inconsistency_count - before.room_inconsistency_count,
        )

    def add(self, block: QualityBlock) -> None:
        self._blocks.append(block)


def quality_policy_from_snapshot(snapshot: Mapping[str, Any]) -> SchedulerQualityPolicy:
    durations = []
    for row in snapshot.get("timetable_grid", []):
        start = ScheduleQualityEvaluator._minute(row["start_time"])
        end = ScheduleQualityEvaluator._minute(row["end_time"])
        if end > start:
            durations.append(end - start)
    return SchedulerQualityPolicy.from_durations(durations or (60,))


def quality_slots_from_snapshot(snapshot: Mapping[str, Any]) -> tuple[QualitySlot, ...]:
    return tuple(
        QualitySlot(
            id=row["id"],
            day_of_week=row["day_of_week"],
            start_minute=ScheduleQualityEvaluator._minute(row["start_time"]),
            end_minute=ScheduleQualityEvaluator._minute(row["end_time"]),
        )
        for row in snapshot.get("timetable_grid", [])
    )
