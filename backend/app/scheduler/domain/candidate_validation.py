"""Independent verification of a materialized v1 candidate schedule.

The validator never consults solver variables or model construction. It only
recomputes coverage, references, resources, dates, editable window, stability,
modular chronology, debt reservations and basic metrics from the snapshot and
the candidate.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
    UnavailableResource,
)

VALIDATOR_VERSION = "v3"


class ValidationViolationCode(StrEnum):
    DUPLICATE_IDENTITY = "DUPLICATE_IDENTITY"
    UNKNOWN_ASSIGNMENT = "UNKNOWN_ASSIGNMENT"
    ASSIGNMENT_RESOURCE_MISMATCH = "ASSIGNMENT_RESOURCE_MISMATCH"
    INELIGIBLE_ROOM = "INELIGIBLE_ROOM"
    OUT_OF_CALENDAR = "OUT_OF_CALENDAR"
    NOT_IN_GRID = "NOT_IN_GRID"
    EDITABLE_WINDOW_VIOLATION = "EDITABLE_WINDOW_VIOLATION"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    COVERAGE_MISMATCH = "COVERAGE_MISMATCH"
    MODULE_MISMATCH = "MODULE_MISMATCH"
    PARTIAL_CREDIT_VIOLATION = "PARTIAL_CREDIT_VIOLATION"
    SLICE_MISMATCH = "SLICE_MISMATCH"
    PROTECTED_LESSON_CHANGED = "PROTECTED_LESSON_CHANGED"
    RESERVATION_UNKNOWN_LESSON = "RESERVATION_UNKNOWN_LESSON"
    RESERVATION_OVERFLOW = "RESERVATION_OVERFLOW"
    RESERVATION_VERSION_MISMATCH = "RESERVATION_VERSION_MISMATCH"
    RESERVATION_ASSIGNMENT_MISMATCH = "RESERVATION_ASSIGNMENT_MISMATCH"
    RESERVATION_DUPLICATE = "RESERVATION_DUPLICATE"
    DEBT_OVERFLOW = "DEBT_OVERFLOW"


@dataclass(frozen=True)
class ValidationViolation:
    code: ValidationViolationCode
    message: str
    assignment_id: int | None = None
    lesson_id: int | None = None
    resource_type: str | None = None
    resource_id: int | None = None


@dataclass(frozen=True)
class ValidationReport:
    validator_version: str
    violations: tuple[ValidationViolation, ...]
    credited_minutes: Mapping[int, int]
    completion_dates: Mapping[int, date] = field(default_factory=dict)
    total_credit_minutes: int = 0

    @property
    def valid(self) -> bool:
        return not self.violations


def _ordered_lessons(lessons: Sequence[ScheduledLesson]) -> list[ScheduledLesson]:
    return sorted(
        lessons,
        key=lambda lesson: (lesson.period.school_date, lesson.period.start_local, lesson.lesson_id),
    )


def _teacher_for(lesson: ScheduledLesson, assignment: Assignment) -> int:
    return lesson.teacher_id if lesson.teacher_id is not None else assignment.teacher_id


def _physically_protected(snapshot: PlanningSnapshot, lesson: ScheduledLesson) -> bool:
    if lesson.period.school_date in snapshot.protected_dates:
        return True
    return snapshot.now_utc is not None and lesson.period.start_utc <= snapshot.now_utc


def _executed_or_fail(
    snapshot: PlanningSnapshot,
    assignment: Assignment,
    violations: list[ValidationViolation],
) -> dict[int, int] | None:
    executed = dict(snapshot.executed_for(assignment.assignment_id))
    known = {module.module_id for module in assignment.modules}
    if set(executed) - known:
        violations.append(
            ValidationViolation(
                ValidationViolationCode.COVERAGE_MISMATCH,
                "Executed progress references an unknown module.",
                assignment_id=assignment.assignment_id,
            )
        )
        return None
    for module in assignment.modules:
        minutes = executed.get(module.module_id, 0)
        if type(minutes) is not int or minutes < 0 or minutes > module.required_minutes:
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.COVERAGE_MISMATCH,
                    "Executed minutes are outside the module requirement.",
                    assignment_id=assignment.assignment_id,
                )
            )
            return None
    return executed


def _check_slices(
    assignment: Assignment,
    lesson: ScheduledLesson,
    violations: list[ValidationViolation],
) -> None:
    modules = {module.module_id: module for module in assignment.modules}
    if any(slice_.lesson_id != lesson.lesson_id for slice_ in lesson.slices):
        violations.append(
            ValidationViolation(
                ValidationViolationCode.SLICE_MISMATCH,
                "A modular slice references another lesson.",
                assignment_id=assignment.assignment_id,
                lesson_id=lesson.lesson_id,
            )
        )
    module_ids = [slice_.module_id for slice_ in lesson.slices]
    if len(set(module_ids)) != len(module_ids):
        violations.append(
            ValidationViolation(
                ValidationViolationCode.SLICE_MISMATCH,
                "A lesson cannot hold two slices of the same module.",
                assignment_id=assignment.assignment_id,
                lesson_id=lesson.lesson_id,
            )
        )
    for slice_ in lesson.slices:
        module = modules.get(slice_.module_id)
        if (
            module is None
            or slice_.offset_minutes + slice_.credit_minutes > module.required_minutes
        ):
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.SLICE_MISMATCH,
                    "A modular slice leaves its assignment module.",
                    assignment_id=assignment.assignment_id,
                    lesson_id=lesson.lesson_id,
                )
            )
    if sum(slice_.credit_minutes for slice_ in lesson.slices) != lesson.credit_minutes:
        violations.append(
            ValidationViolation(
                ValidationViolationCode.SLICE_MISMATCH,
                "Lesson slices do not sum to the lesson curricular credit.",
                assignment_id=assignment.assignment_id,
                lesson_id=lesson.lesson_id,
            )
        )


def _check_curriculum(
    snapshot: PlanningSnapshot,
    assignment: Assignment,
    lessons: Sequence[ScheduledLesson],
    violations: list[ValidationViolation],
) -> None:
    modules = sorted(assignment.modules, key=lambda module: module.sequence)
    executed = _executed_or_fail(snapshot, assignment, violations)
    if executed is None:
        return
    cursor = {module.module_id: executed.get(module.module_id, 0) for module in modules}
    required = {module.module_id: module.required_minutes for module in modules}
    if any(cursor[module_id] > required[module_id] for module_id in required):
        violations.append(
            ValidationViolation(
                ValidationViolationCode.COVERAGE_MISMATCH,
                "Executed minutes exceed the module requirement.",
                assignment_id=assignment.assignment_id,
            )
        )
        return
    frontier = 0
    sequence = {module.module_id: module.sequence for module in modules}

    def advance() -> None:
        nonlocal frontier
        while (
            frontier < len(modules)
            and cursor[modules[frontier].module_id] == required[modules[frontier].module_id]
        ):
            frontier += 1

    advance()
    for lesson in _ordered_lessons(lessons):
        for slice_ in sorted(
            lesson.slices,
            key=lambda row: (sequence.get(row.module_id, 1 << 30), row.offset_minutes),
        ):
            if frontier >= len(modules):
                violations.append(
                    ValidationViolation(
                        ValidationViolationCode.MODULE_MISMATCH,
                        "The candidate credits more curriculum than the assignment requires.",
                        assignment_id=assignment.assignment_id,
                        lesson_id=lesson.lesson_id,
                    )
                )
                break
            module = modules[frontier]
            if (
                slice_.module_id != module.module_id
                or slice_.offset_minutes != cursor[module.module_id]
            ):
                violations.append(
                    ValidationViolation(
                        ValidationViolationCode.MODULE_MISMATCH,
                        "Curricular slices do not follow module chronology.",
                        assignment_id=assignment.assignment_id,
                        lesson_id=lesson.lesson_id,
                    )
                )
                continue
            cursor[module.module_id] += slice_.credit_minutes
            if cursor[module.module_id] > required[module.module_id]:
                violations.append(
                    ValidationViolation(
                        ValidationViolationCode.MODULE_MISMATCH,
                        "Curricular slices exceed the module requirement.",
                        assignment_id=assignment.assignment_id,
                        lesson_id=lesson.lesson_id,
                    )
                )
                return
            advance()
    for module in modules:
        if cursor[module.module_id] != module.required_minutes:
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.MODULE_MISMATCH,
                    "Curricular slices do not cover the module requirement.",
                    assignment_id=assignment.assignment_id,
                )
            )
            return


def _check_partial_credit(
    lessons: Sequence[ScheduledLesson],
    protected_ids: frozenset[int],
    violations: list[ValidationViolation],
) -> None:
    editable = [
        lesson for lesson in _ordered_lessons(lessons) if lesson.lesson_id not in protected_ids
    ]
    for lesson in editable[:-1]:
        if lesson.credit_minutes != lesson.period.duration_minutes:
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.PARTIAL_CREDIT_VIOLATION,
                    "Only the last editable lesson of an assignment may be partial.",
                    assignment_id=lesson.assignment_id,
                    lesson_id=lesson.lesson_id,
                )
            )


def _physical_key(lesson: ScheduledLesson) -> tuple:
    return (
        lesson.assignment_id,
        lesson.period.school_date,
        lesson.period.start_local,
        lesson.period.end_local,
        lesson.period.timezone_name,
        lesson.room_id,
        lesson.credit_minutes,
        lesson.source_lesson_id,
        lesson.teacher_id,
        lesson.class_id,
    )


def _check_reservations(
    snapshot: PlanningSnapshot,
    lessons: Mapping[int, ScheduledLesson],
    violations: list[ValidationViolation],
) -> None:
    reserved_lesson: dict[int, int] = defaultdict(int)
    reserved_claim: dict[int, int] = defaultdict(int)
    seen: set[tuple[int, int]] = set()
    for allocation in snapshot.reservations:
        lesson = lessons.get(allocation.lesson_id)
        if lesson is None:
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.RESERVATION_UNKNOWN_LESSON,
                    "A recovery reservation references an unknown lesson.",
                    lesson_id=allocation.lesson_id,
                )
            )
            continue
        if (
            snapshot.active_version_id is None
            or allocation.version_id != snapshot.active_version_id
        ):
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.RESERVATION_VERSION_MISMATCH,
                    "A recovery reservation belongs to another version.",
                    lesson_id=allocation.lesson_id,
                )
            )
        key = (allocation.lesson_id, allocation.claim_id)
        if key in seen:
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.RESERVATION_DUPLICATE,
                    "A recovery reservation is duplicated for its lesson and claim.",
                    lesson_id=allocation.lesson_id,
                )
            )
            continue
        seen.add(key)
        if snapshot.claim_assignments.get(allocation.claim_id) != lesson.assignment_id:
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.RESERVATION_ASSIGNMENT_MISMATCH,
                    "A recovery reservation does not belong to the lesson assignment.",
                    lesson_id=allocation.lesson_id,
                )
            )
        reserved_lesson[allocation.lesson_id] += allocation.minutes
        reserved_claim[allocation.claim_id] += allocation.minutes
    for lesson_id, minutes in sorted(reserved_lesson.items()):
        if minutes > lessons[lesson_id].credit_minutes:
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.RESERVATION_OVERFLOW,
                    "Recovery reservations exceed the lesson curricular credit.",
                    lesson_id=lesson_id,
                )
            )
    for claim_id, minutes in sorted(reserved_claim.items()):
        if minutes > snapshot.open_debt_minutes.get(claim_id, 0):
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.DEBT_OVERFLOW,
                    "Recovery reservations exceed the open debt for their claim.",
                    lesson_id=None,
                )
            )


def lesson_violations(
    snapshot: PlanningSnapshot,
    lesson: ScheduledLesson,
    *,
    assignments: Mapping[int, Assignment] | None = None,
    protected_ids: frozenset[int] = frozenset(),
) -> tuple[ValidationViolation, ...]:
    """Per-lesson facts shared by candidate validation and baseline assessment.

    Coverage, chronology and partial-credit rules stay in :func:`validate_candidate`:
    a published baseline may be stale and is assessed without demanding completeness.
    """
    if assignments is None:
        assignments = {row.assignment_id: row for row in snapshot.assignments}
    violations: list[ValidationViolation] = []
    assignment = assignments.get(lesson.assignment_id)
    if assignment is None:
        violations.append(
            ValidationViolation(
                ValidationViolationCode.UNKNOWN_ASSIGNMENT,
                "A lesson references an assignment outside the snapshot.",
                lesson_id=lesson.lesson_id,
                assignment_id=lesson.assignment_id,
            )
        )
        return tuple(violations)
    if lesson.lesson_id not in protected_ids and (
        lesson.teacher_id not in (None, assignment.teacher_id)
        or lesson.class_id not in (None, assignment.class_id)
    ):
        violations.append(
            ValidationViolation(
                ValidationViolationCode.ASSIGNMENT_RESOURCE_MISMATCH,
                "A new lesson changes the assigned teacher or class.",
                assignment_id=assignment.assignment_id,
                lesson_id=lesson.lesson_id,
            )
        )
    if lesson.room_id not in assignment.eligible_room_ids:
        violations.append(
            ValidationViolation(
                ValidationViolationCode.INELIGIBLE_ROOM,
                "The lesson uses a room that is not eligible for its assignment.",
                assignment_id=assignment.assignment_id,
                lesson_id=lesson.lesson_id,
                resource_type="room",
                resource_id=lesson.room_id,
            )
        )
    limit = (
        snapshot.preferred_end_date
        if snapshot.strategy is SchedulingStrategy.COMPLETE_GENERATION
        else snapshot.hard_end_date
    )
    if (
        lesson.period.timezone_name != snapshot.timezone_name
        or lesson.period.school_date < snapshot.origin
        or lesson.period.school_date > limit
        or lesson.period.school_date in snapshot.blocked_dates
    ):
        violations.append(
            ValidationViolation(
                ValidationViolationCode.OUT_OF_CALENDAR,
                "The lesson is outside the strategy calendar and date limits.",
                assignment_id=assignment.assignment_id,
                lesson_id=lesson.lesson_id,
            )
        )
    if not any(slot.matches(lesson.period) for slot in snapshot.grid_slots):
        violations.append(
            ValidationViolation(
                ValidationViolationCode.NOT_IN_GRID,
                "The lesson period does not match any configured grid slot.",
                assignment_id=assignment.assignment_id,
                lesson_id=lesson.lesson_id,
            )
        )
    if lesson.lesson_id not in protected_ids and _physically_protected(snapshot, lesson):
        violations.append(
            ValidationViolation(
                ValidationViolationCode.EDITABLE_WINDOW_VIOLATION,
                "A new lesson falls inside the protected editable window.",
                assignment_id=assignment.assignment_id,
                lesson_id=lesson.lesson_id,
            )
        )
    resources = (
        (UnavailableResource.CLASS, assignment.class_id),
        (UnavailableResource.TEACHER, _teacher_for(lesson, assignment)),
        (UnavailableResource.ROOM, lesson.room_id),
    )
    reported: set[tuple[str, int]] = set()
    for resource_type, resource_id in resources:
        if (resource_type.value, resource_id) in reported:
            continue
        if any(
            row.overlaps(lesson.period)
            for row in snapshot.hard_unavailable_on(
                resource_type, resource_id, lesson.period.school_date
            )
        ):
            reported.add((resource_type.value, resource_id))
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.RESOURCE_UNAVAILABLE,
                    "The lesson overlaps a declared resource unavailability.",
                    assignment_id=assignment.assignment_id,
                    lesson_id=lesson.lesson_id,
                    resource_type=resource_type.value,
                    resource_id=resource_id,
                )
            )
    _check_slices(assignment, lesson, violations)
    return tuple(violations)


def validate_candidate(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
) -> ValidationReport:
    """Recompute every invariant from the snapshot and the materialized lessons."""
    if type(snapshot) is not PlanningSnapshot or type(candidate) is not CandidateSchedule:
        raise ValueError("Validation needs a snapshot and a candidate schedule.")
    violations: list[ValidationViolation] = []
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    protected_ids = frozenset(lesson.lesson_id for lesson in snapshot.protected_lessons)

    lesson_by_id: dict[int, ScheduledLesson] = {}
    source_ids: set[int] = set()
    for lesson in candidate.lessons:
        if lesson.lesson_id in lesson_by_id:
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.DUPLICATE_IDENTITY,
                    "Lesson identities must be unique inside a candidate.",
                    lesson_id=lesson.lesson_id,
                )
            )
            continue
        lesson_by_id[lesson.lesson_id] = lesson
        if lesson.source_lesson_id is not None:
            if lesson.source_lesson_id in source_ids:
                violations.append(
                    ValidationViolation(
                        ValidationViolationCode.DUPLICATE_IDENTITY,
                        "Two lessons claim the same published identity.",
                        lesson_id=lesson.lesson_id,
                    )
                )
            source_ids.add(lesson.source_lesson_id)

    accountable: dict[int, list[ScheduledLesson]] = defaultdict(list)
    for lesson in candidate.lessons:
        assignment = assignments.get(lesson.assignment_id)
        if assignment is None:
            violations.extend(lesson_violations(snapshot, lesson, assignments=assignments))
            continue
        accountable[assignment.assignment_id].append(lesson)
        violations.extend(
            lesson_violations(
                snapshot, lesson, assignments=assignments, protected_ids=protected_ids
            )
        )

    for assignment in snapshot.assignments:
        lessons = accountable.get(assignment.assignment_id, [])
        _check_curriculum(snapshot, assignment, lessons, violations)
        _check_partial_credit(lessons, protected_ids, violations)
        residual = sum(
            module.required_minutes
            - snapshot.executed_for(assignment.assignment_id).get(module.module_id, 0)
            for module in assignment.modules
        )
        credited = sum(lesson.credit_minutes for lesson in lessons)
        if credited != residual:
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.COVERAGE_MISMATCH,
                    "Candidate credit does not equal the assignment residual demand.",
                    assignment_id=assignment.assignment_id,
                )
            )

    resource_intervals: dict[tuple[str, int, date], list] = defaultdict(list)
    for assignment_id, lessons in accountable.items():
        assignment = assignments[assignment_id]
        for lesson in lessons:
            for kind, resource_id in (
                ("class", assignment.class_id),
                ("teacher", _teacher_for(lesson, assignment)),
                ("room", lesson.room_id),
            ):
                resource_intervals[(kind, resource_id, lesson.period.school_date)].append(
                    (lesson.period.start_utc, lesson.period.end_utc)
                )
    for (kind, resource_id, _), rows in sorted(
        resource_intervals.items(), key=lambda item: str(item[0])
    ):
        previous_end = None
        for start, end in sorted(rows):
            if previous_end is not None and start < previous_end:
                violations.append(
                    ValidationViolation(
                        ValidationViolationCode.RESOURCE_CONFLICT,
                        "Two lessons overlap for the same resource.",
                        resource_type=kind,
                        resource_id=resource_id,
                    )
                )
            previous_end = end if previous_end is None else max(previous_end, end)

    protected_by_id = {lesson.lesson_id: lesson for lesson in snapshot.protected_lessons}
    for lesson_id, protected in sorted(protected_by_id.items()):
        found = lesson_by_id.get(lesson_id)
        if found is None or _physical_key(found) != _physical_key(protected):
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.PROTECTED_LESSON_CHANGED,
                    "A protected published lesson changed its physical identity.",
                    lesson_id=lesson_id,
                )
            )

    _check_reservations(snapshot, lesson_by_id, violations)

    credited_minutes = {
        assignment.assignment_id: sum(
            lesson.credit_minutes for lesson in accountable.get(assignment.assignment_id, [])
        )
        for assignment in snapshot.assignments
    }
    completion_dates: dict[int, date] = {}
    for assignment_id, lessons in accountable.items():
        class_id = assignments[assignment_id].class_id
        for lesson in lessons:
            previous = completion_dates.get(class_id)
            if previous is None or lesson.period.school_date > previous:
                completion_dates[class_id] = lesson.period.school_date
    return ValidationReport(
        validator_version=VALIDATOR_VERSION,
        violations=tuple(violations),
        credited_minutes=credited_minutes,
        completion_dates=completion_dates,
        total_credit_minutes=sum(credited_minutes.values()),
    )
