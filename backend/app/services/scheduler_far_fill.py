from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from math import ceil
from typing import Any

from app.services.scheduler_candidates import CandidateUniverse, PlacementCandidate
from app.services.scheduler_complete_demand import CompleteDemandLedger, CompleteDemandItem


@dataclass(frozen=True)
class AssembledScheduleBlock:
    stable_block_key: str
    class_id: int
    subject_id: int
    teacher_id: int
    room_id: int
    output_date: date
    timeslot_id: int
    start_minute: int
    end_minute: int
    duration_minutes: int
    module_sequence_index: int
    availability_score: int
    source: str


@dataclass(frozen=True)
class CompleteScheduleAssembly:
    blocks: tuple[AssembledScheduleBlock, ...]
    blockers: tuple[str, ...]
    projected_completion_date: date | None
    required_minutes: int
    scheduled_minutes: int

    @property
    def is_complete(self) -> bool:
        return self.required_minutes == self.scheduled_minutes and not self.blockers


class FarFutureFiller:
    def fill(
        self,
        ledger: CompleteDemandLedger,
        near_selected: tuple[PlacementCandidate, ...],
        far_universe: CandidateUniverse,
        snapshot: dict[str, Any],
        *,
        deadline_at: datetime | None = None,
    ) -> CompleteScheduleAssembly:
        capacity_blockers = {
            "Hard pruning removed every placement candidate.",
            "Candidate window does not intersect the school year.",
        }
        blockers = list(ledger.blockers) + [
            blocker
            for blocker in far_universe.blockers
            if blocker not in capacity_blockers
        ]
        items = {(row.class_id, row.subject_id): row for row in ledger.items}
        remaining = {
            key: item.required_minutes
            for key, item in items.items()
        }
        blocks: list[AssembledScheduleBlock] = []
        occupied: dict[tuple[str, int, date], list[tuple[int, int]]] = defaultdict(list)
        lunch = self._lunch_rule(snapshot.get("lunch_rules"))
        preferred_room: dict[tuple[int, int], int] = {}

        for candidate in sorted(near_selected, key=self._candidate_order):
            self._place(
                candidate,
                "optimized",
                items,
                remaining,
                blocks,
                occupied,
                lunch,
                preferred_room,
            )

        candidates_by_demand: dict[tuple[int, int], int] = defaultdict(int)
        for candidate in far_universe.candidates:
            candidates_by_demand[(candidate.class_id, candidate.subject_id)] += 1
        minimum_duration = min(
            (row.duration_minutes for row in far_universe.candidates),
            default=60,
        )

        ordered_far = sorted(
            far_universe.candidates,
            key=lambda row: (
                row.output_date,
                row.start_minute,
                self._scarcity(
                    row,
                    items,
                    remaining,
                    candidates_by_demand,
                    minimum_duration,
                ),
                -row.availability_score,
                0
                if preferred_room.get((row.class_id, row.subject_id)) == row.room_id
                else 1,
                row.class_id,
                row.subject_id,
                row.room_id,
            ),
        )
        for candidate in ordered_far:
            if deadline_at is not None and datetime.now(timezone.utc) >= deadline_at:
                blockers.append("Far-future fill exhausted its time budget.")
                break
            key = (candidate.class_id, candidate.subject_id)
            if not remaining.get(key, 0):
                continue
            if not self._resources_available(candidate, occupied):
                continue
            if not self._preserves_lunch(candidate, occupied, lunch):
                continue
            self._place(
                candidate,
                "provisional",
                items,
                remaining,
                blocks,
                occupied,
                lunch,
                preferred_room,
            )
            if all(value <= 0 for value in remaining.values()):
                break

        for key, subject_minutes in sorted(remaining.items()):
            residual = max(0, subject_minutes)
            if residual:
                blockers.append(
                    f"Residual demand of {residual} minutes remains for class {key[0]}, subject {key[1]}."
                )
        ordered_blocks = tuple(
            sorted(
                blocks,
                key=lambda row: (
                    row.output_date,
                    row.start_minute,
                    row.class_id,
                    row.subject_id,
                    row.room_id,
                ),
            )
        )
        scheduled_minutes = sum(row.duration_minutes for row in ordered_blocks)
        return CompleteScheduleAssembly(
            blocks=ordered_blocks,
            blockers=tuple(dict.fromkeys(blockers)),
            projected_completion_date=(
                max((row.output_date for row in ordered_blocks), default=None)
            ),
            required_minutes=ledger.required_minutes,
            scheduled_minutes=scheduled_minutes,
        )

    def _place(
        self,
        candidate: PlacementCandidate,
        source: str,
        items: dict[tuple[int, int], CompleteDemandItem],
        remaining: dict[tuple[int, int], int],
        blocks: list[AssembledScheduleBlock],
        occupied: dict[tuple[str, int, date], list[tuple[int, int]]],
        lunch: tuple[int, int, int] | None,
        preferred_room: dict[tuple[int, int], int],
    ) -> bool:
        key = (candidate.class_id, candidate.subject_id)
        item = items.get(key)
        subject_remaining = remaining.get(key)
        if item is None or subject_remaining is None or subject_remaining <= 0:
            return False
        scheduled_so_far = item.required_minutes - subject_remaining
        module_sequence = self._module_sequence_for_offset(item, scheduled_so_far)
        curriculum_minutes = min(candidate.duration_minutes, subject_remaining)
        remaining[key] = subject_remaining - curriculum_minutes
        blocks.append(
            AssembledScheduleBlock(
                stable_block_key=(
                    f"{candidate.candidate_key}-A{scheduled_so_far}"
                ),
                class_id=candidate.class_id,
                subject_id=candidate.subject_id,
                teacher_id=candidate.teacher_id,
                room_id=candidate.room_id,
                output_date=candidate.output_date,
                timeslot_id=candidate.timeslot_id,
                start_minute=candidate.start_minute,
                end_minute=candidate.end_minute,
                duration_minutes=curriculum_minutes,
                module_sequence_index=module_sequence,
                availability_score=candidate.availability_score,
                source=source,
            )
        )
        for kind, resource_id in (
            ("class", candidate.class_id),
            ("teacher", candidate.teacher_id),
            ("room", candidate.room_id),
        ):
            occupied[(kind, resource_id, candidate.output_date)].append(
                (candidate.start_minute, candidate.end_minute)
            )
        preferred_room.setdefault(key, candidate.room_id)
        return True

    @staticmethod
    def _resources_available(
        candidate: PlacementCandidate,
        occupied: dict[tuple[str, int, date], list[tuple[int, int]]],
    ) -> bool:
        for kind, resource_id in (
            ("class", candidate.class_id),
            ("teacher", candidate.teacher_id),
            ("room", candidate.room_id),
        ):
            for start, end in occupied[(kind, resource_id, candidate.output_date)]:
                if candidate.start_minute < end and candidate.end_minute > start:
                    return False
        return True

    def _preserves_lunch(
        self,
        candidate: PlacementCandidate,
        occupied: dict[tuple[str, int, date], list[tuple[int, int]]],
        lunch: tuple[int, int, int] | None,
    ) -> bool:
        if lunch is None:
            return True
        for kind, resource_id in (
            ("class", candidate.class_id),
            ("teacher", candidate.teacher_id),
        ):
            intervals = list(occupied[(kind, resource_id, candidate.output_date)])
            intervals.append((candidate.start_minute, candidate.end_minute))
            if not self._has_lunch_gap(intervals, lunch):
                return False
        return True

    @staticmethod
    def _has_lunch_gap(
        intervals: list[tuple[int, int]],
        lunch: tuple[int, int, int],
    ) -> bool:
        lunch_start, lunch_end, minimum = lunch
        clipped = sorted(
            (max(start, lunch_start), min(end, lunch_end))
            for start, end in intervals
            if start < lunch_end and end > lunch_start
        )
        cursor = lunch_start
        for start, end in clipped:
            if start - cursor >= minimum:
                return True
            cursor = max(cursor, end)
        return lunch_end - cursor >= minimum

    @staticmethod
    def _scarcity(
        candidate: PlacementCandidate,
        items: dict[tuple[int, int], CompleteDemandItem],
        remaining: dict[tuple[int, int], int],
        candidate_counts: dict[tuple[int, int], int],
        minimum_duration: int,
    ) -> float:
        key = (candidate.class_id, candidate.subject_id)
        sessions = ceil(
            max(0, remaining.get(key, 0))
            / max(1, minimum_duration)
        )
        return candidate_counts.get(key, 0) / max(1, sessions)

    @staticmethod
    def _candidate_order(candidate: PlacementCandidate) -> tuple:
        return (
            candidate.output_date,
            candidate.start_minute,
            candidate.class_id,
            candidate.subject_id,
            candidate.room_id,
        )

    @staticmethod
    def _module_sequence_for_offset(item: CompleteDemandItem, scheduled_minutes: int) -> int:
        cumulative = 0
        fallback = item.modules[-1].sequence
        for module in item.modules:
            if module.required_minutes <= 0:
                continue
            cumulative += module.required_minutes
            if scheduled_minutes < cumulative:
                return module.sequence
        return fallback

    @staticmethod
    def _lunch_rule(row: dict[str, Any] | None) -> tuple[int, int, int] | None:
        if not row or not row.get("window_start") or not row.get("window_end"):
            return None
        start = FarFutureFiller._minute(row["window_start"])
        end = FarFutureFiller._minute(row["window_end"])
        minimum = int(row.get("minimum_minutes") or 0)
        if end <= start or minimum <= 0:
            return None
        return start, end, minimum

    @staticmethod
    def _minute(value: str | time) -> int:
        parsed = value if isinstance(value, time) else time.fromisoformat(value)
        return parsed.hour * 60 + parsed.minute
