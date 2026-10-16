from threading import Event
from time import monotonic
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from app.scheduler.infrastructure import placement_model as placement


def scope_state():
    return SimpleNamespace(
        model=cp_model.CpModel(),
        scope=SimpleNamespace(week=None),
        threshold_counts={},
        x={},
    )


def test_scheduler_placement_cancellation_after_build_never_starts_solver(monkeypatch):
    def unexpected_solve(*args):
        raise AssertionError("Cancelled placement must not start native search")

    monkeypatch.setattr(cp_model.CpSolver, "Solve", unexpected_solve)
    status, selections, records, reason = placement._solve_scope(
        scope_state(),
        deadline=monotonic() + 10,
        solver=cp_model.CpSolver(),
        should_cancel=lambda: True,
    )
    assert (status, selections, records, reason) == ("CANCELLED", None, [], "CANCELLED")


@pytest.mark.parametrize("phase", ["feasibility", "quality"])
def test_scheduler_placement_cancellation_interrupts_native_search(monkeypatch, phase):
    cancelled = Event()
    stopped = Event()

    original = cp_model.CpSolver.Solve
    state = scope_state()
    calls = []
    if phase == "quality":
        state.threshold_counts = {1: 0}

    def blocking_solve(solver, model):
        calls.append(True)
        if phase == "quality" and len(calls) == 1:
            return original(solver, model)
        cancelled.set()
        assert stopped.wait(5), "Native search must receive StopSearch while running"
        return cp_model.UNKNOWN

    monkeypatch.setattr(cp_model.CpSolver, "Solve", blocking_solve)
    monkeypatch.setattr(cp_model.CpSolver, "StopSearch", lambda solver: stopped.set())
    status, selections, records, reason = placement._solve_scope(
        state,
        deadline=monotonic() + 10,
        solver=cp_model.CpSolver(),
        should_cancel=cancelled.is_set,
    )
    assert (status, selections, records, reason) == ("CANCELLED", None, [], "CANCELLED")


def test_scheduler_placement_cancellation_preserves_native_errors(monkeypatch):
    def broken_solve(solver, model):
        raise ValueError("native solve failed")

    monkeypatch.setattr(cp_model.CpSolver, "Solve", broken_solve)
    with pytest.raises(ValueError, match="native solve failed"):
        placement._solve_with_cancellation(cp_model.CpSolver(), cp_model.CpModel(), lambda: False)


def test_scheduler_placement_cancellation_monitor_preserves_valid_solution():
    solver = cp_model.CpSolver()
    model = cp_model.CpModel()
    value = model.NewIntVar(1, 1, "value")
    status = placement._solve_with_cancellation(solver, model, lambda: False)
    assert status == cp_model.OPTIMAL
    assert solver.Value(value) == 1
