"""School fixtures that follow the product's real data typology.

The structure mirrors the import templates: each class carries seven subjects,
each subject is four 15-hour modules, every course has exactly three classes so
the class count is always a multiple of three, and each teacher covers two
classes for their subject. The school year starts on 14 September, prefers to
end on 15 June and may not pass 30 July, with the Christmas and Easter breaks
blocked alongside the Portuguese national holidays.

A witness is built by the independent constructor and validated by the
independent validator, so a large case stays checkable without the minimal
oracle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from app.scheduler.domain.calendar import Period, normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    PlanningSnapshot,
    SchedulingStrategy,
    TeacherPresenceRule,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.domain.teaching_units import (
    AssignmentPlan,
    JointGroupPlan,
    build_teaching_units,
)
from app.scheduler.infrastructure.constructive import construct_schedule

TIMEZONE = "Europe/Lisbon"
SUBJECT_COUNT = 7
MODULES_PER_SUBJECT = 4
MODULE_MINUTES = 15 * 60
LESSON_MINUTES = 60
SLOT_START_MINUTES = (9 * 60, 10 * 60, 11 * 60, 14 * 60, 15 * 60)
WEEK_DAYS = 5

# In the joint family the first subjects are shared by the three classes of a
# course (their first three modules are joint), while the technical subjects stay
# separate. This mirrors the product typology: general subjects together,
# technical subjects per class.
GENERAL_SUBJECT_COUNT = 4
JOINT_MODULE_COUNT = 3

SCHOOL_YEAR_START = date(2026, 9, 14)
PREFERRED_END = date(2027, 6, 15)
HARD_END = date(2027, 7, 30)

# Christmas 21 Dec - 1 Jan and Easter 12 - 23 Apr, plus national holidays.
CHRISTMAS_BREAK = (date(2026, 12, 21), date(2027, 1, 1))
EASTER_BREAK = (date(2027, 4, 12), date(2027, 4, 23))
NATIONAL_HOLIDAYS = frozenset(
    {
        date(2026, 10, 5),
        date(2026, 12, 1),
        date(2026, 12, 8),
        date(2027, 2, 16),
        date(2027, 3, 26),
        date(2027, 4, 25),
        date(2027, 5, 1),
        date(2027, 6, 10),
    }
)


@dataclass(frozen=True)
class TypologyFixture:
    class_count: int
    courses: int
    teachers: int
    rooms: int
    snapshot: PlanningSnapshot
    periods: tuple[Period, ...]
    witness: CandidateSchedule | None


def _slot_time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def _school_days(first: date, last: date) -> tuple[date, ...]:
    if first.weekday() != 0:
        raise ValueError("The school year must start on a Monday.")
    days = []
    day = first
    while day <= last:
        days.append(day)
        day = date.fromordinal(day.toordinal() + 1)
    return tuple(days)


def _blocked(day: date) -> bool:
    if day.weekday() >= WEEK_DAYS:
        return True
    if CHRISTMAS_BREAK[0] <= day <= CHRISTMAS_BREAK[1]:
        return True
    return EASTER_BREAK[0] <= day <= EASTER_BREAK[1] or day in NATIONAL_HOLIDAYS


def _periods(first: date, last: date) -> tuple[Period, ...]:
    return tuple(
        normalize_period(day, _slot_time(start), _slot_time(start + LESSON_MINUTES), TIMEZONE)
        for day in _school_days(first, last)
        if not _blocked(day)
        for start in SLOT_START_MINUTES
    )


def _assignment(class_id, subject_id, teacher_id, room_ids, assignment_id):
    modules = tuple(
        ModuleRequirement(module_id, module_id, MODULE_MINUTES)
        for module_id in range(1, MODULES_PER_SUBJECT + 1)
    )
    return Assignment(
        assignment_id=assignment_id,
        class_ids=(class_id,),
        subject_id=subject_id,
        teacher_id=teacher_id,
        eligible_room_ids=frozenset(room_ids),
        modules=modules,
    )


def build_typology_fixture(
    class_count: int,
    *,
    teacher_presence: tuple[TeacherPresenceRule, ...] = (),
    build_witness: bool = True,
) -> TypologyFixture:
    """Build a feasible school with the product typology and a witness.

    ``class_count`` must be a multiple of three because every course has three
    classes. Each assignment shares a pair of neighbouring rooms so alternative
    room sets stay part of the case. ``teacher_presence`` adds the optional
    school presence rules; the default empty tuple keeps the legacy fixture and
    its witness byte-for-byte. Pass ``build_witness=False`` when a rule instance
    has no constructive witness and the caller runs the exact search itself.
    """
    if class_count < 3 or class_count % 3 != 0:
        raise ValueError("Classes are always multiples of three (three per course).")
    rooms = class_count
    periods = _periods(SCHOOL_YEAR_START, PREFERRED_END)
    grid_slots = tuple(
        dict.fromkeys(
            GridSlot(day.weekday(), _slot_time(start), _slot_time(start + LESSON_MINUTES))
            for day in _school_days(SCHOOL_YEAR_START, PREFERRED_END)
            if not _blocked(day)
            for start in SLOT_START_MINUTES
        )
    )
    assignments = []
    for class_index in range(class_count):
        class_id = class_index + 1
        pair = class_index // 2
        eligible = (class_id, (class_index + 1) % rooms + 1)
        for subject_index in range(1, SUBJECT_COUNT + 1):
            teacher_id = subject_index * 1000 + pair + 1
            assignments.append(
                _assignment(
                    class_id,
                    subject_index,
                    teacher_id,
                    eligible,
                    class_id * 10 + subject_index,
                )
            )
    snapshot = PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=SCHOOL_YEAR_START,
        preferred_end_date=PREFERRED_END,
        hard_end_date=HARD_END,
        timezone_name=TIMEZONE,
        grid_slots=grid_slots,
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=frozenset(
            day
            for day in _school_days(SCHOOL_YEAR_START, HARD_END)
            if CHRISTMAS_BREAK[0] <= day <= CHRISTMAS_BREAK[1]
            or EASTER_BREAK[0] <= day <= EASTER_BREAK[1]
            or day in NATIONAL_HOLIDAYS
        ),
        unavailable=(),
        teacher_presence=tuple(teacher_presence),
    )
    witness = construct_schedule(snapshot, periods) if build_witness else None
    if build_witness and witness is None:
        raise ValueError("The typology fixture has no independent witness.")
    return TypologyFixture(
        class_count=class_count,
        courses=class_count // 3,
        teachers=SUBJECT_COUNT * ((class_count + 1) // 2),
        rooms=rooms,
        snapshot=snapshot,
        periods=periods,
        witness=witness,
    )


# Pilot-school profile (tech spec T13): an 8-hour grid, 9h-13h and 14h-18h.
AVAILABILITY_HOURS = (9, 10, 11, 12, 14, 15, 16, 17)
# Subjects in id order: (window end hour, minutes per week). The three full-day
# subjects come first, so they get the lowest ids in each class.
AVAILABILITY_PROFILES = (
    (18, 276),
    (18, 276),
    (18, 276),
    (13, 252),
    (13, 252),
    (12, 300),
    (11, 300),
)


def _split_modules(total_minutes: int) -> tuple[ModuleRequirement, ...]:
    base, extra = divmod(total_minutes, MODULES_PER_SUBJECT)
    return tuple(
        ModuleRequirement(
            module_id, module_id, base + (extra if module_id == MODULES_PER_SUBJECT else 0)
        )
        for module_id in range(1, MODULES_PER_SUBJECT + 1)
    )


def build_availability_typology_fixture(class_count: int) -> TypologyFixture:
    """Build the pilot-school availability case with the typology calendar.

    Each class has three full-day subjects, two morning subjects (9h-13h), one
    9h-12h subject and one 9h-11h subject. Each teacher covers one subject in two
    neighbouring classes and is Impossível outside its window. The weekly
    minutes are exact and spread over the non-blocked school days. There is no
    witness: the construction itself is the proof of feasibility.
    """
    if class_count < 3 or class_count % 3 != 0:
        raise ValueError("Classes are always multiples of three (three per course).")
    days = tuple(day for day in _school_days(SCHOOL_YEAR_START, PREFERRED_END) if not _blocked(day))
    periods = tuple(
        normalize_period(day, time(hour), time(hour + 1), TIMEZONE)
        for day in days
        for hour in AVAILABILITY_HOURS
    )
    grid_slots = tuple(
        dict.fromkeys(
            GridSlot(day.weekday(), time(hour), time(hour + 1))
            for day in days
            for hour in AVAILABILITY_HOURS
        )
    )
    assignments = []
    unavailable = []
    for class_index in range(class_count):
        class_id = class_index + 1
        pair = class_index // 2
        rooms = (class_id, (class_index + 1) % class_count + 1)
        for subject_id, (window_end, minutes_per_week) in enumerate(AVAILABILITY_PROFILES, 1):
            teacher_id = subject_id * 1000 + pair + 1
            assignments.append(
                Assignment(
                    assignment_id=class_id * 10 + subject_id,
                    class_ids=(class_id,),
                    subject_id=subject_id,
                    teacher_id=teacher_id,
                    eligible_room_ids=frozenset(rooms),
                    modules=_split_modules(round(minutes_per_week * len(days) / 5)),
                )
            )
            # The first class of each pair writes the teacher window once.
            if class_index % 2 == 0 and window_end < 18:
                unavailable.extend(
                    Unavailability(
                        UnavailableResource.TEACHER,
                        teacher_id,
                        normalize_period(day, time(window_end), time(18), TIMEZONE),
                    )
                    for day in days
                )
    snapshot = PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=SCHOOL_YEAR_START,
        preferred_end_date=PREFERRED_END,
        hard_end_date=HARD_END,
        timezone_name=TIMEZONE,
        grid_slots=grid_slots,
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=frozenset(
            day
            for day in _school_days(SCHOOL_YEAR_START, HARD_END)
            if CHRISTMAS_BREAK[0] <= day <= CHRISTMAS_BREAK[1]
            or EASTER_BREAK[0] <= day <= EASTER_BREAK[1]
            or day in NATIONAL_HOLIDAYS
        ),
        unavailable=tuple(unavailable),
    )
    return TypologyFixture(
        class_count=class_count,
        courses=class_count // 3,
        teachers=SUBJECT_COUNT * ((class_count + 1) // 2),
        rooms=class_count,
        snapshot=snapshot,
        periods=periods,
        witness=None,
    )


@dataclass(frozen=True)
class JointTypologyFixture:
    class_count: int
    courses: int
    joint_units: int
    separate_units: int
    precedences: int
    snapshot: PlanningSnapshot
    periods: tuple[Period, ...]
    witness: CandidateSchedule


def _general_teacher(course: int, subject: int) -> int:
    return 5000 + course * 10 + subject


def _technical_teacher(class_index: int, subject: int) -> int:
    return 9000 + class_index * 10 + subject


def build_joint_typology_fixture(class_count: int) -> JointTypologyFixture:
    """Build the joint family: general subjects shared, technical ones separate.

    Each course joins its three classes for the first ``JOINT_MODULE_COUNT``
    modules of the general subjects; the remaining subjects (and the general
    subjects' last module) are separate. ``build_teaching_units`` produces the
    units, the deficit units and the precedences, and the independent
    constructor builds the witness. ``class_count`` is a multiple of three.
    """
    if class_count < 3 or class_count % 3 != 0:
        raise ValueError("Classes are always multiples of three (three per course).")
    courses = class_count // 3
    rooms = class_count
    periods = _periods(SCHOOL_YEAR_START, PREFERRED_END)
    grid_slots = tuple(
        dict.fromkeys(
            GridSlot(day.weekday(), _slot_time(start), _slot_time(start + LESSON_MINUTES))
            for day in _school_days(SCHOOL_YEAR_START, PREFERRED_END)
            if not _blocked(day)
            for start in SLOT_START_MINUTES
        )
    )

    room_pairs: dict[int, tuple[int, int]] = {}
    plans: list[AssignmentPlan] = []
    for class_index in range(class_count):
        class_id = class_index + 1
        room_pairs[class_id] = (class_id, (class_index + 1) % rooms + 1)
        course = class_index // 3
        modules = tuple(
            ModuleRequirement(module_id, module_id, MODULE_MINUTES)
            for module_id in range(1, MODULES_PER_SUBJECT + 1)
        )
        for subject in range(1, SUBJECT_COUNT + 1):
            general = subject <= GENERAL_SUBJECT_COUNT
            teacher = (
                _general_teacher(course, subject)
                if general
                else _technical_teacher(class_index, subject)
            )
            plans.append(
                AssignmentPlan(
                    assignment_id=class_id * 10 + subject,
                    class_id=class_id,
                    subject_id=subject,
                    teacher_id=teacher,
                    student_count=20,
                    modules=modules,
                    executed_minutes={},
                )
            )

    groups = tuple(
        JointGroupPlan(
            group_id=course * 100 + subject,
            subject_id=subject,
            member_assignment_ids=tuple(
                class_id * 10 + subject
                for class_id in (3 * course + 1, 3 * course + 2, 3 * course + 3)
            ),
            module_ids=tuple(range(1, JOINT_MODULE_COUNT + 1)),
        )
        for course in range(courses)
        for subject in range(1, GENERAL_SUBJECT_COUNT + 1)
    )
    unit_plan = build_teaching_units(plans, groups, set())

    assignments = tuple(
        Assignment(
            assignment_id=unit.unit_id,
            class_ids=unit.class_ids,
            subject_id=unit.subject_id,
            teacher_id=unit.teacher_id,
            eligible_room_ids=frozenset(
                room for class_id in unit.class_ids for room in room_pairs[class_id]
            ),
            modules=unit.modules,
        )
        for unit in unit_plan.units
    )
    snapshot = PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=SCHOOL_YEAR_START,
        preferred_end_date=PREFERRED_END,
        hard_end_date=HARD_END,
        timezone_name=TIMEZONE,
        grid_slots=grid_slots,
        assignments=assignments,
        executed_minutes={},
        blocked_dates=frozenset(
            day
            for day in _school_days(SCHOOL_YEAR_START, HARD_END)
            if CHRISTMAS_BREAK[0] <= day <= CHRISTMAS_BREAK[1]
            or EASTER_BREAK[0] <= day <= EASTER_BREAK[1]
            or day in NATIONAL_HOLIDAYS
        ),
        unavailable=(),
        precedences=unit_plan.precedences,
    )
    witness = construct_schedule(snapshot, periods)
    if witness is None:
        raise ValueError("The joint typology fixture has no independent witness.")
    return JointTypologyFixture(
        class_count=class_count,
        courses=courses,
        joint_units=sum(1 for unit in assignments if len(unit.class_ids) > 1),
        separate_units=sum(1 for unit in assignments if len(unit.class_ids) == 1),
        precedences=len(snapshot.precedences),
        snapshot=snapshot,
        periods=periods,
        witness=witness,
    )
