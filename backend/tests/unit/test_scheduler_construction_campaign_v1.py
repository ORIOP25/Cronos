"""Manual equivalence campaign; never part of the critical fast manifest."""

import pytest

from app.scheduler.domain.serialization import canonical_json_value, snapshot_to_dict
from tests._support.construction_snapshot import (
    assert_base_sources,
    campaign_profiles,
    read_reference,
    repair_models,
    run_profile,
    update_scenario,
    write_reference,
)

pytestmark = pytest.mark.slow_solver


@pytest.mark.parametrize("profile", tuple(campaign_profiles()))
def test_construction_campaign_freeze_base(profile):
    assert_base_sources()
    write_reference(profile, run_profile(profile))


@pytest.mark.parametrize("profile", tuple(campaign_profiles()))
def test_construction_campaign_matches_frozen_base(profile):
    assert canonical_json_value(run_profile(profile)) == read_reference(profile)


def test_construction_campaign_freeze_base_models(monkeypatch):
    assert_base_sources()
    write_reference("period-models", repair_models(monkeypatch))


def test_construction_campaign_period_models_match_frozen_base(monkeypatch):
    assert repair_models(monkeypatch) == read_reference("period-models")


@pytest.mark.parametrize("event", ("A", "B"))
def test_construction_campaign_freeze_base_update_inputs(event):
    assert_base_sources()
    snapshot, periods, active, history, teacher = update_scenario(event)
    write_reference(
        f"update-input-{event}",
        {
            "snapshot": snapshot_to_dict(snapshot),
            "history": history,
            "teacher": teacher,
        },
    )
