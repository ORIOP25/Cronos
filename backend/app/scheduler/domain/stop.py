"""Search budget honesty, adaptive stopping and offline trajectory replay.

The execution budget covers construction, search, finalization and persistence.
An execution that exceeds its budget is never reported as within it, and a stage
omitted because the budget ran out is never certified.

The exploration controller starts from deterministic rules over the complete
incumbent vector: a complete solution is required before stopping for sufficient
quality, a minimum exploration is spent after the first solution and over a
minimum number of explored proposals, and a stop by low expected return uses
gains observed in comparable calibration cases. No p95 participates.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

STOP_LOW_EXPECTED_RETURN = "LOW_EXPECTED_RETURN"
STOP_CANCELLED = "CANCELLED"
STOP_SAFETY_LIMIT = "SAFETY_LIMIT"


class BudgetPhase(StrEnum):
    CONSTRUCTION = "CONSTRUCTION"
    SEARCH = "SEARCH"
    FINALIZATION = "FINALIZATION"
    PERSISTENCE = "PERSISTENCE"


@dataclass
class ExecutionBudget:
    """Monotonic phase accounting against a finite safety limit."""

    limit_seconds: float
    elapsed_seconds: float = 0.0
    phase_seconds: dict[BudgetPhase, float] = field(default_factory=dict)
    omitted_stages: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if (
            type(self.limit_seconds) not in (int, float)
            or not math.isfinite(float(self.limit_seconds))
            or self.limit_seconds <= 0
        ):
            raise ValueError("The execution budget limit must be finite and positive.")

    def charge(self, phase: BudgetPhase, seconds: float) -> float:
        if type(phase) is not BudgetPhase:
            raise ValueError("A budget charge needs a known phase.")
        if type(seconds) not in (int, float) or not math.isfinite(float(seconds)) or seconds < 0:
            raise ValueError("A budget charge must be finite nonnegative seconds.")
        self.elapsed_seconds += float(seconds)
        self.phase_seconds[phase] = self.phase_seconds.get(phase, 0.0) + float(seconds)
        return self.remaining_seconds

    def omit(self, stage: str) -> None:
        if not stage:
            raise ValueError("An omitted stage needs a name.")
        self.omitted_stages.append(stage)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.limit_seconds - self.elapsed_seconds)

    @property
    def within_budget(self) -> bool:
        return self.elapsed_seconds <= self.limit_seconds

    def as_dict(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "limit_seconds": self.limit_seconds,
                "elapsed_seconds": round(self.elapsed_seconds, 6),
                "within_budget": self.within_budget,
                "phase_seconds": {
                    phase.value: round(value, 6)
                    for phase, value in sorted(self.phase_seconds.items())
                },
                "omitted_stages": tuple(self.omitted_stages),
            }
        )


@dataclass(frozen=True)
class ExplorationPolicy:
    """Explicit calibration parameters; no hidden production defaults."""

    version: str
    minimum_exploration_seconds: float
    gain_window_seconds: float
    minimum_significant_gain_days: int
    corpus_expected_gain_days: int
    minimum_solutions: int

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("An exploration policy needs a version.")
        if (
            type(self.minimum_exploration_seconds) not in (int, float)
            or self.minimum_exploration_seconds < 0
        ):
            raise ValueError("Minimum exploration seconds must be nonnegative.")
        if type(self.gain_window_seconds) not in (int, float) or self.gain_window_seconds < 0:
            raise ValueError("The gain window must be nonnegative seconds.")
        for name in (
            "minimum_significant_gain_days",
            "corpus_expected_gain_days",
            "minimum_solutions",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer.")
        if self.minimum_solutions < 1:
            raise ValueError("At least one explored solution is required.")


@dataclass(frozen=True)
class TrajectoryPoint:
    """One observed incumbent, flattened as its complete quality vector."""

    elapsed_seconds: float
    incumbent: tuple[int, ...]
    complete: bool

    def __post_init__(self) -> None:
        if type(self.elapsed_seconds) not in (int, float) or self.elapsed_seconds < 0:
            raise ValueError("Trajectory time must be nonnegative seconds.")
        if type(self.incumbent) is not tuple or any(
            type(value) is not int for value in self.incumbent
        ):
            raise ValueError("A trajectory incumbent must be a tuple of integers.")


@dataclass(frozen=True)
class StopDecision:
    stop: bool
    reason: str
    scope: str
    explanation: str

    def __post_init__(self) -> None:
        if not self.reason or not self.scope:
            raise ValueError("A stop decision needs a reason and a scope.")


def _last_improvement(complete: Sequence[TrajectoryPoint]) -> float:
    """Time of the last strict improvement; the first solution time otherwise."""
    best: tuple[int, ...] | None = None
    elapsed = complete[0].elapsed_seconds
    for point in complete:
        if best is None or point.incumbent < best:
            best = point.incumbent
            elapsed = point.elapsed_seconds
    return elapsed


def decide_stop(
    points: Sequence[TrajectoryPoint],
    policy: ExplorationPolicy,
    *,
    cancelled: bool = False,
    safety_limit_reached: bool = False,
) -> StopDecision:
    """Deterministic continue/stop decision over one observed trajectory."""
    if cancelled:
        return StopDecision(
            True, STOP_CANCELLED, "GLOBAL", "Administrative cancellation won the race."
        )
    if safety_limit_reached:
        return StopDecision(
            True,
            STOP_SAFETY_LIMIT,
            "GLOBAL",
            "The configured safety limit was reached; this is not a proof of impossibility.",
        )
    complete = [point for point in points if point.complete]
    if not complete:
        return StopDecision(
            False,
            "NO_COMPLETE_SOLUTION",
            "GLOBAL",
            "A complete solution is required before stopping for sufficient quality.",
        )
    if len(complete) < policy.minimum_solutions:
        return StopDecision(
            False,
            "REQUIRE_MORE_SOLUTIONS",
            "GLOBAL",
            "More distinct proposals must be explored before stopping for quality.",
        )
    last = complete[-1]
    first_solution = complete[0]
    if last.elapsed_seconds - first_solution.elapsed_seconds < policy.minimum_exploration_seconds:
        return StopDecision(
            False,
            "MINIMUM_EXPLORATION",
            "GLOBAL",
            "The minimum exploration after the first solution has not been spent yet.",
        )
    quiet_for = last.elapsed_seconds - _last_improvement(complete)
    if quiet_for < policy.gain_window_seconds:
        return StopDecision(
            False,
            "RECENT_IMPROVEMENT",
            "GLOBAL",
            "The complete incumbent vector improved inside the configuration window.",
        )
    if policy.corpus_expected_gain_days <= policy.minimum_significant_gain_days:
        return StopDecision(
            True,
            STOP_LOW_EXPECTED_RETURN,
            "GLOBAL",
            "Comparable calibration cases gained no significant days after this effort.",
        )
    return StopDecision(
        False,
        "CORPUS_EXPECTS_GAIN",
        "GLOBAL",
        "Comparable calibration cases still gained significant days after this effort.",
    )


@dataclass(frozen=True)
class TrajectoryReplay:
    """What an offline stopping policy would have saved and left on the table."""

    stopped_seconds: float
    final_vector: tuple[int, ...]
    best_vector: tuple[int, ...]
    lost_gain: bool
    saved_seconds: float
    reason: str


def replay_stop_policy(
    points: Iterable[TrajectoryPoint],
    policy: ExplorationPolicy,
    *,
    reference_horizon_seconds: float,
) -> TrajectoryReplay:
    """Apply a stopping policy to a recorded trajectory without running a solver."""
    ordered = tuple(points)
    if not ordered:
        raise ValueError("A trajectory replay needs at least one point.")
    if type(reference_horizon_seconds) not in (int, float) or reference_horizon_seconds <= 0:
        raise ValueError("A reference horizon must be positive seconds.")

    def outcome(stopped: TrajectoryPoint, reason: str) -> TrajectoryReplay:
        best = min(point.incumbent for point in ordered)
        return TrajectoryReplay(
            stopped_seconds=stopped.elapsed_seconds,
            final_vector=stopped.incumbent,
            best_vector=best,
            lost_gain=best < stopped.incumbent,
            saved_seconds=max(0.0, reference_horizon_seconds - stopped.elapsed_seconds),
            reason=reason,
        )

    for index in range(1, len(ordered) + 1):
        decision = decide_stop(ordered[:index], policy)
        if decision.stop:
            return outcome(ordered[index - 1], decision.reason)
    return outcome(ordered[-1], "TRAJECTORY_EXHAUSTED")
