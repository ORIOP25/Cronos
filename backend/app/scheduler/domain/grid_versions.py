"""Pure selection of the grid version that applies to a date."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, time

VALID_STATES = frozenset({"PENDING", "ACTIVE", "REJECTED"})


@dataclass(frozen=True)
class GridVersionRef:
    id: int
    effective_date: date
    state: str


def select_effective_grid_version(
    versions: Sequence[GridVersionRef],
    on_date: date,
    pending_version_id: int | None = None,
) -> int | None:
    """Return the grid version id valid on ``on_date``.

    Active versions use the most recent effective date not after the target
    date. Before the first effective date the earliest active version applies so
    a school can be prepared in advance. Pending versions are only visible to
    the job that explicitly references them.
    """
    if type(on_date) is not date:
        raise ValueError("Target date must be a date.")
    for version in versions:
        if type(version) is not GridVersionRef:
            raise ValueError("Grid versions must be references.")
        if version.state not in VALID_STATES:
            raise ValueError(f"Unknown grid version state: {version.state}")

    if pending_version_id is not None:
        for version in versions:
            if version.id == pending_version_id and version.state == "PENDING":
                return version.id
        return None

    actives = [version for version in versions if version.state == "ACTIVE"]
    if not actives:
        return None

    eligible = [version for version in actives if version.effective_date <= on_date]
    if eligible:
        return max(eligible, key=lambda version: (version.effective_date, version.id)).id
    return min(actives, key=lambda version: (version.effective_date, version.id)).id


def _minutes(start: time, end: time) -> int:
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


def _whole_minute(value: time) -> bool:
    return value.second == 0 and value.microsecond == 0


def build_grid_configuration(
    blocks: Sequence[tuple[int, time, time]],
) -> dict | None:
    """Rebuild a regular grid configuration from legacy blocks, else ``None``."""
    if not blocks:
        return None

    by_day: dict[int, list[tuple[time, time]]] = {}
    for day, start, end in blocks:
        if not _whole_minute(start) or not _whole_minute(end) or end <= start:
            return None
        by_day.setdefault(day, []).append((start, end))

    days = sorted(by_day)
    reference: list[tuple[time, time]] | None = None
    usual_break: int | None = None
    for day in days:
        sequence = sorted(by_day[day])
        if not sequence:
            return None
        durations = {_minutes(start, end) for start, end in sequence}
        if len(durations) != 1 or not 15 <= durations.pop() <= 120:
            return None
        if any(
            current[0] < previous[1]
            for previous, current in zip(sequence, sequence[1:], strict=False)
        ):
            return None
        if reference is None:
            reference = sequence
        elif sequence != reference:
            return None
        gaps = [
            _minutes(sequence[index][1], sequence[index + 1][0])
            for index in range(len(sequence) - 1)
        ]
        for gap in gaps:
            if not 0 <= gap <= 60:
                return None
            if usual_break is None:
                usual_break = gap
            elif gap != usual_break:
                return None

    return {
        "opening_time": reference[0][0].strftime("%H:%M"),
        "closing_time": reference[-1][1].strftime("%H:%M"),
        "slot_duration_minutes": _minutes(*reference[0]),
        "break_duration_minutes": usual_break or 0,
        "break_overrides": [],
        "days_of_week": days,
    }
