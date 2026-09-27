"""Pure school-grid calendar helpers shared by scheduler boundaries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from typing import Any

INTERNSHIP_FLOW_EVENT_TYPE = "internship_flow"


def grid_dates(first: date, last: date, weekdays: set[int]) -> tuple[date, ...]:
    if type(first) is not date or type(last) is not date or first > last:
        raise ValueError("Grid date range is invalid.")
    if not weekdays or any(type(day) is not int or day < 0 or day > 6 for day in weekdays):
        raise ValueError("Grid weekdays must be numbers from 0 to 6.")
    days = (last - first).days + 1
    return tuple(
        day
        for offset in range(days)
        if (day := first + timedelta(days=offset)).weekday() in weekdays
    )


def event_blocks_class(event: Mapping[str, Any], class_id: int) -> bool:
    """A general event blocks the school; a flow blocks only its classes."""
    if _value(event.get("event_type")) != INTERNSHIP_FLOW_EVENT_TYPE:
        return True
    return class_id in (event.get("class_ids") or ())


def event_dates(event: Mapping[str, Any]) -> tuple[date, ...]:
    start = _event_date(event["start_date"])
    end = _event_date(event["end_date"])
    if end < start:
        return ()
    return tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))


def blocked_dates_for_class(events: Iterable[Mapping[str, Any]], class_id: int) -> set[date]:
    blocked: set[date] = set()
    for event in events:
        if event_blocks_class(event, class_id):
            blocked.update(event_dates(event))
    return blocked


def blocked_dates_by_class(
    events: Iterable[Mapping[str, Any]],
    class_ids: Iterable[int],
) -> dict[int, set[date]]:
    wanted = tuple(dict.fromkeys(class_ids))
    blocked: dict[int, set[date]] = {class_id: set() for class_id in wanted}
    for event in events:
        dates = event_dates(event)
        if not dates:
            continue
        if _value(event.get("event_type")) != INTERNSHIP_FLOW_EVENT_TYPE:
            for class_id in wanted:
                blocked[class_id].update(dates)
            continue
        for class_id in event.get("class_ids") or ():
            if class_id in blocked:
                blocked[class_id].update(dates)
    return blocked


def _event_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def first_editable_grid_date(
    school_today: date,
    school_start_date: date,
    weekdays: set[int],
    window_days: int,
) -> date:
    """Return the first editable date after protecting a window of grid days."""
    if type(school_today) is not date or type(school_start_date) is not date:
        raise ValueError("School dates must be dates.")
    if type(window_days) is not int or window_days < 0:
        raise ValueError("Repair window must be a non-negative integer.")
    base = max(school_today, school_start_date)
    if window_days == 0 or not weekdays:
        return base
    horizon = base + timedelta(days=7 * (window_days + 1))
    return grid_dates(base, horizon, weekdays)[window_days]
