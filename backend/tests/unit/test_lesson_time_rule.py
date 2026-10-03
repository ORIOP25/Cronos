"""Unit tests for the pure lesson execution time rule."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.scheduler.domain.lesson_time import execution_allowed

LESSON_END = datetime(2026, 10, 5, 10, 50, tzinfo=UTC)


@pytest.mark.parametrize(
    ("now_utc", "expected"),
    (
        (LESSON_END - timedelta(minutes=50), False),
        (LESSON_END - timedelta(seconds=1), False),
        (LESSON_END, True),
        (LESSON_END + timedelta(seconds=1), True),
        (LESSON_END + timedelta(days=1), True),
    ),
)
def test_execution_only_after_the_planned_end(now_utc, expected):
    assert execution_allowed(now_utc, LESSON_END) is expected


def test_execution_rule_normalizes_timezones_for_the_same_instant():
    same_instant = LESSON_END.astimezone(timezone(timedelta(hours=1)))

    assert execution_allowed(same_instant, LESSON_END) is True


def test_execution_rule_rejects_naive_instants():
    with pytest.raises(ValueError):
        execution_allowed(datetime(2026, 10, 5, 11, 0), LESSON_END)
