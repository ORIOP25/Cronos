"""W10.5 failure reduction: shrink a failing spec to a minimal deterministic case.

A corrected failure must leave a permanent, deterministic regression. This
delta-debugging reducer removes independent inputs (assignments, modules,
periods, grid slots, extra rows) while a caller-provided predicate still
reproduces the failure. It never decides correctness itself and never weakens
validation: the predicate is the arbiter.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from app.scheduler.lab.fixtures import CaseExpectation, FixtureSpec
from app.scheduler.lab.manifest import CaseSeeds, LabCase

FailurePredicate = Callable[[FixtureSpec], bool]


@dataclass(frozen=True)
class ReductionResult:
    spec: FixtureSpec
    attempts: int
    accepted: int


def _without_assignment(spec: FixtureSpec, index: int) -> FixtureSpec:
    return replace(
        spec,
        assignments=tuple(
            row for position, row in enumerate(spec.assignments) if position != index
        ),
    )


def _without_module(spec: FixtureSpec, assignment_index: int, module_index: int) -> FixtureSpec:
    rows = list(spec.assignments)
    assignment = rows[assignment_index]
    rows[assignment_index] = replace(
        assignment,
        module_minutes=tuple(
            minutes
            for position, minutes in enumerate(assignment.module_minutes)
            if position != module_index
        ),
    )
    return replace(spec, assignments=tuple(rows))


def _with_halved_module(spec: FixtureSpec, assignment_index: int, module_index: int) -> FixtureSpec:
    rows = list(spec.assignments)
    assignment = rows[assignment_index]
    minutes = list(assignment.module_minutes)
    minutes[module_index] = minutes[module_index] // 2
    rows[assignment_index] = replace(assignment, module_minutes=tuple(minutes))
    return replace(spec, assignments=tuple(rows))


def _without_period(spec: FixtureSpec, index: int) -> FixtureSpec:
    return replace(
        spec, periods=tuple(row for position, row in enumerate(spec.periods) if position != index)
    )


def _without_grid_slot(spec: FixtureSpec, index: int) -> FixtureSpec:
    return replace(
        spec,
        grid_slots=tuple(row for position, row in enumerate(spec.grid_slots) if position != index),
    )


def _without_row(spec: FixtureSpec, field: str, index: int) -> FixtureSpec:
    rows = tuple(getattr(spec, field))
    return replace(spec, **{field: rows[:index] + rows[index + 1 :]})


def _without_set_member(spec: FixtureSpec, field: str, value) -> FixtureSpec:
    rows = frozenset(getattr(spec, field)) - {value}
    return replace(spec, **{field: rows})


def _candidates(spec: FixtureSpec) -> Iterable[FixtureSpec]:
    if len(spec.assignments) > 1:
        for index in range(len(spec.assignments)):
            yield _without_assignment(spec, index)
    for assignment_index, assignment in enumerate(spec.assignments):
        if len(assignment.module_minutes) > 1:
            for module_index in range(len(assignment.module_minutes)):
                yield _without_module(spec, assignment_index, module_index)
        for module_index, minutes in enumerate(assignment.module_minutes):
            if minutes > 1:
                yield _with_halved_module(spec, assignment_index, module_index)
    if len(spec.periods) > 1:
        for index in range(len(spec.periods)):
            yield _without_period(spec, index)
    if len(spec.grid_slots) > 1:
        for index in range(len(spec.grid_slots)):
            yield _without_grid_slot(spec, index)
    for field in (
        "unavailable",
        "soft_unavailable",
        "executed_minutes",
        "reservations",
        "open_debt_minutes",
        "claim_assignments",
    ):
        for index in range(len(getattr(spec, field))):
            yield _without_row(spec, field, index)
    for field in ("blocked_dates", "protected_dates"):
        for value in sorted(getattr(spec, field)):
            yield _without_set_member(spec, field, value)


def reduce_spec(spec: FixtureSpec, fails: FailurePredicate) -> ReductionResult:
    """Greedily remove inputs while the failure predicate still holds."""
    if not fails(spec):
        raise ValueError("The reducer needs a spec that reproduces the failure.")
    attempts = 0
    accepted = 0
    current = spec
    changed = True
    while changed:
        changed = False
        for candidate in _candidates(current):
            attempts += 1
            if candidate == current:
                continue
            if fails(candidate):
                current = candidate
                accepted += 1
                changed = True
                break
    return ReductionResult(current, attempts, accepted)


def reduced_case(
    case_id: str,
    family: str,
    spec: FixtureSpec,
    *,
    expectation: CaseExpectation,
    version: int = 1,
) -> LabCase:
    """Turn a reduced spec into a deterministic regression case."""
    return LabCase(
        case_id=case_id,
        family=family,
        version=version,
        expectation=expectation,
        spec=spec,
        seeds=CaseSeeds(0, 0, 0),
    )
