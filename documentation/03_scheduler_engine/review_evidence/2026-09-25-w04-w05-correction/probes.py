"""Re-execution of the W04/W05 review counterexamples against the corrected tree.

This is a review-evidence script, not product code. It mirrors the scenarios of
`review_evidence/2026-09-24-w04-w05/probes.py`, adapted to the corrected public
API, and records expected versus observed behavior per scenario.

Adaptation notes:

- The application entry point is `app.scheduler.composition.generate_schedule`
  (the application use case receives the search operation by injection).
- `QuotaDistribution` now carries the final group, so F07 supplies it.
- The controlled unproven-prefix probe uses a two-day instance: the corrected
  solver has no completion threshold on a single-day horizon. The pre-solve is
  solver call 1 and the completion threshold is call 2; the probe downgrades
  call 2 to FEASIBLE so an unproven stage precedes a proven stage.
- `recovery` replaces the ambiguous `recoverable` boolean.

Run inside the backend test image:

    docker run --rm --network none \
      --mount type=bind,source=<repo>,target=/workspace \
      -w /workspace/backend -e PYTHONPATH=/workspace/backend \
      cronos-backend-test:local python \
      /workspace/documentation/03_scheduler_engine/review_evidence/2026-09-25-w04-w05-correction/probes.py
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass, replace
from datetime import date, time, timedelta
from pathlib import Path
from time import monotonic
from typing import Any
from unittest.mock import patch

from app.scheduler.composition import generate_schedule
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    PlanningSnapshot,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.oracle import optimal_candidate, oracle_objective
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.infrastructure import placement_model
from app.scheduler.infrastructure.annual_model import QuotaDistribution
from app.scheduler.infrastructure.placement_model import solve_placement
from app.scheduler.lab.annual import PROFILE_LOOSE, PROFILE_SHARED_TEACHER, build_annual_fixture
from app.scheduler.lab.scale import build_scale_fixture

ORIGIN = date(2026, 9, 21)
RESULTS: dict[str, Any] = {}


def serial(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: serial(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): serial(row) for key, row in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [serial(row) for row in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def period(day: int, start: int = 9, end: int = 10, start_min: int = 0, end_min: int = 0):
    return normalize_period(
        ORIGIN + timedelta(days=day),
        time(start, start_min),
        time(end, end_min),
        "Europe/Lisbon",
    )


def snapshot(periods, minutes=60, count=1, **kwargs):
    return PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=ORIGIN + timedelta(days=20),
        hard_end_date=ORIGIN + timedelta(days=30),
        timezone_name="Europe/Lisbon",
        grid_slots=tuple(
            dict.fromkeys(
                GridSlot(row.school_date.weekday(), row.start_local, row.end_local)
                for row in periods
            )
        ),
        assignments=tuple(
            Assignment(
                i,
                i,
                i,
                i,
                frozenset({i}),
                (ModuleRequirement(i, 1, minutes),),
            )
            for i in range(1, count + 1)
        ),
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=kwargs.pop("unavailable", ()),
        **kwargs,
    )


def record(name: str, expected: Any, observed: Any, verdict: str, detail: Any = None) -> None:
    RESULTS[name] = {
        "expected": serial(expected),
        "observed": serial(observed),
        "verdict": verdict,
        "detail": serial(detail) if detail is not None else None,
    }


def total_credit(result) -> int | None:
    return None if result.report is None else result.report.total_credit_minutes


def vector(target, candidate) -> Any:
    return None if candidate is None else oracle_objective(target, candidate)


def run_observation(name: str, target: PlanningSnapshot, periods) -> Any:
    result = generate_schedule(target, periods, time_limit_seconds=10, random_seed=1)
    best = optimal_candidate(target, periods)
    return result, (
        None if best is None else oracle_objective(target, best)
    )


def main() -> None:
    # F04 — waste must not replace an earlier completion.
    periods = (period(0, end=11), period(1, end=10, end_min=30))
    target = snapshot(periods, minutes=90)
    result, oracle = run_observation("annual_waste_delays_completion", target, periods)
    actual = vector(target, result.candidate)
    record(
        "annual_waste_delays_completion",
        {"outcome": "COMPLETE", "vector": (0,)},
        {
            "outcome": result.outcome,
            "vector": actual,
            "valid": result.report.valid if result.report else None,
            "bound": result.evidence.relaxation_bound if result.evidence else None,
        },
        "PASS" if result.outcome == "COMPLETE" and actual == oracle == (0,) else "FAIL",
    )

    # F01 — overlapping lessons of the same assignment.
    periods = (period(0), period(0, start_min=30, end_min=30), period(1))
    target = snapshot(periods, minutes=120)
    result, oracle = run_observation("same_assignment_overlap", target, periods)
    actual = vector(target, result.candidate)
    record(
        "same_assignment_overlap",
        {"outcome": "COMPLETE", "vector": (1,)},
        {"outcome": result.outcome, "vector": actual, "oracle": oracle},
        "PASS" if result.outcome == "COMPLETE" and actual == oracle == (1,) else "FAIL",
    )

    # F02 — input order must not change validity.
    base_periods = (period(0), period(1))
    target = snapshot(base_periods, minutes=90)
    ordered_vectors = []
    ordered_outcomes = []
    for ordered in (base_periods, tuple(reversed(base_periods))):
        result = generate_schedule(target, ordered, time_limit_seconds=10, random_seed=1)
        ordered_vectors.append(vector(target, result.candidate))
        ordered_outcomes.append(result.outcome)
    record(
        "period_order",
        {"outcomes": ["COMPLETE", "COMPLETE"], "vectors": [(1,), (1,)]},
        {"outcomes": ordered_outcomes, "vectors": ordered_vectors},
        "PASS"
        if ordered_outcomes == ["COMPLETE", "COMPLETE"]
        and ordered_vectors == [(1,), (1,)]
        else "FAIL",
    )

    # F05 — the whole completion vector.
    for count in (7, 9):
        periods = (period(0), period(1))
        unavailable = tuple(
            Unavailability(UnavailableResource.TEACHER, i, periods[0])
            for i in range(1, count)
        )
        soft = (Unavailability(UnavailableResource.TEACHER, count, periods[0]),)
        target = snapshot(
            periods, count=count, unavailable=unavailable, soft_unavailable=soft
        )
        result, oracle = run_observation(f"completion_tail_{count}", target, periods)
        actual = vector(target, result.candidate)
        expected = tuple([1] * (count - 1) + [0])
        record(
            f"completion_tail_{count}_classes",
            {"vector": expected},
            {"outcome": result.outcome, "vector": actual, "oracle": oracle},
            "PASS" if actual == oracle == expected else "FAIL",
        )

    # F08 — optimized preference cost equals the recalculated metric.
    periods = (period(0),)
    target = snapshot(
        periods,
        soft_unavailable=(
            Unavailability(UnavailableResource.TEACHER, 1, periods[0]),
            Unavailability(UnavailableResource.ROOM, 1, periods[0]),
        ),
    )
    result = generate_schedule(target, periods, time_limit_seconds=10, random_seed=1)
    stage_values = [
        stage.value
        for stage in (result.evidence.stages if result.evidence else ())
        if stage.stage == "PREFERENCE_COST_MINUTES"
    ]
    measured = result.quality.preference_cost_minutes if result.quality else None
    record(
        "preference_metric_disagreement",
        {"optimized": [60], "measured": 60},
        {"optimized": stage_values, "measured": measured},
        "PASS" if stage_values == [60] and measured == 60 else "FAIL",
    )

    # F03 — protected date and past period.
    periods = (period(0), period(1))
    for name, overrides in (
        ("protected_date", {"protected_dates": frozenset({ORIGIN})}),
        ("past_period", {"now_utc": periods[0].end_utc}),
    ):
        target = snapshot(periods, **overrides)
        result = generate_schedule(target, periods, time_limit_seconds=10, random_seed=1)
        days = sorted(
            lesson.period.school_date for lesson in (result.candidate.lessons if result.candidate else ())
        )
        record(
            name,
            {"outcome": "COMPLETE", "days": [ORIGIN + timedelta(days=1)]},
            {"outcome": result.outcome, "days": days},
            "PASS"
            if result.outcome == "COMPLETE" and days == [ORIGIN + timedelta(days=1)]
            else "FAIL",
        )

    # F09 — margin is not recoverability.
    periods = (period(0), period(7), period(14))
    target = snapshot(
        periods,
        unavailable=tuple(
            Unavailability(UnavailableResource.TEACHER, 1, row) for row in periods[1:]
        ),
    )
    result = generate_schedule(
        target, periods, time_limit_seconds=10, random_seed=1, assess_recovery=True
    )
    margin = result.completion.margin_days if result.completion else None
    recovery = result.completion.recovery.status if result.completion else None
    record(
        "margin_without_recovery_capacity",
        {"margin_days": 20, "recovery": "IMPOSSIBLE_PROVEN"},
        {"margin_days": margin, "recovery": recovery},
        "PASS" if margin == 20 and recovery == "IMPOSSIBLE_PROVEN" else "FAIL",
    )

    # F06 — an unproven stage must not certify a following proven stage.
    periods = (period(0), period(1))
    target = snapshot(
        periods,
        minutes=60,
        soft_unavailable=(Unavailability(UnavailableResource.TEACHER, 1, periods[0]),),
    )
    original = placement_model.cp_model.CpSolver.Solve
    calls = [0]

    def unproven_completion(self, model, *args, **kwargs):
        status = original(self, model, *args, **kwargs)
        calls[0] += 1
        return placement_model.cp_model.FEASIBLE if calls[0] == 2 else status

    with patch.object(placement_model.cp_model.CpSolver, "Solve", unproven_completion):
        outcome = solve_placement(target, periods, time_limit_seconds=10)
    stages = (
        [{"stage": row.stage, "proven": row.proven} for row in outcome.evidence.stages]
        if outcome.evidence
        else []
    )
    certified = outcome.evidence.certified_stages if outcome.evidence else None
    record(
        "controlled_unproven_prefix",
        {"certified_stages": 0, "first_stage_proven": False},
        {"certified_stages": certified, "stages": stages},
        "PASS"
        if certified == 0 and stages and stages[0]["proven"] is False
        else "FAIL",
    )

    # F10 — seed diversity changes the problem, not only the witness.
    first, second = build_scale_fixture(10, seed=1), build_scale_fixture(10, seed=2)
    record(
        "scale_seed_diversity",
        {"snapshots_equal": False},
        {
            "snapshots_equal": first.snapshot == second.snapshot,
            "assignments_equal": first.snapshot.assignments == second.snapshot.assignments,
        },
        "PASS" if first.snapshot != second.snapshot else "FAIL",
    )

    # F07 — the detail materializes the distribution exactly.
    periods = (
        period(0),
        period(0, start=10, end=11),
        period(0, start=11, end=12, end_min=30),
    )
    target = snapshot(periods, count=2)
    target = replace(
        target,
        assignments=(
            target.assignments[0],
            replace(
                target.assignments[1],
                teacher_id=1,
                modules=(ModuleRequirement(2, 1, 90),),
            ),
        ),
        unavailable=(
            Unavailability(UnavailableResource.CLASS, 1, periods[1]),
            Unavailability(UnavailableResource.CLASS, 1, periods[2]),
            Unavailability(UnavailableResource.CLASS, 2, periods[0]),
        ),
    )
    supplied = QuotaDistribution(
        counts={(1, 0, 60): 1, (2, 0, 90): 1},
        final_groups={1: (0, 60), 2: (0, 90)},
    )
    detail = solve_placement(
        target, periods, distribution=supplied, time_limit_seconds=10
    )
    materialized = {}
    for lesson in detail.candidate.lessons if detail.candidate else ():
        materialized.setdefault(lesson.assignment_id, []).append(
            {
                "duration": lesson.period.duration_minutes,
                "credit": lesson.credit_minutes,
            }
        )
    record(
        "detail_ignores_zero_quotas",
        {
            "status": "COMPLETE",
            "assignment_1": [{"duration": 60, "credit": 60}],
            "assignment_2": [{"duration": 90, "credit": 90}],
        },
        {"status": detail.status, "materialized": materialized},
        "PASS"
        if detail.status == "COMPLETE"
        and materialized
        == {
            1: [{"duration": 60, "credit": 60}],
            2: [{"duration": 90, "credit": 90}],
        }
        else "FAIL",
    )

    # Annual sample: 10-class loose and 60-class shared-teacher.
    for class_count, profile, label in (
        (10, PROFILE_LOOSE, "annual_10_loose"),
        (60, PROFILE_SHARED_TEACHER, "annual_60_shared_teacher"),
    ):
        fixture = build_annual_fixture(class_count, profile=profile, seed=1)
        started = monotonic()
        result = generate_schedule(
            fixture.snapshot, fixture.periods, time_limit_seconds=120, random_seed=1
        )
        elapsed = round(monotonic() - started, 1)
        report = result.report
        evidence = result.evidence
        record(
            label,
            {"outcome": "COMPLETE", "valid": True},
            {
                "outcome": result.outcome,
                "valid": report.valid if report else None,
                "lessons": len(result.candidate.lessons) if result.candidate else 0,
                "credit": total_credit(result),
                "quality": {
                    key: getattr(result.quality, key)
                    for key in (
                        "teacher_gap_minutes",
                        "class_gap_minutes",
                        "preference_cost_minutes",
                        "room_change_cost",
                    )
                }
                if result.quality
                else None,
                "certified_stages": evidence.certified_stages if evidence else None,
                "bound_week": evidence.relaxation_bound if evidence else None,
                "stop_reason": evidence.stop_reason if evidence else None,
                "seconds": elapsed,
            },
            "PASS"
            if result.outcome == "COMPLETE" and report is not None and report.valid
            else "FAIL",
        )

    output = Path(__file__).with_name("probes.json")
    failures = sorted(name for name, row in RESULTS.items() if row["verdict"] != "PASS")
    payload = {
        "date": "2026-09-25",
        "scenario_source": "../2026-09-24-w04-w05/probes.py",
        "failures": failures,
        "results": RESULTS,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(output), "failures": failures}, ensure_ascii=False))
    for name, row in RESULTS.items():
        print(f"{row['verdict']:4s} {name}")


if __name__ == "__main__":
    main()
