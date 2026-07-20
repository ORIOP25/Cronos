"""Pure planning helpers shared by scheduler preflight and generation engines."""

import math
from datetime import date, timedelta

MIN_NEAR_FUTURE_HORIZON_WEEKS = 1
MAX_NEAR_FUTURE_HORIZON_WEEKS = 12


def build_blocked_dates(calendar_events: list) -> set[date]:
    blocked: set[date] = set()
    for event in calendar_events:
        current = event.start_date
        while current <= event.end_date:
            blocked.add(current)
            current += timedelta(days=1)
    return blocked


def compute_remaining_minutes(
    lesson,
    modules_by_subject: dict,
    progress_map: dict,
) -> int:
    remaining = 0
    active_found = False
    modules = sorted(
        modules_by_subject.get(lesson.subject_id, []),
        key=lambda module: getattr(module, "order", 0),
    )
    for module in modules:
        total_hours = max(0.0, float(getattr(module, "hours_total", 0) or 0))
        completed_hours = min(
            total_hours,
            max(0.0, float(progress_map.get((lesson.class_id, module.id), 0) or 0)),
        )
        module_remaining = int(round((total_hours - completed_hours) * 60))
        if module_remaining > 0:
            active_found = True
        if active_found:
            remaining += max(0, module_remaining)
    return remaining


def resolve_expansion_start_date(
    school_start_date: date,
    *,
    adaptive_repair: bool,
    repair_window_days: int,
) -> date:
    if not adaptive_repair:
        return school_start_date
    editable_start_date = date.today() + timedelta(days=max(0, repair_window_days))
    return max(school_start_date, editable_start_date)


def build_primary_window(
    *,
    window_start_date: date,
    hard_end_date: date,
    blocked_dates: set[date],
    horizon_weeks: int,
) -> dict[str, int | date]:
    safe_weeks = max(1, int(horizon_weeks))
    end_date = min(
        hard_end_date,
        window_start_date + timedelta(days=(safe_weeks * 7) - 1),
    )
    if end_date < window_start_date:
        return {
            "horizon_weeks": safe_weeks,
            "window_start_date": window_start_date,
            "window_end_date": window_start_date,
            "window_total_days": 0,
            "window_blocked_days": 0,
            "window_usable_days": 0,
        }
    total_days = (end_date - window_start_date).days + 1
    blocked_days = sum(window_start_date <= blocked <= end_date for blocked in blocked_dates)
    return {
        "horizon_weeks": safe_weeks,
        "window_start_date": window_start_date,
        "window_end_date": end_date,
        "window_total_days": total_days,
        "window_blocked_days": blocked_days,
        "window_usable_days": max(0, total_days - blocked_days),
    }


def estimate_capacity_minutes_in_range(
    timeslots: list,
    room_count: int,
    blocked_dates: set[date],
    start_date: date,
    end_date: date,
) -> int:
    if end_date < start_date or room_count <= 0:
        return 0
    minutes_by_weekday: dict[int, int] = {}
    for timeslot in timeslots:
        start = timeslot.start_time.hour * 60 + timeslot.start_time.minute
        end = timeslot.end_time.hour * 60 + timeslot.end_time.minute
        minutes_by_weekday[timeslot.day_of_week] = minutes_by_weekday.get(
            timeslot.day_of_week, 0
        ) + max(0, end - start)
    total = 0
    current = start_date
    while current <= end_date:
        if current not in blocked_dates:
            total += minutes_by_weekday.get(current.weekday(), 0) * room_count
        current += timedelta(days=1)
    return max(0, total)


def select_adaptive_near_future_weeks(
    *,
    class_count: int,
    teacher_count: int,
    room_count: int,
    timeslot_count: int,
    lesson_count: int,
    blocked_dates_count: int,
    remaining_days: int,
) -> int:
    complexity = max(0, class_count) * 3
    complexity += max(0, teacher_count) * 2
    complexity += max(0, room_count) + max(0, lesson_count)
    if timeslot_count < 25:
        complexity += 20
    if blocked_dates_count > 10:
        complexity += blocked_dates_count // 2
    if remaining_days < 90:
        complexity += 20
    weeks = 12 if complexity < 45 else 8 if complexity < 90 else 6
    if complexity >= 150:
        weeks = 4 if complexity < 240 else 2
    remaining_weeks = max(1, math.ceil(max(1, remaining_days) / 7))
    return max(
        MIN_NEAR_FUTURE_HORIZON_WEEKS,
        min(MAX_NEAR_FUTURE_HORIZON_WEEKS, weeks, remaining_weeks),
    )
