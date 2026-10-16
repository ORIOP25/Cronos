from threading import Event

import pytest
from ortools.sat.python import cp_model

from app.scheduler.infrastructure import annual_model
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period, snapshot


def test_scheduler_annual_cancellation_before_build_skips_native_work(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Cancelled annual planning must not build or solve")

    monkeypatch.setattr(annual_model, "_quota_demands", unexpected)
    periods = (period(0),)
    plan = annual_model.plan_annual_quotas(snapshot(periods), periods, should_cancel=lambda: True)
    assert plan.status == "CANCELLED"
    assert plan.distribution is None
    assert not plan.latest_week_proven


@pytest.mark.parametrize("phase", ["LATEST_WEEK", "WASTE"])
def test_scheduler_annual_cancellation_interrupts_native_search(monkeypatch, phase):
    cancelled = Event()
    stopped = Event()
    original = cp_model.CpSolver.Solve
    calls = []

    def blocking(solver, model):
        calls.append(True)
        if phase == "WASTE" and len(calls) == 1:
            return original(solver, model)
        cancelled.set()
        assert stopped.wait(5), "Annual search must receive StopSearch while blocked"
        return cp_model.UNKNOWN

    monkeypatch.setattr(cp_model.CpSolver, "Solve", blocking)
    monkeypatch.setattr(cp_model.CpSolver, "StopSearch", lambda solver: stopped.set())
    periods = (period(0), period(7))
    plan = annual_model.plan_annual_quotas(
        snapshot(periods),
        periods,
        should_cancel=cancelled.is_set,
    )
    assert plan.status == "CANCELLED"
    assert plan.distribution is None
    assert not plan.latest_week_proven


def test_scheduler_annual_cancellation_after_build_skips_native_search(monkeypatch):
    cancelled = Event()

    def unexpected(*args, **kwargs):
        raise AssertionError("Cancellation during annual construction must prevent native solve")

    monkeypatch.setattr(annual_model.diagnostics, "model_built", lambda *a, **k: cancelled.set())
    monkeypatch.setattr(cp_model.CpSolver, "Solve", unexpected)
    periods = (period(0),)
    plan = annual_model.plan_annual_quotas(
        snapshot(periods),
        periods,
        should_cancel=cancelled.is_set,
    )
    assert plan.status == "CANCELLED"
    assert plan.distribution is None
