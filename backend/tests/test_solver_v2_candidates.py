"""Testes para solver_v2_candidates.py — construção e poda do universo de candidatos."""

import pytest
from datetime import date

from app.core.solver_schemas import LessonInput, TimeslotInput, RoomInput
from app.core.solver_v2_candidates import (
    SolverV2Candidate,
    CandidatePruningTelemetry,
    build_candidate_universe,
    prune_candidates_hard_first,
    _slot_lunch_overlap_minutes,
    _build_pruning_telemetry,
    DEFAULT_AVAILABILITY_SCORE,
    IMPOSSIBLE_AVAILABILITY_SCORE,
    REMOVAL_REASON_ROOM_TYPE,
    REMOVAL_REASON_TEACHER_IMPOSSIBLE,
    REMOVAL_REASON_TEACHER_CONFLICT,
    REMOVAL_REASON_CLASS_CONFLICT,
    REMOVAL_REASON_ROOM_CONFLICT,
    REMOVAL_REASON_LUNCH_HARD,
)

pytestmark = pytest.mark.unit


def _make_lesson(lesson_id=1, **kwargs):
    defaults = {
        "lesson_id": lesson_id,
        "class_id": 10,
        "subject_id": 100,
        "teacher_id": 200,
        "required_room_type": "normal",
        "remaining_minutes": 300,
        "target_weekly_minutes": 60,
    }
    defaults.update(kwargs)
    return LessonInput(**defaults)


def _make_ts(ts_id=1, **kwargs):
    defaults = {
        "ts_id": ts_id,
        "day_of_week": 0,
        "duration_minutes": 50,
        "start_minutes": 480,
        "end_minutes": 530,
    }
    defaults.update(kwargs)
    return TimeslotInput(**defaults)


def _make_room(room_id=1, **kwargs):
    defaults = {"room_id": room_id, "room_type": "normal"}
    defaults.update(kwargs)
    return RoomInput(**defaults)


def _make_candidate(**kwargs):
    defaults = {
        "candidate_key": "L1-D2026-01-01-T1-R1",
        "lesson_id": 1, "class_id": 10, "subject_id": 100, "teacher_id": 200,
        "required_room_type": "normal", "room_id": 1, "room_type": "normal",
        "output_date": date(2026, 1, 1), "day_of_week": 3,
        "ts_id": 1, "slot_start_minutes": 480, "slot_end_minutes": 530,
        "duration_minutes": 50,
    }
    defaults.update(kwargs)
    return SolverV2Candidate(**defaults)


# ---------------------------------------------------------------------------
# _slot_lunch_overlap_minutes
# ---------------------------------------------------------------------------

class TestSlotLunchOverlap:
    def test_no_overlap_before_lunch(self):
        assert _slot_lunch_overlap_minutes(480, 530, 720, 840) == 0

    def test_no_overlap_after_lunch(self):
        assert _slot_lunch_overlap_minutes(840, 890, 720, 840) == 0

    def test_full_overlap_inside_lunch(self):
        assert _slot_lunch_overlap_minutes(740, 800, 720, 840) == 60

    def test_partial_overlap_start(self):
        assert _slot_lunch_overlap_minutes(700, 750, 720, 840) == 30

    def test_partial_overlap_end(self):
        assert _slot_lunch_overlap_minutes(820, 860, 720, 840) == 20

    def test_slot_covers_entire_lunch(self):
        assert _slot_lunch_overlap_minutes(700, 860, 720, 840) == 120


# ---------------------------------------------------------------------------
# _build_pruning_telemetry
# ---------------------------------------------------------------------------

class TestPruningTelemetry:
    def test_empty(self):
        telemetry = _build_pruning_telemetry(0, 0, {})
        assert telemetry.candidates_before == 0
        assert telemetry.candidates_after == 0
        assert telemetry.removed_total == 0
        assert telemetry.removed_ratio == 0.0

    def test_half_removed(self):
        telemetry = _build_pruning_telemetry(100, 50, {"room_type_mismatch": 50})
        assert telemetry.candidates_before == 100
        assert telemetry.candidates_after == 50
        assert telemetry.removed_total == 50
        assert telemetry.removed_ratio == 0.5
        assert telemetry.removed_by_reason == {"room_type_mismatch": 50}

    def test_to_dict(self):
        d = _build_pruning_telemetry(10, 8, {"x": 2}).to_dict()
        assert d["candidates_before"] == 10
        assert d["candidates_after"] == 8
        assert d["removed_ratio"] == 0.2


