"""V1 school constraint policy: specific rooms and teacher (un)availability.

Pure domain parsing of the persisted constraint rules that the v1 snapshot can
honour. Rules the v1 intersection does not support (lock_time, min_gap,
max_days) are configuration violations, not silent omissions.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class ConfigurationViolationCode(StrEnum):
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
    UNKNOWN_TYPE = "UNKNOWN_TYPE"


@dataclass(frozen=True)
class ConfigurationViolation:
    code: ConfigurationViolationCode
    message: str
    constraint_id: int | None = None
    rule_type: str | None = None


@dataclass(frozen=True)
class PolicyParseResult:
    policy: SchoolConstraintPolicy | None
    configuration_violations: tuple[ConfigurationViolation, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.policy is not None and not self.configuration_violations


@dataclass(frozen=True)
class SchoolConstraintPolicy:
    """Normalized custom scheduler policy with no infrastructure dependencies."""

    specific_rooms: Mapping[tuple[int, int], frozenset[int]] = field(default_factory=dict)
    teacher_unavailable_timeslots: frozenset[tuple[int, int]] = frozenset()
    teacher_unavailable_days: frozenset[tuple[int, int]] = frozenset()
    teacher_unavailable_dates: frozenset[tuple[int, date]] = frozenset()
    teacher_unavailable_date_slots: frozenset[tuple[int, date, int]] = frozenset()
    teacher_preferred_timeslots: frozenset[tuple[int, int]] = frozenset()

    @classmethod
    def parse(cls, rows: Iterable[Mapping[str, Any] | Any]) -> PolicyParseResult:
        room_rules: dict[tuple[int, int], set[int]] = {}
        unavailable_slots: set[tuple[int, int]] = set()
        unavailable_days: set[tuple[int, int]] = set()
        unavailable_dates: set[tuple[int, date]] = set()
        unavailable_date_slots: set[tuple[int, date, int]] = set()
        preferred_slots: set[tuple[int, int]] = set()
        violations: list[ConfigurationViolation] = []

        for raw_row in rows:
            row = _mapping(raw_row)
            rule_type = _value(row.get("rule_type"))
            constraint_id = _strict_int(row.get("id"), positive=True)
            payload = row.get("rule_payload")
            if not isinstance(payload, Mapping):
                violations.append(
                    _configuration(
                        ConfigurationViolationCode.INVALID_PAYLOAD,
                        f"Constraint {rule_type} has an invalid payload.",
                        constraint_id,
                        rule_type,
                    )
                )
                continue

            if rule_type == "specific_room":
                class_id = _legacy_int(payload, "class_id")
                subject_id = _legacy_int(payload, "subject_id")
                room_id = _legacy_int(payload, "room_id", "specific_room_id")
                valid_keys = set(payload) in (
                    {"class_id", "subject_id", "room_id"},
                    {"class_id", "subject_id", "specific_room_id"},
                )
                if None in (class_id, subject_id, room_id) or not valid_keys:
                    violations.append(
                        _configuration(
                            ConfigurationViolationCode.INVALID_PAYLOAD,
                            "specific_room constraint requires class_id, subject_id, and room_id.",
                            constraint_id,
                            rule_type,
                        )
                    )
                else:
                    room_rules.setdefault((class_id, subject_id), set()).add(room_id)
                continue

            if rule_type == "teacher_preferred":
                teacher_id = _legacy_int(payload, "teacher_id")
                timeslot_id = _legacy_int(payload, "timeslot_id")
                if None in (teacher_id, timeslot_id) or set(payload) != {
                    "teacher_id",
                    "timeslot_id",
                }:
                    violations.append(
                        _configuration(
                            ConfigurationViolationCode.INVALID_PAYLOAD,
                            "teacher_preferred constraint requires teacher_id and timeslot_id.",
                            constraint_id,
                            rule_type,
                        )
                    )
                else:
                    preferred_slots.add((teacher_id, timeslot_id))
                continue

            if rule_type == "teacher_unavailable":
                teacher_id = _legacy_int(payload, "teacher_id")
                timeslot_id = _legacy_int(payload, "timeslot_id")
                weekday = _legacy_int(payload, "day_of_week", "weekday", positive=False)
                blocked_date = _legacy_date(payload, "date", "output_date")
                normalized_keys = {
                    "day_of_week" if key == "weekday" else "date" if key == "output_date" else key
                    for key in payload
                }
                selector_keys = normalized_keys - {"teacher_id"}
                selector_count = int(
                    selector_keys
                    in (
                        {"timeslot_id"},
                        {"day_of_week"},
                        {"date"},
                        {"date", "timeslot_id"},
                    )
                )
                selector_values_valid = (
                    ("date" not in selector_keys or blocked_date is not None)
                    and ("timeslot_id" not in selector_keys or timeslot_id is not None)
                    and ("day_of_week" not in selector_keys or weekday is not None)
                )
                if (
                    teacher_id is None
                    or selector_count != 1
                    or not selector_values_valid
                    or (weekday is not None and weekday not in range(7))
                ):
                    violations.append(
                        _configuration(
                            ConfigurationViolationCode.INVALID_PAYLOAD,
                            "teacher_unavailable constraint requires teacher_id and exactly one "
                            "valid selector.",
                            constraint_id,
                            rule_type,
                        )
                    )
                elif blocked_date is not None and timeslot_id is not None:
                    unavailable_date_slots.add((teacher_id, blocked_date, timeslot_id))
                elif blocked_date is not None:
                    unavailable_dates.add((teacher_id, blocked_date))
                elif timeslot_id is not None:
                    unavailable_slots.add((teacher_id, timeslot_id))
                else:
                    unavailable_days.add((teacher_id, weekday))
                continue

            code = (
                ConfigurationViolationCode.UNSUPPORTED_TYPE
                if rule_type in {"lock_time", "min_gap", "max_days"}
                else ConfigurationViolationCode.UNKNOWN_TYPE
            )
            message = (
                f"{rule_type} constraints are not supported by the current generator."
                if code is ConfigurationViolationCode.UNSUPPORTED_TYPE
                else f"Unknown scheduler constraint type: {rule_type}."
            )
            violations.append(_configuration(code, message, constraint_id, rule_type))

        if violations:
            return PolicyParseResult(
                policy=None,
                configuration_violations=tuple(_deduplicate(violations)),
            )
        return PolicyParseResult(
            policy=cls(
                specific_rooms={key: frozenset(values) for key, values in room_rules.items()},
                teacher_unavailable_timeslots=frozenset(unavailable_slots),
                teacher_unavailable_days=frozenset(unavailable_days),
                teacher_unavailable_dates=frozenset(unavailable_dates),
                teacher_unavailable_date_slots=frozenset(unavailable_date_slots),
                teacher_preferred_timeslots=frozenset(preferred_slots),
            )
        )

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any]) -> PolicyParseResult:
        return cls.parse(snapshot.get("constraints", ()))


class RoomEligibilityReason(StrEnum):
    NO_ROOM_OF_TYPE = "NO_ROOM_OF_TYPE"
    INSUFFICIENT_CAPACITY = "INSUFFICIENT_CAPACITY"
    SPECIFIC_ROOM_RESTRICTION = "SPECIFIC_ROOM_RESTRICTION"


@dataclass(frozen=True)
class RoomEligibility:
    """Which rooms of the required type can host a class of the given size."""

    eligible_room_ids: frozenset[int]
    max_available_capacity: int | None
    reason: RoomEligibilityReason | None


def assess_room_eligibility(
    rooms: Sequence[tuple[int, Any, int]],
    *,
    required_room_type: Any,
    required_capacity: int,
    allowed_room_ids: Iterable[int] | None = None,
) -> RoomEligibility:
    """Classify room compatibility for one class/subject pair.

    ``rooms`` holds ``(id, type, capacity)`` values loaded by infrastructure.
    ``allowed_room_ids=None`` means no ``specific_room`` restriction; an empty
    set still blocks every assignment.
    """
    required = _value(required_room_type)
    of_type = [
        (room_id, capacity)
        for room_id, room_type, capacity in rooms
        if _value(room_type) == required
    ]
    if not of_type:
        return RoomEligibility(frozenset(), None, RoomEligibilityReason.NO_ROOM_OF_TYPE)

    max_capacity = max(capacity for _room_id, capacity in of_type)
    by_capacity = frozenset(
        room_id for room_id, capacity in of_type if capacity >= required_capacity
    )
    if not by_capacity:
        return RoomEligibility(
            frozenset(), max_capacity, RoomEligibilityReason.INSUFFICIENT_CAPACITY
        )

    eligible = (
        by_capacity if allowed_room_ids is None else by_capacity & frozenset(allowed_room_ids)
    )
    if not eligible:
        return RoomEligibility(
            frozenset(), max_capacity, RoomEligibilityReason.SPECIFIC_ROOM_RESTRICTION
        )
    return RoomEligibility(eligible, max_capacity, None)


def _mapping(value: Mapping[str, Any] | Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {
        "id": getattr(value, "id", None),
        "rule_type": getattr(value, "rule_type", None),
        "rule_payload": getattr(value, "rule_payload", None),
    }


def _legacy_int(payload: Mapping[str, Any], *keys: str, positive: bool = True) -> int | None:
    for key in keys:
        if key in payload:
            return _strict_int(payload[key], positive=positive)
    return None


def _strict_int(value: Any, *, positive: bool) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if positive and value <= 0:
        return None
    return value


def _legacy_date(payload: Mapping[str, Any], *keys: str) -> date | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, datetime):
            return None
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _configuration(code, message, constraint_id, rule_type) -> ConfigurationViolation:
    return ConfigurationViolation(code, message, constraint_id, rule_type)


def _deduplicate(rows: list[ConfigurationViolation]) -> list[ConfigurationViolation]:
    result: list[ConfigurationViolation] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = (row.code, row.message, row.constraint_id, row.rule_type)
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result
