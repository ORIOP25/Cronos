from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.solver_schemas import LessonInput, RoomInput, TimeslotInput

DEFAULT_AVAILABILITY_SCORE = 1
IMPOSSIBLE_AVAILABILITY_SCORE = -1

REMOVAL_REASON_ROOM_TYPE = "room_type_mismatch"
REMOVAL_REASON_TEACHER_IMPOSSIBLE = "teacher_impossible"
REMOVAL_REASON_TEACHER_CONFLICT = "teacher_conflict"
REMOVAL_REASON_CLASS_CONFLICT = "class_conflict"
REMOVAL_REASON_ROOM_CONFLICT = "room_conflict"
REMOVAL_REASON_LUNCH_HARD = "lunch_hard"


@dataclass(frozen=True)
class SolverV2Candidate:
    candidate_key: str
    lesson_id: int
    class_id: int
    subject_id: int
    teacher_id: int
    required_room_type: str
    room_id: int
    room_type: str
    output_date: date
    day_of_week: int
    ts_id: int
    slot_start_minutes: int
    slot_end_minutes: int
    duration_minutes: int


@dataclass(frozen=True)
class CandidatePruningTelemetry:
    candidates_before: int
    candidates_after: int
    removed_total: int
    removed_ratio: float
    removed_by_reason: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "candidates_before": self.candidates_before,
            "candidates_after": self.candidates_after,
            "removed_total": self.removed_total,
            "removed_ratio": self.removed_ratio,
            "removed_by_reason": dict(self.removed_by_reason),
        }