# ---------------------------------------------------------------------------
# build_candidate_universe
# ---------------------------------------------------------------------------

class TestBuildCandidateUniverse:
    def test_empty_when_no_lessons(self):
        ts = [_make_ts(1)]
        rooms = [_make_room(1)]
        result = build_candidate_universe(
            lessons=[],
            timeslots=ts,
            rooms=rooms,
            window_start_date=date(2026, 1, 5),
            window_end_date=date(2026, 1, 9),
            blocked_dates=set(),
        )
        assert result == []

    def test_empty_when_inverted_window(self):
        result = build_candidate_universe(
            lessons=[_make_lesson()],
            timeslots=[_make_ts()],
            rooms=[_make_room()],
            window_start_date=date(2026, 1, 9),
            window_end_date=date(2026, 1, 5),
            blocked_dates=set(),
        )
        assert result == []

    def test_basic_universe_size(self):
        result = build_candidate_universe(
            lessons=[_make_lesson(1)],
            timeslots=[_make_ts(1, day_of_week=0)],
            rooms=[_make_room(1)],
            window_start_date=date(2026, 1, 5),
            window_end_date=date(2026, 1, 9),
            blocked_dates=set(),
        )
        assert len(result) == 1

    def test_excludes_blocked_dates(self):
        blocked = {date(2026, 1, 5)}
        result = build_candidate_universe(
            lessons=[_make_lesson(1)],
            timeslots=[_make_ts(1, day_of_week=0)],
            rooms=[_make_room(1)],
            window_start_date=date(2026, 1, 5),
            window_end_date=date(2026, 1, 9),
            blocked_dates=blocked,
        )
        assert len(result) == 0

    def test_multiple_dates_only_matching_weekday(self):
        result = build_candidate_universe(
            lessons=[_make_lesson(1)],
            timeslots=[_make_ts(1, day_of_week=0)],
            rooms=[_make_room(1)],
            window_start_date=date(2026, 1, 5),
            window_end_date=date(2026, 1, 11),
            blocked_dates=set(),
        )
        assert len(result) == 1

    def test_candidate_key_format(self):
        result = build_candidate_universe(
            lessons=[_make_lesson(1)],
            timeslots=[_make_ts(1, day_of_week=0)],
            rooms=[_make_room(1)],
            window_start_date=date(2026, 1, 5),
            window_end_date=date(2026, 1, 5),
            blocked_dates=set(),
        )
        assert len(result) == 1
        assert result[0].candidate_key == "L1-D2026-01-05-T1-R1"

    def test_deterministic_ordering(self):
        lessons = [_make_lesson(1), _make_lesson(2)]
        ts = [_make_ts(day_of_week=0, ts_id=1)]
        rooms = [_make_room(room_id=1)]
        result = build_candidate_universe(
            lessons=lessons, timeslots=ts, rooms=rooms,
            window_start_date=date(2026, 1, 5),
            window_end_date=date(2026, 1, 5),
            blocked_dates=set(),
        )
        keys = [c.candidate_key for c in result]
        assert keys == sorted(keys)
        assert keys[0].startswith("L1-")
        assert keys[1].startswith("L2-")

    def test_cross_product_lessons_timeslots_rooms(self):
        result = build_candidate_universe(
            lessons=[_make_lesson(1), _make_lesson(2)],
            timeslots=[
                _make_ts(day_of_week=0, ts_id=1),
                _make_ts(day_of_week=0, ts_id=2),
            ],
            rooms=[_make_room(room_id=1)],
            window_start_date=date(2026, 1, 5),
            window_end_date=date(2026, 1, 5),
            blocked_dates=set(),
        )
        assert len(result) == 4


# ---------------------------------------------------------------------------
# prune_candidates_hard_first
# ---------------------------------------------------------------------------

