from datetime import date, time

import pytest

from app.scheduler.domain.grid_versions import (
    GridVersionRef,
    build_grid_configuration,
    select_effective_grid_version,
)

V1 = GridVersionRef(id=1, effective_date=date(2025, 9, 15), state="ACTIVE")
V2 = GridVersionRef(id=2, effective_date=date(2026, 1, 5), state="ACTIVE")
PENDING = GridVersionRef(id=3, effective_date=date(2026, 3, 2), state="PENDING")
REJECTED = GridVersionRef(id=4, effective_date=date(2026, 2, 2), state="REJECTED")


def test_selects_the_most_recent_active_version_not_after_the_date():
    assert select_effective_grid_version([V1, V2, PENDING, REJECTED], date(2025, 10, 1)) == 1
    assert select_effective_grid_version([V1, V2, PENDING, REJECTED], date(2026, 1, 5)) == 2
    assert select_effective_grid_version([V1, V2, PENDING, REJECTED], date(2026, 6, 1)) == 2


def test_ignores_pending_and_rejected_versions():
    assert select_effective_grid_version([V1, PENDING, REJECTED], date(2026, 6, 1)) == 1


def test_returns_the_first_version_before_the_year_starts():
    assert select_effective_grid_version([V1, V2], date(2025, 8, 1)) == 1
    assert select_effective_grid_version([V2, V1], date(2025, 8, 1)) == 1


def test_pending_version_is_only_visible_to_the_job_that_references_it():
    assert (
        select_effective_grid_version([V1, V2, PENDING], date(2025, 10, 1), pending_version_id=3)
        == 3
    )
    assert (
        select_effective_grid_version([V1, V2, PENDING], date(2025, 10, 1), pending_version_id=99)
        is None
    )


def test_returns_none_without_versions():
    assert select_effective_grid_version([], date(2026, 1, 1)) is None
    assert select_effective_grid_version([PENDING, REJECTED], date(2026, 1, 1)) is None


def test_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        select_effective_grid_version([V1], "2026-01-01")
    with pytest.raises(ValueError):
        select_effective_grid_version(
            [GridVersionRef(id=5, effective_date=date(2026, 1, 1), state="BROKEN")],
            date(2026, 1, 1),
        )


def test_builds_the_configuration_of_a_regular_grid():
    configuration = build_grid_configuration(
        [
            (0, time(9, 0), time(9, 50)),
            (0, time(10, 0), time(10, 50)),
            (4, time(9, 0), time(9, 50)),
            (4, time(10, 0), time(10, 50)),
        ]
    )

    assert configuration == {
        "opening_time": "09:00",
        "closing_time": "10:50",
        "slot_duration_minutes": 50,
        "break_duration_minutes": 10,
        "break_overrides": [],
        "days_of_week": [0, 4],
    }


def test_rejects_irregular_grid_configuration():
    assert build_grid_configuration([]) is None
    assert (
        build_grid_configuration(
            [
                (0, time(9, 0), time(9, 50)),
                (0, time(10, 0), time(11, 30)),
            ]
        )
        is None
    )
    assert (
        build_grid_configuration(
            [
                (0, time(9, 0), time(9, 50)),
                (0, time(10, 0), time(10, 50)),
                (1, time(9, 0), time(9, 50)),
            ]
        )
        is None
    )


def test_rejects_a_grid_with_a_variable_break():
    assert (
        build_grid_configuration(
            [
                (0, time(9, 0), time(9, 50)),
                (0, time(10, 0), time(10, 50)),
                (0, time(10, 55), time(11, 45)),
            ]
        )
        is None
    )


def test_rejects_invalid_legacy_blocks():
    assert build_grid_configuration([(0, time(9, 0, 30), time(9, 50, 30))]) is None
    assert build_grid_configuration([(0, time(9, 0), time(9, 10))]) is None
    assert build_grid_configuration([(0, time(9, 0), time(11, 1))]) is None
    assert (
        build_grid_configuration(
            [
                (0, time(9, 0), time(9, 50)),
                (0, time(9, 40), time(10, 30)),
            ]
        )
        is None
    )
    assert (
        build_grid_configuration(
            [
                (0, time(9, 0), time(9, 50)),
                (0, time(10, 51), time(11, 41)),
            ]
        )
        is None
    )
