"""C14 longitudinal annual replay: accumulated events over an approved baseline.

Each step advances a simulated school clock, consumes the planned lessons left
behind as executed credit, applies one deterministic perturbation to the active
baseline, repairs it with the same AdaptiveRecovery used in production, and
adopts the validated candidate as the new published baseline (the laboratory
equivalent of approval). Minutes are conserved at every complete step: executed
credit plus planned slices must equal each assignment requirement.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta

from app.scheduler.composition import repair_published_schedule
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
)
from app.scheduler.domain.recovery import RecoveryPolicy
from app.scheduler.lab.annual import AnnualFixture
from app.scheduler.lab.recovery import (
    apply_event_with_effect,
    laboratory_policy,
    recovery_event,
)

EVENT_STRIDE = 7


@dataclass(frozen=True)
class ReplayStep:
    step_index: int
    event: str
    event_seed: int
    outcome: str
    valid: bool
    conserved: bool
    applied: bool
    affected_lessons: int
    executed_minutes: int
    planned_minutes: int
    changed_lessons: int
    excess_days: int
    latest_completion_date: date | None
    message: str


@dataclass(frozen=True)
class AnnualReplay:
    case_id: str
    event_count: int
    steps: tuple[ReplayStep, ...]
    completed: bool
    stopped_reason: str
    conserved: bool
    final_candidate: CandidateSchedule | None
    executed_minutes: int
    planned_minutes: int
    snapshot: PlanningSnapshot


def _consume_executed(
    active: tuple[ScheduledLesson, ...],
    executed: Mapping[int, Mapping[int, int]],
    clock: date,
) -> tuple[tuple[ScheduledLesson, ...], dict[int, dict[int, int]]]:
    """Move lessons left behind by the simulated clock into executed credit."""
    updated = {assignment_id: dict(rows) for assignment_id, rows in executed.items()}
    remaining: list[ScheduledLesson] = []
    for lesson in active:
        if lesson.period.school_date < clock:
            rows = updated.setdefault(lesson.assignment_id, {})
            for slice_ in lesson.slices:
                rows[slice_.module_id] = rows.get(slice_.module_id, 0) + slice_.credit_minutes
        else:
            remaining.append(lesson)
    return tuple(remaining), updated


def _credit_total(executed: Mapping[int, Mapping[int, int]]) -> int:
    return sum(minutes for rows in executed.values() for minutes in rows.values())


def _conservation_problems(
    snapshot: PlanningSnapshot, candidate: CandidateSchedule | None
) -> tuple[str, ...]:
    if candidate is None:
        return ("No final candidate exists to conserve the assignment minutes.",)
    planned: dict[int, dict[int, int]] = {}
    for lesson in candidate.lessons:
        rows = planned.setdefault(lesson.assignment_id, {})
        for slice_ in lesson.slices:
            rows[slice_.module_id] = rows.get(slice_.module_id, 0) + slice_.credit_minutes
    problems: list[str] = []
    for assignment in snapshot.assignments:
        executed_rows = snapshot.executed_minutes.get(assignment.assignment_id, {})
        for module in assignment.modules:
            total = executed_rows.get(module.module_id, 0) + planned.get(
                assignment.assignment_id, {}
            ).get(module.module_id, 0)
            if total != module.required_minutes:
                problems.append(
                    f"assignment {assignment.assignment_id} module {module.module_id}: "
                    f"{total} != {module.required_minutes}"
                )
    return tuple(problems)


def replay_annual_events(
    fixture: AnnualFixture,
    *,
    event_count: int,
    event_seed: int = 0,
    step_days: int = 14,
    time_limit_seconds: float = 10.0,
    solver_seed: int = 1,
    workers: int = 1,
    policy: RecoveryPolicy | None = None,
    case_id: str | None = None,
) -> AnnualReplay:
    """Replay ``event_count`` perturbations over a constructed annual baseline."""
    if event_count < 0:
        raise ValueError("The event count cannot be negative.")
    if step_days <= 0:
        raise ValueError("The simulated step must advance the clock.")
    if fixture.witness is None:
        raise ValueError("An annual replay needs a constructed witness baseline.")
    recovery_policy = policy or laboratory_policy(fixture.snapshot)
    active = fixture.witness.lessons
    snapshot = fixture.snapshot
    steps: list[ReplayStep] = []
    completed = True
    stopped_reason = ""
    final: CandidateSchedule | None = fixture.witness if event_count == 0 else None

    for index in range(event_count):
        clock = snapshot.origin + timedelta(days=step_days * (index + 1))
        active, executed = _consume_executed(active, snapshot.executed_minutes, clock)
        snapshot = replace(
            snapshot,
            executed_minutes=executed,
            baseline_lessons=active,
        )
        if not active:
            completed = False
            stopped_reason = (
                "The simulated execution consumed the year before all events were applied."
            )
            break
        seed = event_seed + index * EVENT_STRIDE
        event = recovery_event(seed)
        perturbed, effect = apply_event_with_effect(
            snapshot, fixture.periods, CandidateSchedule(active), event, seed
        )
        if not effect.applied:
            steps.append(
                ReplayStep(
                    step_index=index,
                    event=event,
                    event_seed=seed,
                    outcome="NOT_APPLIED",
                    valid=False,
                    conserved=False,
                    applied=False,
                    affected_lessons=0,
                    executed_minutes=_credit_total(executed),
                    planned_minutes=sum(lesson.credit_minutes for lesson in active),
                    changed_lessons=0,
                    excess_days=0,
                    latest_completion_date=None,
                    message=f"Event {event} had no future lesson to affect.",
                )
            )
            completed = False
            stopped_reason = f"Event {event} had no future lesson to affect."
            final = None
            break
        repaired = repair_published_schedule(
            perturbed,
            fixture.periods,
            CandidateSchedule(active),
            recovery_policy,
            time_limit_seconds=time_limit_seconds,
            num_workers=workers,
            random_seed=solver_seed + index,
        )
        candidate = repaired.candidate
        problems = _conservation_problems(perturbed, candidate)
        conserved = candidate is not None and not problems
        valid = bool(repaired.report is not None and repaired.report.valid)
        quality = repaired.quality
        summary = repaired.summary
        steps.append(
            ReplayStep(
                step_index=index,
                event=event,
                event_seed=seed,
                outcome=repaired.outcome,
                valid=valid,
                conserved=conserved,
                applied=True,
                affected_lessons=effect.affected_lessons,
                executed_minutes=_credit_total(executed),
                planned_minutes=(
                    0
                    if candidate is None
                    else sum(lesson.credit_minutes for lesson in candidate.lessons)
                ),
                changed_lessons=0 if quality is None else len(quality.disruption.changes),
                excess_days=0 if summary is None else summary.excess_days,
                latest_completion_date=None if summary is None else summary.latest_completion_date,
                message=problems[0] if problems else repaired.message,
            )
        )
        if repaired.outcome != "COMPLETE" or not valid or not conserved:
            completed = False
            stopped_reason = (
                "; ".join(problems) if problems else (repaired.message or repaired.outcome)
            )
            final = candidate if candidate is not None and valid and conserved else None
            break
        active = candidate.lessons
        snapshot = replace(
            perturbed,
            baseline_lessons=active,
        )
        final = candidate

    completed = (
        completed
        and len(steps) == event_count
        and all(
            step.applied and step.outcome == "COMPLETE" and step.valid and step.conserved
            for step in steps
        )
    )
    return AnnualReplay(
        case_id=case_id or f"annual-{fixture.class_count}-{fixture.profile}-{fixture.seed}",
        event_count=event_count,
        steps=tuple(steps),
        completed=completed,
        stopped_reason=stopped_reason,
        conserved=final is not None and _conservation_problems(snapshot, final) == (),
        final_candidate=final,
        executed_minutes=_credit_total(snapshot.executed_minutes),
        planned_minutes=(
            0 if final is None else sum(lesson.credit_minutes for lesson in final.lessons)
        ),
        snapshot=snapshot,
    )


def replay_to_dict(replay: AnnualReplay) -> dict:
    return {
        "case_id": replay.case_id,
        "event_count": replay.event_count,
        "completed": replay.completed,
        "stopped_reason": replay.stopped_reason,
        "conserved": replay.conserved,
        "executed_minutes": replay.executed_minutes,
        "planned_minutes": replay.planned_minutes,
        "steps": [
            {
                "step": step.step_index,
                "event": step.event,
                "event_seed": step.event_seed,
                "outcome": step.outcome,
                "valid": step.valid,
                "conserved": step.conserved,
                "applied": step.applied,
                "affected_lessons": step.affected_lessons,
                "executed_minutes": step.executed_minutes,
                "planned_minutes": step.planned_minutes,
                "changed_lessons": step.changed_lessons,
                "excess_days": step.excess_days,
                "latest_completion_date": (
                    None
                    if step.latest_completion_date is None
                    else step.latest_completion_date.isoformat()
                ),
                "message": step.message,
            }
            for step in replay.steps
        ],
    }
