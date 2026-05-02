"""Testes para funções auxiliares do solver em solver_tasks.py."""

import pytest
from datetime import date, time, timedelta

from app.solver_tasks import (
    _build_blocked_dates,
    _build_timeslot_inputs,
    _build_room_inputs,
    _build_lesson_inputs,
    _resolve_hard_end_date,
    _resolve_lunch_constraints,
    _build_primary_rolling_window,
    _estimate_capacity_minutes_in_range,
    _build_remaining_summary,
)
from app.core.solver_engine import LessonInput, TimeslotInput, RoomInput

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _build_blocked_dates
# ---------------------------------------------------------------------------

class TestBuildBlockedDates:
    def test_single_day_event(self):
        E = type("E", (), {"start_date": date(2026, 3, 15), "end_date": date(2026, 3, 15)})
        result = _build_blocked_dates([E])
        assert result == {date(2026, 3, 15)}

    def test_multi_day_event(self):
        E = type("E", (), {"start_date": date(2026, 3, 15), "end_date": date(2026, 3, 17)})
        result = _build_blocked_dates([E])
        assert result == {date(2026, 3, 15), date(2026, 3, 16), date(2026, 3, 17)}

    def test_multiple_events(self):
        E = type("E", (), {})
        events = [
            type("E", (), {"start_date": date(2026, 3, 15), "end_date": date(2026, 3, 15)}),
            type("E", (), {"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 2)}),
        ]
        result = _build_blocked_dates(events)
        assert date(2026, 3, 15) in result
        assert date(2026, 4, 1) in result
        assert date(2026, 4, 2) in result
        assert len(result) == 3


# ---------------------------------------------------------------------------
# _build_timeslot_inputs
# ---------------------------------------------------------------------------

class TestBuildTimeslotInputs:
    def test_basic_conversion(self):
        T = type("T", (), {"id": 1, "start_time": time(8, 0), "end_time": time(8, 50), "day_of_week": 0})
        result = _build_timeslot_inputs([T])
        assert len(result) == 1
        assert result[0].ts_id == 1
        assert result[0].duration_minutes == 50
        assert result[0].start_minutes == 480

    def test_calculates_end_minutes_correctly(self):
        T = type("T", (), {"id": 1, "start_time": time(9, 15), "end_time": time(10, 30), "day_of_week": 2})
        result = _build_timeslot_inputs([T])
        assert result[0].duration_minutes == 75
        assert result[0].start_minutes == 555
        assert result[0].end_minutes == 630


# ---------------------------------------------------------------------------
# _build_room_inputs
# ---------------------------------------------------------------------------

class TestBuildRoomInputs:
    def test_conversion(self):
        R = type("R", (), {"id": 5, "type": type("RT", (), {"value": "lab"})})
        result = _build_room_inputs([R])
        assert len(result) == 1
        assert result[0].room_id == 5
        assert result[0].room_type == "lab"


# ---------------------------------------------------------------------------
# _resolve_hard_end_date
# ---------------------------------------------------------------------------

class TestResolveHardEndDate:
    def test_explicit_hard_end(self):
        S = type("S", (), {
            "school_hard_end_date": date(2026, 7, 15),
            "school_target_end_date": date(2026, 6, 30),
            "school_start_date": date(2025, 9, 1),
        })
        result = _resolve_hard_end_date(S)
        assert result == date(2026, 7, 15)

    def test_fallback_to_target_year_july_31(self):
        S = type("S", (), {
            "school_hard_end_date": None,
            "school_target_end_date": date(2026, 6, 30),
            "school_start_date": date(2025, 9, 1),
        })
        result = _resolve_hard_end_date(S)
        assert result == date(2026, 7, 31)

    def test_fallback_to_start_plus_one_year(self):
        S = type("S", (), {
            "school_hard_end_date": None,
            "school_target_end_date": None,
            "school_start_date": date(2025, 9, 1),
        })
        result = _resolve_hard_end_date(S)
        assert result == date(2026, 7, 31)

    def test_none_when_no_dates(self):
        S = type("S", (), {
            "school_hard_end_date": None,
            "school_target_end_date": None,
            "school_start_date": None,
        })
        result = _resolve_hard_end_date(S)
        assert result is None


# ---------------------------------------------------------------------------
# _resolve_lunch_constraints
# ---------------------------------------------------------------------------

class TestResolveLunchConstraints:
    def test_defaults_when_none(self):
        result = _resolve_lunch_constraints(None)
        assert result == (720, 840, 60)

    def test_from_grid_settings(self):
        G = type("G", (), {
            "lunch_window_start": time(12, 30),
            "lunch_window_end": time(14, 0),
            "lunch_min_duration_minutes": 45,
        })
        result = _resolve_lunch_constraints(G)
        assert result == (750, 840, 45)

    def test_fallback_on_inverted_window(self):
        G = type("G", (), {
            "lunch_window_start": time(14, 0),
            "lunch_window_end": time(12, 0),
            "lunch_min_duration_minutes": 60,
        })
        result = _resolve_lunch_constraints(G)
        assert result == (720, 840, 60)

    def test_clamps_min_duration_to_window(self):
        G = type("G", (), {
            "lunch_window_start": time(12, 0),
            "lunch_window_end": time(12, 30),
            "lunch_min_duration_minutes": 60,
        })
        result = _resolve_lunch_constraints(G)
        assert result[2] == 30

    def test_default_min_duration_when_none(self):
        G = type("G", (), {
            "lunch_window_start": time(12, 0),
            "lunch_window_end": time(14, 0),
            "lunch_min_duration_minutes": None,
        })
        result = _resolve_lunch_constraints(G)
        assert result[2] == 60


# ---------------------------------------------------------------------------
# _build_primary_rolling_window
# ---------------------------------------------------------------------------

class TestBuildPrimaryRollingWindow:
    def test_basic_window(self):
        result = _build_primary_rolling_window(
            window_start_date=date(2026, 3, 1),
            hard_end_date=date(2026, 7, 31),
            blocked_dates=set(),
            rolling_weeks=8,
        )
        assert result["rolling_weeks"] == 8
        assert result["window_start_date"] == date(2026, 3, 1)
        assert result["window_end_date"] == date(2026, 3, 1) + timedelta(days=55)

    def test_clamped_by_hard_end(self):
        result = _build_primary_rolling_window(
            window_start_date=date(2026, 7, 1),
            hard_end_date=date(2026, 7, 15),
            blocked_dates=set(),
            rolling_weeks=8,
        )
        assert result["window_end_date"] == date(2026, 7, 15)

    def test_counts_blocked_days(self):
        blocked = {date(2026, 3, 2), date(2026, 3, 3)}
        result = _build_primary_rolling_window(
            window_start_date=date(2026, 3, 1),
            hard_end_date=date(2026, 7, 31),
            blocked_dates=blocked,
            rolling_weeks=1,
        )
        assert result["window_blocked_days"] == 2
        assert result["window_usable_days"] == 5

    def test_zero_days_when_start_after_end(self):
        result = _build_primary_rolling_window(
            window_start_date=date(2026, 7, 31),
            hard_end_date=date(2026, 7, 15),
            blocked_dates=set(),
            rolling_weeks=8,
        )
        assert result["window_total_days"] == 0


# ---------------------------------------------------------------------------
# _estimate_capacity_minutes_in_range
# ---------------------------------------------------------------------------

class TestEstimateCapacity:
    def _make_ts(self, ts_id, day_of_week, start_hour, start_min, end_hour, end_min):
        return type("T", (), {
            "id": ts_id, "day_of_week": day_of_week,
            "start_time": time(start_hour, start_min),
            "end_time": time(end_hour, end_min),
        })

    def test_zero_capacity_no_rooms(self):
        result = _estimate_capacity_minutes_in_range(
            timeslots=[], room_count=0,
            blocked_dates=set(),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
        )
        assert result == 0

    def test_positive_capacity(self):
        ts = [self._make_ts(1, 0, 8, 0, 8, 50)]
        result = _estimate_capacity_minutes_in_range(
            timeslots=ts, room_count=2,
            blocked_dates=set(),
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 5),
        )
        assert result == 100

    def test_excludes_blocked_dates(self):
        ts = [self._make_ts(1, 0, 8, 0, 8, 50)]
        blocked = {date(2026, 1, 5)}
        result = _estimate_capacity_minutes_in_range(
            timeslots=ts, room_count=2,
            blocked_dates=blocked,
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 5),
        )
        assert result == 0

    def test_inverted_date_range(self):
        ts = [self._make_ts(1, 0, 8, 0, 8, 50)]
        result = _estimate_capacity_minutes_in_range(
            timeslots=ts, room_count=2,
            blocked_dates=set(),
            start_date=date(2026, 1, 7),
            end_date=date(2026, 1, 1),
        )
        assert result == 0


# ---------------------------------------------------------------------------
# _build_remaining_summary
# ---------------------------------------------------------------------------

class TestBuildRemainingSummary:
    def test_basic(self):
        summary = _build_remaining_summary(300, 250, 50)
        assert summary["raw_remaining_hours"] == 5.0
        assert summary["reconciled_remaining_hours"] == 250 / 60
        assert summary["committed_credited_hours"] == 50 / 60

    def test_with_post_expand(self):
        summary = _build_remaining_summary(300, 250, 50, post_expand_remaining_minutes=100)
        assert summary["post_expand_remaining_hours"] == 100 / 60

    def test_negative_values_clamped(self):
        summary = _build_remaining_summary(-10, -5, -3)
        assert summary["raw_remaining_hours"] == 0.0
