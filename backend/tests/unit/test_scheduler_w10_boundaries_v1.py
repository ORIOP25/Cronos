"""W10 boundaries: proven pressure transitions and their reversal."""

import pytest

from app.scheduler.lab.boundaries import (
    block_resource,
    prove_pressure,
    remove_eligible_rooms,
    remove_grid_slot,
)
from app.scheduler.lab.fixtures import (
    AssignmentSpec,
    CaseExpectation,
    build_fixture,
    build_snapshot,
)
from tests.unit.test_scheduler_lab_campaign import FEASIBLE_SPEC

SINGLE_ROOM_SPEC = type(FEASIBLE_SPEC)(
    **{
        **FEASIBLE_SPEC.__dict__,
        "assignments": (AssignmentSpec(1, 100, (100,), (500,)),),
    }
)


def _pressure_fixture(spec):
    return build_fixture(
        "pressure",
        spec,
        family="frontier",
        expectation=CaseExpectation.INFEASIBLE_PROVEN,
    )


def test_blocking_the_only_room_is_a_proven_boundary_and_the_reversal_restores_it():
    transition = block_resource(SINGLE_ROOM_SPEC, "room", 500)

    pressure = _pressure_fixture(transition.pressure)
    reversal = build_fixture(
        "reversal", transition.reversal, expectation=CaseExpectation.FEASIBLE_WITH_WITNESS
    )

    assert pressure.witness is None
    assert reversal.witness is not None
    assert transition.reversal == SINGLE_ROOM_SPEC
    assert "PROVEN_LOWER_BOUND" in prove_pressure(transition.pressure)[0]


def test_removing_an_alternative_is_valid_but_not_proven_and_is_rejected_loudly():
    two_rooms = AssignmentSpec(1, 100, (100,), (500, 501))
    transition = remove_eligible_rooms(
        type(FEASIBLE_SPEC)(**{**FEASIBLE_SPEC.__dict__, "assignments": (two_rooms,)})
    )

    assert len(transition.pressure.assignments[0].eligible_rooms) == 1
    with pytest.raises(ValueError, match="not proven"):
        prove_pressure(transition.pressure)


def test_removing_every_room_is_rejected_because_the_domain_requires_one():
    with pytest.raises(ValueError, match="keep between one and all"):
        remove_eligible_rooms(SINGLE_ROOM_SPEC, keep=0)


def test_blocking_the_teacher_is_a_proven_boundary():
    transition = block_resource(SINGLE_ROOM_SPEC, "teacher", 100)

    _pressure_fixture(transition.pressure)
    explanations = prove_pressure(transition.pressure)

    assert explanations
    assert all("PROVEN_LOWER_BOUND" in row for row in explanations)


def test_removing_a_grid_slot_is_a_proven_boundary_when_capacity_falls_short():
    transition = remove_grid_slot(FEASIBLE_SPEC)

    _pressure_fixture(transition.pressure)

    assert len(transition.pressure.grid_slots) == 1
    assert prove_pressure(transition.pressure)


def test_pressure_never_claims_impossibility_without_a_deficit():
    with pytest.raises(ValueError, match="not proven"):
        prove_pressure(SINGLE_ROOM_SPEC)


def test_boundary_transition_serializes_the_pressure_and_the_reversal():
    transition = block_resource(SINGLE_ROOM_SPEC, "room", 500)

    snapshot = build_snapshot(transition.pressure)

    assert snapshot.assignments[0].eligible_room_ids == frozenset({500})
    assert transition.explanation
