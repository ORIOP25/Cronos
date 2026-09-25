from datetime import date

import pytest

from app.scheduler.domain.calendar import first_editable_grid_date

MONDAY = date(2026, 9, 21)


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
