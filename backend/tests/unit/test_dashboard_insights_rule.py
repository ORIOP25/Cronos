"""Unit tests for the pure dashboard insight rules."""

from datetime import UTC, date, datetime

from app.scheduler.domain.dashboard_insights import (
    DebtEvent,
    LessonFact,
    planned_minutes_to_date,
    teacher_totals,
    weekly_debt,
    weekly_pulse,
)

MONDAY = date(2026, 10, 19)
NEXT_MONDAY = date(2026, 10, 26)
NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)


def lesson(
    lesson_id,
    day,
    *,
    hour=9,
    status=None,
    decision=None,
    teacher_id=1,
    class_id=10,
    unit_key=None,
    minutes=50,
    credit_minutes=None,
):
    return LessonFact(
        lesson_id=lesson_id,
        school_date=day,
        ends_at=datetime(day.year, day.month, day.day, hour, tzinfo=UTC),
        minutes=minutes,
        credit_minutes=credit_minutes or minutes,
        unit_key=unit_key or f"U:{lesson_id}",
        teacher_id=teacher_id,
        class_id=class_id,
        status=status,
        decision=decision,
    )


def test_weekly_pulse_counts_given_absent_substituted_and_missing_lessons():
    lessons = [
        lesson(1, MONDAY, status="COMPLETED"),
        lesson(2, MONDAY, status="OCCURRENCE", decision="SUBSTITUTED"),
        lesson(3, MONDAY, status="OCCURRENCE", decision="GAP"),
        lesson(4, MONDAY, status="OCCURRENCE"),
        lesson(5, MONDAY),
        lesson(6, MONDAY, status="REVOKED"),
        lesson(7, NEXT_MONDAY, status="COMPLETED"),
        lesson(8, date(2026, 10, 28)),
    ]

    weeks = weekly_pulse(lessons, MONDAY, NEXT_MONDAY, NOW)

    assert [week.week_start for week in weeks] == [MONDAY, NEXT_MONDAY]
    first, second = weeks
    assert (first.lessons_due, first.lessons_given, first.missing_logs) == (6, 2, 2)
    assert (first.absence_minutes, first.substituted_minutes) == (150, 50)
    assert (second.lessons_due, second.lessons_given, second.missing_logs) == (1, 1, 0)


def test_joint_lesson_absence_counts_the_teacher_time_once():
    lessons = [
        lesson(1, MONDAY, status="OCCURRENCE", unit_key="J:7", class_id=10),
        lesson(2, MONDAY, status="OCCURRENCE", unit_key="J:7", class_id=11),
    ]

    (week,) = weekly_pulse(lessons, MONDAY, MONDAY, NOW)
    absence, _ = teacher_totals(lessons, NOW)

    assert week.absence_minutes == 50
    assert week.lessons_due == 2
    assert absence == {1: 50}


def test_teacher_totals_rank_absence_minutes_and_missing_logs():
    lessons = [
        lesson(1, MONDAY, status="OCCURRENCE", teacher_id=1),
        lesson(2, MONDAY, teacher_id=2),
        lesson(3, MONDAY, status="REVOKED", teacher_id=2),
        lesson(4, date(2026, 10, 28), teacher_id=3),
    ]

    absence, missing = teacher_totals(lessons, NOW)

    assert absence == {1: 50}
    assert missing == {2: 2}


def test_planned_minutes_to_date_sum_each_class_through_today():
    lessons = [
        lesson(1, MONDAY, class_id=10),
        lesson(2, NEXT_MONDAY, class_id=10, credit_minutes=100),
        lesson(3, date(2026, 10, 28), class_id=10),
        lesson(4, MONDAY, class_id=11),
    ]

    assert planned_minutes_to_date(lessons, date(2026, 10, 27)) == {10: 150, 11: 50}


def test_weekly_debt_keeps_each_claim_balance_at_each_week_end():
    events = [
        DebtEvent(claim_id=1, class_id=10, day=date(2026, 10, 20), delta_minutes=100),
        DebtEvent(claim_id=1, class_id=10, day=date(2026, 10, 27), delta_minutes=-60),
        DebtEvent(claim_id=2, class_id=11, day=date(2026, 10, 21), delta_minutes=50),
        DebtEvent(claim_id=2, class_id=11, day=date(2026, 10, 22), delta_minutes=-80),
        DebtEvent(claim_id=3, class_id=10, day=date(2026, 11, 3), delta_minutes=30),
    ]

    assert weekly_debt(events, MONDAY, NEXT_MONDAY) == [{10: 100}, {10: 40}]


def test_empty_ranges_give_no_weeks():
    assert weekly_pulse([], NEXT_MONDAY, MONDAY, NOW) == []
    assert weekly_debt([], NEXT_MONDAY, MONDAY) == []
