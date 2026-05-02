"""Testes para _build_solver_v2_demands e _resolve_active_module_and_backlog em solver_tasks.py."""

import pytest
from datetime import date
from types import SimpleNamespace

from app.solver_tasks import (
    _resolve_active_module_and_backlog_minutes,
    _build_solver_v2_demands,
    _compute_remaining_minutes,
    SolverV2Demand,
)

pytestmark = pytest.mark.unit


def _lesson(id=1, class_id=10, subject_id=100, teacher_id=200):
    return SimpleNamespace(id=id, class_id=class_id, subject_id=subject_id, teacher_id=teacher_id)


def _module(id=1, name="M1", hours_total=50, order=0):
    return SimpleNamespace(id=id, name=name, hours_total=hours_total, order=order)


# ---------------------------------------------------------------------------
# _resolve_active_module_and_backlog_minutes
# ---------------------------------------------------------------------------

class TestResolveActiveModule:
    def test_no_modules(self):
        result = _resolve_active_module_and_backlog_minutes(
            _lesson(1, 10, 100), {}, {},
        )
        assert result == (None, 0)

    def test_single_module_no_progress(self):
        lesson = _lesson(1, 10, 100)
        modules = {100: [_module(1, hours_total=50)]}
        result = _resolve_active_module_and_backlog_minutes(lesson, modules, {})
        assert result == (1, 3000)

    def test_single_module_partial_progress(self):
        lesson = _lesson(1, 10, 100)
        modules = {100: [_module(1, hours_total=50)]}
        progress = {(10, 1): 30.0}
        result = _resolve_active_module_and_backlog_minutes(lesson, modules, progress)
        assert result == (1, 1200)

    def test_single_module_fully_completed(self):
        lesson = _lesson(1, 10, 100)
        modules = {100: [_module(1, hours_total=50)]}
        progress = {(10, 1): 50.0}
        result = _resolve_active_module_and_backlog_minutes(lesson, modules, progress)
        assert result == (None, 0)

    def test_multiple_modules_sequential(self):
        lesson = _lesson(1, 10, 100)
        modules = {
            100: [
                _module(1, "M1", hours_total=50, order=0),
                _module(2, "M2", hours_total=30, order=1),
                _module(3, "M3", hours_total=20, order=2),
            ]
        }
        progress = {(10, 1): 50.0}
        result = _resolve_active_module_and_backlog_minutes(lesson, modules, progress)
        assert result[0] == 2
        assert result[1] == (30 + 20) * 60

    def test_active_module_is_first_non_completed(self):
        lesson = _lesson(1, 10, 100)
        modules = {
            100: [
                _module(1, "M1", hours_total=50, order=0),
                _module(2, "M2", hours_total=30, order=1),
            ]
        }
        progress = {(10, 1): 40.0}
        result = _resolve_active_module_and_backlog_minutes(lesson, modules, progress)
        assert result[0] == 1

    def test_progress_clamped_to_hours_total(self):
        lesson = _lesson(1, 10, 100)
        modules = {100: [_module(1, hours_total=50)]}
        progress = {(10, 1): 99.0}
        result = _resolve_active_module_and_backlog_minutes(lesson, modules, progress)
        assert result[1] == 0

    def test_zero_hour_module_skipped(self):
        lesson = _lesson(1, 10, 100)
        modules = {100: [_module(1, hours_total=0)]}
        result = _resolve_active_module_and_backlog_minutes(lesson, modules, {})
        assert result == (None, 0)

    def test_module_order_respected_from_attribute(self):
        lesson = _lesson(1, 10, 100)
        modules = {
            100: [
                _module(3, "M3", hours_total=20, order=2),
                _module(1, "M1", hours_total=50, order=0),
                _module(2, "M2", hours_total=30, order=1),
            ]
        }
        result = _resolve_active_module_and_backlog_minutes(lesson, modules, {})
        assert result[0] == 1


# ---------------------------------------------------------------------------
# _compute_remaining_minutes
# ---------------------------------------------------------------------------

class TestComputeRemaining:
    def test_basic(self):
        lesson = _lesson(1, 10, 100)
        modules = {100: [_module(1, hours_total=50)]}
        result = _compute_remaining_minutes(lesson, modules, {})
        assert result == 3000

    def test_partial(self):
        lesson = _lesson(1, 10, 100)
        modules = {100: [_module(1, hours_total=50), _module(2, hours_total=30)]}
        progress = {(10, 1): 25.0}
        result = _compute_remaining_minutes(lesson, modules, progress)
        assert result == (25 + 30) * 60


# ---------------------------------------------------------------------------
# _build_solver_v2_demands
# ---------------------------------------------------------------------------

class TestBuildDemands:
    def test_empty_when_all_completed(self):
        lessons = [_lesson(1, 10, 100)]
        modules = {100: [_module(1, hours_total=50)]}
        progress = {(10, 1): 50.0}
        result = _build_solver_v2_demands(lessons, modules, progress, target_end_date=None)
        assert result == []

    def test_single_demand(self):
        lessons = [_lesson(1, 10, 100)]
        modules = {100: [_module(1, hours_total=50)]}
        progress = {(10, 1): 25.0}
        result = _build_solver_v2_demands(lessons, modules, progress, target_end_date=None)
        assert len(result) == 1
        assert result[0].lesson_id == 1
        assert result[0].class_id == 10
        assert result[0].subject_id == 100
        assert result[0].module_id == 1
        assert result[0].backlog_minutes == 1500

    def test_multiple_lessons(self):
        lessons = [_lesson(1, 10, 100), _lesson(2, 20, 200)]
        modules = {
            100: [_module(1, hours_total=50)],
            200: [_module(2, hours_total=30)],
        }
        progress = {}
        result = _build_solver_v2_demands(lessons, modules, progress, target_end_date=None)
        assert len(result) == 2

    def test_deducts_committed_minutes(self):
        lessons = [_lesson(1, 10, 100)]
        modules = {100: [_module(1, hours_total=50)]}
        progress = {(10, 1): 10.0}
        committed = {1: 600}
        result = _build_solver_v2_demands(
            lessons, modules, progress,
            target_end_date=None,
            committed_minutes_by_lesson=committed,
        )
        assert result[0].backlog_minutes == 1800

    def test_removes_lesson_when_committed_covers_all(self):
        lessons = [_lesson(1, 10, 100)]
        modules = {100: [_module(1, hours_total=50)]}
        progress = {(10, 1): 10.0}
        committed = {1: 2400}
        result = _build_solver_v2_demands(
            lessons, modules, progress,
            target_end_date=None,
            committed_minutes_by_lesson=committed,
        )
        assert result == []

    def test_target_end_date_preserved(self):
        lessons = [_lesson(1, 10, 100)]
        modules = {100: [_module(1, hours_total=50)]}
        target = date(2026, 6, 30)
        result = _build_solver_v2_demands(lessons, modules, {}, target_end_date=target)
        assert result[0].target_end_date == target
