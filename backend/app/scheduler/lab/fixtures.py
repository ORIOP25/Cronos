"""Deterministic minimal fixtures with validated witnesses and mutations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time
from enum import StrEnum

from app.scheduler.domain.calendar import Period, normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    PlanningSnapshot,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import (
    ValidationReport,
    validate_candidate,
)
from app.scheduler.domain.debt import RecoveryAllocation
from app.scheduler.domain.oracle import optimal_candidate
from app.scheduler.domain.projection import ModuleRequirement


class CaseExpectation(StrEnum):
    FEASIBLE_WITH_WITNESS = "FEASIBLE_WITH_WITNESS"
    INFEASIBLE_PROVEN = "INFEASIBLE_PROVEN"
    INVALID_INPUT = "INVALID_INPUT"
    EXPLORATORY_UNKNOWN = "EXPLORATORY_UNKNOWN"


@dataclass(frozen=True)
class AssignmentSpec:
    class_id: int
    teacher_id: int
    module_minutes: tuple[int, ...]
    eligible_rooms: tuple[int, ...]

    def to_assignment(self, assignment_id: int) -> Assignment:
        return Assignment(
            assignment_id=assignment_id,
            class_ids=(self.class_id,),
            subject_id=assignment_id,
            teacher_id=self.teacher_id,
            eligible_room_ids=frozenset(self.eligible_rooms),
            modules=tuple(
                ModuleRequirement(module_id, module_id, minutes)
                for module_id, minutes in enumerate(self.module_minutes, start=1)
            ),
        )


@dataclass(frozen=True)
class FixtureSpec:
    strategy: SchedulingStrategy
    origin: date
    preferred_end_date: date
    hard_end_date: date
    timezone_name: str
    grid_slots: tuple[tuple[int, time, time], ...]
    periods: tuple[tuple[date, time, time], ...]
    assignments: tuple[AssignmentSpec, ...]
    blocked_dates: frozenset[date] = frozenset()
    executed_minutes: tuple[tuple[int, tuple[tuple[int, int], ...]], ...] = ()
    unavailable: tuple[tuple[str, int, tuple[date, time, time]], ...] = ()
    soft_unavailable: tuple[tuple[str, int, tuple[date, time, time]], ...] = ()
    protected_dates: frozenset[date] = frozenset()
    now_utc: datetime | None = None
    reservations: tuple[tuple[int, int, int, int], ...] = ()
    open_debt_minutes: tuple[tuple[int, int], ...] = ()
    claim_assignments: tuple[tuple[int, int], ...] = ()
    active_version_id: int | None = None


@dataclass(frozen=True)
class Fixture:
    case_id: str
    family: str
    version: int
    expectation: CaseExpectation
    snapshot: PlanningSnapshot
    periods: tuple[Period, ...]
    witness: CandidateSchedule | None
    parent_case_id: str | None = None
    mutation: str | None = None
    fixture_seed: int = 0
    event_seed: int = 0
    solver_seed: int = 0


def _normalize_periods(spec: FixtureSpec) -> tuple[Period, ...]:
    return tuple(
        normalize_period(day, start, end, spec.timezone_name) for day, start, end in spec.periods
    )


def _unavailability(
    rows: tuple[tuple[str, int, tuple[date, time, time]], ...], timezone_name: str
) -> tuple[Unavailability, ...]:
    return tuple(
        Unavailability(
            UnavailableResource(resource_type),
            resource_id,
            normalize_period(day, start, end, timezone_name),
        )
        for resource_type, resource_id, (day, start, end) in rows
    )


def build_snapshot(spec: FixtureSpec) -> PlanningSnapshot:
    unavailable = _unavailability(spec.unavailable, spec.timezone_name)
    return PlanningSnapshot(
        strategy=spec.strategy,
        origin=spec.origin,
        preferred_end_date=spec.preferred_end_date,
        hard_end_date=spec.hard_end_date,
        timezone_name=spec.timezone_name,
        grid_slots=tuple(
            GridSlot(day_of_week, start, end) for day_of_week, start, end in spec.grid_slots
        ),
        assignments=tuple(
            row.to_assignment(index) for index, row in enumerate(spec.assignments, start=1)
        ),
        executed_minutes={
            assignment_id: dict(rows) for assignment_id, rows in spec.executed_minutes
        },
        blocked_dates=spec.blocked_dates,
        unavailable=unavailable,
        soft_unavailable=_unavailability(spec.soft_unavailable, spec.timezone_name),
        protected_dates=spec.protected_dates,
        now_utc=spec.now_utc,
        reservations=tuple(
            RecoveryAllocation(version_id, lesson_id, claim_id, minutes)
            for version_id, lesson_id, claim_id, minutes in spec.reservations
        ),
        open_debt_minutes=dict(spec.open_debt_minutes),
        claim_assignments=dict(spec.claim_assignments),
        active_version_id=spec.active_version_id,
    )


def build_fixture(
    case_id: str,
    spec: FixtureSpec,
    *,
    family: str = "minimal",
    version: int = 1,
    expectation: CaseExpectation = CaseExpectation.FEASIBLE_WITH_WITNESS,
    fixture_seed: int = 0,
    event_seed: int = 0,
    solver_seed: int = 0,
) -> Fixture:
    """Build inputs and derive a witness from the independent oracle."""
    snapshot = build_snapshot(spec)
    periods = _normalize_periods(spec)
    witness = optimal_candidate(snapshot, periods)
    if expectation is CaseExpectation.FEASIBLE_WITH_WITNESS and witness is None:
        raise ValueError("The fixture spec has no complete witness.")
    if expectation is CaseExpectation.INFEASIBLE_PROVEN and witness is not None:
        raise ValueError("The fixture spec is not provably infeasible.")
    return Fixture(
        case_id=case_id,
        family=family,
        version=version,
        expectation=expectation,
        snapshot=snapshot,
        periods=periods,
        witness=witness,
        fixture_seed=fixture_seed,
        event_seed=event_seed,
        solver_seed=solver_seed,
    )


def witness_report(fixture: Fixture) -> ValidationReport:
    if fixture.witness is None:
        raise ValueError("This fixture has no witness to validate.")
    return validate_candidate(fixture.snapshot, fixture.witness)


def _first_lesson(fixture: Fixture):
    assert fixture.witness is not None
    return fixture.witness.lessons[0]


def _mutate_drop_lesson(fixture: Fixture):
    assert fixture.witness is not None
    return fixture.snapshot, CandidateSchedule(fixture.witness.lessons[:-1])


def _mutate_duplicate_identity(fixture: Fixture):
    assert fixture.witness is not None
    return fixture.snapshot, CandidateSchedule((*fixture.witness.lessons, _first_lesson(fixture)))


def _mutate_ineligible_room(fixture: Fixture):
    assert fixture.witness is not None
    lesson = _first_lesson(fixture)
    moved = replace(lesson, room_id=max(lesson.room_id, 500) + 9_000)
    return fixture.snapshot, CandidateSchedule((moved, *fixture.witness.lessons[1:]))


def _mutate_out_of_calendar(fixture: Fixture):
    assert fixture.witness is not None
    lesson = _first_lesson(fixture)
    grid_days = {slot.day_of_week for slot in fixture.snapshot.grid_slots}
    day = lesson.period.school_date
    for _ in range(7):
        if day.weekday() not in grid_days:
            break
        day = date.fromordinal(day.toordinal() + 1)
    else:
        raise ValueError("Every weekday is a grid day; the lesson cannot leave the calendar.")
    moved = replace(
        lesson,
        period=normalize_period(
            day, lesson.period.start_local, lesson.period.end_local, lesson.period.timezone_name
        ),
    )
    return fixture.snapshot, CandidateSchedule((moved, *fixture.witness.lessons[1:]))


def _mutate_teacher_unavailable(fixture: Fixture):
    lesson = _first_lesson(fixture)
    assignment = fixture.snapshot.assignment_for(lesson.assignment_id)
    assert assignment is not None
    teacher = lesson.teacher_id if lesson.teacher_id is not None else assignment.teacher_id
    added = Unavailability(UnavailableResource.TEACHER, teacher, lesson.period)
    snapshot = replace(fixture.snapshot, unavailable=(*fixture.snapshot.unavailable, added))
    return snapshot, fixture.witness


def _mutate_resource_conflict(fixture: Fixture):
    assert fixture.witness is not None
    first = _first_lesson(fixture)
    if len(fixture.witness.lessons) < 2:
        raise ValueError("A resource conflict needs two lessons.")
    second = fixture.witness.lessons[1]
    moved = replace(second, period=first.period, room_id=first.room_id)
    return fixture.snapshot, CandidateSchedule((first, moved, *fixture.witness.lessons[2:]))


def _mutate_protected_lesson(fixture: Fixture):
    assert fixture.witness is not None
    published = fixture.witness.lessons
    first = _first_lesson(fixture)
    other_room = next(
        room_id
        for room_id in sorted(
            fixture.snapshot.assignment_for(first.assignment_id).eligible_room_ids
        )
        if room_id != first.room_id
    )
    moved = replace(first, room_id=other_room)
    snapshot = replace(fixture.snapshot, protected_lessons=published)
    return snapshot, CandidateSchedule((moved, *fixture.witness.lessons[1:]))


def _mutate_slice_sum(fixture: Fixture):
    assert fixture.witness is not None
    lesson = _first_lesson(fixture)
    shortened = tuple(
        replace(slice_, credit_minutes=slice_.credit_minutes - 1) for slice_ in lesson.slices
    )
    moved = replace(lesson, slices=shortened)
    return fixture.snapshot, CandidateSchedule((moved, *fixture.witness.lessons[1:]))


def _mutate_module_gap(fixture: Fixture):
    assert fixture.witness is not None
    lesson = _first_lesson(fixture)
    shifted = tuple(
        replace(slice_, offset_minutes=slice_.offset_minutes + 1) for slice_ in lesson.slices
    )
    moved = replace(lesson, slices=shifted)
    return fixture.snapshot, CandidateSchedule((moved, *fixture.witness.lessons[1:]))


def _mutate_module_order(fixture: Fixture):
    assert fixture.witness is not None
    if len(fixture.witness.lessons) < 2:
        raise ValueError("A module-order mutation needs two lessons.")
    first, second = fixture.witness.lessons[0], fixture.witness.lessons[1]
    swapped_first = replace(first, slices=second.slices)
    swapped_second = replace(second, slices=first.slices)
    return fixture.snapshot, CandidateSchedule((swapped_first, swapped_second))


def _mutate_partial_credit(fixture: Fixture):
    assert fixture.witness is not None
    if len(fixture.witness.lessons) < 2:
        raise ValueError("A partial-credit mutation needs two lessons.")
    first = fixture.witness.lessons[0]
    half = first.period.duration_minutes // 2
    partial = replace(
        first,
        credit_minutes=half,
        slices=(replace(first.slices[0], credit_minutes=half),),
    )
    return fixture.snapshot, CandidateSchedule((partial, *fixture.witness.lessons[1:]))


def _mutate_reservation_version(fixture: Fixture):
    lesson = _first_lesson(fixture)
    snapshot = replace(
        fixture.snapshot,
        active_version_id=5,
        reservations=(RecoveryAllocation(6, lesson.lesson_id, 31, lesson.credit_minutes),),
        open_debt_minutes={31: lesson.credit_minutes},
        claim_assignments={31: lesson.assignment_id},
    )
    return snapshot, fixture.witness


def _mutate_debt_overflow(fixture: Fixture):
    lesson = _first_lesson(fixture)
    snapshot = replace(
        fixture.snapshot,
        active_version_id=9,
        reservations=(
            RecoveryAllocation(9, lesson.lesson_id, 77, max(1, lesson.credit_minutes // 2)),
        ),
        open_debt_minutes={77: 1},
        claim_assignments={77: lesson.assignment_id},
    )
    return snapshot, fixture.witness


MUTATIONS = {
    "DROP_LESSON": _mutate_drop_lesson,
    "DUPLICATE_IDENTITY": _mutate_duplicate_identity,
    "INELIGIBLE_ROOM": _mutate_ineligible_room,
    "OUT_OF_CALENDAR": _mutate_out_of_calendar,
    "RESOURCE_UNAVAILABLE": _mutate_teacher_unavailable,
    "RESOURCE_CONFLICT": _mutate_resource_conflict,
    "PROTECTED_LESSON_CHANGED": _mutate_protected_lesson,
    "SLICE_MISMATCH": _mutate_slice_sum,
    "MODULE_MISMATCH": _mutate_module_gap,
    "MODULE_ORDER": _mutate_module_order,
    "PARTIAL_CREDIT_VIOLATION": _mutate_partial_credit,
    "RESERVATION_VERSION_MISMATCH": _mutate_reservation_version,
    "DEBT_OVERFLOW": _mutate_debt_overflow,
}

MUTATION_EXPECTED_VIOLATIONS = {
    "DROP_LESSON": ("COVERAGE_MISMATCH",),
    "DUPLICATE_IDENTITY": ("DUPLICATE_IDENTITY",),
    "INELIGIBLE_ROOM": ("INELIGIBLE_ROOM",),
    "OUT_OF_CALENDAR": ("NOT_IN_GRID",),
    "RESOURCE_UNAVAILABLE": ("RESOURCE_UNAVAILABLE",),
    "RESOURCE_CONFLICT": ("RESOURCE_CONFLICT",),
    "PROTECTED_LESSON_CHANGED": ("PROTECTED_LESSON_CHANGED",),
    "SLICE_MISMATCH": ("SLICE_MISMATCH",),
    "MODULE_MISMATCH": ("MODULE_MISMATCH",),
    "MODULE_ORDER": ("MODULE_MISMATCH",),
    "PARTIAL_CREDIT_VIOLATION": ("PARTIAL_CREDIT_VIOLATION",),
    "RESERVATION_VERSION_MISMATCH": ("RESERVATION_VERSION_MISMATCH",),
    "DEBT_OVERFLOW": ("DEBT_OVERFLOW",),
}


def expected_violations_for(mutation: str) -> tuple[str, ...]:
    if mutation not in MUTATION_EXPECTED_VIOLATIONS:
        raise ValueError(f"Unknown mutation: {mutation}")
    return MUTATION_EXPECTED_VIOLATIONS[mutation]


def mutate(fixture: Fixture, mutation: str) -> Fixture:
    """Return a traceable variant that preserves the parent case identity."""
    if mutation not in MUTATIONS:
        raise ValueError(f"Unknown mutation: {mutation}")
    snapshot, witness = MUTATIONS[mutation](fixture)
    return Fixture(
        case_id=f"{fixture.case_id}~{mutation.lower()}",
        family=fixture.family,
        version=fixture.version,
        expectation=CaseExpectation.INVALID_INPUT,
        snapshot=snapshot,
        periods=fixture.periods,
        witness=witness,
        parent_case_id=fixture.case_id,
        mutation=mutation,
        fixture_seed=fixture.fixture_seed,
        event_seed=fixture.event_seed,
        solver_seed=fixture.solver_seed,
    )
