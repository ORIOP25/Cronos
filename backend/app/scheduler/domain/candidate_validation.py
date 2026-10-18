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
    continuous_break_minutes,
)
from app.scheduler.domain.teacher_presence import PresenceLesson, teacher_day_complies

VALIDATOR_VERSION = "v8"


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
    LUNCH_BREAK_VIOLATION = "LUNCH_BREAK_VIOLATION"
    TEACHER_PRESENCE_VIOLATION = "TEACHER_PRESENCE_VIOLATION"
    PRECEDENCE_VIOLATION = "PRECEDENCE_VIOLATION"


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


def _has_started(snapshot: PlanningSnapshot, lesson: ScheduledLesson) -> bool:
    return snapshot.now_utc is not None and lesson.period.start_utc <= snapshot.now_utc


def _physically_protected(snapshot: PlanningSnapshot, lesson: ScheduledLesson) -> bool:
    return lesson.period.school_date in snapshot.protected_dates or _has_started(snapshot, lesson)


def _hard_availability_applies(
    snapshot: PlanningSnapshot, lesson: ScheduledLesson, protected_ids: frozenset[int]
) -> bool:
    """Availability declared after a protected lesson started never applies to it."""
    return lesson.lesson_id not in protected_ids or not _has_started(snapshot, lesson)


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
        lesson.class_ids,
    )


def _local_minutes(value) -> int:
    return value.hour * 60 + value.minute


def _check_lunch(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
    violations: list[ValidationViolation],
) -> None:
    """Reject any class or teacher without a continuous break inside the window.

    A teacher whose presence rule dispenses the lunch break is exempt; classes
    always keep the school lunch rule (D06).
    """
    rule = snapshot.lunch_rule
    if rule is None:
        return
    dispensed = {row.teacher_id for row in snapshot.teacher_presence if not row.lunch_required}
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    occupied: dict[tuple[str, int, date], list[tuple[int, int]]] = defaultdict(list)
    for lesson in candidate.lessons:
        assignment = assignments.get(lesson.assignment_id)
        if assignment is None:
            continue
        teacher_id = lesson.teacher_id if lesson.teacher_id is not None else assignment.teacher_id
        interval = (
            _local_minutes(lesson.period.start_local),
            _local_minutes(lesson.period.end_local),
        )
        for class_id in assignment.class_ids:
            occupied[("class", class_id, lesson.period.school_date)].append(interval)
        occupied[("teacher", teacher_id, lesson.period.school_date)].append(interval)
    for (resource_type, resource_id, _), intervals in sorted(occupied.items()):
        if resource_type == "teacher" and resource_id in dispensed:
            continue
        if continuous_break_minutes(intervals, rule) < rule.minimum_minutes:
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.LUNCH_BREAK_VIOLATION,
                    "A resource has no continuous lunch break inside the window.",
                    resource_type=resource_type,
                    resource_id=resource_id,
                )
            )


def _check_teacher_presence(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
    protected_ids: frozenset[int],
    violations: list[ValidationViolation],
) -> None:
    """Reject a teacher day that no free lunch choice splits into compliant presences.

    A presence with only protected lessons is exempt; a presence with at least one
    editable lesson counts every lesson, protected included (T04).
    """
    if not snapshot.teacher_presence:
        return
    rules = {row.teacher_id: row for row in snapshot.teacher_presence}
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    by_teacher_day: dict[tuple[int, date], list[PresenceLesson]] = defaultdict(list)
    for lesson in candidate.lessons:
        assignment = assignments.get(lesson.assignment_id)
        if assignment is None:
            continue
        teacher_id = _teacher_for(lesson, assignment)
        if teacher_id not in rules:
            continue
        by_teacher_day[(teacher_id, lesson.period.school_date)].append(
            PresenceLesson(
                start_minute=_local_minutes(lesson.period.start_local),
                end_minute=_local_minutes(lesson.period.end_local),
                protected=lesson.lesson_id in protected_ids,
            )
        )
    slots_by_weekday: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for slot in snapshot.grid_slots:
        slots_by_weekday[slot.day_of_week].append(
            (_local_minutes(slot.start_local), _local_minutes(slot.end_local))
        )
    for (teacher_id, school_date), lessons in sorted(
        by_teacher_day.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        rule = rules[teacher_id]
        if not teacher_day_complies(
            lessons,
            rule,
            lunch_rule=snapshot.lunch_rule,
            grid_slots=slots_by_weekday.get(school_date.weekday(), ()),
        ):
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.TEACHER_PRESENCE_VIOLATION,
                    "A teacher presence breaks the school minimum or maximum gap.",
                    resource_type="teacher",
                    resource_id=teacher_id,
                )
            )


