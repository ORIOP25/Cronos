"""Fallback search and diagnostics preservation (scheduler v1).

The seasonal master/detail search can exhaust its feedback rounds or stop on an
inconclusive window without an incumbent. These tests force that situation and
require the search to either return a complete candidate through the unrestricted
fallback or an inconclusive outcome that keeps its evidence and statistics.
"""

from __future__ import annotations

import app.scheduler.infrastructure.search as search_module
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.infrastructure.annual_model import (
    STATUS_INCONCLUSIVE as ANNUAL_INCONCLUSIVE,
)
from app.scheduler.infrastructure.annual_model import AnnualPlan
from app.scheduler.infrastructure.placement_model import (
    STATUS_INCONCLUSIVE as PLACEMENT_INCONCLUSIVE,
)
from app.scheduler.infrastructure.placement_model import PlacementOutcome
from app.scheduler.lab.scale import build_scale_fixture

INCONCLUSIVE_PLAN = AnnualPlan(
    ANNUAL_INCONCLUSIVE, None, None, None, 0, False, 0.0, {"variables": 0}
)


def _inconclusive_plan(*_args, **_kwargs) -> AnnualPlan:
    return INCONCLUSIVE_PLAN


def _inconclusive_placement(*_args, **_kwargs) -> PlacementOutcome:
    return PlacementOutcome(
        PLACEMENT_INCONCLUSIVE,
        None,
        None,
        0.0,
        "UNRESTRICTED",
        {"variables": 12, "windows": 1},
    )


def _no_construction(*_args, **_kwargs):
    return None


def test_fallback_completes_when_the_annual_relaxation_is_inconclusive(monkeypatch):
    fixture = build_scale_fixture(6, seed=1)
    monkeypatch.setattr(search_module, "plan_annual_quotas", _inconclusive_plan)
    monkeypatch.setattr(search_module, "construct_schedule", _no_construction)

    outcome = search_module.search_complete_schedule(
        fixture.snapshot, fixture.periods, time_limit_seconds=10.0, num_workers=2, random_seed=3
    )

    assert outcome.status == "COMPLETE"
    assert outcome.candidate is not None
    assert validate_candidate(fixture.snapshot, outcome.candidate).valid
    assert outcome.evidence is not None
    assert outcome.evidence.stop_reason == "FALLBACK_UNRESTRICTED"


def test_inconclusive_search_preserves_evidence_and_statistics(monkeypatch):
    fixture = build_scale_fixture(6, seed=1)
    monkeypatch.setattr(search_module, "plan_annual_quotas", _inconclusive_plan)
    monkeypatch.setattr(search_module, "solve_placement", _inconclusive_placement)
    monkeypatch.setattr(search_module, "construct_schedule", _no_construction)

    outcome = search_module.search_complete_schedule(
        fixture.snapshot, fixture.periods, time_limit_seconds=10.0, num_workers=2, random_seed=3
    )

    assert outcome.status == "INCONCLUSIVE"
    assert outcome.evidence is not None
    assert outcome.evidence.stop_reason == "SEARCH_STOPPED"
    assert outcome.statistics.get("variables") == 12


def test_the_constructive_fallback_settles_a_viable_case(monkeypatch):
    fixture = build_scale_fixture(6, seed=1)
    monkeypatch.setattr(search_module, "plan_annual_quotas", _inconclusive_plan)

    outcome = search_module.search_complete_schedule(
        fixture.snapshot, fixture.periods, time_limit_seconds=10.0, num_workers=2, random_seed=3
    )

    assert outcome.status == "COMPLETE"
    assert outcome.candidate is not None
    assert validate_candidate(fixture.snapshot, outcome.candidate).valid
    assert outcome.evidence is not None
    assert outcome.evidence.stop_reason == "CONSTRUCTIVE"


def test_stop_at_first_complete_returns_the_constructor_without_optimizing():
    fixture = build_scale_fixture(6, seed=1)

    outcome = search_module.search_complete_schedule(
        fixture.snapshot,
        fixture.periods,
        time_limit_seconds=10.0,
        num_workers=2,
        random_seed=3,
        stop_at_first_complete=True,
    )

    assert outcome.status == "COMPLETE"
    assert outcome.candidate is not None
    assert validate_candidate(fixture.snapshot, outcome.candidate).valid
    assert outcome.evidence is not None
    assert outcome.evidence.stop_reason == "CONSTRUCTIVE"
