from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SchedulerConstraintRules:
    specific_rooms: dict[tuple[int, int], frozenset[int]] = field(default_factory=dict)
    locked_timeslots: dict[tuple[int, int], frozenset[int]] = field(default_factory=dict)
    teacher_unavailable_timeslots: frozenset[tuple[int, int]] = frozenset()
    teacher_unavailable_days: frozenset[tuple[int, int]] = frozenset()
    teacher_unavailable_dates: frozenset[tuple[int, date]] = frozenset()
    teacher_unavailable_date_slots: frozenset[tuple[int, date, int]] = frozenset()
    teacher_preferred_timeslots: frozenset[tuple[int, int]] = frozenset()
    blockers: tuple[str, ...] = ()

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> "SchedulerConstraintRules":
        room_rules: dict[tuple[int, int], set[int]] = {}
        lock_rules: dict[tuple[int, int], set[int]] = {}
        unavailable_slots: set[tuple[int, int]] = set()
        unavailable_days: set[tuple[int, int]] = set()
        unavailable_dates: set[tuple[int, date]] = set()
        unavailable_date_slots: set[tuple[int, date, int]] = set()
        preferred_slots: set[tuple[int, int]] = set()
        blockers: list[str] = []

        for row in snapshot.get("constraints", []):
            rule_type = _value(row.get("rule_type"))
            payload = row.get("rule_payload") or {}
            if not isinstance(payload, dict):
                blockers.append(f"Constraint {rule_type} has an invalid payload.")
                continue

            if rule_type == "specific_room":
                class_id = _int(payload, "class_id")
                subject_id = _int(payload, "subject_id")
                room_id = _int(payload, "room_id", "specific_room_id")
                if None in (class_id, subject_id, room_id):
                    blockers.append("specific_room constraint requires class_id, subject_id, and room_id.")
                    continue
                room_rules.setdefault((class_id, subject_id), set()).add(room_id)
                continue

            if rule_type == "lock_time":
                class_id = _int(payload, "class_id")
                subject_id = _int(payload, "subject_id")
                timeslot_id = _int(payload, "timeslot_id")
                if None in (class_id, subject_id, timeslot_id):
                    blockers.append("lock_time constraint requires class_id, subject_id, and timeslot_id.")
                    continue
                lock_rules.setdefault((class_id, subject_id), set()).add(timeslot_id)
                continue

            if rule_type == "teacher_unavailable":
                teacher_id = _int(payload, "teacher_id")
                timeslot_id = _int(payload, "timeslot_id")
                weekday = _int(payload, "day_of_week", "weekday")
                blocked_date = _date(payload, "date", "output_date")
                if teacher_id is None:
                    blockers.append("teacher_unavailable constraint requires teacher_id.")
                    continue
                if blocked_date is not None and timeslot_id is not None:
                    unavailable_date_slots.add((teacher_id, blocked_date, timeslot_id))
                elif blocked_date is not None:
                    unavailable_dates.add((teacher_id, blocked_date))
                elif timeslot_id is not None:
                    unavailable_slots.add((teacher_id, timeslot_id))
                elif weekday is not None:
                    unavailable_days.add((teacher_id, weekday))
                else:
                    blockers.append(
                        "teacher_unavailable constraint requires timeslot_id, day_of_week, or date."
                    )
                continue

            if rule_type == "teacher_preferred":
                teacher_id = _int(payload, "teacher_id")
                timeslot_id = _int(payload, "timeslot_id")
                if None in (teacher_id, timeslot_id):
                    blockers.append("teacher_preferred constraint requires teacher_id and timeslot_id.")
                    continue
                preferred_slots.add((teacher_id, timeslot_id))
                continue

            if rule_type in {"min_gap", "max_days"}:
                blockers.append(
                    f"{rule_type} constraints are not supported by the current generator."
                )
                continue

            blockers.append(f"Unknown scheduler constraint type: {rule_type}.")

        return cls(
            specific_rooms={
                key: frozenset(values) for key, values in room_rules.items()
            },
            locked_timeslots={
                key: frozenset(values) for key, values in lock_rules.items()
            },
            teacher_unavailable_timeslots=frozenset(unavailable_slots),
            teacher_unavailable_days=frozenset(unavailable_days),
            teacher_unavailable_dates=frozenset(unavailable_dates),
            teacher_unavailable_date_slots=frozenset(unavailable_date_slots),
            teacher_preferred_timeslots=frozenset(preferred_slots),
            blockers=tuple(dict.fromkeys(blockers)),
        )

    def is_candidate_allowed(self, candidate: Any) -> bool:
        key = (candidate.class_id, candidate.subject_id)
        room_ids = self.specific_rooms.get(key)
        if room_ids is not None and candidate.room_id not in room_ids:
            return False
        timeslot_ids = self.locked_timeslots.get(key)
        if timeslot_ids is not None and candidate.timeslot_id not in timeslot_ids:
            return False
        if self._teacher_unavailable(
            candidate.teacher_id,
            candidate.output_date,
            candidate.timeslot_id,
        ):
            return False
        return True

    def preference_bonus(self, teacher_id: int, timeslot_id: int) -> int:
        return 1 if (teacher_id, timeslot_id) in self.teacher_preferred_timeslots else 0

    def violation_for_block(self, block: Any) -> str | None:
        key = (block.class_id, block.subject_id)
        room_ids = self.specific_rooms.get(key)
        if room_ids is not None and block.room_id not in room_ids:
            return "Draft violates a specific_room scheduler constraint."
        timeslot_ids = self.locked_timeslots.get(key)
        if timeslot_ids is not None and block.timeslot_id not in timeslot_ids:
            return "Draft violates a lock_time scheduler constraint."
        block_date = getattr(block, "date", None) or getattr(block, "output_date")
        if self._teacher_unavailable(block.teacher_id, block_date, block.timeslot_id):
            return "Draft violates a teacher_unavailable scheduler constraint."
        return None

    def _teacher_unavailable(
        self,
        teacher_id: int,
        block_date: date,
        timeslot_id: int,
    ) -> bool:
        return (
            (teacher_id, timeslot_id) in self.teacher_unavailable_timeslots
            or (teacher_id, block_date.weekday()) in self.teacher_unavailable_days
            or (teacher_id, block_date) in self.teacher_unavailable_dates
            or (teacher_id, block_date, timeslot_id)
            in self.teacher_unavailable_date_slots
        )


def _int(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _date(payload: dict[str, Any], *keys: str) -> date | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None
    return None


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))
