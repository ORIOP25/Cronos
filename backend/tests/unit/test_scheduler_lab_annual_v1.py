"""Annual corpus fixtures and payload roundtrips."""

from dataclasses import replace

from app.scheduler.composition import generate_schedule
from app.scheduler.domain.candidate import Unavailability, UnavailableResource
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import aggregate_capacity_check
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
