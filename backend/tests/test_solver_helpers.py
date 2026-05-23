"""Testes para funções auxiliares puras do solver (solver_tasks.py).

Testa: _build_blocked_dates, _build_timeslot_inputs, _build_room_inputs,
_resolve_hard_end_date, _resolve_lunch_constraints, _build_primary_rolling_window,
_estimate_capacity_minutes_in_range, _build_remaining_summary.
"""

import pytest
from datetime import date, time, timedelta

from app.solver_tasks import (
    _build_blocked_dates,
    _build_timeslot_inputs,
    _build_room_inputs,
    _resolve_hard_end_date,
    _resolve_lunch_constraints,
    _build_primary_rolling_window,
    _estimate_capacity_minutes_in_range,
    _build_remaining_summary,
)
from app.core.solver_schemas import LessonInput, TimeslotInput, RoomInput

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _build_blocked_dates
# ---------------------------------------------------------------------------

class TestBlockedDates:
    def test_expands_single_day_event_to_set(self):
        E = type("E", (), {"start_date": date(2026, 3, 15), "end_date": date(2026, 3, 15)})
        result = _build_blocked_dates([E])
        assert result == {date(2026, 3, 15)}

    def test_expands_multi_day_event_to_all_dates(self):
        E = type("E", (), {"start_date": date(2026, 3, 15), "end_date": date(2026, 3, 17)})
        result = _build_blocked_dates([E])
        assert result == {date(2026, 3, 15), date(2026, 3, 16), date(2026, 3, 17)}

    def test_merges_multiple_events_in_one_set(self):
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

class TestTimeslotInputs:
    def test_converts_orm_to_input_with_correct_duration(self):
        T = type("T", (), {"id": 1, "start_time": time(8, 0), "end_time": time(8, 50), "day_of_week": 0})
        result = _build_timeslot_inputs([T])
        assert len(result) == 1
        assert result[0].ts_id == 1
        assert result[0].duration_minutes == 50
        assert result[0].start_minutes == 480

    def test_calculates_duration_and_start_end_in_minutes(self):
        T = type("T", (), {"id": 1, "start_time": time(9, 15), "end_time": time(10, 30), "day_of_week": 2})
        result = _build_timeslot_inputs([T])
        assert result[0].duration_minutes == 75
        assert result[0].start_minutes == 555
        assert result[0].end_minutes == 630


# ---------------------------------------------------------------------------
# _build_room_inputs
# ---------------------------------------------------------------------------

class TestRoomInputs:
    def test_converts_orm_room_to_input(self):
        R = type("R", (), {"id": 5, "type": type("RT", (), {"value": "lab"})})
        result = _build_room_inputs([R])
        assert len(result) == 1
        assert result[0].room_id == 5
        assert result[0].room_type == "lab"


# ---------------------------------------------------------------------------
# _resolve_hard_end_date
# ---------------------------------------------------------------------------

class TestHardEndDate:
    def test_returns_explicit_hard_end_when_set(self):
        S = type("S", (), {
            "school_hard_end_date": date(2026, 7, 15),
            "school_target_end_date": date(2026, 6, 30),
            "school_start_date": date(2025, 9, 1),
        })
        assert _resolve_hard_end_date(S) == date(2026, 7, 15)

    def test_falls_back_to_july_31_of_target_year(self):
        S = type("S", (), {
            "school_hard_end_date": None,
            "school_target_end_date": date(2026, 6, 30),
            "school_start_date": date(2025, 9, 1),
        })
        assert _resolve_hard_end_date(S) == date(2026, 7, 31)

    def test_falls_back_to_start_year_plus_one_july_31(self):
        S = type("S", (), {
            "school_hard_end_date": None,
            "school_target_end_date": None,
            "school_start_date": date(2025, 9, 1),
        })
        assert _resolve_hard_end_date(S) == date(2026, 7, 31)

    def test_returns_none_when_no_dates_configured(self):
        S = type("S", (), {
            "school_hard_end_date": None,
            "school_target_end_date": None,
            "school_start_date": None,
        })
        assert _resolve_hard_end_date(S) is None


# ---------------------------------------------------------------------------
# _resolve_lunch_constraints
# ---------------------------------------------------------------------------

