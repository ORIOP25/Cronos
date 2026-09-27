from datetime import UTC, date, datetime, time

import pytest

from app.scheduler.domain.calendar import (
    first_editable_grid_date,
    grid_dates,
    is_physically_protected,
    normalize_period,
    protected_grid_dates,
)
from app.scheduler.domain.projection import (
    FutureLesson,
    ModuleRequirement,
    ModuleSlice,
    project_module_slices,
)

MONDAY = date(2026, 9, 21)


def test_adjacent_periods_do_not_overlap_but_intersecting_periods_do():
    first = normalize_period(date(2026, 9, 22), time(9), time(9, 50), "Europe/Lisbon")
    adjacent = normalize_period(date(2026, 9, 22), time(9, 50), time(10, 40), "Europe/Lisbon")
    overlap = normalize_period(date(2026, 9, 22), time(9, 49), time(10, 40), "Europe/Lisbon")

    assert first.duration_minutes == 50
    assert not first.overlaps(adjacent)
    assert first.overlaps(overlap)


@pytest.mark.parametrize(
    ("day", "start", "end"),
    [
        (date(2026, 3, 29), time(1, 30), time(2, 30)),  # nonexistent local time
        (date(2026, 10, 25), time(1, 30), time(2, 30)),  # ambiguous local time
        (date(2026, 9, 22), time(9), time(9)),
    ],
)
def test_invalid_local_periods_are_rejected(day, start, end):
    with pytest.raises(ValueError):
        normalize_period(day, start, end, "Europe/Lisbon")


def test_physical_duration_accounts_for_daylight_saving_change():
    period = normalize_period(date(2026, 3, 29), time(0, 30), time(2, 30), "Europe/Lisbon")

    assert period.duration_minutes == 60


def test_t08_nine_grid_days_count_only_configured_weekdays():
    school_today = date(2026, 9, 21)
    horizon = date(2026, 10, 20)
    for weekdays in ({0, 2, 4}, {0, 1, 2, 3, 4}, set(range(7))):
        dates = grid_dates(school_today, horizon, weekdays)
        protected = protected_grid_dates(dates, school_today, 9)

        assert len(protected) == 9
        assert protected == dates[:9]
        assert dates[9] not in protected


def test_t09_holiday_still_counts_as_grid_day_and_approval_uses_new_today():
    dates = grid_dates(date(2026, 12, 23), date(2026, 12, 30), {0, 1, 2, 3, 4})
    assert date(2026, 12, 25) in dates
    assert protected_grid_dates(dates, date(2026, 12, 23), 3)[-1] == date(2026, 12, 25)
    assert protected_grid_dates(dates, date(2026, 12, 24), 3)[-1] == date(2026, 12, 28)


def test_zero_day_window_protects_started_periods_but_not_future_ones():
    periods = (
        normalize_period(date(2026, 9, 22), time(9), time(9, 50), "Europe/Lisbon"),
        normalize_period(date(2026, 9, 22), time(10), time(10, 50), "Europe/Lisbon"),
    )
    now = datetime(2026, 9, 22, 8, 30, tzinfo=UTC)

    assert is_physically_protected(periods[0], now, ())
    assert not is_physically_protected(periods[1], now, ())
    assert is_physically_protected(periods[1], now, (date(2026, 9, 22),))


def test_t03_protected_wednesday_keeps_its_period_when_modules_shift():
    wednesday = date(2026, 9, 23)
    period = normalize_period(wednesday, time(9), time(9, 50), "Europe/Lisbon")
    protected = protected_grid_dates(
        grid_dates(date(2026, 9, 22), date(2026, 9, 24), {0, 1, 2, 3, 4}),
        date(2026, 9, 22),
        2,
    )
    lessons = (
        FutureLesson(20, wednesday, 9 * 60, 50, 50),
        FutureLesson(30, date(2026, 9, 24), 9 * 60, 50, 50),
        FutureLesson(40, date(2026, 9, 24), 10 * 60, 50, 50),
    )

    assert is_physically_protected(period, datetime(2026, 9, 22, 8, tzinfo=UTC), protected)
    assert project_module_slices(
        (ModuleRequirement(1, 1, 75), ModuleRequirement(2, 2, 75)),
        completed_minutes={},
        lessons=lessons,
    )[0] == ModuleSlice(20, 1, 0, 50)


def test_first_editable_date_counts_selected_grid_days():
    assert first_editable_grid_date(MONDAY, MONDAY, {0, 1, 2}, 9) == date(2026, 10, 12)
    assert first_editable_grid_date(MONDAY, MONDAY, {0, 1, 2, 3, 4}, 9) == date(2026, 10, 2)
    assert first_editable_grid_date(MONDAY, MONDAY, set(range(7)), 9) == date(2026, 9, 30)


def test_first_editable_date_with_zero_window_returns_the_base_date():
    assert first_editable_grid_date(MONDAY, MONDAY, {0, 1, 2}, 0) == MONDAY
    assert first_editable_grid_date(MONDAY, date(2026, 9, 28), {0, 1, 2}, 0) == date(2026, 9, 28)


def test_first_editable_date_protects_the_first_selected_day():
    assert first_editable_grid_date(MONDAY, MONDAY, {0, 1, 2, 3, 4}, 1) == date(2026, 9, 22)


def test_first_editable_date_skips_days_outside_the_grid():
    sunday = date(2026, 9, 20)
    assert first_editable_grid_date(sunday, MONDAY, {0, 1, 2, 3, 4}, 1) == date(2026, 9, 22)


def test_first_editable_date_counts_from_the_later_of_today_and_school_start():
    thursday = date(2026, 9, 24)
    assert first_editable_grid_date(MONDAY, thursday, {3, 4}, 1) == date(2026, 9, 25)
    assert first_editable_grid_date(MONDAY, thursday, {0, 1, 2, 3, 4}, 2) == date(2026, 9, 28)


def test_first_editable_date_without_grid_returns_the_base_date():
    assert first_editable_grid_date(MONDAY, MONDAY, set(), 9) == MONDAY


def test_first_editable_date_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        first_editable_grid_date(MONDAY, MONDAY, {0}, -1)
    with pytest.raises(ValueError):
        first_editable_grid_date(MONDAY, MONDAY, {7}, 1)
