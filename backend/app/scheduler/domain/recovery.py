"""AdaptiveRecovery domain: baseline assessment, disruption and recovery quality.

The published baseline is a reference, never an obligation. A stale baseline
(teacher reassigned, room withdrawn, period blocked) is described by explicit
issues instead of being accepted because it was once approved. Disruption is
measured by real physical transformations between the baseline and a candidate:
identity swaps do not hide movements, and a modular projection update alone is
not a physical change.

The recovery quality vector is the approved progressive policy: excess over the
preferred end date first, then a margin function plus disruption, then the
completion vector, disruption, gaps and secondary preferences. Coefficients are
explicit experimental parameters supplied by the caller; this module invents no
production defaults.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from zoneinfo import ZoneInfo

from app.scheduler.domain.candidate import (
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
)
from app.scheduler.domain.candidate_validation import (
    ValidationViolationCode,
    validate_candidate,
)
from app.scheduler.domain.capacity import residual_minutes
from app.scheduler.domain.debt import (
    DebtBalance,
    DebtClaim,
    DebtRevision,
    DebtSettlement,
    RecoveryAllocation,
    reconcile_debt,
)
from app.scheduler.domain.quality import (
    AdaptiveQualityPolicy,
    AdaptiveQualityVector,
    InitialQualityMetrics,
    adaptive_quality_vector,
    measure_initial_quality,
)


class BaselineIssueKind(StrEnum):
    MISSING_COVERAGE = "MISSING_COVERAGE"
    EXCESS_CREDIT = "EXCESS_CREDIT"
    UNKNOWN_ASSIGNMENT = "UNKNOWN_ASSIGNMENT"
    RESOURCE_MISMATCH = "RESOURCE_MISMATCH"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    DUPLICATE_IDENTITY = "DUPLICATE_IDENTITY"
    INELIGIBLE_ROOM = "INELIGIBLE_ROOM"
    OUT_OF_CALENDAR = "OUT_OF_CALENDAR"
    NOT_IN_GRID = "NOT_IN_GRID"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"
    PROTECTED_WINDOW = "PROTECTED_WINDOW"
    PROTECTED_LESSON_CHANGED = "PROTECTED_LESSON_CHANGED"
    COVERAGE_MISMATCH = "COVERAGE_MISMATCH"
    CURRICULUM_MISMATCH = "CURRICULUM_MISMATCH"
    RESERVATION_INVALID = "RESERVATION_INVALID"
    DEBT_OVERFLOW = "DEBT_OVERFLOW"
    INVALID = "INVALID"


_ISSUE_BY_VIOLATION = {
    ValidationViolationCode.UNKNOWN_ASSIGNMENT: BaselineIssueKind.UNKNOWN_ASSIGNMENT,
    ValidationViolationCode.ASSIGNMENT_RESOURCE_MISMATCH: BaselineIssueKind.RESOURCE_MISMATCH,
    ValidationViolationCode.RESOURCE_CONFLICT: BaselineIssueKind.RESOURCE_CONFLICT,
    ValidationViolationCode.DUPLICATE_IDENTITY: BaselineIssueKind.DUPLICATE_IDENTITY,
    ValidationViolationCode.INELIGIBLE_ROOM: BaselineIssueKind.INELIGIBLE_ROOM,
    ValidationViolationCode.OUT_OF_CALENDAR: BaselineIssueKind.OUT_OF_CALENDAR,
    ValidationViolationCode.NOT_IN_GRID: BaselineIssueKind.NOT_IN_GRID,
    ValidationViolationCode.RESOURCE_UNAVAILABLE: BaselineIssueKind.RESOURCE_UNAVAILABLE,
    ValidationViolationCode.EDITABLE_WINDOW_VIOLATION: BaselineIssueKind.PROTECTED_WINDOW,
    ValidationViolationCode.PROTECTED_LESSON_CHANGED: BaselineIssueKind.PROTECTED_LESSON_CHANGED,
    ValidationViolationCode.COVERAGE_MISMATCH: BaselineIssueKind.COVERAGE_MISMATCH,
    ValidationViolationCode.MODULE_MISMATCH: BaselineIssueKind.CURRICULUM_MISMATCH,
    ValidationViolationCode.PARTIAL_CREDIT_VIOLATION: BaselineIssueKind.CURRICULUM_MISMATCH,
    ValidationViolationCode.SLICE_MISMATCH: BaselineIssueKind.CURRICULUM_MISMATCH,
    ValidationViolationCode.RESERVATION_UNKNOWN_LESSON: BaselineIssueKind.RESERVATION_INVALID,
    ValidationViolationCode.RESERVATION_OVERFLOW: BaselineIssueKind.RESERVATION_INVALID,
    ValidationViolationCode.RESERVATION_VERSION_MISMATCH: BaselineIssueKind.RESERVATION_INVALID,
    ValidationViolationCode.RESERVATION_ASSIGNMENT_MISMATCH: BaselineIssueKind.RESERVATION_INVALID,
    ValidationViolationCode.RESERVATION_DUPLICATE: BaselineIssueKind.RESERVATION_INVALID,
    ValidationViolationCode.DEBT_OVERFLOW: BaselineIssueKind.DEBT_OVERFLOW,
}


@dataclass(frozen=True)
class BaselineIssue:
    kind: BaselineIssueKind
    lesson_id: int | None = None
    assignment_id: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class BaselineAssessment:
    """Missing and excess coverage plus physical invalidity of the baseline."""

    missing_minutes_by_assignment: Mapping[int, int]
    excess_minutes_by_assignment: Mapping[int, int]
    issues: tuple[BaselineIssue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "missing_minutes_by_assignment",
            MappingProxyType(dict(sorted(self.missing_minutes_by_assignment.items()))),
        )
        object.__setattr__(
            self,
            "excess_minutes_by_assignment",
            MappingProxyType(dict(sorted(self.excess_minutes_by_assignment.items()))),
        )

    @property
    def missing_minutes(self) -> int:
        return sum(self.missing_minutes_by_assignment.values())

    @property
    def excess_minutes(self) -> int:
        return sum(self.excess_minutes_by_assignment.values())

    @property
    def valid(self) -> bool:
        return not self.issues and self.missing_minutes == 0 and self.excess_minutes == 0

    @property
    def requires_repair(self) -> bool:
        return not self.valid


def assess_baseline(
    snapshot: PlanningSnapshot, baseline: Sequence[ScheduledLesson]
) -> BaselineAssessment:
    """Describe how the published baseline fails against the current state.

    The published schedule, completed with the protected lessons of the
    snapshot, is revalidated by the independent validator: conflicts,
    duplicates, chronology, curriculum, protection and reservations all count.
    Coverage is then compared on the editable part only, because the residual
    demand already excludes protected credit.
    """
    if type(snapshot) is not PlanningSnapshot:
        raise ValueError("Baseline assessment needs a planning snapshot.")
    lessons = tuple(baseline)
    protected_ids = {lesson.lesson_id for lesson in snapshot.protected_lessons}
    known_assignments = {row.assignment_id for row in snapshot.assignments}
    by_id = {lesson.lesson_id: lesson for lesson in lessons}
    full = list(lessons)
    for protected in snapshot.protected_lessons:
        if protected.lesson_id not in by_id:
            full.append(protected)
    report = validate_candidate(snapshot, CandidateSchedule(tuple(full)))
    issues: list[BaselineIssue] = []
    seen: set[tuple] = set()
    for violation in report.violations:
        kind = _ISSUE_BY_VIOLATION.get(violation.code, BaselineIssueKind.INVALID)
        key = (kind, violation.lesson_id, violation.assignment_id)
        if key in seen:
            continue
        seen.add(key)
        issues.append(
            BaselineIssue(
                kind,
                lesson_id=violation.lesson_id,
                assignment_id=violation.assignment_id,
                detail=violation.message,
            )
        )
    credited: dict[int, int] = defaultdict(int)
    for lesson in full:
        if lesson.lesson_id in protected_ids or lesson.assignment_id not in known_assignments:
            continue
        credited[lesson.assignment_id] += lesson.credit_minutes
    missing: dict[int, int] = {}
    excess: dict[int, int] = {}
    for assignment in snapshot.assignments:
        assignment_id = assignment.assignment_id
        residual = residual_minutes(snapshot, assignment_id)
        published = credited.get(assignment_id, 0)
        if published < residual:
            missing[assignment_id] = residual - published
        elif published > residual:
            excess[assignment_id] = published - residual
    if missing:
        issues.append(
            BaselineIssue(
                BaselineIssueKind.MISSING_COVERAGE,
                detail=f"{sum(missing.values())} minute(s) without a published lesson.",
            )
        )
    if excess:
        issues.append(
            BaselineIssue(
                BaselineIssueKind.EXCESS_CREDIT,
                detail=f"{sum(excess.values())} published minute(s) beyond the demand.",
            )
        )
    return BaselineAssessment(missing, excess, tuple(issues))


class LessonChangeKind(StrEnum):
    INSERTED = "INSERTED"
    REMOVED = "REMOVED"
    MOVED = "MOVED"
    ROOM_CHANGED = "ROOM_CHANGED"


@dataclass(frozen=True)
class LessonChange:
    kind: LessonChangeKind
    cost: int
    source_lesson_id: int | None = None
    candidate_lesson_id: int | None = None

    def __post_init__(self) -> None:
        if type(self.cost) is not int or self.cost < 0:
            raise ValueError("A lesson change cost must be a nonnegative integer.")


@dataclass(frozen=True)
class DisruptionMetrics:
    changes: tuple[LessonChange, ...]
    total_cost: int

    def __post_init__(self) -> None:
        if type(self.total_cost) is not int or self.total_cost < 0:
            raise ValueError("Disruption cost must be a nonnegative integer.")
        if self.total_cost != sum(change.cost for change in self.changes):
            raise ValueError("Disruption cost must equal the sum of its changes.")

    @property
    def moved_lessons(self) -> int:
        return sum(1 for row in self.changes if row.kind is LessonChangeKind.MOVED)

    @property
    def inserted_lessons(self) -> int:
        return sum(1 for row in self.changes if row.kind is LessonChangeKind.INSERTED)

    @property
    def removed_lessons(self) -> int:
        return sum(1 for row in self.changes if row.kind is LessonChangeKind.REMOVED)

    @property
    def room_changes(self) -> int:
        return sum(1 for row in self.changes if row.kind is LessonChangeKind.ROOM_CHANGED)


@dataclass(frozen=True)
class RecoveryPolicy:
    """Versioned experimental policy; no coefficient is a silent production default."""

    version: str
    daily_slopes: tuple[int, ...]
    disruption_weight: int
    move_cost: int
    insert_cost: int
    remove_cost: int
    room_change_cost: int
    urgency_horizon_days: int
    urgency_slope: int
    recurrence_penalty: int

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("A recovery policy needs a version.")
        if type(self.daily_slopes) is not tuple or any(
            type(slope) is not int or slope <= 0 for slope in self.daily_slopes
        ):
            raise ValueError("Margin slopes must be positive integers.")
        if any(
            left >= right
            for left, right in zip(self.daily_slopes, self.daily_slopes[1:], strict=False)
        ):
            raise ValueError("Margin slopes must increase toward the preferred end date.")
        for name in ("disruption_weight", "move_cost", "insert_cost", "remove_cost"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        for name in (
            "room_change_cost",
            "urgency_horizon_days",
            "urgency_slope",
            "recurrence_penalty",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer.")

    @property
    def adaptive_policy(self) -> AdaptiveQualityPolicy:
        return AdaptiveQualityPolicy(self.version, self.daily_slopes, self.disruption_weight)

    def urgency(self, snapshot: PlanningSnapshot, lesson: ScheduledLesson) -> int:
        frontier = editable_frontier(snapshot)
        if frontier is None:
            return 1
        distance = max(0, (lesson.period.school_date - frontier).days)
        window = max(0, self.urgency_horizon_days - distance)
        return 1 + self.urgency_slope * window

    def change_cost(
        self, base: int, snapshot: PlanningSnapshot, lesson: ScheduledLesson, prior: bool
    ) -> int:
        cost = base * self.urgency(snapshot, lesson)
        if prior:
            cost *= 1 + self.recurrence_penalty
        return cost


def editable_frontier(snapshot: PlanningSnapshot) -> date | None:
    """Last physically protected school date; urgency rises when approaching it."""
    candidates: list[date] = list(snapshot.protected_dates)
    if snapshot.now_utc is not None:
        candidates.append(snapshot.now_utc.astimezone(ZoneInfo(snapshot.timezone_name)).date())
    return max(candidates) if candidates else None


def _same_physical_position(left: ScheduledLesson, right: ScheduledLesson) -> bool:
    return (
        left.assignment_id == right.assignment_id
        and left.period.start_utc == right.period.start_utc
        and left.period.end_utc == right.period.end_utc
    )


def _lesson_order(lesson: ScheduledLesson) -> tuple:
    return (lesson.period.school_date, lesson.period.start_utc, lesson.lesson_id)


def _match_baseline(
    baseline: Sequence[ScheduledLesson],
    candidate: Sequence[ScheduledLesson],
) -> tuple[
    list[tuple[ScheduledLesson, ScheduledLesson]], list[ScheduledLesson], list[ScheduledLesson]
]:
    """Pair candidate lessons with their published source.

    A candidate may name its source explicitly. Without that, an identical
    physical position is still not a change. The remaining lessons are paired
    per assignment in chronological order, so a displacement without a source
    is priced as one movement instead of a removal plus an insertion.
    """
    unmatched = list(baseline)
    matched: list[tuple[ScheduledLesson, ScheduledLesson]] = []
    extra: list[ScheduledLesson] = []
    for lesson in candidate:
        source = next((row for row in unmatched if row.lesson_id == lesson.source_lesson_id), None)
        if source is None:
            source = next((row for row in unmatched if _same_physical_position(row, lesson)), None)
        if source is None:
            extra.append(lesson)
        else:
            unmatched.remove(source)
            matched.append((source, lesson))
    base_by_assignment: dict[int, list[ScheduledLesson]] = defaultdict(list)
    for row in unmatched:
        base_by_assignment[row.assignment_id].append(row)
    new_by_assignment: dict[int, list[ScheduledLesson]] = defaultdict(list)
    for row in extra:
        new_by_assignment[row.assignment_id].append(row)
    leftover_base: list[ScheduledLesson] = []
    leftover_extra: list[ScheduledLesson] = []
    for assignment_id in sorted(set(base_by_assignment) | set(new_by_assignment)):
        base_rows = sorted(base_by_assignment.get(assignment_id, ()), key=_lesson_order)
        new_rows = sorted(new_by_assignment.get(assignment_id, ()), key=_lesson_order)
        for source, lesson in zip(base_rows, new_rows, strict=False):
            matched.append((source, lesson))
        leftover_base.extend(base_rows[len(new_rows) :])
        leftover_extra.extend(new_rows[len(base_rows) :])
    return matched, leftover_extra, leftover_base


def measure_disruption(
    snapshot: PlanningSnapshot,
    baseline: CandidateSchedule,
    candidate: CandidateSchedule,
    policy: RecoveryPolicy,
    *,
    prior_changes: frozenset[int] = frozenset(),
) -> DisruptionMetrics:
    """Real physical transformations against the published baseline."""
    if (
        type(snapshot) is not PlanningSnapshot
        or type(baseline) is not CandidateSchedule
        or type(candidate) is not CandidateSchedule
    ):
        raise ValueError("Disruption needs a snapshot, a baseline and a candidate.")
    protected_ids = {lesson.lesson_id for lesson in snapshot.protected_lessons}
    published = [row for row in baseline.lessons if row.lesson_id not in protected_ids]
    planned = [row for row in candidate.lessons if row.lesson_id not in protected_ids]
    matched, extra, removed = _match_baseline(published, planned)
    changes: list[LessonChange] = []
    for source, result in matched:
        prior = source.lesson_id in prior_changes
        moved = not _same_physical_position(source, result)
        if moved:
            changes.append(
                LessonChange(
                    LessonChangeKind.MOVED,
                    policy.change_cost(policy.move_cost, snapshot, source, prior),
                    source.lesson_id,
                    result.lesson_id,
                )
            )
        elif source.room_id != result.room_id:
            changes.append(
                LessonChange(
                    LessonChangeKind.ROOM_CHANGED,
                    policy.change_cost(policy.room_change_cost, snapshot, source, prior),
                    source.lesson_id,
                    result.lesson_id,
                )
            )
    for lesson in removed:
        prior = lesson.lesson_id in prior_changes
        changes.append(
            LessonChange(
                LessonChangeKind.REMOVED,
                policy.change_cost(policy.remove_cost, snapshot, lesson, prior),
                lesson.lesson_id,
                None,
            )
        )
    for lesson in extra:
        changes.append(
            LessonChange(
                LessonChangeKind.INSERTED,
                policy.change_cost(policy.insert_cost, snapshot, lesson, False),
                None,
                lesson.lesson_id,
            )
        )
    ordered = tuple(
        sorted(
            changes,
            key=lambda row: (
                row.kind.value,
                row.source_lesson_id or 0,
                row.candidate_lesson_id or 0,
            ),
        )
    )
    return DisruptionMetrics(ordered, sum(row.cost for row in ordered))


@dataclass(frozen=True)
class RecoveryQualityMetrics:
    """Adaptive metrics recalculated from snapshot, baseline and candidate alone."""

    initial: InitialQualityMetrics
    disruption: DisruptionMetrics

    def vector(
        self,
        *,
        origin: date,
        preferred_end_date: date,
        hard_end_date: date,
        policy: RecoveryPolicy,
        class_ids: Sequence[int] | None = None,
    ) -> AdaptiveQualityVector:
        return adaptive_quality_vector(
            self.initial.completion_dates,
            class_ids=tuple(sorted(self.initial.completion_dates))
            if class_ids is None
            else class_ids,
            origin=origin,
            preferred_end_date=preferred_end_date,
            hard_end_date=hard_end_date,
            disruption_cost=self.disruption.total_cost,
            teacher_gap_minutes=self.initial.teacher_gap_minutes,
            class_gap_minutes=self.initial.class_gap_minutes,
            preference_cost=self.initial.preference_cost_minutes,
            room_change_cost=self.initial.room_change_cost,
            policy=policy.adaptive_policy,
        )


def measure_recovery_quality(
    snapshot: PlanningSnapshot,
    baseline: CandidateSchedule,
    candidate: CandidateSchedule,
    policy: RecoveryPolicy,
    *,
    prior_changes: frozenset[int] = frozenset(),
) -> RecoveryQualityMetrics:
    """Recalculate the adaptive metrics without consulting the solver."""
    if type(snapshot) is not PlanningSnapshot or type(candidate) is not CandidateSchedule:
        raise ValueError("Recovery quality needs a snapshot, a baseline and a candidate.")
    if snapshot.strategy is not SchedulingStrategy.ADAPTIVE_RECOVERY:
        raise ValueError("Recovery quality needs an ADAPTIVE_RECOVERY snapshot.")
    return RecoveryQualityMetrics(
        initial=measure_initial_quality(snapshot, candidate),
        disruption=measure_disruption(
            snapshot, baseline, candidate, policy, prior_changes=prior_changes
        ),
    )


def reconcile_after_repair(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
    claims: Sequence[DebtClaim],
    *,
    revisions: Sequence[DebtRevision] = (),
    settlements: Sequence[DebtSettlement] = (),
    allocations: Sequence[RecoveryAllocation] = (),
    executed_credit_by_event: Mapping[tuple[str, int], int] | None = None,
) -> tuple[DebtBalance, ...]:
    """Reconcile debt and future credits after a repair without settling a proposal.

    Reservations of another version are ignored by reconciliation: minutes are
    settled by recorded execution only, never because a proposal exists.
    """
    if type(snapshot) is not PlanningSnapshot or type(candidate) is not CandidateSchedule:
        raise ValueError("Reconciliation needs a snapshot and a repaired candidate.")
    residual = sum(
        max(0, residual_minutes(snapshot, assignment.assignment_id))
        for assignment in snapshot.assignments
    )
    credits = {lesson.lesson_id: lesson.credit_minutes for lesson in candidate.lessons}
    return reconcile_debt(
        claims,
        residual_minutes=residual,
        revisions=revisions,
        settlements=settlements,
        allocations=allocations,
        active_version_id=snapshot.active_version_id,
        future_lesson_credits=credits,
        executed_credit_by_event=executed_credit_by_event,
    )


def recovery_vector(
    snapshot: PlanningSnapshot,
    baseline: CandidateSchedule,
    candidate: CandidateSchedule,
    policy: RecoveryPolicy,
    *,
    prior_changes: frozenset[int] = frozenset(),
) -> AdaptiveQualityVector:
    metrics = measure_recovery_quality(
        snapshot, baseline, candidate, policy, prior_changes=prior_changes
    )
    return metrics.vector(
        origin=snapshot.origin,
        preferred_end_date=snapshot.preferred_end_date,
        hard_end_date=snapshot.hard_end_date,
        policy=policy,
    )
