"""W11.3: a still-valid published baseline is the first recorded trajectory point."""

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.infrastructure.search import search_adaptive_schedule
from app.scheduler.lab.fixtures import build_fixture
from app.scheduler.lab.recovery import laboratory_policy
from tests.unit.test_scheduler_recovery_solver_v1 import _spec


def test_a_valid_published_baseline_opens_the_trajectory():
    fixture = build_fixture(
        "trajectory-baseline",
        _spec(strategy=SchedulingStrategy.ADAPTIVE_RECOVERY),
    )
    assert fixture.witness is not None
    points = []

    outcome = search_adaptive_schedule(
        fixture.snapshot,
        fixture.periods,
        fixture.witness,
        laboratory_policy(fixture.snapshot),
        time_limit_seconds=10,
        num_workers=1,
        random_seed=1,
        trajectory_out=points,
    )

    assert outcome.status in ("COMPLETE", "INFEASIBLE", "INCONCLUSIVE")
    assert points
    assert points[0].elapsed_seconds == 0.0
    assert points[0].complete is True
    elapsed = [point.elapsed_seconds for point in points]
    assert elapsed == sorted(elapsed)
