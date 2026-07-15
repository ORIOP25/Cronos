from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time, timedelta
from enum import StrEnum
from typing import Any, Iterable, Mapping

from app.scheduler.domain.constraints import SchedulerConstraintPolicy, placement_facts


class TargetViolationCode(StrEnum):
    GENERATION_ENVELOPE_INVALID = "GENERATION_ENVELOPE_INVALID"
    CONSTRAINT_CONFIGURATION_INVALID = "CONSTRAINT_CONFIGURATION_INVALID"
    HARD_CONSTRAINT_VIOLATION = "HARD_CONSTRAINT_VIOLATION"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    CUSTOM_CONSTRAINT_VIOLATION = "CUSTOM_CONSTRAINT_VIOLATION"
    LUNCH_BREAK_VIOLATION = "LUNCH_BREAK_VIOLATION"


@dataclass(frozen=True)
class TargetViolation:
    code: TargetViolationCode
    message: str
    resource_type: str | None = None
    resource_id: int | None = None
    output_date: date | None = None


class GenerationEnvelopeValidator:
    @staticmethod
    def validate(
        strategy: Any,
        result: Any,
        expected_hard_end: date,
    ) -> tuple[TargetViolation, ...]:
        strategy_value = str(getattr(strategy, "value", strategy))
        category_value = str(getattr(result.result_category, "value", result.result_category))
        messages: list[str] = []
        if strategy_value == "COMPLETE_GENERATION" and category_value != "COMPLETE_SUCCESS":
            messages.append("Complete Generation must produce a complete-success draft.")
        if not result.blocks:
            messages.append("A validated draft must contain schedule blocks.")
        if result.projected_completion_date > result.hard_end_date:
            messages.append("Projected completion exceeds the hard end date.")
        if result.hard_end_date != expected_hard_end:
            messages.append("Result hard end date differs from its snapshot.")
        return tuple(
            TargetViolation(TargetViolationCode.GENERATION_ENVELOPE_INVALID, message)
            for message in messages
        )


