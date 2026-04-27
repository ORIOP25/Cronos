"""Solver V2 — Fase F: Expansão adaptativa, fill-opportunistic e residual transparente.

F.01: valida blocos CP-SAT contra calendário (blocked_dates e hard_end_date).
F.02: fill-opportunistic — preenche densamente TODOS os slots do calendário para
      cobrir o backlog remanescente de cada lição.  O CP-SAT (Fase E) produz um
      *padrão exemplar* de 1 bloco por disciplina; a Fase F **não fica presa**
      ao (ts_id, room_id) desse padrão.  Em vez disso, para cada data livre
      tenta colocar cada lição em qualquer (timeslot, room) compatível
      (tipo de sala correto) enquanto respeita:
        - datas bloqueadas por calendário;
        - hard_end_date absoluto;
        - HC1 sala: max 1 lição por (room, date, ts_id)
        - HC2 professor: max 1 lição por (teacher, date, ts_id)
        - HC3 turma: max 1 lição por (class, date, ts_id)
        - HC_LUNCH: a soma de minutos de almoço ocupados por (turma|professor, dia)
                    não pode exceder total_lunch_overlap − lunch_min_duration
        - HC_DAILY: cada lesson tem no máximo max_blocks_per_lesson_per_day blocos/dia
      A iteração usa round-robin diário: por cada passe, cada lição recebe no
      máximo 1 bloco extra — garante variedade de disciplinas ao longo do dia.
F.03: calcula e devolve residual transparente (backlog_remaining_hours).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import NamedTuple

import structlog

from app.core.solver_engine_v2 import ScheduledBlockV2

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# F.01 — Validação de calendário
# ---------------------------------------------------------------------------

def validate_v2_blocks_calendar(
    blocks: list[ScheduledBlockV2],
    *,
    blocked_dates: set[date],
    hard_end_date: date,
) -> tuple[list[ScheduledBlockV2], list[ScheduledBlockV2]]:
    """F.01: Partitions blocks into valid and invalid by calendar rules.

    Returns (valid_blocks, rejected_blocks).
    A block is invalid if its output_date is in blocked_dates or after hard_end_date.
    In a correct pipeline, rejected_blocks should always be empty because Phase D
    already excluded blocked dates from candidates. This function acts as a safety net.
    """
    valid: list[ScheduledBlockV2] = []
    rejected: list[ScheduledBlockV2] = []

    for block in blocks:
        if block.output_date > hard_end_date or block.output_date in blocked_dates:
            rejected.append(block)
        else:
            valid.append(block)

    if rejected:
        logger.warning(
            "F.01: blocos V2 rejeitados por calendário (inesperado)",
            rejected=len(rejected),
            valid=len(valid),
        )

    return valid, rejected


# ---------------------------------------------------------------------------
# F.02 — Fill-opportunistic
# ---------------------------------------------------------------------------

@dataclass
class FillOpportunisticResult:
    """Resultado do fill-opportunistic."""
    all_blocks: list[ScheduledBlockV2]        # primary + fill blocks
    primary_blocks: list[ScheduledBlockV2]    # from CP-SAT (1 occurrence/lesson)
    fill_blocks: list[ScheduledBlockV2]       # extra occurrences added
    backlog_remaining_minutes: int            # unscheduled backlog after fill
    fill_iterations: int                      # number of days processed


@dataclass
class _TimeslotInfo:
    """Lightweight timeslot descriptor for fill."""
    ts_id: int
    day_of_week: int
    duration_minutes: int
    start_minutes: int = 0   # minutes from midnight
    end_minutes: int = 0     # minutes from midnight


@dataclass
class _RoomInfo:
    """Lightweight room descriptor for fill."""
    room_id: int
    room_type: str


def _slot_lunch_overlap(
    ts: _TimeslotInfo,
    lunch_start: int,
    lunch_end: int,
) -> int:
    """Returns overlap in minutes between a timeslot and the lunch window."""
    return max(0, min(ts.end_minutes, lunch_end) - max(ts.start_minutes, lunch_start))


def _build_lunch_filtered_slots(
    timeslots_by_dow: dict[int, list[_TimeslotInfo]],
    lunch_window_start_minutes: int | None,
    lunch_window_end_minutes: int | None,
    lunch_min_duration_minutes: int,
) -> dict[int, list[_TimeslotInfo]]:
    """Pre-filter timeslots: remove slots whose lunch overlap exceeds the allowed maximum.

    Algorithm mirrors Phase D (prune_candidates_hard_first) but applied globally:
      total_overlap = sum of all slots' overlaps with the lunch window on that day
      max_occupied  = total_overlap - lunch_min_duration  (headroom before break is violated)
      A slot is REMOVED if its individual overlap > max_occupied.

    This ensures every class and teacher automatically has lunch_min_duration free
    in the lunch window, without needing per-entity tracking in the fill loop.
    """
    if (
        lunch_window_start_minutes is None
        or lunch_window_end_minutes is None
        or lunch_window_end_minutes <= lunch_window_start_minutes
    ):
        return timeslots_by_dow  # no lunch constraint configured

    lw_start = int(lunch_window_start_minutes)
    lw_end = int(lunch_window_end_minutes)
    lw_min = max(1, int(lunch_min_duration_minutes))

    filtered: dict[int, list[_TimeslotInfo]] = {}
    for dow, slots in timeslots_by_dow.items():
        total_overlap = sum(_slot_lunch_overlap(ts, lw_start, lw_end) for ts in slots)
        max_occupied = max(0, total_overlap - lw_min)

        kept = []
        for ts in slots:
            overlap = _slot_lunch_overlap(ts, lw_start, lw_end)
            # Keep the slot only if its overlap stays within the allowable maximum.
            # (overlap == 0 → always kept; overlap > max_occupied → blocked)
            if overlap <= max_occupied:
                kept.append(ts)

        filtered[dow] = kept

    return filtered


def fill_opportunistic_v2(
    primary_blocks: list[ScheduledBlockV2],
    *,
    backlog_by_lesson: dict[int, int],        # lesson_id -> remaining minutes
    lesson_class_map: dict[int, int],         # lesson_id -> class_id
    lesson_teacher_map: dict[int, int],       # lesson_id -> teacher_id
    lesson_room_type_map: dict[int, str],     # lesson_id -> required_room_type
    timeslots_by_dow: dict[int, list[_TimeslotInfo]],  # day_of_week -> ordered timeslots
    rooms_by_type: dict[str, list[_RoomInfo]],          # room_type -> rooms
    window_start_date: date,
    window_end_date: date,
    hard_end_date: date,
    blocked_dates: set[date],
    lunch_window_start_minutes: int | None = None,
    lunch_window_end_minutes: int | None = None,
    lunch_min_duration_minutes: int = 60,
    max_blocks_per_lesson_per_day: int = 3,
) -> FillOpportunisticResult:
    """F.02: Dense greedy fill with fair daily distribution.

    Strategy:
      1. Pre-filter timeslots to enforce lunch break (HC_LUNCH).
      2. Walk every date in [window_start, hard_end_date] that is not blocked.
      3. Per day, use round-robin passes (up to max_blocks_per_lesson_per_day):
           Pass 0: give each active lesson its FIRST block of the day.
           Pass 1: give each active lesson its SECOND block.
           ...
         This guarantees discipline variety within each day — no single discipline
         monopolises all timeslots of a day.
      4. Within each pass, lessons are sorted by remaining backlog (descending)
         so higher-debt lessons get priority for the earlier timeslots.
      5. Enforce HC1 (room), HC2 (teacher), HC3 (class), HC4 (room type).
      6. Stop when all backlogs reach 0 or effective_end is reached.
    """
    # Apply lunch filter once to all days
    usable_slots_by_dow = _build_lunch_filtered_slots(
        timeslots_by_dow,
        lunch_window_start_minutes,
        lunch_window_end_minutes,
        lunch_min_duration_minutes,
    )

    # Debit CP-SAT primary blocks from backlog
    primary_minutes_by_lesson: dict[int, int] = defaultdict(int)
    for block in primary_blocks:
        primary_minutes_by_lesson[block.lesson_id] += block.duration_minutes

    remaining: dict[int, int] = {}
    for lesson_id, backlog_mins in backlog_by_lesson.items():
        placed = primary_minutes_by_lesson.get(lesson_id, 0)
        remaining[lesson_id] = max(0, backlog_mins - placed)

    fill_blocks: list[ScheduledBlockV2] = []

    # Conflict tracking: (entity_id, date, ts_id)
    teacher_slots_used: set[tuple[int, date, int]] = set()
    class_slots_used: set[tuple[int, date, int]] = set()
    room_slots_used: set[tuple[int, date, int]] = set()

    # Seed conflict sets with primary blocks
    for block in primary_blocks:
        teacher_id = lesson_teacher_map.get(block.lesson_id)
        class_id = lesson_class_map.get(block.lesson_id)
        if teacher_id:
            teacher_slots_used.add((teacher_id, block.output_date, block.ts_id))
        if class_id:
            class_slots_used.add((class_id, block.output_date, block.ts_id))
        room_slots_used.add((block.room_id, block.output_date, block.ts_id))

    effective_end = min(window_end_date, hard_end_date)
    current = window_start_date
    iterations = 0

    while current <= effective_end:
        if current in blocked_dates or current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        if all(v <= 0 for v in remaining.values()):
            break

        dow = current.weekday()
        day_slots = usable_slots_by_dow.get(dow, [])

        # Daily round-robin: sorted by remaining backlog desc, tiebreak by lesson_id
        # Re-sort each day so lessons that received less recently are still behind
        # those with genuinely more total backlog.
        active_lessons = [
            lid for lid in remaining if remaining[lid] > 0
        ]
        day_sorted = sorted(
            active_lessons,
            key=lambda lid: (-remaining[lid], lid),
        )

        # daily_count[lesson_id] = number of blocks placed for that lesson today
        daily_count: dict[int, int] = defaultdict(int)

        for pass_num in range(max_blocks_per_lesson_per_day):
            any_placed_this_pass = False

            for lesson_id in day_sorted:
                if remaining.get(lesson_id, 0) <= 0:
                    continue
                # Only attempt this lesson if it has placed exactly pass_num blocks
                # so far today (i.e., one block per pass → round-robin)
                if daily_count[lesson_id] != pass_num:
                    continue

                teacher_id = lesson_teacher_map.get(lesson_id)
                class_id = lesson_class_map.get(lesson_id)
                required_type = lesson_room_type_map.get(lesson_id, "normal")

                # Try each available timeslot for this lesson (first-fit)
                for ts_info in day_slots:
                    ts_id = ts_info.ts_id

                    # HC2: teacher conflict
                    if teacher_id and (teacher_id, current, ts_id) in teacher_slots_used:
                        continue
                    # HC3: class conflict
                    if class_id and (class_id, current, ts_id) in class_slots_used:
                        continue

                    # HC1 + HC4: find a compatible room that is free
                    placed_room: _RoomInfo | None = None
                    for room_info in rooms_by_type.get(required_type, []):
                        if (room_info.room_id, current, ts_id) not in room_slots_used:
                            placed_room = room_info
                            break

                    if placed_room is None:
                        continue

                    # Place the block
                    fill_blocks.append(ScheduledBlockV2(
                        lesson_id=lesson_id,
                        class_id=class_id or 0,
                        ts_id=ts_id,
                        room_id=placed_room.room_id,
                        output_date=current,
                        duration_minutes=ts_info.duration_minutes,
                    ))
                    remaining[lesson_id] = max(0, remaining[lesson_id] - ts_info.duration_minutes)

                    if teacher_id:
                        teacher_slots_used.add((teacher_id, current, ts_id))
                    if class_id:
                        class_slots_used.add((class_id, current, ts_id))
                    room_slots_used.add((placed_room.room_id, current, ts_id))
                    daily_count[lesson_id] += 1
                    any_placed_this_pass = True
                    break  # Got 1 block for this lesson in this pass → next lesson

            if not any_placed_this_pass:
                break  # No lesson could be placed in this pass → stop for today

        current += timedelta(days=1)
        iterations += 1

    backlog_remaining = sum(max(0, v) for v in remaining.values())
    all_blocks = list(primary_blocks) + fill_blocks

    logger.info(
        "F.02 fill-opportunistic concluído",
        primary=len(primary_blocks),
        fill_added=len(fill_blocks),
        backlog_remaining_minutes=backlog_remaining,
        iterations=iterations,
    )

    return FillOpportunisticResult(
        all_blocks=all_blocks,
        primary_blocks=primary_blocks,
        fill_blocks=fill_blocks,
        backlog_remaining_minutes=backlog_remaining,
        fill_iterations=iterations,
    )


# ---------------------------------------------------------------------------
# F.03 — Residual transparente
# ---------------------------------------------------------------------------

@dataclass
class ResidualSummary:
    """F.03: Resumo transparente de carga remanescente pós-fill."""
    backlog_total_minutes: int
    backlog_scheduled_minutes: int
    backlog_remaining_minutes: int
    backlog_remaining_hours: float
    hard_limit_reached: bool
    hard_end_date: date | None
    detail: str | None


def compute_residual_summary(
    backlog_by_lesson: dict[int, int],
    fill_result: FillOpportunisticResult,
    *,
    hard_end_date: date | None,
) -> ResidualSummary:
    """F.03: Computes and returns transparent residual after fill.

    If backlog_remaining_minutes > 0, the hard_end_date physically prevents
    scheduling all remaining load. This is surfaced explicitly (never masked).
    """
    total_backlog = sum(max(0, v) for v in backlog_by_lesson.values())
    remaining = fill_result.backlog_remaining_minutes
    scheduled = max(0, total_backlog - remaining)
    hard_limit_reached = remaining > 0

    detail: str | None = None
    if hard_limit_reached and hard_end_date:
        hours_left = round(remaining / 60, 1)
        detail = (
            f"Data-limite rígida atingida ({hard_end_date.isoformat()}); "
            f"ficaram por agendar {hours_left}h de carga curricular."
        )

    return ResidualSummary(
        backlog_total_minutes=total_backlog,
        backlog_scheduled_minutes=scheduled,
        backlog_remaining_minutes=remaining,
        backlog_remaining_hours=round(remaining / 60, 1),
        hard_limit_reached=hard_limit_reached,
        hard_end_date=hard_end_date,
        detail=detail,
    )
