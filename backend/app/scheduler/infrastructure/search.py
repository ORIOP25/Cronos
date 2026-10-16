"""Coordinated master/detail search for CompleteGeneration and AdaptiveRecovery.

The annual relaxation proposes quota distributions; the detailed placement
certifies one window at a time. A distribution proven infeasible is excluded
with a no-good cut, so later weeks are reopened instead of frozen. A timeout
never produces a cut.

The search keeps an annual incumbent measured by the domain quality vector and
continues while the relaxation can still propose something better: proposals are
bounded by the incumbent's latest completion week, with the same week allowed,
so a distribution that cannot beat the incumbent is never solved. A completed
candidate improves the incumbent only when its full vector is strictly better.

AdaptiveRecovery reuses the same machinery with the progressive recovery vector
and a published baseline: repaired positions may return to their published
period and room when that strictly improves the full vector, and an optional
exploration controller may finish the search early with an explicit reason.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from time import monotonic

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
    SchedulingStrategy,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import available_rooms, eligible_periods
from app.scheduler.domain.diagnostics import diagnose_joint_isolation
from app.scheduler.domain.quality import SearchEvidence, measure_initial_quality
from app.scheduler.domain.recovery import RecoveryPolicy, recovery_vector
from app.scheduler.domain.results import (
    OUTCOME_CANCELLED,
    OUTCOME_COMPLETE,
    OUTCOME_FAILED,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_INFEASIBLE,
    SearchOutcome,
)
from app.scheduler.domain.stop import (
    ExplorationPolicy,
    TrajectoryPoint,
    decide_stop,
)
from app.scheduler.infrastructure.annual_model import (
    STATUS_FEASIBLE as ANNUAL_FEASIBLE,
)
from app.scheduler.infrastructure.annual_model import (
    STATUS_INFEASIBLE as ANNUAL_INFEASIBLE,
)
from app.scheduler.infrastructure.annual_model import (
    QuotaDistribution,
    plan_annual_quotas,
    week_index,
)
from app.scheduler.infrastructure.constructive import construct_schedule
from app.scheduler.infrastructure.diagnostics import phase_finished, phase_started
from app.scheduler.infrastructure.placement_model import (
    STATUS_CANCELLED,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_INCONCLUSIVE,
    STATUS_INFEASIBLE,
    NoEligiblePeriodsError,
    _replace_lesson,
    solve_placement,
)
from app.scheduler.infrastructure.recovery_construction import construct_recovery

MAX_FEEDBACK_ROUNDS = 6
MIN_SEARCH_SECONDS = 0.05
MAX_STABILITY_MOVES = 50

# At most half of the remaining budget goes to the annual relaxation per
# feedback round; the detailed placement needs the rest to certify a candidate.
MASTER_BUDGET_SHARE = 0.5

# A search that exhausts the annual feedback rounds or stops on an inconclusive
# phase without an incumbent keeps its remaining budget to place the residual
# demand directly, without an annual quota distribution, over growing week
# horizons. The seasonal search is the first choice; this path only exists so a
# real school still receives a complete schedule when the relaxation cannot
# certify a distribution.
FALLBACK_HORIZON_FRACTIONS = (0.25, 0.5, 0.75, 1.0)

RELAXATION_SCOPE = "ANNUAL_LATEST_WEEK_LOWER_BOUND"


def feedback_cut(outcome_status: str) -> bool:
    """Only a proven detailed infeasibility excludes an annual distribution."""
    return outcome_status == STATUS_INFEASIBLE


def _merge_statistics(totals: dict[str, int], rows) -> None:
    """Accumulate phase statistics across feedback rounds.

    The search re-plans and re-solves several distributions; reporting only the
    last round understates the real construction and solve cost.
    """
    for key, value in (rows or {}).items():
        if type(value) is int:
            totals[key] = totals.get(key, 0) + value


def _latest_days(snapshot: PlanningSnapshot, candidate: CandidateSchedule) -> int:
    return max(
        ((lesson.period.school_date - snapshot.origin).days for lesson in candidate.lessons),
        default=0,
    )


def _latest_week(snapshot: PlanningSnapshot, candidate: CandidateSchedule) -> int:
    return _latest_days(snapshot, candidate) // 7


def _initial_vector(snapshot: PlanningSnapshot, candidate: CandidateSchedule):
    return measure_initial_quality(snapshot, candidate).vector(
        origin=snapshot.origin, preferred_end_date=snapshot.preferred_end_date
    )


def _flatten_vector(vector) -> tuple[int, ...]:
    """Complete quality vector as one integer tuple for the stop controller."""
    parts: list[int] = []
    for name in ("excess_days_desc", "progressive_cost_desc", "completion_days_desc"):
        rows = getattr(vector, name, None)
        if rows:
            parts.extend(rows)
    for name in (
        "disruption_cost",
        "teacher_gap_minutes",
        "class_gap_minutes",
        "preference_cost",
        "room_change_cost",
    ):
        value = getattr(vector, name, None)
        if value is not None:
            parts.append(value)
    return tuple(parts)


def _prune_week_limit(snapshot: PlanningSnapshot, profile: _SearchProfile, vector) -> int | None:
    """Latest week a candidate could still strictly improve the incumbent.

    A candidate that loses on the first vector component cannot win, so its
    maximum completion day is bounded by the preferred day plus the incumbent
    excess. The same week is allowed.
    """
    if vector is None:
        return None
    if profile.adaptive:
        excess = vector.excess_days_desc[0] if vector.excess_days_desc else 0
        day_limit = (snapshot.preferred_end_date - snapshot.origin).days + excess
    else:
        day_limit = vector.completion_days_desc[0] if vector.completion_days_desc else 0
    return day_limit // 7


def _baseline_incumbent(
    snapshot: PlanningSnapshot, profile: _SearchProfile
) -> tuple[SearchOutcome, object] | None:
    """A published baseline that still satisfies the validator is the incumbent."""
    if not profile.adaptive:
        return None
    assert profile.baseline is not None
    if not validate_candidate(snapshot, profile.baseline).valid:
        return None
    vector = profile.vector(snapshot, profile.baseline)
    outcome = SearchOutcome(
        OUTCOME_COMPLETE,
        profile.baseline,
        _latest_days(snapshot, profile.baseline),
        None,
        "The published baseline remains valid for the current state.",
        0.0,
        {},
        measure_initial_quality(snapshot, profile.baseline),
    )
    return outcome, vector


def _room_cost_for_profile(
    snapshot: PlanningSnapshot, profile: _SearchProfile
) -> Callable[[Assignment, Period, int], int] | None:
    """Published-room penalty used by both room matching paths."""
    if not profile.adaptive:
        return None
    published = {
        (lesson.assignment_id, lesson.period.start_utc, lesson.period.end_utc): lesson
        for lesson in profile.baseline.lessons
    }
    policy = profile.policy

    def room_cost(assignment: Assignment, period: Period, room_id: int) -> int:
        source = published.get((assignment.assignment_id, period.start_utc, period.end_utc))
        if source is None or room_id == source.room_id:
            return 0
        return policy.change_cost(
            policy.room_change_cost,
            snapshot,
            source,
            source.lesson_id in profile.prior_changes,
        )

    return room_cost


@dataclass(frozen=True)
class _SearchProfile:
    """Quality and stability rules; None means plain CompleteGeneration."""

    baseline: CandidateSchedule | None = None
    policy: RecoveryPolicy | None = None
    prior_changes: frozenset[int] = frozenset()
    cache_salt: str = ""

    @property
    def adaptive(self) -> bool:
        return self.policy is not None and self.baseline is not None

    def vector(self, snapshot: PlanningSnapshot, candidate: CandidateSchedule):
        if self.adaptive:
            return recovery_vector(
                snapshot,
                self.baseline,
                candidate,
                self.policy,
                prior_changes=self.prior_changes,
            )
        return _initial_vector(snapshot, candidate)

    def refine_quality(self, snapshot: PlanningSnapshot):
        if self.adaptive:
            return lambda row: self.vector(snapshot, row)
        return None


def _stabilize_recovery(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    profile: _SearchProfile,
    candidate: CandidateSchedule,
    *,
    deadline: float,
) -> CandidateSchedule:
    """Return movable lessons to their published position when the vector improves.

    Positions stay fixed during room matching; this pass only reopens a lesson
    to its own published period or room, and accepts the trial solely when the
    full recovery vector improves strictly.
    """
    assert profile.baseline is not None
    published = {lesson.lesson_id: lesson for lesson in profile.baseline.lessons}
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    eligible = {
        row.assignment_id: eligible_periods(snapshot, row, periods) for row in snapshot.assignments
    }
    protected_ids = {row.lesson_id for row in snapshot.protected_lessons}
    current = candidate
    current_vector = profile.vector(snapshot, current)
    moves = 0
    improved = True
    while improved and moves < MAX_STABILITY_MOVES and monotonic() < deadline:
        improved = False
        for lesson in sorted(
            current.lessons,
            key=lambda row: (row.assignment_id, row.period.start_utc, row.lesson_id),
        ):
            if lesson.lesson_id in protected_ids or monotonic() >= deadline:
                continue
            source = published.get(lesson.source_lesson_id) if lesson.source_lesson_id else None
            if source is None:
                continue
            assignment = assignments.get(lesson.assignment_id)
            if assignment is None:
                continue
            touches = (
                (source.period, source.room_id),
                (lesson.period, source.room_id),
            )
            for period, room_id in touches:
                if period == lesson.period and room_id == lesson.room_id:
                    continue
                if period not in eligible[assignment.assignment_id]:
                    continue
                if room_id not in available_rooms(snapshot, assignment, period):
                    continue
                trial = _replace_lesson(current, replace(lesson, period=period, room_id=room_id))
                if not validate_candidate(snapshot, trial).valid:
                    continue
                vector = profile.vector(snapshot, trial)
                if vector < current_vector:
                    current, current_vector = trial, vector
                    moves += 1
                    improved = True
                    break
            if improved:
                break
    improved = True
    while improved and moves < MAX_STABILITY_MOVES and monotonic() < deadline:
        improved = False
        for lesson in sorted(
            current.lessons,
            key=lambda row: (row.assignment_id, row.period.start_utc, row.lesson_id),
        ):
            if lesson.lesson_id in protected_ids or monotonic() >= deadline:
                continue
            source = published.get(lesson.source_lesson_id) if lesson.source_lesson_id else None
            if source is None:
                continue
            if lesson.period == source.period and lesson.room_id == source.room_id:
                continue
            assignment = assignments.get(lesson.assignment_id)
            if assignment is None or source.period not in eligible[assignment.assignment_id]:
                continue
            if source.room_id not in available_rooms(snapshot, assignment, source.period):
                continue
            direct = _replace_lesson(
                current, replace(lesson, period=source.period, room_id=source.room_id)
            )
            if validate_candidate(snapshot, direct).valid:
                vector = profile.vector(snapshot, direct)
                if vector < current_vector:
                    current, current_vector = direct, vector
                    moves += 1
                    improved = True
                    break
                continue
            blocker = next(
                (
                    row
                    for row in current.lessons
                    if row.lesson_id != lesson.lesson_id
                    and row.period == source.period
                    and row.room_id == source.room_id
                ),
                None,
            )
            if blocker is None or blocker.lesson_id in protected_ids:
                continue
            blocker_assignment = assignments.get(blocker.assignment_id)
            if blocker_assignment is None:
                continue
            for alternative in eligible[blocker_assignment.assignment_id][:MAX_STABILITY_MOVES]:
                if alternative == blocker.period or monotonic() >= deadline:
                    continue
                for room_id in available_rooms(snapshot, blocker_assignment, alternative):
                    relocated = replace(blocker, period=alternative, room_id=room_id)
                    trial = _replace_lesson(
                        _replace_lesson(current, relocated),
                        replace(lesson, period=source.period, room_id=source.room_id),
                    )
                    if not validate_candidate(snapshot, trial).valid:
                        continue
                    vector = profile.vector(snapshot, trial)
                    if vector < current_vector:
                        current, current_vector = trial, vector
                        moves += 2
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
    return current


def _cancelled(start: float, message: str) -> SearchOutcome:
    return SearchOutcome(
        OUTCOME_CANCELLED,
        None,
        None,
        None,
        message,
        monotonic() - start,
        {},
    )


def _joint_search(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    *,
    profile: _SearchProfile,
    time_limit_seconds: float,
    num_workers: int,
    random_seed: int,
    max_feedback_rounds: int,
    exploration: ExplorationPolicy | None = None,
    should_cancel: Callable[[], bool] | None = None,
    trajectory_out: list[TrajectoryPoint] | None = None,
    stop_at_first_complete: bool = False,
) -> SearchOutcome:
    start = monotonic()
    hard_deadline = start + time_limit_seconds
    deadline = hard_deadline
    excluded: list[QuotaDistribution] = []
    window_cache: dict = {}
    incumbent: SearchOutcome | None = None
    best_vector = None
    best_bound: int | None = None
    best_bound_proven = False
    rounds = 0
    exhausted = False
    interrupted = False
    controller_reason: str | None = None
    trajectory: list[TrajectoryPoint] = []
    room_cost = _room_cost_for_profile(snapshot, profile)
    published = _baseline_incumbent(snapshot, profile)
    if published is not None:
        incumbent, best_vector = published
        start_point = TrajectoryPoint(0.0, _flatten_vector(best_vector), complete=True)
        trajectory.append(start_point)
        if trajectory_out is not None:
            trajectory_out.append(start_point)
    # Build the guaranteed candidate before the expensive search so its cost is
    # inside the budget: a failed search can always return it within the limit.
    constructive_start = monotonic()
    phase_started("CONSTRUCTIVE")
    constructed = (
        construct_schedule(snapshot, periods, deadline=hard_deadline, should_cancel=should_cancel)
        if incumbent is None
        else None
    )
    phase_finished(
        "CONSTRUCTIVE",
        started_at=constructive_start,
        status="BUILT" if constructed is not None else "NONE",
    )
    phase_totals: dict[str, int] = {}

    def constructive_outcome() -> SearchOutcome:
        assert constructed is not None
        return _constructive_outcome(
            snapshot,
            profile,
            constructed,
            start=start,
            exploration=exploration,
            trajectory_out=trajectory_out,
            phase_totals=phase_totals,
            excluded=excluded,
            rounds=rounds,
            best_bound=best_bound,
            best_bound_proven=best_bound_proven,
        )

    if constructed is not None and stop_at_first_complete:
        return constructive_outcome()
    while rounds < max_feedback_rounds:
        if should_cancel is not None and should_cancel():
            return _cancelled(start, "The request was cancelled during the search.")
        remaining = deadline - monotonic()
        if remaining <= MIN_SEARCH_SECONDS:
            interrupted = True
            break
        limit = _prune_week_limit(snapshot, profile, best_vector)
        # Reserve the other half of the budget for the detailed placement: a
        # master that consumes the whole window starves the detail and returns
        # no candidate even when one exists.
        plan = plan_annual_quotas(
            snapshot,
            periods,
            excluded=tuple(excluded),
            latest_week_limit=limit,
            time_limit_seconds=max(MIN_SEARCH_SECONDS, remaining * MASTER_BUDGET_SHARE),
            num_workers=num_workers,
            random_seed=random_seed,
            stop_at_first_complete=stop_at_first_complete,
            should_cancel=should_cancel,
        )
        _merge_statistics(phase_totals, plan.statistics)
        if plan.status == OUTCOME_CANCELLED or (should_cancel is not None and should_cancel()):
            return _cancelled(start, "The request was cancelled during annual planning.")
        if plan.status == ANNUAL_INFEASIBLE:
            exhausted = True
            break
        if plan.status != ANNUAL_FEASIBLE or plan.distribution is None:
            interrupted = True
            break
        if plan.latest_week_bound is not None and (
            best_bound is None or plan.latest_week_bound < best_bound
        ):
            best_bound = plan.latest_week_bound
            best_bound_proven = plan.latest_week_proven
        remaining = deadline - monotonic()
        if remaining <= MIN_SEARCH_SECONDS:
            interrupted = True
            break
        placement = solve_placement(
            snapshot,
            periods,
            distribution=plan.distribution,
            time_limit_seconds=remaining,
            num_workers=num_workers,
            random_seed=random_seed,
            reuse=window_cache,
            cache_salt=profile.cache_salt,
            should_cancel=should_cancel,
            quality_of=profile.refine_quality(snapshot),
            room_cost=room_cost,
            stop_at_first_complete=stop_at_first_complete,
        )
        _merge_statistics(phase_totals, placement.statistics)
        rounds += 1
        if placement.status == STATUS_CANCELLED:
            return _cancelled(start, placement.message)
        if placement.status == STATUS_COMPLETE and placement.candidate is not None:
            candidate = placement.candidate
            if profile.adaptive:
                candidate = _stabilize_recovery(
                    snapshot, periods, profile, candidate, deadline=deadline
                )
            vector = profile.vector(snapshot, candidate)
            if stop_at_first_complete:
                return SearchOutcome(
                    OUTCOME_COMPLETE,
                    candidate,
                    placement.objective_days,
                    placement.evidence,
                    "The first complete placement was returned without further search.",
                    monotonic() - start,
                    dict(phase_totals),
                    measure_initial_quality(snapshot, candidate),
                )
            if best_vector is None or vector < best_vector:
                best_vector = vector
                incumbent = SearchOutcome(
                    OUTCOME_COMPLETE,
                    candidate,
                    placement.objective_days,
                    placement.evidence,
                    "",
                    monotonic() - start,
                    dict(phase_totals),
                    measure_initial_quality(snapshot, candidate),
                )
                if exploration is not None or trajectory_out is not None:
                    trajectory.append(
                        TrajectoryPoint(
                            monotonic() - start,
                            _flatten_vector(vector),
                            complete=True,
                        )
                    )
                    if trajectory_out is not None:
                        trajectory_out.append(trajectory[-1])
                    if exploration is not None:
                        decision = decide_stop(trajectory, exploration)
                        if decision.stop:
                            controller_reason = decision.reason
                            break
            excluded.append(plan.distribution)
            continue
        if feedback_cut(placement.status):
            excluded.append(plan.distribution)
            continue
        if placement.status == STATUS_FAILED:
            return SearchOutcome(
                OUTCOME_FAILED,
                None,
                None,
                placement.evidence,
                placement.message,
                monotonic() - start,
                dict(phase_totals),
            )
        interrupted = True
        break
    if incumbent is None and constructed is not None:
        return constructive_outcome()
    # The search only replaces the guaranteed candidate when it is strictly
    # better by the full quality vector. Without this the first detailed
    # candidate would win over a better constructor when the search is cut short.
    if (
        incumbent is not None
        and constructed is not None
        and profile.vector(snapshot, constructed) < best_vector
    ):
        return constructive_outcome()
    if incumbent is None and monotonic() < hard_deadline - MIN_SEARCH_SECONDS:
        fallback = _unrestricted_fallback(
            snapshot,
            periods,
            profile,
            start=start,
            deadline=hard_deadline,
            num_workers=num_workers,
            random_seed=random_seed,
            room_cost=room_cost,
            should_cancel=should_cancel,
            exploration=exploration,
            trajectory_out=trajectory_out,
            phase_totals=phase_totals,
            excluded=excluded,
            rounds=rounds,
            stop_at_first_complete=stop_at_first_complete,
        )
        if fallback is not None:
            return fallback
    if incumbent is None:
        if exhausted:
            # A single joint unit left without any eligible period is a proven
            # isolation, not a generic relaxation failure (WBS 3.9).
            isolation = diagnose_joint_isolation(snapshot, periods)
            return SearchOutcome(
                OUTCOME_INFEASIBLE,
                None,
                None,
                SearchEvidence(
                    objective_scope="ANNUAL_QUOTA_RELAXATION",
                    stages=(),
                    certified_stages=0,
                    stop_reason="INFEASIBLE",
                    rounds=max(rounds, 1),
                    proposals_excluded=len(excluded),
                    relaxation_scope=RELAXATION_SCOPE,
                    relaxation_proven=True,
                ),
                isolation.message
                if isolation is not None
                else "The annual quota relaxation is infeasible.",
                monotonic() - start,
                dict(phase_totals),
            )
        return SearchOutcome(
            OUTCOME_INCONCLUSIVE,
            None,
            None,
            SearchEvidence(
                objective_scope="ANNUAL_QUOTA_SEARCH",
                stages=(),
                certified_stages=0,
                stop_reason="SEARCH_STOPPED",
                rounds=max(rounds, 1),
                proposals_excluded=len(excluded),
                relaxation_bound=best_bound,
                relaxation_incumbent=None,
                relaxation_proven=best_bound_proven,
                relaxation_scope=RELAXATION_SCOPE,
            ),
            "The search stopped before a complete candidate or a proof.",
            monotonic() - start,
            dict(phase_totals),
        )
    if controller_reason is not None:
        stop_reason = controller_reason
    elif exhausted:
        stop_reason = "PROPOSALS_EXHAUSTED"
    elif interrupted:
        stop_reason = "SAFETY_LIMIT"
    else:
        stop_reason = "ROUND_LIMIT"
    evidence = incumbent.evidence
    if evidence is not None:
        evidence = replace(
            evidence,
            rounds=max(rounds, 1),
            proposals_excluded=len(excluded),
            relaxation_bound=best_bound,
            relaxation_incumbent=(
                _latest_week(snapshot, incumbent.candidate) if incumbent.candidate else None
            ),
            relaxation_proven=best_bound_proven,
            relaxation_scope=RELAXATION_SCOPE,
            stop_reason=stop_reason,
        )
    if stop_reason == "SAFETY_LIMIT":
        message = (
            "The safety limit interrupted the search. The best complete candidate found "
            "is returned without a full quality certificate."
        )
    else:
        message = (
            "The search returned the best complete candidate found for the explored "
            "annual distributions."
        )
    return replace(
        incumbent,
        message=message,
        wall_time_seconds=monotonic() - start,
        evidence=evidence,
    )


def _constructive_outcome(
    snapshot: PlanningSnapshot,
    profile: _SearchProfile,
    candidate: CandidateSchedule,
    *,
    start: float,
    exploration: ExplorationPolicy | None,
    trajectory_out: list[TrajectoryPoint] | None,
    phase_totals: dict[str, int],
    excluded: list[QuotaDistribution],
    rounds: int,
    best_bound: int | None,
    best_bound_proven: bool,
) -> SearchOutcome:
    """Wrap an already validated constructive candidate as a search outcome.

    A fast greedy construction is validated independently before it is accepted,
    so a real school still receives a complete schedule when the master/detail
    search cannot settle one within the budget. It never claims a quality
    certificate.
    """
    evidence = SearchEvidence(
        objective_scope="CONSTRUCTIVE_RECOVERY" if profile.adaptive else "CONSTRUCTIVE_INITIAL",
        stages=(),
        certified_stages=0,
        stop_reason="CONSTRUCTIVE_RECOVERY" if profile.adaptive else "CONSTRUCTIVE",
        rounds=max(rounds, 1),
        proposals_excluded=len(excluded),
        relaxation_bound=best_bound,
        relaxation_incumbent=_latest_week(snapshot, candidate),
        relaxation_proven=best_bound_proven,
        relaxation_scope=RELAXATION_SCOPE,
    )
    if trajectory_out is not None or exploration is not None:
        point = TrajectoryPoint(
            monotonic() - start,
            _flatten_vector(profile.vector(snapshot, candidate)),
            complete=True,
        )
        if trajectory_out is not None:
            trajectory_out.append(point)
        if exploration is not None:
            decide_stop([point], exploration)
    return SearchOutcome(
        OUTCOME_COMPLETE,
        candidate,
        _latest_days(snapshot, candidate),
        evidence,
        "The constructive route found a complete candidate without a quota certificate.",
        monotonic() - start,
        dict(phase_totals),
        measure_initial_quality(snapshot, candidate),
    )


def _unrestricted_fallback(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    profile: _SearchProfile,
    *,
    start: float,
    deadline: float,
    num_workers: int,
    random_seed: int,
    room_cost: Callable[[Assignment, Period, int], int] | None,
    should_cancel: Callable[[], bool] | None,
    exploration: ExplorationPolicy | None,
    trajectory_out: list[TrajectoryPoint] | None,
    phase_totals: dict[str, int],
    excluded: list[QuotaDistribution],
    rounds: int,
    stop_at_first_complete: bool = False,
) -> SearchOutcome | None:
    """Place the residual demand without an annual quota distribution.

    The seasonal search can exhaust its feedback rounds or stop on an
    inconclusive window without an incumbent. This path solves the detail model
    directly over progressively larger week horizons, returning the first
    complete candidate. It never claims a quality certificate.
    """
    weeks = sorted({week_index(snapshot.origin, period) for period in periods})
    if not weeks:
        return None
    horizons = sorted(
        {
            weeks[min(len(weeks) - 1, max(0, math.ceil(fraction * len(weeks)) - 1))]
            for fraction in FALLBACK_HORIZON_FRACTIONS
        }
    )
    for index, horizon_week in enumerate(horizons):
        if should_cancel is not None and should_cancel():
            return _cancelled(start, "The request was cancelled during the fallback search.")
        remaining = deadline - monotonic()
        if remaining <= MIN_SEARCH_SECONDS:
            break
        horizon_periods = tuple(
            period for period in periods if week_index(snapshot.origin, period) <= horizon_week
        )
        if not horizon_periods:
            continue
        budget = remaining / (len(horizons) - index)
        try:
            placement = solve_placement(
                snapshot,
                horizon_periods,
                distribution=None,
                time_limit_seconds=budget,
                num_workers=num_workers,
                random_seed=random_seed,
                should_cancel=should_cancel,
                quality_of=profile.refine_quality(snapshot),
                room_cost=room_cost,
                stop_at_first_complete=stop_at_first_complete,
            )
        except NoEligiblePeriodsError:
            continue
        _merge_statistics(phase_totals, placement.statistics)
        if placement.status == STATUS_CANCELLED:
            return _cancelled(start, placement.message)
        if placement.status == STATUS_COMPLETE and placement.candidate is not None:
            candidate = placement.candidate
            if profile.adaptive:
                candidate = _stabilize_recovery(
                    snapshot, periods, profile, candidate, deadline=deadline
                )
            evidence = placement.evidence
            if evidence is not None:
                evidence = replace(
                    evidence,
                    stop_reason="FALLBACK_UNRESTRICTED",
                    rounds=max(rounds, 1),
                    proposals_excluded=len(excluded),
                    relaxation_scope=RELAXATION_SCOPE,
                    relaxation_proven=False,
                )
            if trajectory_out is not None or exploration is not None:
                point = TrajectoryPoint(
                    monotonic() - start,
                    _flatten_vector(profile.vector(snapshot, candidate)),
                    complete=True,
                )
                if trajectory_out is not None:
                    trajectory_out.append(point)
                if exploration is not None:
                    decide_stop([point], exploration)
            return SearchOutcome(
                OUTCOME_COMPLETE,
                candidate,
                placement.objective_days,
                evidence,
                "The fallback placement returned a complete candidate without a quota certificate.",
                monotonic() - start,
                dict(phase_totals),
                measure_initial_quality(snapshot, candidate),
            )
        if placement.status == STATUS_INCONCLUSIVE:
            continue
        if placement.status == STATUS_FAILED:
            break
    return None


def _profile_cache_salt(profile: _SearchProfile, snapshot: PlanningSnapshot) -> str:
    if not profile.adaptive:
        return ""
    parts = [
        f"p={profile.policy.version}",
        *(
            f"{lesson.lesson_id}:{lesson.period.start_utc.isoformat()}:{lesson.room_id}"
            for lesson in sorted(profile.baseline.lessons, key=lambda row: row.lesson_id)
        ),
        *(
            f"protected:{lesson.lesson_id}:{lesson.period.start_utc.isoformat()}"
            for lesson in sorted(snapshot.protected_lessons, key=lambda row: row.lesson_id)
        ),
    ]
    return "|".join(parts)


def search_complete_schedule(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    *,
    time_limit_seconds: float = 10.0,
    num_workers: int = 1,
    random_seed: int = 1,
    max_feedback_rounds: int = MAX_FEEDBACK_ROUNDS,
    should_cancel: Callable[[], bool] | None = None,
    stop_at_first_complete: bool = False,
) -> SearchOutcome:
    if type(snapshot) is not PlanningSnapshot:
        raise ValueError("The search needs a planning snapshot.")
    if time_limit_seconds <= 0:
        raise ValueError("The time limit must be positive.")
    if max_feedback_rounds < 1:
        raise ValueError("At least one feedback round is required.")
    return _joint_search(
        snapshot,
        periods,
        profile=_SearchProfile(),
        time_limit_seconds=time_limit_seconds,
        num_workers=num_workers,
        random_seed=random_seed,
        max_feedback_rounds=max_feedback_rounds,
        should_cancel=should_cancel,
        stop_at_first_complete=stop_at_first_complete,
    )


def search_adaptive_schedule(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    baseline: CandidateSchedule,
    policy: RecoveryPolicy,
    *,
    prior_changes: frozenset[int] = frozenset(),
    time_limit_seconds: float = 10.0,
    num_workers: int = 1,
    random_seed: int = 1,
    max_feedback_rounds: int = MAX_FEEDBACK_ROUNDS,
    exploration: ExplorationPolicy | None = None,
    should_cancel: Callable[[], bool] | None = None,
    trajectory_out: list[TrajectoryPoint] | None = None,
    stop_at_first_complete: bool = False,
) -> SearchOutcome:
    if type(snapshot) is not PlanningSnapshot:
        raise ValueError("The search needs a planning snapshot.")
    if snapshot.strategy is not SchedulingStrategy.ADAPTIVE_RECOVERY:
        raise ValueError("Adaptive search needs an ADAPTIVE_RECOVERY snapshot.")
    if type(baseline) is not CandidateSchedule or type(policy) is not RecoveryPolicy:
        raise ValueError("Adaptive search needs a published baseline and a recovery policy.")
    if time_limit_seconds <= 0:
        raise ValueError("The time limit must be positive.")
    profile: _SearchProfile = _SearchProfile(baseline, policy, prior_changes)
    profile = replace(profile, cache_salt=_profile_cache_salt(profile, snapshot))
    if stop_at_first_complete:
        start = monotonic()
        deadline = start + time_limit_seconds
        planning = replace(snapshot, baseline_lessons=baseline.lessons)
        if should_cancel is not None and should_cancel():
            return _cancelled(start, "The request was cancelled before repair.")
        phase_start = monotonic()
        phase_started("RECOVERY_RETAIN")
        local = construct_recovery(
            planning, periods, deadline=deadline, should_cancel=should_cancel
        )
        phase_finished(
            "RECOVERY_RETAIN",
            started_at=phase_start,
            status="BUILT" if local is not None else "NONE",
        )
        # Compare validated constructions first; only use placement when both
        # fail, so a greedy dead end does not discard the remaining budget.
        phase_start = monotonic()
        phase_started("RECOVERY_REBUILD")
        rebuilt = construct_schedule(
            planning,
            periods,
            deadline=deadline,
            should_cancel=should_cancel,
            weekly_reference=baseline,
        )
        phase_finished(
            "RECOVERY_REBUILD",
            started_at=phase_start,
            status="BUILT" if rebuilt is not None else "NONE",
        )
        if should_cancel is not None and should_cancel():
            return _cancelled(start, "The request was cancelled during repair.")
        candidates = [row for row in (local, rebuilt) if row is not None]
        if not candidates:
            return _unrestricted_fallback(
                planning,
                periods,
                profile,
                start=start,
                deadline=deadline,
                num_workers=num_workers,
                random_seed=random_seed,
                room_cost=_room_cost_for_profile(planning, profile),
                should_cancel=should_cancel,
                exploration=exploration,
                trajectory_out=trajectory_out,
                phase_totals={},
                excluded=[],
                rounds=0,
                stop_at_first_complete=True,
            ) or SearchOutcome(
                OUTCOME_INCONCLUSIVE,
                None,
                None,
                None,
                "No complete repair was found within the budget.",
                monotonic() - start,
                {},
                None,
            )
        candidate = min(candidates, key=lambda row: profile.vector(planning, row))
        return _constructive_outcome(
            planning,
            profile,
            candidate,
            start=start,
            exploration=exploration,
            trajectory_out=trajectory_out,
            phase_totals={},
            excluded=[],
            rounds=0,
            best_bound=None,
            best_bound_proven=False,
        )
    return _joint_search(
        snapshot,
        periods,
        profile=profile,
        time_limit_seconds=time_limit_seconds,
        num_workers=num_workers,
        random_seed=random_seed,
        max_feedback_rounds=max_feedback_rounds,
        exploration=exploration,
        should_cancel=should_cancel,
        trajectory_out=trajectory_out,
    )