def _iter_dates(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current = current + timedelta(days=1)


def build_candidate_universe(
    *,
    lessons: list[LessonInput],
    timeslots: list[TimeslotInput],
    rooms: list[RoomInput],
    window_start_date: date,
    window_end_date: date,
    blocked_dates: set[date],
) -> list[SolverV2Candidate]:
    """Builds deterministic candidate universe for V2 on real dates."""
    if window_end_date < window_start_date:
        return []

    timeslots_by_weekday: dict[int, list[TimeslotInput]] = defaultdict(list)
    for slot in timeslots:
        timeslots_by_weekday[int(slot.day_of_week)].append(slot)

    sorted_lessons = sorted(lessons, key=lambda item: int(item.lesson_id))
    sorted_rooms = sorted(rooms, key=lambda item: int(item.room_id))
    for weekday_slots in timeslots_by_weekday.values():
        weekday_slots.sort(key=lambda item: int(item.ts_id))

    candidates: list[SolverV2Candidate] = []
    for output_date in _iter_dates(window_start_date, window_end_date):
        if output_date in blocked_dates:
            continue

        weekday = output_date.weekday()
        day_slots = timeslots_by_weekday.get(weekday, [])
        if not day_slots:
            continue

        for lesson in sorted_lessons:
            for slot in day_slots:
                for room in sorted_rooms:
                    key = (
                        f"L{lesson.lesson_id}-"
                        f"D{output_date.isoformat()}-"
                        f"T{slot.ts_id}-"
                        f"R{room.room_id}"
                    )
                    candidates.append(
                        SolverV2Candidate(
                            candidate_key=key,
                            lesson_id=int(lesson.lesson_id),
                            class_id=int(lesson.class_id),
                            subject_id=int(lesson.subject_id),
                            teacher_id=int(lesson.teacher_id),
                            required_room_type=str(lesson.required_room_type),
                            room_id=int(room.room_id),
                            room_type=str(room.room_type),
                            output_date=output_date,
                            day_of_week=weekday,
                            ts_id=int(slot.ts_id),
                            slot_start_minutes=int(slot.start_minutes),
                            slot_end_minutes=int(slot.end_minutes),
                            duration_minutes=int(slot.duration_minutes),
                        )
                    )

    return candidates


def _slot_lunch_overlap_minutes(
    slot_start_minutes: int,
    slot_end_minutes: int,
    lunch_window_start_minutes: int,
    lunch_window_end_minutes: int,
) -> int:
    overlap_start = max(slot_start_minutes, lunch_window_start_minutes)
    overlap_end = min(slot_end_minutes, lunch_window_end_minutes)
    return max(0, overlap_end - overlap_start)


def _build_pruning_telemetry(
    candidates_before: int,
    candidates_after: int,
    removed_by_reason: dict[str, int],
) -> CandidatePruningTelemetry:
    removed_total = max(0, candidates_before - candidates_after)
    removed_ratio = round((removed_total / candidates_before), 4) if candidates_before > 0 else 0.0
    return CandidatePruningTelemetry(
        candidates_before=candidates_before,
        candidates_after=candidates_after,
        removed_total=removed_total,
        removed_ratio=removed_ratio,
        removed_by_reason=dict(sorted(removed_by_reason.items())),
    )


def prune_candidates_hard_first(
    candidates: list[SolverV2Candidate],
    *,
    availability_map: dict[tuple[int, int], int],
    fixed_teacher_conflicts: set[tuple[int, date, int]] | None = None,
    fixed_class_conflicts: set[tuple[int, date, int]] | None = None,
    fixed_room_conflicts: set[tuple[int, date, int]] | None = None,
    lunch_window_start_minutes: int | None = None,
    lunch_window_end_minutes: int | None = None,
    lunch_min_duration_minutes: int = 60,
) -> tuple[list[SolverV2Candidate], CandidatePruningTelemetry]:
    """Applies deterministic hard-first pruning on unary/locked constraints."""
    teacher_conflicts = fixed_teacher_conflicts or set()
    class_conflicts = fixed_class_conflicts or set()
    room_conflicts = fixed_room_conflicts or set()

    lunch_overlap_by_slot: dict[tuple[int, int], int] = {}
    lunch_max_occupied_by_weekday: dict[int, int] = {}

    has_lunch_window = (
        lunch_window_start_minutes is not None
        and lunch_window_end_minutes is not None
        and int(lunch_window_end_minutes) > int(lunch_window_start_minutes)
    )

    if has_lunch_window:
        total_overlap_by_weekday: dict[int, int] = defaultdict(int)
        seen_slots: set[tuple[int, int]] = set()

        for candidate in candidates:
            slot_key = (candidate.day_of_week, candidate.ts_id)
            if slot_key in seen_slots:
                continue
            seen_slots.add(slot_key)

            overlap = _slot_lunch_overlap_minutes(
                candidate.slot_start_minutes,
                candidate.slot_end_minutes,
                int(lunch_window_start_minutes),
                int(lunch_window_end_minutes),
            )
            lunch_overlap_by_slot[slot_key] = overlap
            total_overlap_by_weekday[candidate.day_of_week] += overlap

        for day_of_week, total_overlap in total_overlap_by_weekday.items():
            required_break = min(max(1, int(lunch_min_duration_minutes)), max(0, int(total_overlap)))
            lunch_max_occupied_by_weekday[day_of_week] = max(0, int(total_overlap) - required_break)

    kept: list[SolverV2Candidate] = []
    removed_by_reason: dict[str, int] = defaultdict(int)

    for candidate in candidates:
        removal_reason: str | None = None

        if candidate.required_room_type != candidate.room_type:
            removal_reason = REMOVAL_REASON_ROOM_TYPE
        elif availability_map.get((candidate.teacher_id, candidate.ts_id), DEFAULT_AVAILABILITY_SCORE) == IMPOSSIBLE_AVAILABILITY_SCORE:
            removal_reason = REMOVAL_REASON_TEACHER_IMPOSSIBLE
        elif (candidate.teacher_id, candidate.output_date, candidate.ts_id) in teacher_conflicts:
            removal_reason = REMOVAL_REASON_TEACHER_CONFLICT
        elif (candidate.class_id, candidate.output_date, candidate.ts_id) in class_conflicts:
            removal_reason = REMOVAL_REASON_CLASS_CONFLICT
        elif (candidate.room_id, candidate.output_date, candidate.ts_id) in room_conflicts:
            removal_reason = REMOVAL_REASON_ROOM_CONFLICT
        elif has_lunch_window:
            slot_key = (candidate.day_of_week, candidate.ts_id)
            overlap = lunch_overlap_by_slot.get(slot_key, 0)
            max_occupied = lunch_max_occupied_by_weekday.get(candidate.day_of_week, overlap)
            if overlap > max_occupied:
                removal_reason = REMOVAL_REASON_LUNCH_HARD

        if removal_reason is None:
            kept.append(candidate)
        else:
            removed_by_reason[removal_reason] += 1

    telemetry = _build_pruning_telemetry(
        candidates_before=len(candidates),
        candidates_after=len(kept),
        removed_by_reason=dict(removed_by_reason),
    )
    return kept, telemetry
