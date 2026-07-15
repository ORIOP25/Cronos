from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, time
from enum import StrEnum
from typing import Any, Iterable, Mapping, Sequence


QUALITY_POLICY_VERSION = "baseline-v1"


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
            self.class_gap_minutes
            + self.teacher_gap_minutes
            + self.availability_disutility_minutes
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in self.__dict__.items()
            if key != "class_progress_per_mille"
        } | {"class_progress_per_mille": dict(self.class_progress_per_mille)}


class ScheduleQualityEvaluator:
    def __init__(
        self,
        policy: SchedulerQualityPolicy,
        slots: Sequence[QualitySlot],
        lunch_rule: Mapping[str, Any] | None = None,
    ):
        self.policy = policy
        self.slots = tuple(sorted(slots, key=lambda row: (row.day_of_week, row.start_minute, row.id)))
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
        class_excess = sum(max(0, value - self.policy.healthy_class_daily_minutes) for value in class_daily.values())
        teacher_excess = sum(max(0, value - self.policy.healthy_teacher_daily_minutes) for value in teacher_daily.values())
        class_heavy = {key for key, value in class_daily.items() if value > self.policy.healthy_class_daily_minutes}
        teacher_heavy = {key for key, value in teacher_daily.items() if value > self.policy.healthy_teacher_daily_minutes}
        repeated_heavy_count = self._repeated_heavy(class_heavy) + self._repeated_heavy(teacher_heavy)
        repeated_heavy_penalty = repeated_heavy_count * self.policy.standard_block_minutes
        consecutive = self._consecutive_excess(ordered, "class_id") + self._consecutive_excess(ordered, "teacher_id")
        late = sum(
            block.duration_minutes
            for block in ordered
            if self._is_late(block)
        )
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
