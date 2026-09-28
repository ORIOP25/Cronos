from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import CandidateSchedule, PlanningSnapshot
from app.scheduler.domain.recovery import RecoveryPolicy
from app.scheduler.domain.results import SearchOutcome
from app.scheduler.domain.stop import ExplorationPolicy


class ScheduleSearch(Protocol):
    """Concrete search operation injected by the composition root."""

    def __call__(
        self,
        snapshot: PlanningSnapshot,
        periods: tuple[Period, ...],
        *,
        time_limit_seconds: float,
        num_workers: int,
        random_seed: int,
        should_cancel: Callable[[], bool] | None = None,
        stop_at_first_complete: bool = False,
    ) -> SearchOutcome: ...


class AdaptiveSearch(Protocol):
    """Concrete AdaptiveRecovery search injected by the composition root."""

    def __call__(
        self,
        snapshot: PlanningSnapshot,
        periods: tuple[Period, ...],
        baseline: CandidateSchedule,
        policy: RecoveryPolicy,
        *,
        prior_changes: frozenset[int],
        time_limit_seconds: float,
        num_workers: int,
        random_seed: int,
        exploration: ExplorationPolicy | None,
        should_cancel: Callable[[], bool] | None,
    ) -> SearchOutcome: ...


class SchedulerTaskDispatcher(Protocol):
    def dispatch(self, *, organization_id: int, job_id: int, task_id: str) -> None: ...


NOT_ASSESSED = "NOT_ASSESSED"
DEMONSTRATED = "DEMONSTRATED"
IMPOSSIBLE_PROVEN = "IMPOSSIBLE_PROVEN"
INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class RecoveryAssessment:
    """Result of a defined perturbation scenario, not a general promise."""

    scenario: str
    status: str
    message: str = ""

    def __post_init__(self) -> None:
        if self.status not in (NOT_ASSESSED, DEMONSTRATED, IMPOSSIBLE_PROVEN, INCONCLUSIVE):
            raise ValueError("Unknown recovery assessment status.")
        if not self.scenario:
            raise ValueError("A recovery assessment needs its scenario.")


@dataclass(frozen=True)
class RepairSummary:
    """Recovery impact: excess over the preference and real physical changes."""

    completion_dates: Mapping[int, date]
    latest_completion_date: date
    preferred_end_date: date
    hard_end_date: date
    classes_after_preferred: tuple[int, ...]
    excess_days: int
    disruption_cost: int
    changed_lessons: int

    def __post_init__(self) -> None:
        if not self.completion_dates or type(self.latest_completion_date) is not date:
            raise ValueError("A repair summary needs dated completions.")
        if max(self.completion_dates.values()) != self.latest_completion_date:
            raise ValueError("The repair latest completion must be the maximum completion.")
        if not self.preferred_end_date <= self.hard_end_date:
            raise ValueError("The hard limit must not precede the preference.")
        after = tuple(
            sorted(
                class_id
                for class_id, day in self.completion_dates.items()
                if day > self.preferred_end_date
            )
        )
        if after != self.classes_after_preferred:
            raise ValueError("Classes after the preference must match the completion dates.")
        if any(
            type(value) is not int or value < 0
            for value in (self.excess_days, self.disruption_cost, self.changed_lessons)
        ):
            raise ValueError("Repair impact values must be nonnegative integers.")


@dataclass(frozen=True)
class CompletionReport:
    """Collective completion dates, margin and tested recoverability."""

    completion_dates: Mapping[int, date]
    latest_completion_date: date
    preferred_end_date: date
    margin_days: int
    classes_after_preferred: tuple[int, ...]
    recovery: RecoveryAssessment

    def __post_init__(self) -> None:
        if not self.completion_dates or type(self.latest_completion_date) is not date:
            raise ValueError("A completion report needs dated completions.")
        if (
            max(self.completion_dates.values()) != self.latest_completion_date
            or self.latest_completion_date > self.preferred_end_date
        ):
            raise ValueError("The latest completion must be the preferred-limited maximum.")
        if (self.preferred_end_date - self.latest_completion_date).days != self.margin_days:
            raise ValueError("The margin must be the distance to the preferred end date.")
        if self.classes_after_preferred:
            raise ValueError("An initial completion report cannot exceed the preference.")
