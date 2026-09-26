"""Deterministic full-vector oracle comparison; run from backend in local Docker."""

import json
from dataclasses import asdict, replace
from random import Random

from app.scheduler.composition import generate_schedule
from app.scheduler.domain.candidate import Unavailability, UnavailableResource
from app.scheduler.domain.oracle import enumerate_candidates
from app.scheduler.domain.quality import measure_initial_quality
from app.scheduler.infrastructure.placement_model import solve_placement
from app.scheduler.lab.manifest import snapshot_to_dict, period_to_dict
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period, snapshot


def vector(target, candidate):
    return measure_initial_quality(target, candidate).vector(
        origin=target.origin, preferred_end_date=target.preferred_end_date
    )


def run():
    rows = []
    for seed in range(40):
        rng = Random(seed)
        periods = (period(0), period(0, start_min=30, end_min=30), period(1), period(7))
        target = snapshot(periods, minutes=rng.choice((30, 60, 90, 120)), count=2)
        assignments = tuple(
            replace(a, teacher_id=rng.choice((1, 2)), eligible_room_ids=frozenset({1, 2}))
            for a in target.assignments
        )
        hard, soft = [], []
        for kind in UnavailableResource:
            for identity in (1, 2):
                for when in periods:
                    chance = rng.random()
                    row = Unavailability(kind, identity, when)
                    if chance < 0.10:
                        hard.append(row)
                    elif chance < 0.25:
                        soft.append(row)
        target = replace(target, assignments=assignments, unavailable=tuple(hard), soft_unavailable=tuple(soft))
        oracle = enumerate_candidates(target, periods)
        best = min((vector(target, candidate) for candidate in oracle.candidates), default=None)
        result = generate_schedule(target, periods, time_limit_seconds=5)
        actual = vector(target, result.candidate) if result.candidate else None
        record = {"seed": seed, "outcome": result.outcome, "oracle_feasible": best is not None,
                  "oracle": None if best is None else asdict(best),
                  "actual": None if actual is None else asdict(actual), "equal": actual == best}
        if actual != best:
            detail = solve_placement(target, periods, time_limit_seconds=5)
            record.update(snapshot=snapshot_to_dict(target), periods=[period_to_dict(p) for p in periods],
                          detail_vector=asdict(vector(target, detail.candidate)) if detail.candidate else None,
                          detail_evidence=asdict(detail.evidence) if detail.evidence else None)
        rows.append(record)
    print(json.dumps({"cases": len(rows), "mismatches": sum(not row["equal"] for row in rows), "results": rows}, indent=2))


if __name__ == "__main__":
    run()
