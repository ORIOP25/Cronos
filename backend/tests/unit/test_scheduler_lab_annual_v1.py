"""Annual corpus, stored artifacts and independent revalidation."""

import json
from dataclasses import replace

from app.scheduler.composition import generate_schedule
from app.scheduler.domain.candidate import Unavailability, UnavailableResource
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import aggregate_capacity_check
from app.scheduler.domain.quality import measure_initial_quality
from app.scheduler.domain.serialization import (
    candidate_digest,
    candidate_from_dict,
    candidate_to_dict,
    period_from_dict,
    period_to_dict,
    snapshot_from_dict,
    snapshot_to_dict,
)
from app.scheduler.lab.annual import (
    PROFILE_CONNECTED,
    PROFILE_LOOSE,
    PROFILE_SCARCE_ROOMS,
    PROFILE_SHARED_TEACHER,
    annual_topology,
    build_annual_fixture,
)
from app.scheduler.lab.fixtures import CaseExpectation
from app.scheduler.lab.manifest import (
    AnnualCaseSpec,
    CaseSeeds,
    LabCase,
    build_case,
    from_manifest,
    to_manifest,
)
from app.scheduler.lab.payload import quality_to_dict, validation_to_dict
from app.scheduler.lab.revalidate import revalidate
from app.scheduler.lab.scale import build_scale_fixture


def test_annual_fixture_witnesses_are_valid_for_every_profile():
    for profile in (
        PROFILE_LOOSE,
        PROFILE_SHARED_TEACHER,
        PROFILE_SCARCE_ROOMS,
        PROFILE_CONNECTED,
    ):
        fixture = build_annual_fixture(6, profile=profile, seed=1)

        report = validate_candidate(fixture.snapshot, fixture.witness)

        assert report.valid, (profile, sorted(row.code.value for row in report.violations))
        assert len(fixture.snapshot.assignments) == 6 * 3
        assert len({row.subject_id for row in fixture.snapshot.assignments}) == 3
        weeks = {
            (period.school_date - fixture.snapshot.origin).days // 7 for period in fixture.periods
        }
        assert len(weeks) >= 30
        assert fixture.snapshot.blocked_dates


def test_connected_profile_adds_alternatives_and_transversal_teachers():
    connected = build_annual_fixture(6, profile=PROFILE_CONNECTED, seed=1)
    loose = build_annual_fixture(6, profile=PROFILE_LOOSE, seed=1)

    topology = annual_topology(connected.snapshot)

    assert topology["assignments_with_room_alternatives"] == len(connected.snapshot.assignments)
    assert topology["teachers_with_transversal_classes"] >= 1
    assert topology["shared_teachers"] >= 1
    assert topology["unavailable_intervals"] > 0
    assert annual_topology(loose.snapshot)["assignments_with_room_alternatives"] == 0
    assert validate_candidate(connected.snapshot, connected.witness).valid


def test_connected_annual_fixture_has_a_proven_impossible_variant():
    fixture = build_annual_fixture(4, profile=PROFILE_CONNECTED, seed=1)
    victim = fixture.snapshot.assignments[0]
    blocked = tuple(
        Unavailability(UnavailableResource.TEACHER, victim.teacher_id, period)
        for period in fixture.periods
    )
    snapshot = replace(fixture.snapshot, unavailable=(*fixture.snapshot.unavailable, *blocked))

    result = generate_schedule(snapshot, fixture.periods, time_limit_seconds=10)

    assert aggregate_capacity_check(snapshot, fixture.periods).proven_infeasible
    assert result.outcome == "INFEASIBLE"


def test_annual_fixture_seed_changes_the_problem_topology():
    base = build_annual_fixture(8, profile=PROFILE_LOOSE, seed=1)
    other = build_annual_fixture(8, profile=PROFILE_LOOSE, seed=2)

    assert base.snapshot != other.snapshot
    assert base.snapshot.assignments != other.snapshot.assignments


def test_scale_fixture_seed_changes_the_problem_topology():
    first = build_scale_fixture(10, seed=1)
    second = build_scale_fixture(10, seed=2)

    assert first.snapshot != second.snapshot
    assert {row.teacher_id for row in first.snapshot.assignments} != {
        row.teacher_id for row in second.snapshot.assignments
    }


def test_annual_snapshot_and_candidate_payloads_roundtrip():
    fixture = build_annual_fixture(4, profile=PROFILE_SCARCE_ROOMS, seed=3)

    snapshot = snapshot_from_dict(snapshot_to_dict(fixture.snapshot))
    candidate = candidate_from_dict(candidate_to_dict(fixture.witness))

    assert snapshot == fixture.snapshot
    assert candidate == fixture.witness
    assert candidate_digest(candidate) == candidate_digest(fixture.witness)
    periods = tuple(period_from_dict(period_to_dict(row)) for row in fixture.periods)
    assert periods == fixture.periods


def test_a_stored_candidate_revalidates_and_detects_tampering(tmp_path):
    case = LabCase(
        case_id="annual-roundtrip",
        family="A-roundtrip",
        version=1,
        expectation=CaseExpectation.FEASIBLE_WITH_WITNESS,
        spec=None,
        seeds=CaseSeeds(1, 2, 3),
        annual=AnnualCaseSpec(4, PROFILE_LOOSE, 1),
    )
    fixture = build_case(case)
    generated = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=20)
    assert generated.outcome == "COMPLETE"
    payload = {
        "case_id": case.case_id,
        "snapshot": snapshot_to_dict(fixture.snapshot),
        "periods": [period_to_dict(period) for period in fixture.periods],
        "candidate": candidate_to_dict(generated.candidate),
        "candidate_digest": candidate_digest(generated.candidate),
        "validation": validation_to_dict(generated.report),
        "quality": quality_to_dict(generated.quality),
    }
    stored = tmp_path / "case.json"
    stored.write_text(json.dumps({"result": {"payload": payload}}), encoding="utf-8")

    summary = revalidate(stored)

    assert summary["revalidated"] is True
    assert summary["valid"] is True
    lessons = [list(row) for row in payload["candidate"]["lessons"]]
    lessons[0][3] = lessons[0][3] + 1
    adulterated = {**payload, "candidate": {"lessons": lessons}}
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps({"result": {"payload": adulterated}}), encoding="utf-8")

    summary = revalidate(tampered)

    assert summary["revalidated"] is False
    assert "candidate digest does not match the stored payload" in summary["problems"]


def test_the_annual_manifest_builds_without_the_oracle():
    manifest = {
        "schema_version": "scheduler-lab-v3",
        "campaign_id": "annual-unit",
        "cases": [
            {
                "case_id": "annual-unit-1",
                "family": "A",
                "version": 1,
                "expectation": "FEASIBLE_WITH_WITNESS",
                "mutation": None,
                "expected_violations": [],
                "seeds": {"fixture_seed": 1, "event_seed": 2, "solver_seed": 3},
                "spec": None,
                "scale": None,
                "annual": {"class_count": 4, "profile": "loose", "seed": 1},
            }
        ],
    }

    campaign_id, cases = from_manifest(manifest)
    fixture = build_case(cases[0])

    assert campaign_id == "annual-unit"
    assert fixture.witness is not None
    assert validate_candidate(fixture.snapshot, fixture.witness).valid
    assert measure_initial_quality(fixture.snapshot, fixture.witness).completion_dates
    assert to_manifest("annual-unit", cases)["cases"][0]["annual"]["class_count"] == 4
