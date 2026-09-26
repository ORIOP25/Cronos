"""Pure timetable-block calculation with a usual break and per-position overrides."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

MIN_SLOT_MINUTES = 15
MAX_SLOT_MINUTES = 120
MAX_BREAK_MINUTES = 60


class TimetableConfigError(ValueError):
    """Invalid timetable configuration, addressed by a stable error code."""

    def __init__(self, code: str, message: str, position: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.position = position


@dataclass(frozen=True)
class BreakOverride:
    after_slot: int
    duration_minutes: int


@dataclass(frozen=True)
class DailySlot:
    index: int
    start: time
    end: time
    break_after_minutes: int


def _is_int(value: object) -> bool:
    return type(value) is int


def build_daily_slots(
    opening_time: time,
    closing_time: time,
    slot_duration_minutes: int,
    break_duration_minutes: int = 0,
    break_overrides: tuple[BreakOverride, ...] = (),
) -> tuple[DailySlot, ...]:
    """Build one day of lessons, applying the usual break or a per-position override.

    A lesson is added only when it fits entirely before closing time. The break
    after the last lesson is always zero, and an override that ends up without a
    following lesson is an error instead of a silent no-op.
    """
    if type(opening_time) is not time or type(closing_time) is not time:
        raise TimetableConfigError("timetable.invalid_window", "As horas devem ser horas válidas.")
    if not _is_int(slot_duration_minutes) or not (
        MIN_SLOT_MINUTES <= slot_duration_minutes <= MAX_SLOT_MINUTES
    ):
        raise TimetableConfigError(
            "timetable.invalid_slot_duration",
            f"A duração da aula deve estar entre {MIN_SLOT_MINUTES} e {MAX_SLOT_MINUTES} minutos.",
        )
    if not _is_int(break_duration_minutes) or not (
        0 <= break_duration_minutes <= MAX_BREAK_MINUTES
    ):
        raise TimetableConfigError(
            "timetable.invalid_break_duration",
            f"A pausa habitual deve estar entre 0 e {MAX_BREAK_MINUTES} minutos.",
        )
    if closing_time <= opening_time:
        raise TimetableConfigError(
            "timetable.invalid_window",
            "A hora de fecho deve ser posterior à hora de abertura.",
        )

    override_by_position: dict[int, int] = {}
    for override in break_overrides:
        if type(override) is not BreakOverride:
            raise TimetableConfigError(
                "timetable.invalid_override",
                "Cada ajuste de intervalo deve indicar a aula e a duração.",
            )
        if not _is_int(override.after_slot) or override.after_slot < 1:
            raise TimetableConfigError(
                "timetable.invalid_override_position",
                "A posição do ajuste deve ser a aula após a qual ocorre a pausa (a primeira aula é 1).",
            )
        if override.after_slot in override_by_position:
            raise TimetableConfigError(
                "timetable.duplicate_override_position",
                f"Existe mais de um ajuste para a aula {override.after_slot}.",
            )
        if not _is_int(override.duration_minutes) or not (
            0 <= override.duration_minutes <= MAX_BREAK_MINUTES
        ):
            raise TimetableConfigError(
                "timetable.invalid_override_duration",
                f"A duração do ajuste deve estar entre 0 e {MAX_BREAK_MINUTES} minutos.",
            )
        override_by_position[override.after_slot] = override.duration_minutes

    slots: list[DailySlot] = []
    current = datetime.combine(date.min, opening_time)
    limit = datetime.combine(date.min, closing_time)
    while current + timedelta(minutes=slot_duration_minutes) <= limit:
        end = current + timedelta(minutes=slot_duration_minutes)
        index = len(slots) + 1
        break_after = override_by_position.get(index, break_duration_minutes)
        slots.append(
            DailySlot(
                index=index,
                start=current.time(),
                end=end.time(),
                break_after_minutes=break_after,
            )
        )
        current = end + timedelta(minutes=break_after)

    unused = sorted(position for position in override_by_position if position >= len(slots))
    if unused:
        raise TimetableConfigError(
            "timetable.unused_break_override",
            f"O ajuste de intervalo após a aula {unused[0]} não tem aula seguinte na grelha resultante.",
            position=unused[0],
        )

    if slots:
        last = slots[-1]
        slots[-1] = DailySlot(
            index=last.index,
            start=last.start,
            end=last.end,
            break_after_minutes=0,
        )
    return tuple(slots)
