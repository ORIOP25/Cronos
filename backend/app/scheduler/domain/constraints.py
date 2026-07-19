from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class ConstraintViolationCode(StrEnum):
    SPECIFIC_ROOM = "SPECIFIC_ROOM"
    LOCK_TIME = "LOCK_TIME"
    TEACHER_UNAVAILABLE = "TEACHER_UNAVAILABLE"


class RepairDimension(StrEnum):
    RESOURCE = "RESOURCE"
    TIME = "TIME"


class ConfigurationViolationCode(StrEnum):
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
    UNKNOWN_TYPE = "UNKNOWN_TYPE"


@dataclass(frozen=True)
class PlacementFacts:
    class_id: int
    subject_id: int
    teacher_id: int
    room_id: int
    output_date: date
    timeslot_id: int


@dataclass(frozen=True)
class ConstraintViolation:
    code: ConstraintViolationCode
    repair_dimension: RepairDimension
    message: str


@dataclass(frozen=True)
class ConstraintEvaluation:
    hard_violations: tuple[ConstraintViolation, ...] = ()
    preference_tier_adjustment: int = 0

    @property
    def required_repair_dimension(self) -> RepairDimension | None:
        if any(row.repair_dimension is RepairDimension.TIME for row in self.hard_violations):
            return RepairDimension.TIME
        if self.hard_violations:
            return RepairDimension.RESOURCE
        return None


@dataclass(frozen=True)
class ConfigurationViolation:
    code: ConfigurationViolationCode
    message: str
    constraint_id: int | None = None
    rule_type: str | None = None


@dataclass(frozen=True)
class PolicyParseResult:
    policy: SchedulerConstraintPolicy | None
    configuration_violations: tuple[ConfigurationViolation, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.policy is not None and not self.configuration_violations


@dataclass(frozen=True)
class SchedulerConstraintPolicy:
    """Normalized custom scheduler policy with no infrastructure dependencies."""

    specific_rooms: Mapping[tuple[int, int], frozenset[int]] = field(default_factory=dict)
    locked_timeslots: Mapping[tuple[int, int], frozenset[int]] = field(default_factory=dict)
    teacher_unavailable_timeslots: frozenset[tuple[int, int]] = frozenset()
    teacher_unavailable_days: frozenset[tuple[int, int]] = frozenset()
    teacher_unavailable_dates: frozenset[tuple[int, date]] = frozenset()
    teacher_unavailable_date_slots: frozenset[tuple[int, date, int]] = frozenset()
    teacher_preferred_timeslots: frozenset[tuple[int, int]] = frozenset()

    @classmethod
    def parse(cls, rows: Iterable[Mapping[str, Any] | Any]) -> PolicyParseResult:
        room_rules: dict[tuple[int, int], set[int]] = {}
        lock_rules: dict[tuple[int, int], set[int]] = {}
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

            if rule_type == "lock_time":
                class_id = _legacy_int(payload, "class_id")
                subject_id = _legacy_int(payload, "subject_id")
                timeslot_id = _legacy_int(payload, "timeslot_id")
                if None in (class_id, subject_id, timeslot_id) or set(payload) != {
                    "class_id",
                    "subject_id",
                    "timeslot_id",
                }:
                    violations.append(
                        _configuration(
                            ConfigurationViolationCode.INVALID_PAYLOAD,
                            "lock_time constraint requires class_id, subject_id, and timeslot_id.",
                            constraint_id,
                            rule_type,
                        )
                    )
                else:
                    lock_rules.setdefault((class_id, subject_id), set()).add(timeslot_id)
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
                            "teacher_unavailable constraint requires teacher_id and exactly one valid selector.",
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
                if rule_type in {"min_gap", "max_days"}
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
                locked_timeslots={key: frozenset(values) for key, values in lock_rules.items()},
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

    def evaluate(self, facts: PlacementFacts) -> ConstraintEvaluation:
        violations: list[ConstraintViolation] = []
        key = (facts.class_id, facts.subject_id)
        rooms = self.specific_rooms.get(key)
        if rooms is not None and facts.room_id not in rooms:
            violations.append(
                ConstraintViolation(
                    ConstraintViolationCode.SPECIFIC_ROOM,
                    RepairDimension.RESOURCE,
                    "Draft violates a specific_room scheduler constraint.",
                )
            )
        timeslots = self.locked_timeslots.get(key)
        if timeslots is not None and facts.timeslot_id not in timeslots:
            violations.append(
                ConstraintViolation(
                    ConstraintViolationCode.LOCK_TIME,
                    RepairDimension.TIME,
                    "Draft violates a lock_time scheduler constraint.",
                )
            )
        if self._teacher_unavailable(facts.teacher_id, facts.output_date, facts.timeslot_id):
            violations.append(
                ConstraintViolation(
                    ConstraintViolationCode.TEACHER_UNAVAILABLE,
                    RepairDimension.TIME,
                    "Draft violates a teacher_unavailable scheduler constraint.",
                )
            )
        return ConstraintEvaluation(
            hard_violations=tuple(violations),
            preference_tier_adjustment=(
                1
                if (facts.teacher_id, facts.timeslot_id) in self.teacher_preferred_timeslots
                else 0
            ),
        )

    def _teacher_unavailable(self, teacher_id: int, output_date: date, timeslot_id: int) -> bool:
        return (
            (teacher_id, timeslot_id) in self.teacher_unavailable_timeslots
            or (teacher_id, output_date.weekday()) in self.teacher_unavailable_days
            or (teacher_id, output_date) in self.teacher_unavailable_dates
            or (teacher_id, output_date, timeslot_id) in self.teacher_unavailable_date_slots
        )


def placement_facts(value: Any) -> PlacementFacts:
    output_date = _get_optional(value, "date") or _get_optional(value, "output_date")
    if isinstance(output_date, str):
        output_date = date.fromisoformat(output_date)
    return PlacementFacts(
        class_id=int(_get(value, "class_id")),
        subject_id=int(_get(value, "subject_id")),
        teacher_id=int(_get(value, "teacher_id")),
        room_id=int(_get(value, "room_id")),
        output_date=output_date,
        timeslot_id=int(_get(value, "timeslot_id")),
    )


def _mapping(value: Mapping[str, Any] | Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {
        "id": getattr(value, "id", None),
        "rule_type": getattr(value, "rule_type", None),
        "rule_payload": getattr(value, "rule_payload", None),
    }


def _get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else getattr(value, key)


def _get_optional(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else getattr(value, key, None)


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
