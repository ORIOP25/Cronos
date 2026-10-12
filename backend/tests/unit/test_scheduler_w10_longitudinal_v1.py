"""W10 longitudinal annual replays: events accumulated over an approved baseline."""

from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.lab.annual import build_annual_fixture
from app.scheduler.lab.longitudinal import (
    AnnualReplay,
    replay_annual_events,
    replay_to_dict,
)


def _replay() -> AnnualReplay:
    fixture = build_annual_fixture(2, profile="loose", seed=1)
    return replay_annual_events(
        fixture,
        event_count=3,
        event_seed=1,
        step_days=14,
        time_limit_seconds=10.0,
        solver_seed=3,
        stop_at_first_complete=True,
    )


def test_a_completed_replay_validates_every_event_and_conserves_minutes():
    replay = _replay()

    assert replay.completed is True
    assert len(replay.steps) == 3
    assert replay.stopped_reason == ""
    assert replay.conserved is True
    assert replay.final_candidate is not None
    assert validate_candidate(replay.snapshot, replay.final_candidate).valid is True

    for step in replay.steps:
        assert step.outcome == "COMPLETE"
        assert step.applied is True
        assert step.affected_lessons >= 1
        assert step.valid is True
        assert step.conserved is True

    first = replay.steps[0]
    assert first.executed_minutes > 0
    assert first.planned_minutes > 0
    assert replay.steps[-1].executed_minutes > first.executed_minutes

    payload = replay_to_dict(replay)
    assert payload["completed"] is True
    assert len(payload["steps"]) == 3
    assert {"step", "event", "outcome", "valid", "conserved"} <= set(payload["steps"][0])


def test_replay_forwards_the_native_stop_at_first_complete_flag(monkeypatch):
    import app.scheduler.lab.longitudinal as longitudinal

    seen: list[bool | None] = []
    real = longitudinal.repair_published_schedule

    def spy(*args, **kwargs):
        seen.append(kwargs.get("stop_at_first_complete"))
        return real(*args, **kwargs)

    monkeypatch.setattr(longitudinal, "repair_published_schedule", spy)
    fixture = build_annual_fixture(2, profile="loose", seed=1)

    replay_annual_events(
        fixture,
        event_count=2,
        event_seed=1,
        step_days=14,
        time_limit_seconds=10.0,
        solver_seed=3,
        stop_at_first_complete=True,
    )

    assert seen == [True, True]


def test_replay_default_keeps_the_optimized_mode():
    import inspect

    parameter = inspect.signature(replay_annual_events).parameters["stop_at_first_complete"]

    assert parameter.default is False


def test_an_event_free_replay_is_valid_and_reports_no_steps():
    fixture = build_annual_fixture(2, profile="loose", seed=1)

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


def test_a_clock_that_consumes_the_year_before_events_is_incomplete():
    fixture = build_annual_fixture(2, profile="loose", seed=1)

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
    outcome = result.outcome.value
    replay = result.payload["replay"]
    # This certifies the longitudinal campaign plumbing and payload, not generation
    # quality: the bounded campaign may legitimately settle as INCONCLUSIVE.
    assert outcome in {"VALID", "INCONCLUSIVE"}
    assert replay["event_count"] == 1
    if outcome == "VALID":
        assert replay["completed"] is True
        assert replay["conserved"] is True
        assert replay["stopped_reason"] == ""
    else:
        assert replay["completed"] is False
