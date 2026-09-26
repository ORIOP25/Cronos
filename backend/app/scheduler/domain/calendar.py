"""School-local periods and physical stability boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class Period:
    school_date: date
    start_local: time
    end_local: time
    timezone_name: str
    start_utc: datetime
    end_utc: datetime

    def __post_init__(self) -> None:
        if type(self.school_date) is not date:
            raise ValueError("Period school date must be a date.")
        if any(
            type(value) is not time or value.tzinfo is not None or value.second or value.microsecond
            for value in (self.start_local, self.end_local)
        ):
            raise ValueError("Period endpoints must be naive minute-precision local times.")
        if self.start_local >= self.end_local:
            raise ValueError("Period duration must be positive within one school date.")
        try:
            zone = ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
            raise ValueError("Unknown school timezone.") from exc
        for name in ("start_utc", "end_utc"):
            value = getattr(self, name)
            if (
                type(value) is not datetime
                or value.tzinfo is None
                or value.utcoffset() != timedelta(0)
            ):
                raise ValueError(f"Period {name} must be a UTC instant.")
        if self.end_utc <= self.start_utc:
            raise ValueError("Physical period duration must be positive.")
        if (
            _unambiguous_utc(self.school_date, self.start_local, zone) != self.start_utc
            or _unambiguous_utc(self.school_date, self.end_local, zone) != self.end_utc
        ):
            raise ValueError("Period UTC instants do not match its local school times.")

    @property
    def duration_minutes(self) -> int:
        return int((self.end_utc - self.start_utc).total_seconds() // 60)

    def overlaps(self, other: Period) -> bool:
        return self.start_utc < other.end_utc and other.start_utc < self.end_utc


def _unambiguous_utc(day: date, local_time: time, zone: ZoneInfo) -> datetime:
    local = datetime.combine(day, local_time)
    candidates = set()
    for fold in (0, 1):
        instant = local.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == local:
            candidates.add(instant)
    if len(candidates) != 1:
        raise ValueError("Local time is ambiguous or does not exist in the school timezone.")
    return candidates.pop()


def normalize_period(
    school_date: date, start_local: time, end_local: time, timezone_name: str
) -> Period:
    if type(school_date) is not date:
        raise ValueError("school_date must be a date.")
    if any(
        type(value) is not time or value.tzinfo is not None or value.second or value.microsecond
        for value in (start_local, end_local)
    ):
        raise ValueError("Period endpoints must be naive minute-precision local times.")
    if start_local >= end_local:
        raise ValueError("Period duration must be positive within one school date.")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise ValueError("Unknown school timezone.") from exc
    start_utc = _unambiguous_utc(school_date, start_local, zone)
    end_utc = _unambiguous_utc(school_date, end_local, zone)
    if end_utc <= start_utc:
        raise ValueError("Physical period duration must be positive.")
    return Period(school_date, start_local, end_local, timezone_name, start_utc, end_utc)


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


def protected_grid_dates(
    dates: tuple[date, ...], school_today: date, count: int
) -> tuple[date, ...]:
    if type(school_today) is not date or type(count) is not int or count < 0:
        raise ValueError("Protected grid window is invalid.")
    return tuple(day for day in dates if day >= school_today)[:count]


def is_physically_protected(
    period: Period, now_utc: datetime, protected_dates: tuple[date, ...]
) -> bool:
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware.")
    return period.start_utc <= now_utc or period.school_date in protected_dates
