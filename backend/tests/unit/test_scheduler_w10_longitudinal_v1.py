"""W10 longitudinal annual replays: events accumulated over an approved baseline."""

import json
from functools import lru_cache

from app.scheduler.lab.annual import build_annual_fixture
from app.scheduler.lab.longitudinal import (
    AnnualReplay,
    replay_annual_events,
    replay_to_dict,
)


@lru_cache(maxsize=1)
def _replay(time_limit_seconds: float = 10.0) -> AnnualReplay:
    fixture = build_annual_fixture(4, profile="loose", seed=1)
    return replay_annual_events(
        fixture,
        event_count=2,
        event_seed=1,
        step_days=14,
        time_limit_seconds=time_limit_seconds,
        solver_seed=3,
    )


def test_every_step_is_validated_and_conserves_minutes():
    replay = _replay()

    assert replay.steps, "The replay must record at least one step."
    for step in replay.steps:
        if step.outcome == "COMPLETE":
            assert step.valid
            assert step.conserved
            assert step.planned_minutes + step.executed_minutes >= 0
    if replay.completed:
        assert len(replay.steps) == 2
        assert replay.stopped_reason == ""


def test_execution_advances_the_clock_and_reduces_the_plannable_baseline():
    replay = _replay()

    first = replay.steps[0]
    assert first.executed_minutes > 0, "The first step must consume executed lessons."
    assert first.planned_minutes > 0


def test_a_completed_replay_keeps_all_assignments_covered():
    replay = _replay()

    if replay.completed:
        assert replay.final_candidate is not None
        assert replay.conserved


def test_replay_serializes_steps_and_conservation_for_the_campaign():
    replay = _replay()

    data = replay_to_dict(replay)

    assert data["case_id"] == replay.case_id
    assert data["completed"] is replay.completed
    assert len(data["steps"]) == len(replay.steps)
    for row in data["steps"]:
        assert {"step", "event", "outcome", "valid", "conserved"} <= set(row)
    assert "executed_minutes" in data
    assert "planned_minutes" in data


def test_an_event_free_replay_is_valid_and_reports_no_steps():
    fixture = build_annual_fixture(4, profile="loose", seed=1)

    replay = replay_annual_events(
        fixture,
        event_count=0,
        event_seed=0,
        step_days=14,
        time_limit_seconds=5.0,
        solver_seed=1,
    )

    assert isinstance(replay, AnnualReplay)
    assert replay.completed
    assert replay.steps == ()
    assert replay.conserved


def test_a_later_step_never_loses_the_conservation_invariant():
    replay = _replay()

    for step in replay.steps:
        assert step.conserved or step.outcome != "COMPLETE"


def test_a_clock_that_consumes_the_year_before_events_is_incomplete():
    fixture = build_annual_fixture(4, profile="loose", seed=1)

    replay = replay_annual_events(
        fixture,
        event_count=1,
        event_seed=0,
        step_days=400,
        time_limit_seconds=5.0,
        solver_seed=1,
    )

    assert replay.completed is False
    assert replay.final_candidate is None
    assert replay.conserved is False
    assert replay.steps == ()
    assert "consumed" in replay.stopped_reason.lower()


def test_every_declared_event_must_be_applied_to_future_lessons():
    fixture = build_annual_fixture(4, profile="loose", seed=1)

    replay = replay_annual_events(
        fixture,
        event_count=3,
        event_seed=1,
        step_days=14,
        time_limit_seconds=10.0,
        solver_seed=3,
    )

    assert replay.steps
    for step in replay.steps:
        assert step.applied is True
        assert step.affected_lessons >= 1
    if replay.completed:
        assert len(replay.steps) == 3
        assert all(step.outcome == "COMPLETE" for step in replay.steps)
        assert replay.conserved is True
        assert replay.final_candidate is not None


def test_replay_payload_roundtrips_as_json():
    replay = _replay()

    encoded = json.dumps(replay_to_dict(replay), sort_keys=True)

    assert "steps" in encoded


def test_the_campaign_exposes_the_longitudinal_mode(tmp_path):
    from app.scheduler.lab.campaign import run_campaign_directory
    from app.scheduler.lab.fixtures import CaseExpectation
    from app.scheduler.lab.manifest import AnnualCaseSpec, CaseSeeds, LabCase, to_manifest

    case = LabCase(
        "annual-replay",
        "C14",
        1,
        CaseExpectation.EXPLORATORY_UNKNOWN,
        None,
        CaseSeeds(1, 1, 3),
        annual=AnnualCaseSpec(4, "loose", 1, events=1, step_days=14),
    )
    manifest = to_manifest("w10-longitudinal", (case,))

    report = run_campaign_directory(
        manifest, tmp_path, commit="test", mode="longitudinal", time_limit_seconds=10
    )

    result = report.results[0]
    assert result.outcome.value in {"VALID", "INCONCLUSIVE"}
    assert result.payload["replay"]["event_count"] == 1
    if result.outcome.value == "VALID":
        assert result.payload["replay"]["conserved"] is True