class TestLunchConstraints:
    def test_returns_defaults_when_grid_settings_is_none(self):
        assert _resolve_lunch_constraints(None) == (720, 840, 60)

    def test_extracts_values_from_grid_settings(self):
        G = type("G", (), {
            "lunch_window_start": time(12, 30),
            "lunch_window_end": time(14, 0),
            "lunch_min_duration_minutes": 45,
        })
        assert _resolve_lunch_constraints(G) == (750, 840, 45)

    def test_falls_back_to_defaults_on_inverted_window(self):
        G = type("G", (), {
            "lunch_window_start": time(14, 0),
            "lunch_window_end": time(12, 0),
            "lunch_min_duration_minutes": 60,
        })
        assert _resolve_lunch_constraints(G) == (720, 840, 60)

    def test_clamps_min_duration_to_window_size(self):
        G = type("G", (), {
            "lunch_window_start": time(12, 0),
            "lunch_window_end": time(12, 30),
            "lunch_min_duration_minutes": 60,
        })
        assert _resolve_lunch_constraints(G)[2] == 30

    def test_uses_default_min_duration_when_none(self):
        G = type("G", (), {
            "lunch_window_start": time(12, 0),
            "lunch_window_end": time(14, 0),
            "lunch_min_duration_minutes": None,
        })
        assert _resolve_lunch_constraints(G)[2] == 60


# ---------------------------------------------------------------------------
# _build_primary_rolling_window
# ---------------------------------------------------------------------------

class TestRollingWindow:
    def test_builds_8_week_window_from_start_date(self):
        result = _build_primary_rolling_window(
            window_start_date=date(2026, 3, 1),
            hard_end_date=date(2026, 7, 31),
            blocked_dates=set(),
            rolling_weeks=8,
        )
        assert result["rolling_weeks"] == 8
        assert result["window_start_date"] == date(2026, 3, 1)
        assert result["window_end_date"] == date(2026, 3, 1) + timedelta(days=55)

    def test_clamps_window_end_to_hard_end_date(self):
        result = _build_primary_rolling_window(
            window_start_date=date(2026, 7, 1),
            hard_end_date=date(2026, 7, 15),
            blocked_dates=set(),
            rolling_weeks=8,
        )
        assert result["window_end_date"] == date(2026, 7, 15)

    def test_counts_blocked_days_correctly(self):
        blocked = {date(2026, 3, 2), date(2026, 3, 3)}
        result = _build_primary_rolling_window(
            window_start_date=date(2026, 3, 1),
            hard_end_date=date(2026, 7, 31),
            blocked_dates=blocked,
            rolling_weeks=1,
        )
        assert result["window_blocked_days"] == 2
        assert result["window_usable_days"] == 5

    def test_returns_zero_days_when_start_after_hard_end(self):
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

class TestCapacity:
    def _mk_ts(self, ts_id, day, sh, sm, eh, em):
        return type("T", (), {"id": ts_id, "day_of_week": day, "start_time": time(sh, sm), "end_time": time(eh, em)})

    def test_returns_zero_when_no_rooms(self):
        assert _estimate_capacity_minutes_in_range(
            timeslots=[], room_count=0, blocked_dates=set(),
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 7),
        ) == 0

    def test_calculates_capacity_for_one_day_one_slot_one_room(self):
        ts = [self._mk_ts(1, 0, 8, 0, 8, 50)]
        result = _estimate_capacity_minutes_in_range(
            timeslots=ts, room_count=2, blocked_dates=set(),
            start_date=date(2026, 1, 5), end_date=date(2026, 1, 5),
        )
        assert result == 100

    def test_excludes_blocked_dates_from_capacity(self):
        ts = [self._mk_ts(1, 0, 8, 0, 8, 50)]
        blocked = {date(2026, 1, 5)}
        result = _estimate_capacity_minutes_in_range(
            timeslots=ts, room_count=2, blocked_dates=blocked,
            start_date=date(2026, 1, 5), end_date=date(2026, 1, 5),
        )
        assert result == 0

    def test_returns_zero_for_inverted_date_range(self):
        ts = [self._mk_ts(1, 0, 8, 0, 8, 50)]
        result = _estimate_capacity_minutes_in_range(
            timeslots=ts, room_count=2, blocked_dates=set(),
            start_date=date(2026, 1, 7), end_date=date(2026, 1, 1),
        )
        assert result == 0


# ---------------------------------------------------------------------------
# _build_remaining_summary
# ---------------------------------------------------------------------------

class TestRemainingSummary:
    def test_rounds_minutes_to_hours_with_one_decimal(self):
        summary = _build_remaining_summary(300, 250, 50)
        assert summary["raw_remaining_hours"] == round(300 / 60, 1)
        assert summary["reconciled_remaining_hours"] == round(250 / 60, 1)
        assert summary["committed_credited_hours"] == round(50 / 60, 1)

    def test_includes_post_expand_field_when_provided(self):
        summary = _build_remaining_summary(300, 250, 50, post_expand_remaining_minutes=100)
        assert summary["post_expand_remaining_hours"] == round(100 / 60, 1)

    def test_clamps_negative_inputs_to_zero(self):
        summary = _build_remaining_summary(-10, -5, -3)
        assert summary["raw_remaining_hours"] == 0.0
        assert summary["reconciled_remaining_hours"] == 0.0
