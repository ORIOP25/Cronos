"""Read-only review probes. Run with the repository backend on PYTHONPATH.

These are diagnostic reproductions, not acceptance tests: observed defects are
recorded alongside independent oracle results, not asserted as desired behavior.
"""
import json
from dataclasses import fields, is_dataclass, replace
from datetime import date, time, timedelta
from collections.abc import Mapping
from unittest.mock import patch

from app.scheduler.application.generation import generate_complete
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment, GridSlot, PlanningSnapshot, SchedulingStrategy,
    Unavailability, UnavailableResource,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.oracle import optimal_candidate, oracle_objective
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.infrastructure.placement_model import solve_placement
from app.scheduler.infrastructure import placement_model
from app.scheduler.infrastructure.annual_model import QuotaDistribution
from app.scheduler.lab.scale import build_scale_fixture

ORIGIN = date(2026, 9, 21)

def serial(value):
    if is_dataclass(value):
        return {f.name: serial(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): serial(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [serial(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)

def period(day, start=9, end=10, start_min=0, end_min=0):
    return normalize_period(ORIGIN + timedelta(days=day), time(start, start_min),
                            time(end, end_min), "Europe/Lisbon")

def snapshot(periods, minutes=60, count=1, **kwargs):
    return PlanningSnapshot(
        SchedulingStrategy.COMPLETE_GENERATION, ORIGIN, ORIGIN + timedelta(days=20),
        ORIGIN + timedelta(days=30), "Europe/Lisbon",
        tuple(dict.fromkeys(GridSlot(p.school_date.weekday(), p.start_local, p.end_local)
                            for p in periods)),
        tuple(Assignment(i, i, i, i, frozenset({i}),
                         (ModuleRequirement(i, 1, minutes),)) for i in range(1, count+1)),
        {}, frozenset(), kwargs.pop("unavailable", ()), **kwargs,
    )

def observe(s, ps, oracle=True):
    result = generate_complete(s, ps, time_limit_seconds=10)
    row = {"result": serial(result)}
    if oracle:
        best = optimal_candidate(s, ps)
        row["oracle_vector"] = None if best is None else oracle_objective(s, best)
        row["oracle_valid"] = best is not None and validate_candidate(s, best).valid
    if result.candidate:
        row["actual_vector"] = oracle_objective(s, result.candidate)
    return row

results = {}
ps = (period(0, end=11), period(1, end=10, end_min=30))
s = snapshot(ps, minutes=90)
results["annual_waste_delays_completion"] = observe(s, ps)
results["annual_waste_delays_completion"]["unrestricted_detail"] = serial(solve_placement(s, ps))

ps = (period(0), period(0, start_min=30, end_min=30), period(1))
results["same_assignment_overlap"] = observe(snapshot(ps, minutes=120), ps)

ps = (period(0), period(1))
s = snapshot(ps, minutes=90)
results["period_order_sorted"] = observe(s, ps)
results["period_order_reversed"] = observe(s, tuple(reversed(ps)))

for count in (7, 9):
    unavailable = tuple(Unavailability(UnavailableResource.TEACHER, i, ps[0])
                        for i in range(1, count))
    soft = (Unavailability(UnavailableResource.TEACHER, count, ps[0]),)
    s = snapshot(ps, count=count, unavailable=unavailable, soft_unavailable=soft)
    results[f"completion_tail_{count}_classes"] = observe(s, ps)

ps = (period(0),)
s = snapshot(ps, soft_unavailable=(
    Unavailability(UnavailableResource.TEACHER, 1, ps[0]),
    Unavailability(UnavailableResource.ROOM, 1, ps[0]),
))
results["preference_metric_disagreement"] = observe(s, ps)

ps = (period(0), period(1))
results["protected_date"] = observe(snapshot(ps, protected_dates=frozenset({ORIGIN})), ps)
results["past_period"] = observe(snapshot(ps, now_utc=ps[0].end_utc), ps)

ps = (period(0), period(7), period(14))
s = snapshot(ps, unavailable=tuple(Unavailability(UnavailableResource.TEACHER, 1, p)
                                   for p in ps[1:]))
results["margin_without_recovery_capacity"] = observe(s, ps)
results["margin_without_recovery_capacity"]["after_only_available_lesson_cancelled"] = observe(
    replace(s, unavailable=s.unavailable + (Unavailability(UnavailableResource.TEACHER, 1, ps[0]),)), ps)

# Controlled solver-status injection isolates certification logic without relying
# on machine-specific timeouts. Real solutions are computed before downgrading
# the first returned proof status to FEASIBLE.
ps = (period(0),)
s = snapshot(ps, soft_unavailable=(Unavailability(UnavailableResource.TEACHER, 1, ps[0]),))
original = placement_model.cp_model.CpSolver.Solve
calls = [0]
def feasible_first(self, model, *args, **kwargs):
    status = original(self, model, *args, **kwargs)
    calls[0] += 1
    return placement_model.cp_model.FEASIBLE if calls[0] == 1 else status
with patch.object(placement_model.cp_model.CpSolver, "Solve", feasible_first):
    results["controlled_unproven_prefix"] = serial(solve_placement(s, ps))

first, second = build_scale_fixture(10, seed=1), build_scale_fixture(10, seed=2)
results["scale_seed_diversity"] = {
    "snapshots_equal": first.snapshot == second.snapshot,
    "periods_equal": first.periods == second.periods,
    "witnesses_equal": first.witness == second.witness,
}

# A positive quota does not constrain omitted (zero) groups. Filling the
# teacher's gap adds a 60-minute placement absent from the annual distribution.
ps = (period(0), period(0, start=10, end=11), period(0, start=11, end=12, end_min=30))
s = snapshot(ps, count=2)
s = replace(s, assignments=(s.assignments[0],
    replace(s.assignments[1], teacher_id=1, modules=(ModuleRequirement(2, 1, 90),))),
    unavailable=(Unavailability(UnavailableResource.CLASS, 1, ps[1]),
                 Unavailability(UnavailableResource.CLASS, 1, ps[2]),
                 Unavailability(UnavailableResource.CLASS, 2, ps[0])))
detail = solve_placement(s, ps, distribution=QuotaDistribution({(1, 0, 60): 1, (2, 0, 90): 1}))
results["detail_ignores_zero_quotas"] = {
    "supplied_counts": {"1,0,60": 1, "2,0,90": 1},
    "detail": serial(detail),
    "valid": detail.candidate is not None and validate_candidate(s, detail.candidate).valid,
}
print(json.dumps(serial(results), ensure_ascii=False, indent=2))
