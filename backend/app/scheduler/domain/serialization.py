"""Canonical JSON serialization of immutable domain values.

The lab manifests and the production lifecycle both need to store and digest
the same values, so the encoding lives in the domain layer and works without
database, solver or environment access.
"""

from __future__ import annotations

import enum
import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from app.scheduler.domain.calendar import Period, normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    LunchRule,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.debt import RecoveryAllocation
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice


def time_token(value: time) -> str:
    return value.strftime("%H:%M")


class SchedulerSerializationError(ValueError):
    pass


def canonical_json_value(value: Any) -> Any:
    """Normalize a value into plain JSON types with a deterministic ordering."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise SchedulerSerializationError("Scheduler snapshots require finite numbers.")
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, enum.Enum):
        return canonical_json_value(value.value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): canonical_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [canonical_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((canonical_json_value(item) for item in value), key=canonical_json)
    raise SchedulerSerializationError(
        f"Unsupported scheduler snapshot value: {type(value).__name__}."
    )


def canonical_json(payload: Any) -> str:
    return json.dumps(
        canonical_json_value(payload),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def payload_digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def period_to_dict(period: Period) -> list[str]:
    return [
        period.school_date.isoformat(),
        time_token(period.start_local),
        time_token(period.end_local),
        period.timezone_name,
    ]


def period_from_dict(data: list[Any]) -> Period:
    return normalize_period(
        date.fromisoformat(data[0]),
        time.fromisoformat(data[1]),
        time.fromisoformat(data[2]),
        data[3],
    )


def lesson_to_dict(lesson: ScheduledLesson) -> list[Any]:
    return [
        lesson.lesson_id,
        lesson.assignment_id,
        period_to_dict(lesson.period),
        lesson.room_id,
        lesson.credit_minutes,
        sorted([row.module_id, row.offset_minutes, row.credit_minutes] for row in lesson.slices),
        lesson.source_lesson_id,
        lesson.teacher_id,
        lesson.class_id,
    ]


def lesson_from_dict(data: list[Any]) -> ScheduledLesson:
    return ScheduledLesson(
        lesson_id=data[0],
        assignment_id=data[1],
        period=period_from_dict(data[2]),
        room_id=data[3],
        credit_minutes=data[4],
        slices=tuple(ModuleSlice(data[0], row[0], row[1], row[2]) for row in data[5]),
        source_lesson_id=data[6],
        teacher_id=data[7],
        class_id=data[8],
    )


def candidate_to_dict(candidate: CandidateSchedule) -> dict[str, Any]:
    return {"lessons": [lesson_to_dict(lesson) for lesson in candidate.lessons]}


def candidate_from_dict(data: Mapping[str, Any]) -> CandidateSchedule:
    return CandidateSchedule(tuple(lesson_from_dict(row) for row in data["lessons"]))


def candidate_digest(candidate: CandidateSchedule) -> str:
    return payload_digest(candidate_to_dict(candidate))


def _unavailability_to_dict(row: Unavailability) -> list[Any]:
    return [row.resource_type.value, row.resource_id, period_to_dict(row.period)]


def _unavailability_from_dict(data: list[Any]) -> Unavailability:
    return Unavailability(UnavailableResource(data[0]), data[1], period_from_dict(data[2]))


def snapshot_to_dict(snapshot: PlanningSnapshot) -> dict[str, Any]:
    """Complete snapshot payload, sufficient to revalidate a stored candidate."""
    payload: dict[str, Any] = {
        "strategy": snapshot.strategy.value,
        "origin": snapshot.origin.isoformat(),
        "preferred_end_date": snapshot.preferred_end_date.isoformat(),
        "hard_end_date": snapshot.hard_end_date.isoformat(),
        "timezone_name": snapshot.timezone_name,
        "grid_slots": [
            [slot.day_of_week, time_token(slot.start_local), time_token(slot.end_local)]
            for slot in snapshot.grid_slots
        ],
        "assignments": [
            {
                "assignment_id": row.assignment_id,
                "class_id": row.class_id,
                "subject_id": row.subject_id,
                "teacher_id": row.teacher_id,
                "eligible_room_ids": sorted(row.eligible_room_ids),
                "modules": [
                    [module.module_id, module.sequence, module.required_minutes]
                    for module in row.modules
                ],
            }
            for row in snapshot.assignments
        ],
        "executed_minutes": [
            [assignment_id, sorted([module_id, minutes] for module_id, minutes in rows.items())]
            for assignment_id, rows in sorted(snapshot.executed_minutes.items())
        ],
        "blocked_dates": sorted(day.isoformat() for day in snapshot.blocked_dates),
        "unavailable": [_unavailability_to_dict(row) for row in snapshot.unavailable],
        "soft_unavailable": [_unavailability_to_dict(row) for row in snapshot.soft_unavailable],
        "protected_lessons": [lesson_to_dict(row) for row in snapshot.protected_lessons],
        "baseline_lessons": [lesson_to_dict(row) for row in snapshot.baseline_lessons],
        "protected_dates": sorted(day.isoformat() for day in snapshot.protected_dates),
        "now_utc": None if snapshot.now_utc is None else snapshot.now_utc.isoformat(),
        "reservations": [
            [row.version_id, row.lesson_id, row.claim_id, row.minutes]
            for row in snapshot.reservations
        ],
        "open_debt_minutes": sorted(
            [claim_id, minutes] for claim_id, minutes in snapshot.open_debt_minutes.items()
        ),
        "claim_assignments": sorted(
            [claim_id, assignment_id]
            for claim_id, assignment_id in snapshot.claim_assignments.items()
        ),
        "active_version_id": snapshot.active_version_id,
        "lunch_rule": None
        if snapshot.lunch_rule is None
        else [
            time_token(snapshot.lunch_rule.window_start),
            time_token(snapshot.lunch_rule.window_end),
            snapshot.lunch_rule.minimum_minutes,
        ],
    }
    if snapshot.class_blocked_dates:
        payload["class_blocked_dates"] = {
            str(class_id): sorted(day.isoformat() for day in days)
            for class_id, days in sorted(snapshot.class_blocked_dates.items())
        }
    if snapshot.reserved_lesson_ids:
        payload["reserved_lesson_ids"] = sorted(snapshot.reserved_lesson_ids)
    return payload


def snapshot_from_dict(data: Mapping[str, Any]) -> PlanningSnapshot:
    return PlanningSnapshot(
        strategy=SchedulingStrategy(data["strategy"]),
        origin=date.fromisoformat(data["origin"]),
        preferred_end_date=date.fromisoformat(data["preferred_end_date"]),
        hard_end_date=date.fromisoformat(data["hard_end_date"]),
        timezone_name=data["timezone_name"],
        grid_slots=tuple(
            GridSlot(row[0], time.fromisoformat(row[1]), time.fromisoformat(row[2]))
            for row in data["grid_slots"]
        ),
        assignments=tuple(
            Assignment(
                assignment_id=row["assignment_id"],
                class_id=row["class_id"],
                subject_id=row["subject_id"],
                teacher_id=row["teacher_id"],
                eligible_room_ids=frozenset(row["eligible_room_ids"]),
                modules=tuple(
                    ModuleRequirement(module[0], module[1], module[2]) for module in row["modules"]
                ),
            )
            for row in data["assignments"]
        ),
        executed_minutes={
            assignment_id: {module_id: minutes for module_id, minutes in rows}
            for assignment_id, rows in data["executed_minutes"]
        },
        blocked_dates=frozenset(date.fromisoformat(day) for day in data["blocked_dates"]),
        unavailable=tuple(_unavailability_from_dict(row) for row in data["unavailable"]),
        soft_unavailable=tuple(
            _unavailability_from_dict(row) for row in data.get("soft_unavailable", ())
        ),
        protected_lessons=tuple(lesson_from_dict(row) for row in data.get("protected_lessons", ())),
        baseline_lessons=tuple(lesson_from_dict(row) for row in data.get("baseline_lessons", ())),
        protected_dates=frozenset(date.fromisoformat(day) for day in data["protected_dates"]),
        now_utc=None if data.get("now_utc") is None else datetime.fromisoformat(data["now_utc"]),
        reservations=tuple(
            RecoveryAllocation(row[0], row[1], row[2], row[3])
            for row in data.get("reservations", ())
        ),
        open_debt_minutes={
            claim_id: minutes for claim_id, minutes in data.get("open_debt_minutes", ())
        },
        claim_assignments={
            claim_id: assignment_id for claim_id, assignment_id in data.get("claim_assignments", ())
        },
        active_version_id=data.get("active_version_id"),
        reserved_lesson_ids=frozenset(data.get("reserved_lesson_ids", ())),
        lunch_rule=(
            None
            if data.get("lunch_rule") is None
            else LunchRule(
                window_start=time.fromisoformat(data["lunch_rule"][0]),
                window_end=time.fromisoformat(data["lunch_rule"][1]),
                minimum_minutes=data["lunch_rule"][2],
            )
        ),
        class_blocked_dates={
            int(class_id): frozenset(date.fromisoformat(day) for day in days)
            for class_id, days in data.get("class_blocked_dates", {}).items()
        },
    )
