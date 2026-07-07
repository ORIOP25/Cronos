from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from app.services.scheduler_complete_demand import CompleteDemandLedger
from app.services.scheduler_constraint_rules import SchedulerConstraintRules


@dataclass(frozen=True)
class PlacementCandidate:
    candidate_key: str
    class_id: int
    subject_id: int
    teacher_id: int
    room_id: int
    output_date: date
    timeslot_id: int
    start_minute: int
    end_minute: int
    duration_minutes: int
    availability_score: int


@dataclass(frozen=True)
class CandidateUniverse:
    candidates: tuple[PlacementCandidate, ...]
    blockers: tuple[str, ...]
    removed_by_reason: dict[str, int]

    @property
    def is_usable(self) -> bool:
        return bool(self.candidates) and not self.blockers


class CandidateUniverseBuilder:
    def build(
        self,
        snapshot: dict[str, Any],
        ledger: CompleteDemandLedger,
        *,
        window_start: date,
        window_end: date,
        fixed_teacher_conflicts: set[tuple[int, date, int]] | None = None,
        fixed_class_conflicts: set[tuple[int, date, int]] | None = None,
        fixed_room_conflicts: set[tuple[int, date, int]] | None = None,
        deadline_at: datetime | None = None,
        max_candidates: int = 500_000,
    ) -> CandidateUniverse:
        blockers = list(ledger.blockers)
        hard_end = date.fromisoformat(snapshot["hard_end_date"])
        school_start = date.fromisoformat(snapshot["start_date"])
        start = max(window_start, school_start)
        end = min(window_end, hard_end)
        if end < start:
            blockers.append("Candidate window does not intersect the school year.")
            return CandidateUniverse((), tuple(dict.fromkeys(blockers)), {})

        slots, grid_blockers = self._validated_slots(snapshot.get("timetable_grid", []))
        blockers.extend(grid_blockers)
        if not slots:
            blockers.append("No valid timetable slots are configured.")
        constraint_rules = SchedulerConstraintRules.from_snapshot(snapshot)
        blockers.extend(constraint_rules.blockers)
        blocked_dates = self._blocked_dates(snapshot.get("calendar_events", []))
        availability = {
            (row["teacher_id"], row["timeslot_id"]): row["score"]
            for row in snapshot.get("teacher_availability", [])
        }
        lunch = self._lunch_rule(snapshot.get("lunch_rules"))
        teacher_conflicts = fixed_teacher_conflicts or set()
        class_conflicts = fixed_class_conflicts or set()
        room_conflicts = fixed_room_conflicts or set()
        removed: dict[str, int] = {}
        candidates: list[PlacementCandidate] = []

        current = start
        while current <= end:
            if deadline_at is not None and datetime.now(timezone.utc) >= deadline_at:
                blockers.append("Candidate generation exhausted its time budget.")
                break
            if current not in blocked_dates:
                for item in ledger.items:
                    for slot in slots.get(current.weekday(), ()):
                        score = availability.get((item.teacher_id, slot["id"]), 1)
                        if score == -1:
                            self._removed(removed, "teacher_impossible")
                            continue
                        if not self._slot_preserves_lunch(slot, lunch):
                            self._removed(removed, "lunch_hard")
                            continue
                        if (item.teacher_id, current, slot["id"]) in teacher_conflicts:
                            self._removed(removed, "teacher_conflict")
                            continue
                        if (item.class_id, current, slot["id"]) in class_conflicts:
                            self._removed(removed, "class_conflict")
                            continue
                        for room_id in item.eligible_room_ids:
                            if (room_id, current, slot["id"]) in room_conflicts:
                                self._removed(removed, "room_conflict")
                                continue
                            candidate = PlacementCandidate(
                                candidate_key=(
                                    f"C{item.class_id}-S{item.subject_id}-"
                                    f"D{current.isoformat()}-T{slot['id']}-R{room_id}"
                                ),
                                class_id=item.class_id,
                                subject_id=item.subject_id,
                                teacher_id=item.teacher_id,
                                room_id=room_id,
                                output_date=current,
                                timeslot_id=slot["id"],
                                start_minute=slot["start_minute"],
                                end_minute=slot["end_minute"],
                                duration_minutes=slot["duration_minutes"],
                                availability_score=(
                                    score
                                    + constraint_rules.preference_bonus(
                                        item.teacher_id,
                                        slot["id"],
                                    )
                                ),
                            )
                            if not constraint_rules.is_candidate_allowed(candidate):
                                self._removed(removed, "scheduler_constraint")
                                continue
                            candidates.append(candidate)
                            if len(candidates) >= max_candidates:
                                blockers.append(
                                    "Candidate universe exceeds the safe solve-size limit."
                                )
                                return CandidateUniverse(
                                    candidates=tuple(candidates),
                                    blockers=tuple(dict.fromkeys(blockers)),
                                    removed_by_reason=dict(sorted(removed.items())),
                                )
            current += timedelta(days=1)

        if ledger.items and not candidates:
            blockers.append("Hard pruning removed every placement candidate.")
        return CandidateUniverse(
            candidates=tuple(candidates),
            blockers=tuple(dict.fromkeys(blockers)),
            removed_by_reason=dict(sorted(removed.items())),
        )

    def _validated_slots(
        self,
        rows: list[dict[str, Any]],
    ) -> tuple[dict[int, tuple[dict[str, int], ...]], list[str]]:
        by_day: dict[int, list[dict[str, int]]] = {}
        blockers: list[str] = []
        seen_ids: set[int] = set()
        for row in rows:
            slot_id = row["id"]
            weekday = row["day_of_week"]
            start = self._minute(row["start_time"])
            end = self._minute(row["end_time"])
            if slot_id in seen_ids or weekday not in range(7) or end <= start:
                blockers.append(f"Timeslot {slot_id} is invalid or duplicated.")
                continue
            seen_ids.add(slot_id)
            by_day.setdefault(weekday, []).append(
                {
                    "id": slot_id,
                    "start_minute": start,
                    "end_minute": end,
                    "duration_minutes": end - start,
                }
            )
        validated: dict[int, tuple[dict[str, int], ...]] = {}
        for weekday, slots in by_day.items():
            ordered = sorted(slots, key=lambda row: (row["start_minute"], row["id"]))
            for previous, current in zip(ordered, ordered[1:]):
                if current["start_minute"] < previous["end_minute"]:
                    blockers.append(f"Timetable slots overlap on weekday {weekday}.")
            validated[weekday] = tuple(ordered)
        return validated, blockers

    @staticmethod
    def _blocked_dates(rows: list[dict[str, Any]]) -> set[date]:
        blocked: set[date] = set()
        for row in rows:
            current = date.fromisoformat(row["start_date"])
            end = date.fromisoformat(row["end_date"])
            while current <= end:
                blocked.add(current)
                current += timedelta(days=1)
        return blocked

    @classmethod
    def _lunch_rule(cls, row: dict[str, Any] | None) -> tuple[int, int, int] | None:
        if not row or row.get("window_start") is None or row.get("window_end") is None:
            return None
        start = cls._minute(row["window_start"])
        end = cls._minute(row["window_end"])
        minimum = int(row.get("minimum_minutes") or 0)
        if end <= start or minimum <= 0 or minimum > end - start:
            return None
        return start, end, minimum

    @staticmethod
    def _slot_preserves_lunch(
        slot: dict[str, int],
        lunch: tuple[int, int, int] | None,
    ) -> bool:
        if lunch is None:
            return True
        lunch_start, lunch_end, minimum = lunch
        occupied_start = max(lunch_start, slot["start_minute"])
        occupied_end = min(lunch_end, slot["end_minute"])
        if occupied_end <= occupied_start:
            return True
        longest_free = max(occupied_start - lunch_start, lunch_end - occupied_end)
        return longest_free >= minimum

    @staticmethod
    def _minute(value: str | time) -> int:
        parsed = value if isinstance(value, time) else time.fromisoformat(value)
        return parsed.hour * 60 + parsed.minute

    @staticmethod
    def _removed(removed: dict[str, int], reason: str) -> None:
        removed[reason] = removed.get(reason, 0) + 1
