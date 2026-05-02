"""Testes para solver_v2_expansion.py — validação de calendário e fill-opportunistic."""

import pytest
from datetime import date

from app.core.solver_engine_v2 import ScheduledBlockV2
from app.core.solver_v2_expansion import (
    validate_v2_blocks_calendar,
    _TimeslotInfo,
    _RoomInfo,
    _slot_lunch_overlap,
    _build_lunch_filtered_slots,
    compute_residual_summary,
    FillOpportunisticResult,
)

pytestmark = pytest.mark.unit


def _make_block(lesson_id=1, **kwargs):
    defaults = {
        "lesson_id": lesson_id,
        "class_id": 10,
        "ts_id": 1,
        "room_id": 1,
        "output_date": date(2026, 3, 15),
        "duration_minutes": 50,
    }
    defaults.update(kwargs)
    return ScheduledBlockV2(**defaults)


def _make_ts(ts_id=1, **kwargs):
    defaults = {
        "ts_id": ts_id,
        "day_of_week": 0,
        "duration_minutes": 50,
        "start_minutes": 480,
        "end_minutes": 530,
    }
    defaults.update(kwargs)
    return _TimeslotInfo(**defaults)


def _make_room(room_id=1, **kwargs):
    defaults = {"room_id": room_id, "room_type": "normal"}
    defaults.update(kwargs)
    return _RoomInfo(**defaults)


# ---------------------------------------------------------------------------
# validate_v2_blocks_calendar
# ---------------------------------------------------------------------------

class TestValidateBlocks:
    def test_all_valid_no_blocked_dates(self):
        blocks = [_make_block(output_date=date(2026, 3, 15))]
        valid, rejected = validate_v2_blocks_calendar(
            blocks,
            blocked_dates=set(),
            hard_end_date=date(2026, 12, 31),
        )
        assert len(valid) == 1
        assert len(rejected) == 0

    def test_rejects_blocked_date(self):
        blocks = [_make_block(output_date=date(2026, 3, 15))]
        blocked = {date(2026, 3, 15)}
        valid, rejected = validate_v2_blocks_calendar(
            blocks,
            blocked_dates=blocked,
            hard_end_date=date(2026, 12, 31),
        )
        assert len(valid) == 0
        assert len(rejected) == 1

    def test_rejects_after_hard_end(self):
        blocks = [_make_block(output_date=date(2026, 12, 31))]
        valid, rejected = validate_v2_blocks_calendar(
            blocks,
            blocked_dates=set(),
            hard_end_date=date(2026, 7, 31),
        )
        assert len(valid) == 0
        assert len(rejected) == 1

    def test_accepts_on_hard_end_boundary(self):
        blocks = [_make_block(output_date=date(2026, 7, 31))]
        valid, rejected = validate_v2_blocks_calendar(
            blocks,
            blocked_dates=set(),
            hard_end_date=date(2026, 7, 31),
        )
        assert len(valid) == 1
        assert len(rejected) == 0

    def test_mixed_result(self):
        blocks = [
            _make_block(1, output_date=date(2026, 3, 15)),
            _make_block(2, output_date=date(2026, 12, 25)),
        ]
        blocked = {date(2026, 3, 15)}
        valid, rejected = validate_v2_blocks_calendar(
            blocks,
            blocked_dates=blocked,
            hard_end_date=date(2026, 12, 31),
        )
        assert len(valid) == 1
        assert valid[0].lesson_id == 2
        assert len(rejected) == 1
        assert rejected[0].lesson_id == 1


# ---------------------------------------------------------------------------
# _slot_lunch_overlap
# ---------------------------------------------------------------------------

class TestSlotLunchOverlap:
    def test_no_overlap(self):
        ts = _make_ts(start_minutes=480, end_minutes=530)
        assert _slot_lunch_overlap(ts, 720, 840) == 0

    def test_full_overlap(self):
        ts = _make_ts(start_minutes=740, end_minutes=800)
        assert _slot_lunch_overlap(ts, 720, 840) == 60

    def test_partial_overlap(self):
        ts = _make_ts(start_minutes=700, end_minutes=750)
        assert _slot_lunch_overlap(ts, 720, 840) == 30


# ---------------------------------------------------------------------------
# _build_lunch_filtered_slots
# ---------------------------------------------------------------------------

class TestBuildLunchFilteredSlots:
    def test_removes_slots_exceeding_lunch_budget(self):
        ts1 = _make_ts(1, day_of_week=0, start_minutes=720, end_minutes=780)
        ts2 = _make_ts(2, day_of_week=0, start_minutes=780, end_minutes=840)
        timeslots_by_dow = {0: [ts1, ts2]}
        result = _build_lunch_filtered_slots(
            timeslots_by_dow,
            lunch_window_start_minutes=720,
            lunch_window_end_minutes=840,
            lunch_min_duration_minutes=60,
        )
        assert len(result[0]) == 2

    def test_keeps_all_when_no_lunch(self):
        ts1 = _make_ts(1, day_of_week=0)
        ts2 = _make_ts(2, day_of_week=0)
        timeslots_by_dow = {0: [ts1, ts2]}
        result = _build_lunch_filtered_slots(
            timeslots_by_dow,
            lunch_window_start_minutes=None,
            lunch_window_end_minutes=None,
            lunch_min_duration_minutes=60,
        )
        assert len(result[0]) == 2

    def test_keeps_all_when_slots_outside_lunch(self):
        ts1 = _make_ts(1, day_of_week=0, start_minutes=480, end_minutes=530)
        ts2 = _make_ts(2, day_of_week=0, start_minutes=540, end_minutes=590)
        timeslots_by_dow = {0: [ts1, ts2]}
        result = _build_lunch_filtered_slots(
            timeslots_by_dow,
            lunch_window_start_minutes=720,
            lunch_window_end_minutes=840,
            lunch_min_duration_minutes=60,
        )
        assert len(result[0]) == 2


# ---------------------------------------------------------------------------
# compute_residual_summary
# ---------------------------------------------------------------------------

class TestComputeResidual:
    def test_all_covered_no_backlog(self):
        backlog = {1: 50}
        fill_result = FillOpportunisticResult(
            all_blocks=[_make_block(1, duration_minutes=50)],
            primary_blocks=[],
            fill_blocks=[],
            backlog_remaining_minutes=0,
            fill_iterations=1,
        )
        summary = compute_residual_summary(backlog, fill_result, hard_end_date=date(2026, 12, 31))
        assert summary.backlog_remaining_hours == 0
        assert not summary.hard_limit_reached

    def test_backlog_remaining(self):
        backlog = {1: 120}
        fill_result = FillOpportunisticResult(
            all_blocks=[_make_block(1, duration_minutes=70)],
            primary_blocks=[],
            fill_blocks=[],
            backlog_remaining_minutes=50,
            fill_iterations=1,
        )
        summary = compute_residual_summary(backlog, fill_result, hard_end_date=date(2026, 12, 31))
        assert summary.backlog_remaining_hours == round(50 / 60, 1)

    def test_hard_limit_reached_flag(self):
        backlog = {1: 9999}
        fill_result = FillOpportunisticResult(
            all_blocks=[],
            primary_blocks=[],
            fill_blocks=[],
            backlog_remaining_minutes=9999,
            fill_iterations=1,
        )
        summary = compute_residual_summary(backlog, fill_result, hard_end_date=date(2026, 7, 31))
        assert summary.hard_limit_reached
