"""Memory guard for the exact placement model (scheduler v1).

A placement model whose decision variables exceed the worker memory budget is
never built. The engine reports an inconclusive outcome, so the worker ends
without a claim instead of being killed by the out-of-memory killer.
"""

from __future__ import annotations

from app.scheduler.infrastructure import placement_model
from app.scheduler.lab.scale import build_scale_fixture

OVERSIZED_MESSAGE = "The exact placement model exceeds the worker memory budget."


def _fail_build(*_args, **_kwargs):
    raise AssertionError("An oversized placement model must not be built")


def test_oversized_model_is_refused_before_it_is_built(monkeypatch):
    fixture = build_scale_fixture(6, seed=1)
    monkeypatch.setattr(placement_model, "MAX_PLACEMENT_VARIABLES", 1)
    monkeypatch.setattr(placement_model, "_build_scope_state", _fail_build)

    outcome = placement_model.solve_placement(
        fixture.snapshot, fixture.periods, distribution=None, time_limit_seconds=5
    )

    assert outcome.status == placement_model.STATUS_INCONCLUSIVE
    assert outcome.candidate is None
    assert outcome.statistics["oversized_scopes"] == 1
    assert outcome.message == OVERSIZED_MESSAGE


def test_variable_estimate_bounds_the_built_assignment_options():
    fixture = build_scale_fixture(6, seed=1)
    scope = placement_model._unrestricted_scope(fixture.snapshot, fixture.periods)
    state = placement_model._build_scope_state(fixture.snapshot, scope)

    estimate = placement_model._estimated_variables(scope)

    assert estimate > 0
    assert estimate >= len(state.x) + len(state.room_choice) + len(state.last) + len(state.waste)


def test_normal_size_model_still_solves_completely():
    fixture = build_scale_fixture(6, seed=1)

    outcome = placement_model.solve_placement(
        fixture.snapshot, fixture.periods, distribution=None, time_limit_seconds=5
    )

    assert outcome.status == placement_model.STATUS_COMPLETE
    assert "oversized_scopes" not in outcome.statistics
