"""Testes para solver_engine_v2.py — dataclasses e estrutura do motor V2."""

import pytest
from datetime import date

from app.core.solver_v2_candidates import SolverV2Candidate
from app.core.solver_engine_v2 import (
    ScheduledBlockV2,
    SolverV2Result,
    ScheduleEngineV2,
)

pytestmark = pytest.mark.unit


def _make_candidate(**kwargs):
    defaults = {
        "candidate_key": "L1-D2026-03-15-T1-R1",
        "lesson_id": 1, "class_id": 10, "subject_id": 100, "teacher_id": 200,
        "required_room_type": "normal", "room_id": 1, "room_type": "normal",
        "output_date": date(2026, 3, 15), "day_of_week": 6,
        "ts_id": 1, "slot_start_minutes": 480, "slot_end_minutes": 530,
        "duration_minutes": 50,
    }
    defaults.update(kwargs)
    return SolverV2Candidate(**defaults)


class TestScheduledBlockV2:
    def test_creation(self):
        block = ScheduledBlockV2(
            lesson_id=1, class_id=10, ts_id=2, room_id=3,
            output_date=date(2026, 3, 15), duration_minutes=50,
        )
        assert block.lesson_id == 1
        assert block.output_date == date(2026, 3, 15)


class TestSolverV2Result:
    def test_infeasible_result(self):
        result = SolverV2Result(
            status="infeasible", blocks=[],
            makespan_days=None, projected_end_date=None,
            end_date_spread_days=None, target_drift_days=None,
            churn_blocks=None, gaps_total=None,
            objective_value=None, solver_wall_time=None,
        )
        assert result.status == "infeasible"
        assert result.blocks == []

    def test_success_result_with_metrics(self):
        result = SolverV2Result(
            status="optimal",
            blocks=[ScheduledBlockV2(1, 10, 1, 1, date(2026, 6, 30), 50)],
            makespan_days=176, projected_end_date=date(2026, 6, 30),
            end_date_spread_days=5, target_drift_days=10,
            churn_blocks=3, gaps_total=2,
            objective_value=42.0, solver_wall_time=1.5,
        )
        assert result.status == "optimal"
        assert result.projected_end_date == date(2026, 6, 30)
        assert result.end_date_spread_days == 5


class TestScheduleEngineV2Basics:
    def test_infeasible_with_no_candidates(self):
        engine = ScheduleEngineV2(
            candidates=[],
            window_start_date=date(2026, 1, 1),
            window_end_date=date(2026, 12, 31),
        )
        result = engine.solve()
        assert result.status == "infeasible"

    def test_date_index_builds_correctly(self):
        engine = ScheduleEngineV2(
            candidates=[_make_candidate()],
            window_start_date=date(2026, 3, 15),
            window_end_date=date(2026, 3, 17),
        )
        assert engine._n_dates == 3
        assert engine._dates == [date(2026, 3, 15), date(2026, 3, 16), date(2026, 3, 17)]
        assert engine._date_to_idx[date(2026, 3, 15)] == 0
        assert engine._date_to_idx[date(2026, 3, 17)] == 2

    def test_candidate_grouping(self):
        candidates = [
            _make_candidate(candidate_key="k1", lesson_id=1),
            _make_candidate(candidate_key="k2", lesson_id=2),
        ]
        engine = ScheduleEngineV2(
            candidates=candidates,
            window_start_date=date(2026, 3, 15),
            window_end_date=date(2026, 3, 15),
        )
        assert len(engine._cands_by_lesson[1]) == 1
        assert len(engine._cands_by_lesson[2]) == 1
        assert engine._lesson_class[1] == 10
        assert engine._lesson_duration[1] == 50

    def test_single_candidate_solves(self):
        candidates = [_make_candidate()]
        engine = ScheduleEngineV2(
            candidates=candidates,
            window_start_date=date(2026, 3, 15),
            window_end_date=date(2026, 3, 15),
        )
        result = engine.solve()
        assert result.status in ("optimal", "feasible")
        assert len(result.blocks) == 1
        assert result.blocks[0].output_date == date(2026, 3, 15)

    def test_two_candidates_for_same_class_but_one_selected(self):
        c1 = _make_candidate(candidate_key="k1", lesson_id=1, class_id=10, room_id=1)
        c2 = _make_candidate(
            candidate_key="k2", lesson_id=1, class_id=10, room_id=2,
            ts_id=1, output_date=date(2026, 3, 15),
        )
        engine = ScheduleEngineV2(
            candidates=[c1, c2],
            window_start_date=date(2026, 3, 15),
            window_end_date=date(2026, 3, 15),
        )
        result = engine.solve()
        assert result.status in ("optimal", "feasible")
        assert len(result.blocks) == 1

    def test_infeasible_when_no_room_type_match_but_pruning_removes_all(self):
        from app.core.solver_v2_candidates import (
            prune_candidates_hard_first,
            REMOVAL_REASON_ROOM_TYPE,
        )
        candidates = [
            _make_candidate(candidate_key="k1", required_room_type="lab", room_type="normal"),
            _make_candidate(candidate_key="k2", required_room_type="gym", room_type="normal"),
        ]
        kept, telemetry = prune_candidates_hard_first(candidates, availability_map={})
        assert len(kept) == 0
        assert telemetry.removed_by_reason.get(REMOVAL_REASON_ROOM_TYPE, 0) == 2
