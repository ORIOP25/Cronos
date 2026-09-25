"""Pure school-grid calendar helpers shared by scheduler boundaries."""

from __future__ import annotations

from datetime import date, timedelta


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
