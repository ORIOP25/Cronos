"""Recovery fixtures: a published baseline perturbed by one deterministic event.

The baseline is the witness of the base fixture. The event is derived from the
event seed, never selected by looking at the solver result: lesson cancellation,
teacher absence or room closure. Small fixtures keep an oracle-derived
expectation; large fixtures stay exploratory and are never called impossible
without proof.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.scheduler.domain.calendar import Period, normalize_period
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    PlanningSnapshot,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.oracle import optimal_candidate
from app.scheduler.domain.recovery import RecoveryPolicy
from app.scheduler.infrastructure.constructive import construct_schedule
from app.scheduler.lab.fixtures import (
    CaseExpectation,
    FixtureSpec,
    build_fixture,
    build_snapshot,
)

CANCEL_LESSON = "CANCEL_LESSON"
TEACHER_ABSENCE = "TEACHER_ABSENCE"
ROOM_CLOSED = "ROOM_CLOSED"
EVENTS = (CANCEL_LESSON, TEACHER_ABSENCE, ROOM_CLOSED)


@dataclass(frozen=True)
class RecoveryCase:
    case_id: str
    family: str
    version: int
    expectation: CaseExpectation
    snapshot: PlanningSnapshot
    periods: tuple[Period, ...]
    baseline: CandidateSchedule
    event: str
    fixture_seed: int = 0
    event_seed: int = 0
    solver_seed: int = 0
    parent_case_id: str | None = None


@dataclass(frozen=True)
class EventEffect:
    """What a deterministic perturbation actually changed."""

    event: str
    applied: bool
    affected_lessons: int
    resource_type: str | None = None
    resource_id: int | None = None


def laboratory_policy(snapshot: PlanningSnapshot) -> RecoveryPolicy:
    """Explicit experimental coefficients; calibration is W11 work."""
    days = max(1, (snapshot.preferred_end_date - snapshot.origin).days)
    return RecoveryPolicy(
        version="laboratory-default",
        daily_slopes=tuple(range(1, days + 1)),
        disruption_weight=1,
        move_cost=10,
        insert_cost=12,
        remove_cost=15,
        room_change_cost=3,
        urgency_horizon_days=10,
        urgency_slope=1,
        recurrence_penalty=1,
    )


def recovery_event(event_seed: int) -> str:
    if type(event_seed) is not int or event_seed < 0:
        raise ValueError("The event seed must be a nonnegative integer.")
    return EVENTS[event_seed % len(EVENTS)]


def _ordered(lessons: tuple) -> list:
    return sorted(
        lessons,
        key=lambda row: (row.period.school_date, row.period.start_local, row.lesson_id),
    )


def apply_event(
    snapshot: PlanningSnapshot,
    baseline: CandidateSchedule,
    event: str,
    event_seed: int,
) -> PlanningSnapshot:
    """One audited perturbation over the published baseline."""
    return apply_event_with_effect(snapshot, baseline, event, event_seed)[0]


def apply_event_with_effect(
    snapshot: PlanningSnapshot,
    baseline: CandidateSchedule,
    event: str,
    event_seed: int,
) -> tuple[PlanningSnapshot, EventEffect]:
    """Apply one perturbation and report whether it affected future lessons.

    Every event targets lessons of the supplied baseline. In a replay the
    baseline is the active (future) plan, so an absence never lands in the past
    and a no-effect event is reported instead of silently doing nothing.
    """
    lessons = _ordered(baseline.lessons)
    if not lessons:
        raise ValueError("A recovery event needs published lessons.")
    if event == CANCEL_LESSON:
        rank = (event_seed // len(EVENTS)) % len(lessons)
        lesson = lessons[rank]
        assignment = snapshot.assignment_for(lesson.assignment_id)
        if assignment is None:
            raise ValueError("The published baseline does not belong to the snapshot.")
        rows = [
            *(
                Unavailability(UnavailableResource.CLASS, class_id, lesson.period)
                for class_id in assignment.class_ids
            ),
            Unavailability(UnavailableResource.TEACHER, assignment.teacher_id, lesson.period),
        ]
        effect = EventEffect(CANCEL_LESSON, True, 1, "class", assignment.class_ids[0])
    elif event == ROOM_CLOSED:
        rank = (event_seed // len(EVENTS)) % len(lessons)
        lesson = lessons[rank]
        rows = [Unavailability(UnavailableResource.ROOM, lesson.room_id, lesson.period)]
        effect = EventEffect(ROOM_CLOSED, True, 1, "room", lesson.room_id)
    elif event == TEACHER_ABSENCE:
        teachers = sorted({row.teacher_id for row in snapshot.assignments})
        teacher_id = teachers[(event_seed // len(EVENTS)) % len(teachers)]
        duration = 1 + (event_seed // (len(EVENTS) * len(teachers))) % 2
        protected_periods = [lesson.period for lesson in snapshot.protected_lessons]
        future = [
            lesson
            for lesson in lessons
            if (assignment := snapshot.assignment_for(lesson.assignment_id)) is not None
            and assignment.teacher_id == teacher_id
            and lesson.period.school_date not in snapshot.protected_dates
            and not any(lesson.period.overlaps(occupied) for occupied in protected_periods)
        ]
        if not future:
            return snapshot, EventEffect(TEACHER_ABSENCE, False, 0, "teacher", teacher_id)
        target_dates = sorted({lesson.period.school_date for lesson in future})[:duration]
        rows = [
            Unavailability(UnavailableResource.TEACHER, teacher_id, lesson.period)
            for lesson in future
            if lesson.period.school_date in target_dates
        ]
        effect = EventEffect(TEACHER_ABSENCE, True, len(rows), "teacher", teacher_id)
    else:
        raise ValueError(f"Unknown recovery event: {event}")
    perturbed = replace(
        snapshot,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        baseline_lessons=baseline.lessons,
        unavailable=(*snapshot.unavailable, *rows),
    )
    return perturbed, effect


def build_recovery_case(
    case_id: str,
    spec: FixtureSpec,
    *,
    family: str = "recovery",
    version: int = 1,
    fixture_seed: int = 0,
    event_seed: int = 0,
    solver_seed: int = 0,
) -> RecoveryCase:
    """Build the published baseline and its deterministic perturbation."""
    base = build_fixture(case_id + "-base", spec, fixture_seed=fixture_seed)
    baseline = base.witness
    event = recovery_event(event_seed)
    snapshot = apply_event(base.snapshot, baseline, event, event_seed)
    witness = optimal_candidate(snapshot, base.periods)
    expectation = (
        CaseExpectation.FEASIBLE_WITH_WITNESS
        if witness is not None
        else CaseExpectation.INFEASIBLE_PROVEN
    )
    return RecoveryCase(
        case_id=case_id,
        family=family,
        version=version,
        expectation=expectation,
        snapshot=snapshot,
        periods=base.periods,
        baseline=baseline,
        event=event,
        fixture_seed=fixture_seed,
        event_seed=event_seed,
        solver_seed=solver_seed,
    )


def build_constructed_recovery_case(
    case_id: str,
    spec: FixtureSpec,
    *,
    family: str = "constructed",
    version: int = 1,
    fixture_seed: int = 0,
    event_seed: int = 0,
    solver_seed: int = 0,
) -> RecoveryCase:
    """A repair case with independent constructive witnesses on both sides.

    The published baseline is constructed for the unperturbed snapshot; after
    applying the events, a second constructive witness is validated by the
    independent validator. The minimal oracle is never called, so the case can
    grow beyond enumerable size without weakening the witness guarantee.
    """
    snapshot = build_snapshot(spec)
    periods = tuple(
        normalize_period(day, start, end, spec.timezone_name) for day, start, end in spec.periods
    )
    baseline = construct_schedule(snapshot, periods)
    if baseline is None:
        raise ValueError("The constructed baseline has no independent witness.")
    event = recovery_event(event_seed)
    perturbed = apply_event(snapshot, baseline, event, event_seed)
    target = construct_schedule(perturbed, periods)
    if target is None:
        raise ValueError("The perturbed case has no independent constructive witness.")
    return RecoveryCase(
        case_id=case_id,
        family=family,
        version=version,
        expectation=CaseExpectation.FEASIBLE_WITH_WITNESS,
        snapshot=perturbed,
        periods=periods,
        baseline=baseline,
        event=event,
        fixture_seed=fixture_seed,
        event_seed=event_seed,
        solver_seed=solver_seed,
    )
