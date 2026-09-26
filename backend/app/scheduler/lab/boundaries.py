"""C02–C08/C15: feasibility boundaries and pressure reversal.

Pressure is a controlled removal of indispensable capacity over a feasible
baseline. The transition is only declared when the necessary-capacity check
proves the deficit; the reversal restores exactly the original data. A timeout
is never used as a proof of impossibility.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.capacity import aggregate_capacity_check, canonical_periods
from app.scheduler.lab.fixtures import FixtureSpec, build_snapshot


@dataclass(frozen=True)
class BoundaryTransition:
    resource: str
    pressure: FixtureSpec
    reversal: FixtureSpec
    explanation: str


def _with_assignment(spec: FixtureSpec, index: int, assignment) -> FixtureSpec:
    rows = list(spec.assignments)
    rows[index] = assignment
    return replace(spec, assignments=tuple(rows))


def remove_eligible_rooms(
    spec: FixtureSpec, *, assignment_index: int = 0, keep: int = 1
) -> BoundaryTransition:
    """Leave ``keep`` eligible rooms on one assignment, removing the alternatives.

    The domain always requires at least one eligible room; blocking the last
    usable room is modelled with :func:`block_resource`.
    """
    assignment = spec.assignments[assignment_index]
    if keep < 1 or keep >= len(assignment.eligible_rooms):
        raise ValueError("The boundary must keep between one and all rooms.")
    remaining = assignment.eligible_rooms[:keep]
    pressure = _with_assignment(
        spec, assignment_index, replace(assignment, eligible_rooms=remaining)
    )
    removed = sorted(set(assignment.eligible_rooms) - set(remaining))
    return BoundaryTransition(
        resource=f"rooms:{removed}",
        pressure=pressure,
        reversal=spec,
        explanation=(
            f"Removing eligible rooms {removed} leaves assignment "
            f"{assignment_index + 1} with fewer alternatives."
        ),
    )


def block_resource(
    spec: FixtureSpec, resource_type: str, resource_id: int, *, start_index: int = 0
) -> BoundaryTransition:
    """Make a class or teacher unavailable on every period from ``start_index``."""
    rows = tuple(
        (resource_type, resource_id, (day, start, end))
        for day, start, end in spec.periods[start_index:]
    )
    if not rows:
        raise ValueError("Blocking a resource needs at least one period.")
    pressure = replace(spec, unavailable=(*spec.unavailable, *rows))
    return BoundaryTransition(
        resource=f"{resource_type.lower()}:{resource_id}",
        pressure=pressure,
        reversal=spec,
        explanation=(
            f"{resource_type} {resource_id} is unavailable from period {start_index + 1}; "
            "the demand cannot be placed."
        ),
    )


def remove_grid_slot(spec: FixtureSpec, *, slot_index: int = 0) -> BoundaryTransition:
    """Remove one recurring grid slot and every concrete period it matched."""
    slot = spec.grid_slots[slot_index]
    day_of_week, start, end = slot
    periods = tuple(
        row for row in spec.periods if not (row[0].weekday() == day_of_week and row[1] == start)
    )
    pressure = replace(
        spec,
        grid_slots=tuple(row for index, row in enumerate(spec.grid_slots) if index != slot_index),
        periods=periods,
    )
    return BoundaryTransition(
        resource=f"grid:{day_of_week}-{start.isoformat()}",
        pressure=pressure,
        reversal=spec,
        explanation=(
            f"Grid slot {day_of_week} {start.isoformat()}–{end.isoformat()} and its "
            "concrete periods were removed."
        ),
    )


def prove_pressure(spec: FixtureSpec) -> tuple[str, ...]:
    """Proven deficit explanations; raises when the pressure is not demonstrated."""
    snapshot = build_snapshot(spec)
    periods = canonical_periods(
        tuple(
            normalize_period(day, start, end, spec.timezone_name)
            for day, start, end in spec.periods
        )
    )
    check = aggregate_capacity_check(snapshot, periods)
    if not check.proven_infeasible:
        raise ValueError("The transition pressure is not proven by the capacity check.")
    return tuple(
        f"assignment {assignment_id}: {deficit} minutes without eligible capacity "
        f"({check.evidence_kind})"
        for assignment_id, deficit in sorted(check.deficits.items())
        if deficit > 0
    )