def _check_reservations(
    snapshot: PlanningSnapshot,
    lessons: Mapping[int, ScheduledLesson],
    violations: list[ValidationViolation],
) -> None:
    owners = {row.assignment_id: row for row in snapshot.assignments}
    reserved_lesson: dict[tuple[int, int | None], int] = defaultdict(int)
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
        owner = owners.get(lesson.assignment_id)
        claim_class = snapshot.claim_classes.get(allocation.claim_id)
        member_classes = (
            lesson.class_ids
            if lesson.class_ids is not None
            else (owner.class_ids if owner is not None else ())
        )
        if claim_class is None and member_classes:
            claim_class = member_classes[0]
        if snapshot.claim_assignments.get(allocation.claim_id) != lesson.assignment_id or (
            claim_class is not None and claim_class not in member_classes
        ):
            violations.append(
                ValidationViolation(
                    ValidationViolationCode.RESERVATION_ASSIGNMENT_MISMATCH,
                    "A recovery reservation does not belong to the lesson unit and class.",
                    lesson_id=allocation.lesson_id,
                )
            )
        reserved_lesson[(allocation.lesson_id, claim_class)] += allocation.minutes
        reserved_claim[allocation.claim_id] += allocation.minutes
    for (lesson_id, _), minutes in sorted(reserved_lesson.items(), key=lambda item: str(item[0])):
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
        or (lesson.class_ids is not None and lesson.class_ids != assignment.class_ids)
    ):
        violations.append(
            ValidationViolation(
                ValidationViolationCode.ASSIGNMENT_RESOURCE_MISMATCH,
                "A new lesson changes the assigned teacher or classes.",
                assignment_id=assignment.assignment_id,
                lesson_id=lesson.lesson_id,
            )
        )
    if lesson.lesson_id not in protected_ids and lesson.room_id not in assignment.eligible_room_ids:
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
        or any(
            snapshot.blocked_on(class_id, lesson.period.school_date)
            for class_id in assignment.class_ids
        )
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
    resources = [(UnavailableResource.TEACHER, _teacher_for(lesson, assignment))]
    resources.extend((UnavailableResource.CLASS, class_id) for class_id in assignment.class_ids)
    resources.append((UnavailableResource.ROOM, lesson.room_id))
    reported: set[tuple[str, int]] = set()
    applicable = resources if _hard_availability_applies(snapshot, lesson, protected_ids) else []
    for resource_type, resource_id in applicable:
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


def _check_precedences(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
    protected_ids: frozenset[int],
    violations: list[ValidationViolation],
) -> None:
    """Every new lesson of the target starts after the last lesson of the source.

    Protected lessons of either unit are facts and are never reported: a
    published target lesson keeps its slot even when the source moved earlier.
    """
    if not snapshot.precedences:
        return
    by_assignment: dict[int, list[ScheduledLesson]] = defaultdict(list)
    for lesson in candidate.lessons:
        by_assignment[lesson.assignment_id].append(lesson)
    for source, target in snapshot.precedences:
        source_lessons = by_assignment.get(source, [])
        if not source_lessons:
            continue
        last_end = max(lesson.period.end_utc for lesson in source_lessons)
        for lesson in by_assignment.get(target, []):
            if lesson.lesson_id in protected_ids:
                continue
            if lesson.period.start_utc < last_end:
                violations.append(
                    ValidationViolation(
                        ValidationViolationCode.PRECEDENCE_VIOLATION,
                        "A new lesson starts before its predecessor unit ended.",
                        assignment_id=target,
                        lesson_id=lesson.lesson_id,
                    )
                )


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
            for class_id in assignment.class_ids:
                resource_intervals[("class", class_id, lesson.period.school_date)].append(
                    (lesson.period.start_utc, lesson.period.end_utc)
                )
            for kind, resource_id in (
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
    _check_precedences(snapshot, candidate, protected_ids, violations)
    _check_lunch(snapshot, candidate, violations)
    _check_teacher_presence(snapshot, candidate, protected_ids, violations)

    credited_minutes = {
        assignment.assignment_id: sum(
            lesson.credit_minutes for lesson in accountable.get(assignment.assignment_id, [])
        )
        for assignment in snapshot.assignments
    }
    completion_dates: dict[int, date] = {}
    for assignment_id, lessons in accountable.items():
        for class_id in assignments[assignment_id].class_ids:
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