class TestPruneCandidates:
    def test_passes_with_no_constraints(self):
        candidates = [_make_candidate()]
        kept, telemetry = prune_candidates_hard_first(
            candidates, availability_map={},
        )
        assert len(kept) == 1
        assert telemetry.candidates_before == 1
        assert telemetry.candidates_after == 1

    def test_removes_room_type_mismatch(self):
        c = _make_candidate(required_room_type="lab", room_type="normal")
        kept, telemetry = prune_candidates_hard_first([c], availability_map={})
        assert len(kept) == 0
        assert telemetry.removed_by_reason[REMOVAL_REASON_ROOM_TYPE] == 1

    def test_removes_teacher_impossible(self):
        c = _make_candidate(teacher_id=200, ts_id=1)
        avail_map = {(200, 1): IMPOSSIBLE_AVAILABILITY_SCORE}
        kept, telemetry = prune_candidates_hard_first([c], availability_map=avail_map)
        assert len(kept) == 0
        assert telemetry.removed_by_reason[REMOVAL_REASON_TEACHER_IMPOSSIBLE] == 1

    def test_removes_teacher_conflict(self):
        c = _make_candidate(teacher_id=200, output_date=date(2026, 1, 1), ts_id=1)
        conflicts = {(200, date(2026, 1, 1), 1)}
        kept, telemetry = prune_candidates_hard_first(
            [c], availability_map={}, fixed_teacher_conflicts=conflicts,
        )
        assert len(kept) == 0
        assert telemetry.removed_by_reason[REMOVAL_REASON_TEACHER_CONFLICT] == 1

    def test_removes_class_conflict(self):
        c = _make_candidate(class_id=10, output_date=date(2026, 1, 1), ts_id=1)
        conflicts = {(10, date(2026, 1, 1), 1)}
        kept, telemetry = prune_candidates_hard_first(
            [c], availability_map={}, fixed_class_conflicts=conflicts,
        )
        assert len(kept) == 0
        assert telemetry.removed_by_reason[REMOVAL_REASON_CLASS_CONFLICT] == 1

    def test_removes_room_conflict(self):
        c = _make_candidate(room_id=1, output_date=date(2026, 1, 1), ts_id=1)
        conflicts = {(1, date(2026, 1, 1), 1)}
        kept, telemetry = prune_candidates_hard_first(
            [c], availability_map={}, fixed_room_conflicts=conflicts,
        )
        assert len(kept) == 0
        assert telemetry.removed_by_reason[REMOVAL_REASON_ROOM_CONFLICT] == 1

    def test_normal_room_type_passes(self):
        c = _make_candidate(required_room_type="normal", room_type="normal")
        kept, _ = prune_candidates_hard_first([c], availability_map={})
        assert len(kept) == 1

    def test_neutral_availability_passes(self):
        c = _make_candidate(teacher_id=200, ts_id=1)
        avail_map = {(200, 1): DEFAULT_AVAILABILITY_SCORE}
        kept, _ = prune_candidates_hard_first([c], availability_map=avail_map)
        assert len(kept) == 1

    def test_multiple_reasons_counted(self):
        c1 = _make_candidate(
            candidate_key="k1", required_room_type="lab", room_type="normal",
        )
        c2 = _make_candidate(
            candidate_key="k2", teacher_id=200, ts_id=1,
            output_date=date(2026, 1, 1),
        )
        avail_map = {(200, 1): IMPOSSIBLE_AVAILABILITY_SCORE}
        kept, telemetry = prune_candidates_hard_first(
            [c1, c2], availability_map=avail_map,
        )
        assert len(kept) == 0
        assert telemetry.removed_by_reason[REMOVAL_REASON_ROOM_TYPE] == 1
        assert telemetry.removed_by_reason[REMOVAL_REASON_TEACHER_IMPOSSIBLE] == 1

    def test_lunch_window_pruning_removes_slot_in_lunch_only(self):
        c = _make_candidate(
            slot_start_minutes=720, slot_end_minutes=780,
            day_of_week=0, ts_id=1,
        )
        kept, telemetry = prune_candidates_hard_first(
            [c], availability_map={},
            lunch_window_start_minutes=720,
            lunch_window_end_minutes=840,
            lunch_min_duration_minutes=60,
        )
        assert len(kept) == 0
        assert telemetry.removed_by_reason.get(REMOVAL_REASON_LUNCH_HARD, 0) == 1

    def test_lunch_window_passing_slot_outside_lunch(self):
        c = _make_candidate(
            slot_start_minutes=480, slot_end_minutes=530,
            day_of_week=0, ts_id=1,
        )
        kept, telemetry = prune_candidates_hard_first(
            [c], availability_map={},
            lunch_window_start_minutes=720,
            lunch_window_end_minutes=840,
            lunch_min_duration_minutes=60,
        )
        assert len(kept) == 1
