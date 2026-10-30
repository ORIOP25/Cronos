"""Weekly trends and rankings that the admin dashboard derives from lessons and debt."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

WEEK = timedelta(days=7)


@dataclass(frozen=True)
class LessonFact:
    lesson_id: int
    school_date: date
    ends_at: datetime
    minutes: int
    credit_minutes: int
    unit_key: str
    teacher_id: int
    class_id: int
    status: str | None
    decision: str | None

    @property
    def teacher_unit(self) -> object:
        # Joint lessons of one group share a unit key: the teacher teaches them once.
        return self.unit_key if self.unit_key.startswith("J:") else self.lesson_id

    @property
    def is_absence(self) -> bool:
        return self.status == "OCCURRENCE"

    @property
    def is_given(self) -> bool:
        return self.status == "COMPLETED" or (self.is_absence and self.decision == "SUBSTITUTED")

    def is_missing_log(self, now: datetime) -> bool:
        # A revoked occurrence sends the lesson back to "no record yet".
        return self.ends_at <= now and self.status in (None, "REVOKED")


@dataclass(frozen=True)
class WeekPulse:
    week_start: date
    lessons_due: int
    lessons_given: int
    absence_minutes: int
    substituted_minutes: int
    missing_logs: int


@dataclass(frozen=True)
class DebtEvent:
    claim_id: int
    class_id: int
    day: date
    delta_minutes: int


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _weeks(first_week: date, last_week: date) -> list[date]:
    weeks = []
    current = first_week
    while current <= last_week:
        weeks.append(current)
        current += WEEK
    return weeks


def weekly_pulse(
    lessons: Iterable[LessonFact], first_week: date, last_week: date, now: datetime
) -> list[WeekPulse]:
    weeks = _weeks(first_week, last_week)
    by_week: dict[date, list[LessonFact]] = defaultdict(list)
    for fact in lessons:
        by_week[week_start(fact.school_date)].append(fact)
    pulse = []
    for start in weeks:
        facts = by_week[start]
        due = [fact for fact in facts if fact.ends_at <= now]
        absences = {fact.teacher_unit: fact for fact in facts if fact.is_absence}
        pulse.append(
            WeekPulse(
                week_start=start,
                lessons_due=len(due),
                lessons_given=sum(fact.is_given for fact in due),
                absence_minutes=sum(fact.minutes for fact in absences.values()),
                substituted_minutes=sum(
                    fact.minutes for fact in absences.values() if fact.decision == "SUBSTITUTED"
                ),
                missing_logs=sum(fact.is_missing_log(now) for fact in due),
            )
        )
    return pulse


def teacher_totals(
    lessons: Iterable[LessonFact], now: datetime
) -> tuple[Counter[int], Counter[int]]:
    """Absence minutes and missing lesson logs per teacher, for the whole year."""
    absences: dict[object, LessonFact] = {}
    missing: Counter[int] = Counter()
    for fact in lessons:
        if fact.is_absence:
            absences[fact.teacher_unit] = fact
        if fact.is_missing_log(now):
            missing[fact.teacher_id] += 1
    absence_minutes: Counter[int] = Counter()
    for fact in absences.values():
        absence_minutes[fact.teacher_id] += fact.minutes
    return absence_minutes, missing


def planned_minutes_to_date(lessons: Iterable[LessonFact], today: date) -> Counter[int]:
    planned: Counter[int] = Counter()
    for fact in lessons:
        if fact.school_date <= today:
            planned[fact.class_id] += fact.credit_minutes
    return planned


def weekly_debt(
    events: Sequence[DebtEvent], first_week: date, last_week: date
) -> list[dict[int, int]]:
    """Open debt minutes per class at the end of each week.

    Each claim keeps its own balance and never goes below zero, as in the debt ledger.
    The last week takes every remaining event: a gap decided ahead is dated on its
    future lesson but is already owed, as in the debt ledger.
    """
    ordered = sorted(events, key=lambda event: event.day)
    balances: dict[int, int] = defaultdict(int)
    class_of: dict[int, int] = {}
    series = []
    index = 0
    for start in _weeks(first_week, last_week):
        week_end = date.max if start == last_week else start + timedelta(days=6)
        while index < len(ordered) and ordered[index].day <= week_end:
            event = ordered[index]
            balances[event.claim_id] += event.delta_minutes
            class_of[event.claim_id] = event.class_id
            index += 1
        by_class: Counter[int] = Counter()
        for claim_id, minutes in balances.items():
            if minutes > 0:
                by_class[class_of[claim_id]] += minutes
        series.append(dict(by_class))
    return series
