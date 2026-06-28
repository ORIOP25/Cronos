from __future__ import annotations

from collections import defaultdict
from datetime import date, time, timedelta
from typing import Any

from app import models
from app.services.scheduler_job_runtime import (
    DraftBlockSpec,
    GenerationValidationError,
    SchedulerJobRuntime,
)


class SchedulerTargetValidationError(RuntimeError):
    pass


class SchedulerTargetValidator:
    @classmethod
    def validate(
        cls,
        snapshot: dict[str, Any],
        specs: tuple[DraftBlockSpec, ...],
        *,
        complete: bool,
    ) -> None:
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
        intervals: dict[tuple[str, int, date], list[tuple[int, int]]] = defaultdict(list)
        stable_keys: set[str] = set()
        school_start = date.fromisoformat(snapshot["start_date"])
        hard_end = date.fromisoformat(snapshot["hard_end_date"])
        for block in specs:
            slot = grid.get(block.timeslot_id)
            class_row = classes.get(block.class_id)
            subject_row = subjects.get(block.subject_id)
            room_row = rooms.get(block.room_id)
            if (
                slot is None
                or slot[0] != block.date.weekday()
                or block.date < school_start
                or block.date > hard_end
                or block.duration_minutes <= 0
                or block.duration_minutes > slot[2] - slot[1]
                or block.date in blocked
                or block.stable_block_key in stable_keys
                or class_row is None
                or subject_row is None
                or room_row is None
                or assignments.get((block.class_id, block.subject_id)) != block.teacher_id
                or (qualifications and (block.teacher_id, block.subject_id) not in qualifications)
                or int(room_row.get("capacity") or 0) < int(class_row["size"])
                or cls._value(room_row.get("type"))
                != cls._value(subject_row.get("required_room_type"))
                or (block.teacher_id, block.timeslot_id) in impossible
                or block.is_recovery_block
                != (
                    block.recovery_source_occurrence_id is not None
                    and block.recovery_source_occurrence_revision is not None
                )
            ):
                raise SchedulerTargetValidationError(
                    "The draft target no longer satisfies hard scheduler constraints."
                )
            stable_keys.add(block.stable_block_key)
            cls._add_resource_intervals(block, slot, intervals)
        cls._validate_lunch(snapshot.get("lunch_rules"), specs, grid)
        if complete:
            cls._validate_complete(snapshot, specs)

    @staticmethod
    def _add_resource_intervals(block, slot, intervals) -> None:
        for kind, resource_id in (
            ("class", block.class_id),
            ("teacher", block.teacher_id),
            ("room", block.room_id),
        ):
            key = (kind, resource_id, block.date)
            if any(slot[1] < end and slot[2] > start for start, end in intervals[key]):
                raise SchedulerTargetValidationError(
                    "The draft target contains a resource conflict."
                )
            intervals[key].append((slot[1], slot[2]))

    @staticmethod
    def _validate_complete(snapshot, specs) -> None:
        if any(
            block.change_type != models.ScheduleDraftBlockChangeType.ADDED
            or block.source_active_block_id is not None
            or block.is_recovery_block
            for block in specs
        ):
            raise SchedulerTargetValidationError(
                "A complete first schedule contains repair-only target semantics."
            )
        try:
            SchedulerJobRuntime._validate_complete_demand(snapshot, specs)
        except GenerationValidationError as exc:
            raise SchedulerTargetValidationError(str(exc)) from exc

    @classmethod
    def _validate_lunch(cls, rule, specs, grid) -> None:
        if not rule or not rule.get("window_start") or not rule.get("window_end"):
            return
        lunch_start = cls._minute(rule["window_start"])
        lunch_end = cls._minute(rule["window_end"])
        minimum = int(rule.get("minimum_minutes") or 0)
        grouped: dict[tuple[str, int, date], list[tuple[int, int]]] = defaultdict(list)
        for block in specs:
            slot = grid[block.timeslot_id]
            grouped[("class", block.class_id, block.date)].append((slot[1], slot[2]))
            grouped[("teacher", block.teacher_id, block.date)].append((slot[1], slot[2]))
        for rows in grouped.values():
            clipped = sorted(
                (max(start, lunch_start), min(end, lunch_end))
                for start, end in rows
                if start < lunch_end and end > lunch_start
            )
            cursor = lunch_start
            gaps = []
            for start, end in clipped:
                gaps.append(start - cursor)
                cursor = max(cursor, end)
            gaps.append(lunch_end - cursor)
            if max(gaps, default=0) < minimum:
                raise SchedulerTargetValidationError(
                    "The draft target does not preserve the required lunch break."
                )

    @staticmethod
    def _blocked_dates(rows):
        blocked = set()
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