class TargetHardConstraintValidator:
    @classmethod
    def validate(
        cls,
        snapshot: Mapping[str, Any],
        specs: Iterable[Any],
    ) -> tuple[TargetViolation, ...]:
        blocks = tuple(specs)
        grid = {
            row["id"]: (
                row["day_of_week"],
                cls._minute(row["start_time"]),
                cls._minute(row["end_time"]),
            )
            for row in snapshot.get("timetable_grid", [])
        }
        blocked = cls._blocked_dates(snapshot.get("calendar_events", []))
        assignments = {
            (row["class_id"], row["subject_id"]): row.get("teacher_id")
            for row in snapshot.get("class_subject_requirements", [])
        }
        classes = {row["id"]: row for row in snapshot.get("classes", [])}
        subjects = {row["id"]: row for row in snapshot.get("subjects", [])}
        rooms = {row["id"]: row for row in snapshot.get("rooms", [])}
        qualifications = {
            (row["teacher_id"], row["subject_id"])
            for row in snapshot.get("teacher_subject_eligibility", [])
        }
        impossible = {
            (row["teacher_id"], row["timeslot_id"])
            for row in snapshot.get("teacher_availability", [])
            if int(row.get("score", 0)) == -1
        }
        parsed_policy = SchedulerConstraintPolicy.from_snapshot(snapshot)
        if parsed_policy.configuration_violations:
            return tuple(
                TargetViolation(TargetViolationCode.CONSTRAINT_CONFIGURATION_INVALID, row.message)
                for row in parsed_policy.configuration_violations
            )
        policy = parsed_policy.policy or SchedulerConstraintPolicy()
        school_start = date.fromisoformat(snapshot["start_date"])
        hard_end = date.fromisoformat(snapshot["hard_end_date"])
        intervals: dict[tuple[str, int, date], list[tuple[int, int]]] = defaultdict(list)
        stable_keys: set[str] = set()
        violations: list[TargetViolation] = []

        for block in blocks:
            slot = grid.get(block.timeslot_id)
            class_row = classes.get(block.class_id)
            subject_row = subjects.get(block.subject_id)
            room_row = rooms.get(block.room_id)
            invalid = (
                slot is None
                or (slot is not None and slot[0] != block.date.weekday())
                or block.date < school_start
                or block.date > hard_end
                or block.duration_minutes <= 0
                or (slot is not None and block.duration_minutes > slot[2] - slot[1])
                or block.date in blocked
                or not block.stable_block_key.strip()
                or block.stable_block_key in stable_keys
                or class_row is None
                or subject_row is None
                or room_row is None
                or assignments.get((block.class_id, block.subject_id)) != block.teacher_id
                or (block.teacher_id, block.subject_id) not in qualifications
                or (
                    class_row is not None
                    and room_row is not None
                    and int(room_row.get("capacity") or 0) < int(class_row["size"])
                )
                or (
                    subject_row is not None
                    and room_row is not None
                    and cls._value(room_row.get("type"))
                    != cls._value(subject_row.get("required_room_type"))
                )
                or (block.teacher_id, block.timeslot_id) in impossible
                or block.is_recovery_block
                != (
                    block.recovery_source_occurrence_id is not None
                    and block.recovery_source_occurrence_revision is not None
                )
            )
            if invalid:
                violations.append(TargetViolation(
                    TargetViolationCode.HARD_CONSTRAINT_VIOLATION,
                    "The draft target no longer satisfies hard scheduler constraints.",
                ))
                continue
            stable_keys.add(block.stable_block_key)
            evaluation = policy.evaluate(placement_facts(block))
            violations.extend(
                TargetViolation(
                    TargetViolationCode.CUSTOM_CONSTRAINT_VIOLATION,
                    row.message,
                )
                for row in evaluation.hard_violations
            )
            for kind, resource_id in (
                ("class", block.class_id),
                ("teacher", block.teacher_id),
                ("room", block.room_id),
            ):
                key = (kind, resource_id, block.date)
                if any(slot[1] < end and slot[2] > start for start, end in intervals[key]):
                    violations.append(TargetViolation(
                        TargetViolationCode.RESOURCE_CONFLICT,
                        "The draft target contains a resource conflict.",
                        kind,
                        resource_id,
                        block.date,
                    ))
                intervals[key].append((slot[1], slot[2]))

        violations.extend(LunchBreakValidator.validate(
            snapshot.get("lunch_rules"),
            blocks,
            grid,
        ))
        return tuple(violations)

    @staticmethod
    def _blocked_dates(rows: Iterable[Mapping[str, Any]]) -> set[date]:
        blocked: set[date] = set()
        for row in rows:
            current = date.fromisoformat(row["start_date"])
            end = date.fromisoformat(row["end_date"])
            while current <= end:
                blocked.add(current)
                current += timedelta(days=1)
        return blocked

    @staticmethod
    def _minute(value: str | time) -> int:
        parsed = value if isinstance(value, time) else time.fromisoformat(value)
        return parsed.hour * 60 + parsed.minute

    @staticmethod
    def _value(value: Any) -> str:
        return str(getattr(value, "value", value))


class LunchBreakValidator:
    @classmethod
    def validate(
        cls,
        rule: Mapping[str, Any] | None,
        specs: Iterable[Any],
        grid: Mapping[int, tuple[int, int, int]],
    ) -> tuple[TargetViolation, ...]:
        if not rule or not rule.get("window_start") or not rule.get("window_end"):
            return ()
        lunch_start = TargetHardConstraintValidator._minute(rule["window_start"])
        lunch_end = TargetHardConstraintValidator._minute(rule["window_end"])
        minimum = int(rule.get("minimum_minutes") or 0)
        grouped: dict[tuple[str, int, date], list[tuple[int, int]]] = defaultdict(list)
        for block in specs:
            slot = grid.get(block.timeslot_id)
            if slot is None:
                continue
            grouped[("class", block.class_id, block.date)].append((slot[1], slot[2]))
            grouped[("teacher", block.teacher_id, block.date)].append((slot[1], slot[2]))
        violations: list[TargetViolation] = []
        for (kind, resource_id, output_date), rows in sorted(grouped.items()):
            clipped = sorted(
                (max(start, lunch_start), min(end, lunch_end))
                for start, end in rows
                if start < lunch_end and end > lunch_start
            )
            merged: list[tuple[int, int]] = []
            for start, end in clipped:
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            cursor = lunch_start
            gaps: list[int] = []
            for start, end in merged:
                gaps.append(max(0, start - cursor))
                cursor = max(cursor, end)
            gaps.append(max(0, lunch_end - cursor))
            if max(gaps, default=0) < minimum:
                violations.append(TargetViolation(
                    TargetViolationCode.LUNCH_BREAK_VIOLATION,
                    "The draft target does not preserve the required lunch break.",
                    kind,
                    resource_id,
                    output_date,
                ))
        return tuple(violations)
