"""Composition root: wire the scheduler use cases to their concrete search."""

from __future__ import annotations

from collections.abc import Callable

from app.scheduler.application.generation import GenerationResult, generate_complete
from app.scheduler.application.recovery import RepairResult, repair_schedule
from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import CandidateSchedule, PlanningSnapshot
from app.scheduler.domain.recovery import RecoveryPolicy
from app.scheduler.domain.stop import ExplorationPolicy
from app.scheduler.infrastructure.search import (
    search_adaptive_schedule,
    search_complete_schedule,
)


def generate_schedule(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    *,
    assess_recovery: bool = False,
    should_cancel: Callable[[], bool] | None = None,
    recovery_time_limit_seconds: float | None = None,
    time_limit_seconds: float = 10.0,
    num_workers: int = 1,
    random_seed: int = 1,
) -> GenerationResult:
    return generate_complete(
        snapshot,
        periods,
        search=search_complete_schedule,
        assess_recovery=assess_recovery,
        should_cancel=should_cancel,
        recovery_time_limit_seconds=recovery_time_limit_seconds,
        time_limit_seconds=time_limit_seconds,
        num_workers=num_workers,
        random_seed=random_seed,
    )


def repair_published_schedule(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    baseline: CandidateSchedule,
    policy: RecoveryPolicy,
    *,
    prior_changes: frozenset[int] = frozenset(),
    exploration: ExplorationPolicy | None = None,
    should_cancel: Callable[[], bool] | None = None,
    trajectory_out: list | None = None,
    time_limit_seconds: float = 10.0,
    num_workers: int = 1,
    random_seed: int = 1,
) -> RepairResult:
    return repair_schedule(
        snapshot,
        periods,
        baseline,
        search=search_adaptive_schedule,
        policy=policy,
        prior_changes=prior_changes,
        exploration=exploration,
        should_cancel=should_cancel,
        trajectory_out=trajectory_out,
        time_limit_seconds=time_limit_seconds,
        num_workers=num_workers,
        random_seed=random_seed,
    )
