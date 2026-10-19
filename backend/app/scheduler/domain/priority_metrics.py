"""Pure measurements and integer cost for school schedule priorities."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, time

from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.home_rooms import avoidable_room_changes
from app.scheduler.domain.priorities import (
    CRITERION_KEYS,
    PRIORITY_MULTIPLIERS,
    UNIT_COSTS,
    PriorityWeights,
    shift_of,
)
from app.scheduler.domain.quality import _gap_minutes


def _slot_positions(snapshot: PlanningSnapshot, candidate: CandidateSchedule):
    teachers: dict[tuple[int, date], set[int]] = defaultdict(set)
    classes: dict[tuple[int, date], set[int]] = defaultdict(set)
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    slots_by_day = {
        weekday: tuple(
            sorted(
                (slot for slot in snapshot.grid_slots if slot.day_of_week == weekday),
                key=lambda row: (row.start_local, row.end_local),
            )
        )
        for weekday in range(7)
    }
    for lesson in candidate.lessons:
        assignment = assignments.get(lesson.assignment_id)
        if assignment is None:
            raise ValueError("The candidate references an assignment outside the snapshot.")
        slots = slots_by_day[lesson.period.school_date.weekday()]
        position = next(
            (index for index, slot in enumerate(slots) if slot.matches(lesson.period)), None
        )
        if position is None:
            continue
        teacher_id = lesson.teacher_id or assignment.teacher_id
        teachers[(teacher_id, lesson.period.school_date)].add(position)
        for class_id in assignment.class_ids:
            classes[(class_id, lesson.period.school_date)].add(position)
    return teachers, classes


def _preference_minutes(
    snapshot: PlanningSnapshot,
    assignment: Assignment,
    lesson: ScheduledLesson,
) -> tuple[int, int]:
    teacher_id = lesson.teacher_id or assignment.teacher_id
    teacher_minutes = _overlap_minutes(
        lesson,
        snapshot.soft_unavailable_on(
            UnavailableResource.TEACHER, teacher_id, lesson.period.school_date
        ),
    )
    class_minutes = sum(
        _overlap_minutes(
            lesson,
            snapshot.soft_unavailable_on(
                UnavailableResource.CLASS, class_id, lesson.period.school_date
            ),
        )
        for class_id in assignment.class_ids
    )
    return teacher_minutes, class_minutes


def _overlap_minutes(lesson: ScheduledLesson, blocks: Sequence[Unavailability]) -> int:
    intervals = sorted(
        (
            max(lesson.period.start_utc, block.period.start_utc),
            min(lesson.period.end_utc, block.period.end_utc),
        )
        for block in blocks
        if block.overlaps(lesson.period)
    )
    total = 0
    end = None
    for start, stop in intervals:
        if end is not None and start <= end:
            end = max(end, stop)
            continue
        if end is not None:
            duration = end - first
            total += duration.days * 1440 + duration.seconds // 60
        first, end = start, stop
    if end is not None:
        duration = end - first
        total += duration.days * 1440 + duration.seconds // 60
    return total


def _single_lesson_turns(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
    assignments: Mapping[int, Assignment],
) -> tuple[int, int]:
    teacher_turns: dict[tuple[int, date, str], int] = defaultdict(int)
    class_turns: dict[tuple[int, date, str], int] = defaultdict(int)
    presence = {row.teacher_id: row for row in snapshot.teacher_presence}
    teachers_with_minimum = {
        teacher_id for teacher_id, rule in presence.items() if rule.minimum_minutes is not None
    }
    for lesson in candidate.lessons:
        assignment = assignments[lesson.assignment_id]
        teacher_id = lesson.teacher_id or assignment.teacher_id
        rule = presence.get(teacher_id)
        if teacher_id not in teachers_with_minimum:
            teacher_turns[(
                teacher_id,
                lesson.period.school_date,
                shift_of(
                    lesson.period.start_local,
                    snapshot.lunch_rule,
                    lunch_required=rule.lunch_required if rule is not None else True,
                ),
            )] += 1
        for class_id in assignment.class_ids:
            class_turns[(
                class_id,
                lesson.period.school_date,
                shift_of(lesson.period.start_local, snapshot.lunch_rule),
            )] += 1
    return (
        sum(count == 1 for count in teacher_turns.values()),
        sum(count == 1 for count in class_turns.values()),
    )


def _weekly_stability(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
    assignments: Mapping[int, Assignment],
) -> int:
    days: dict[tuple[int, int], set[date]] = defaultdict(set)
    subjects: dict[tuple[int, int, time, date], int] = {}
    starts: dict[tuple[int, int], set[time]] = defaultdict(set)
    for lesson in candidate.lessons:
        assignment = assignments[lesson.assignment_id]
        weekday = lesson.period.school_date.weekday()
        for class_id in assignment.class_ids:
            if snapshot.blocked_on(class_id, lesson.period.school_date):
                continue
            group = (class_id, weekday)
            days[group].add(lesson.period.school_date)
            starts[group].add(lesson.period.start_local)
            subjects[(class_id, weekday, lesson.period.start_local, lesson.period.school_date)] = (
                assignment.subject_id
            )
    changes = 0
    for (class_id, weekday), teaching_days in days.items():
        starts_for_day = starts[(class_id, weekday)]
        ordered_days = sorted(teaching_days)
        for previous, current in zip(ordered_days, ordered_days[1:], strict=False):
            for start in starts_for_day:
                before = subjects.get((class_id, weekday, start, previous))
                after = subjects.get((class_id, weekday, start, current))
                if before != after and (before is not None or after is not None):
                    changes += 1
    return changes


def _subject_pace(
    candidate: CandidateSchedule, assignments: Mapping[int, Assignment]
) -> int:
    completion: dict[tuple[int, int], date] = {}
    for lesson in candidate.lessons:
        assignment = assignments[lesson.assignment_id]
        for class_id in assignment.class_ids:
            key = (class_id, assignment.subject_id)
            completion[key] = max(
                completion.get(key, lesson.period.school_date), lesson.period.school_date
            )
    by_class: dict[int, list[date]] = defaultdict(list)
    for (class_id, _subject_id), day in completion.items():
        by_class[class_id].append(day)
    return sum((max(days) - min(days)).days for days in by_class.values() if len(days) > 1)


def _changed_lesson_count(candidate: CandidateSchedule, published: CandidateSchedule) -> int:
    def signature(lesson: ScheduledLesson):
        return (
            lesson.assignment_id,
            lesson.period.start_utc,
            lesson.period.end_utc,
            lesson.room_id,
            lesson.credit_minutes,
            lesson.slices,
        )

    before = {lesson.lesson_id: signature(lesson) for lesson in published.lessons}
    after = {lesson.lesson_id: signature(lesson) for lesson in candidate.lessons}
    return sum(
        before.get(identity) != after.get(identity)
        for identity in before.keys() | after.keys()
    )


def measure_priority_metrics(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
    *,
    published: CandidateSchedule | None = None,
    changed_lessons: int | None = None,
) -> dict[str, int | date]:
    """Measure all eleven priorities in integer domain units and a completion date."""
    if type(snapshot) is not PlanningSnapshot or type(candidate) is not CandidateSchedule:
        raise ValueError("Priority measurements need a snapshot and candidate schedule.")
    if published is not None and type(published) is not CandidateSchedule:
        raise ValueError("Published priority measurements need a candidate schedule.")
    if changed_lessons is not None and (type(changed_lessons) is not int or changed_lessons < 0):
        raise ValueError("Changed lesson count must be a nonnegative integer.")
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    teacher_occupied, class_occupied = _slot_positions(snapshot, candidate)
    teacher_preferences = class_preferences = 0
    for lesson in candidate.lessons:
        assignment = assignments[lesson.assignment_id]
        teacher_minutes, class_minutes = _preference_minutes(snapshot, assignment, lesson)
        teacher_preferences += teacher_minutes
        class_preferences += class_minutes
    teacher_single, class_single = _single_lesson_turns(snapshot, candidate, assignments)
    return {
        "finish_early": max(
            (lesson.period.school_date for lesson in candidate.lessons), default=snapshot.origin
        ),
        "teacher_gaps": _gap_minutes(snapshot.grid_slots, teacher_occupied),
        "class_gaps": _gap_minutes(snapshot.grid_slots, class_occupied),
        "teacher_single_lessons": teacher_single,
        "class_single_lessons": class_single,
        "teacher_preferences": teacher_preferences,
        "class_preferences": class_preferences,
        "class_same_room": avoidable_room_changes(snapshot, candidate),
        "weekly_stability": _weekly_stability(snapshot, candidate, assignments),
        "subject_pace": _subject_pace(candidate, assignments),
        "update_stability": (
            changed_lessons
            if changed_lessons is not None
            else _changed_lesson_count(candidate, published)
            if published is not None
            else 0
        ),
    }


def priority_cost(
    metrics: Mapping[str, int | date], weights: PriorityWeights, *, origin: date
) -> int:
    """Return the T13 weighted metric cost using integer arithmetic only."""
    if set(metrics) != set(CRITERION_KEYS) or type(weights) is not PriorityWeights:
        raise ValueError("Priority cost needs exactly eleven metrics and validated weights.")
    if type(origin) is not date or type(metrics["finish_early"]) is not date:
        raise ValueError("Priority cost needs valid origin and completion dates.")
    completion_days = (metrics["finish_early"] - origin).days
    if completion_days < 0:
        raise ValueError("The completion date cannot precede the schedule origin.")
    total = 0
    for key in CRITERION_KEYS:
        measure = completion_days if key == "finish_early" else metrics[key]
        if type(measure) is not int or measure < 0:
            raise ValueError("Priority measures must be nonnegative integers.")
        total += PRIORITY_MULTIPLIERS[getattr(weights, key)] * UNIT_COSTS[key] * measure
    return total
