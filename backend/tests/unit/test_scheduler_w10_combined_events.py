"""W10 lab: combined recovery cases with accumulated events."""

from dataclasses import replace

from app.scheduler.lab.campaign import run_campaign_directory
from app.scheduler.lab.fixtures import CaseExpectation
from app.scheduler.lab.manifest import (
    CaseSeeds,
    LabCase,
    case_from_dict,
    case_to_dict,
    to_manifest,
)
from app.scheduler.lab.recovery import (
    EVENTS,
    ROOM_CLOSED,
    build_recovery_case,
    perturb_constructed_fixture,
    recovery_event,
)
from tests.unit.test_scheduler_lab_recovery_v1 import MANIFEST
from tests.unit.test_scheduler_recovery_solver_v1 import _spec


def test_lab_case_events_roundtrip_through_the_manifest():
    case = LabCase(
        "combined",
        "C08",
        1,
        CaseExpectation.FEASIBLE_WITH_WITNESS,
        _spec(),
        CaseSeeds(1, 2, 3),
        events=(0, 2),
    )

    restored = case_from_dict(case_to_dict(case))

    assert restored.events == (0, 2)


def test_a_legacy_manifest_without_events_defaults_to_none():
    case = LabCase(
        "plain",
        "C01",
        1,
        CaseExpectation.FEASIBLE_WITH_WITNESS,
        _spec(),
        CaseSeeds(1, 2, 3),
    )

    data = case_to_dict(case)
    data.pop("events")

    restored = case_from_dict(data)

    assert restored.events == ()


def test_extra_events_accumulate_unavailability_on_the_snapshot():
    single = build_recovery_case("single", _spec(), event_seed=0)
    combined = build_recovery_case("combined", _spec(), event_seed=0, extra_events=(2,))

    assert len(combined.snapshot.unavailable) > len(single.snapshot.unavailable)
    assert combined.event == single.event


def test_a_perturbed_constructed_fixture_accepts_extra_events():
    from app.scheduler.lab.scale import build_scale_fixture

    fixture = build_scale_fixture(4, seed=1)
    single = perturb_constructed_fixture(fixture, event_seed=0)
    combined = perturb_constructed_fixture(fixture, event_seed=0, extra_events=(1, 2))

    assert len(combined.snapshot.unavailable) > len(single.snapshot.unavailable)


def test_the_campaign_applies_declared_events_to_a_small_case(tmp_path):
    base = build_recovery_case("events-base", _spec(), event_seed=0)
    spec = _spec()
    case = LabCase(
        "events-case",
        "C08",
        1,
        CaseExpectation.FEASIBLE_WITH_WITNESS,
        spec,
        CaseSeeds(1, 0, 1),
        events=(2,),
    )
    manifest = to_manifest("events-campaign", (case,))

    report = run_campaign_directory(
        manifest, tmp_path, commit="test", mode="repair", time_limit_seconds=10
    )

    result = report.results[0]
    assert result.outcome.value in {"VALID", "INFEASIBLE", "INCONCLUSIVE"}
    if result.outcome.value == "VALID":
        assert len(result.payload["baseline"]) == len(base.baseline.lessons)


def test_unknown_event_seeds_are_rejected_before_the_solve(tmp_path):
    case = replace(
        LabCase(
            "bad-events",
            "C08",
            1,
            CaseExpectation.FEASIBLE_WITH_WITNESS,
            _spec(),
            CaseSeeds(1, 0, 1),
        ),
        events=(0, -1),
    )
    manifest = to_manifest("events-campaign", (case,))

    report = run_campaign_directory(manifest, tmp_path, commit="test", mode="repair")

    assert report.results[0].outcome.value == "ERROR"


def test_repair_manifest_still_loads_with_explicit_empty_events():
    import json

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    _campaign_id, cases = __import__(
        "app.scheduler.lab.manifest", fromlist=["from_manifest"]
    ).from_manifest(manifest)

    assert all(case.events == () for case in cases)


def test_event_seeds_map_to_declared_codes():
    assert recovery_event(0) == EVENTS[0]
    assert recovery_event(1) == EVENTS[1]
    assert recovery_event(2) == EVENTS[2]
    assert recovery_event(3) == EVENTS[0]
    assert build_recovery_case("codes", _spec(), event_seed=2).event == ROOM_CLOSED
