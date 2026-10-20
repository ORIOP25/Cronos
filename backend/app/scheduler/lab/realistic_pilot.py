"""A realistic pilot school for schedule-priority measurements (owner brief, 20 Oct 2026).

Sixteen courses with three classes each (years 10, 11 and 12). Each class has 8 or
9 subjects of 6 or 7 modules between 16 and 22 hours, about 1 050 hours a year.
Classes of the same year in paired courses share 2 or 3 general subjects as joint
lessons. The grid has eight 60-minute lessons with 10-minute breaks and no break
between 12:30-13:30 and 13:30-14:30; lunch is 60 minutes inside 12:30-14:30.

At least 30% of the teachers are external; half of them have a presence minimum of
2 hours and half of 3 hours, with a 1-hour maximum gap. One teacher in three avoids
one afternoon a week, one in five prefers mornings only, one in eight is impossible
one day a week, and one class in four avoids Friday afternoon. Every value is
derived from indexes, so the school is the same on every run.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time
from math import ceil

from app.scheduler.domain.calendar import Period, normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    HomeRoom,
    LunchRule,
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
from app.scheduler.lab.typology import (
    HARD_END,
    PREFERRED_END,
    SCHOOL_YEAR_START,
    TIMEZONE,
    _blocked,
    _school_days,
)

COURSES = 16
YEARS = (10, 11, 12)
SLOT_STARTS = (
    time(9, 0),
    time(10, 10),
    time(11, 20),
    time(12, 30),
    time(13, 30),
    time(14, 40),
    time(15, 50),
    time(17, 0),
)
LESSON_MINUTES = 60
AFTERNOON = (time(13, 30), time(18, 0))
LUNCH = LunchRule(window_start=time(12, 30), window_end=time(14, 30), minimum_minutes=60)
ROOM_COUNT = 48
INTERNAL_LOAD_HOURS = 650
EXTERNAL_SHARE = 0.30

# General subjects every class has; the first three can be joint, in this order.
PORTUGUES, INGLES, AREA_INTEGRACAO, EDUCACAO_FISICA, MATEMATICA = 1, 2, 3, 4, 5
FISICA_QUIMICA, ECONOMIA = 6, 7
JOINT_CANDIDATES = (EDUCACAO_FISICA, INGLES, AREA_INTEGRACAO)
GENERAL_NAMES = {
    PORTUGUES: "Português",
    INGLES: "Inglês",
    AREA_INTEGRACAO: "Área de Integração",
    EDUCACAO_FISICA: "Educação Física",
    MATEMATICA: "Matemática",
    FISICA_QUIMICA: "Física e Química",
    ECONOMIA: "Economia",
}
COURSE_NAMES = (
    "Programação",
    "Multimédia",
    "Eletrónica",
    "Gestão",
    "Turismo",
    "Cozinha",
    "Restauração",
    "Desporto",
    "Saúde",
    "Design",
    "Mecatrónica",
    "Comércio",
    "Audiovisuais",
    "Energias",
    "Informática",
    "Marketing",
)
TECHNICAL_ROOMS = ("Laboratório", "Oficina", "Normal")

NORMAL, LARGE, LAB, WORKSHOP, GYM = "Normal", "Sala grande", "Laboratório", "Oficina", "Ginásio"
ROOM_CAPACITY = {NORMAL: 30, LARGE: 60, LAB: 30, WORKSHOP: 30, GYM: 60}
# Fraction of the yearly room hours a type may plan for, so rooms keep some slack.
ROOM_PLANNING_SHARE = 0.6


@dataclass(frozen=True)
class RealisticPilot:
    snapshot: PlanningSnapshot
    periods: tuple[Period, ...]
    labels: dict[str, dict[str, str]]
    external_teachers: frozenset[int]


def _class_id(course: int, year_index: int) -> int:
    return course * 3 + year_index + 1


def _class_size(class_id: int) -> int:
    return 20 + (class_id * 7) % 9


def _subjects(course: int) -> tuple[int, ...]:
    """8 or 9 subjects: five general, one scientific and 2 or 3 technical ones."""
    scientific = FISICA_QUIMICA if course % 2 == 0 else ECONOMIA
    technical_count = 2 + course % 2
    technical = tuple(100 + course * 10 + index for index in range(1, technical_count + 1))
    return (PORTUGUES, INGLES, AREA_INTEGRACAO, EDUCACAO_FISICA, MATEMATICA, scientific, *technical)


def _modules(subject: int, year_index: int, course: int) -> tuple[ModuleRequirement, ...]:
    """6 or 7 modules of 16 to 22 hours; general subjects ignore the course so joints match."""
    seed = course if subject >= 100 else 0
    count = 6 + (subject + year_index + seed) % 2
    return tuple(
        ModuleRequirement(
            module_id=module,
            sequence=module,
            required_minutes=(16 + (seed * 5 + subject * 3 + year_index + module) % 7) * 60,
        )
        for module in range(1, count + 1)
    )


def _room_type(subject: int) -> str:
    if subject == EDUCACAO_FISICA:
        return GYM
    if subject == FISICA_QUIMICA:
        return LAB
    if subject >= 100:
        return {"Laboratório": LAB, "Oficina": WORKSHOP, "Normal": NORMAL}[
            TECHNICAL_ROOMS[subject % len(TECHNICAL_ROOMS)]
        ]
    return NORMAL


def _joint_subjects(pair: int, year_index: int) -> tuple[int, ...]:
    return JOINT_CANDIDATES[: 2 + (pair + year_index) % 2]


def _grid(days: tuple[date, ...]) -> tuple[GridSlot, ...]:
    return tuple(
        dict.fromkeys(
            GridSlot(day.weekday(), start, time(start.hour + 1, start.minute))
            for day in days
            for start in SLOT_STARTS
        )
    )


def build_realistic_pilot() -> RealisticPilot:
    days = tuple(day for day in _school_days(SCHOOL_YEAR_START, HARD_END) if not _blocked(day))
    periods = tuple(
        normalize_period(day, start, time(start.hour + 1, start.minute), TIMEZONE)
        for day in days
        for start in SLOT_STARTS
    )

    # Class-subject assignments, before teachers.
    rows: list[tuple[int, int, int, tuple[ModuleRequirement, ...]]] = []
    for course in range(COURSES):
        for year_index in range(len(YEARS)):
            class_id = _class_id(course, year_index)
            for subject in _subjects(course):
                rows.append(
                    (
                        class_id * 100 + (50 + subject % 10 if subject >= 100 else subject),
                        class_id,
                        subject,
                        _modules(subject, year_index, course),
                    )
                )
    by_class_subject = {(class_id, subject): identity for identity, class_id, subject, _ in rows}
    modules_of = {identity: modules for identity, _owner, _subject, modules in rows}
    hours = {
        identity: sum(m.required_minutes for m in modules) // 60 for identity, *_, modules in rows
    }

    # Joint pairs: classes of the same year in courses 2p and 2p+1.
    joint_members: list[tuple[int, int, int]] = []
    for pair in range(COURSES // 2):
        for year_index in range(len(YEARS)):
            first, second = _class_id(2 * pair, year_index), _class_id(2 * pair + 1, year_index)
            for subject in _joint_subjects(pair, year_index):
                joint_members.append(
                    (
                        subject,
                        by_class_subject[(first, subject)],
                        by_class_subject[(second, subject)],
                    )
                )
    partner = {}
    for _subject, first, second in joint_members:
        partner[first] = second
        partner[second] = first

    # Teaching blocks: a joint pair is one block taught once.
    blocks: list[tuple[int, tuple[int, ...], int]] = []
    seen = set()
    for identity, _owner, subject, _modules_row in rows:
        if identity in seen:
            continue
        members = (identity, partner[identity]) if identity in partner else (identity,)
        seen.update(members)
        blocks.append((subject, members, hours[identity]))

    # External teachers take whole technical subjects of one course (its three classes),
    # in a fixed order, until they are at least 30% of all teachers.
    technical_groups: dict[int, list[int]] = defaultdict(list)
    for index, (subject, _members, _hours) in enumerate(blocks):
        if subject >= 100:
            technical_groups[subject].append(index)
    technical_order = sorted(technical_groups, key=lambda subject: (-(subject % 10), subject))

    def staff(external_subjects: set[int]) -> tuple[dict[int, int], set[int]]:
        teacher_of: dict[int, int] = {}
        externals: set[int] = set()
        next_id = 1
        for subject in sorted(external_subjects):
            for index in technical_groups[subject]:
                teacher_of[index] = next_id
            externals.add(next_id)
            next_id += 1
        family_teacher: dict[object, tuple[int, int]] = {}
        for index, (subject, _members, block_hours) in enumerate(blocks):
            if index in teacher_of:
                continue
            family = subject if subject < 100 else ("technical", subject // 10)
            current = family_teacher.get(family)
            if current is None or current[1] + block_hours > INTERNAL_LOAD_HOURS:
                current = (next_id, 0)
                next_id += 1
            teacher_of[index] = current[0]
            family_teacher[family] = (current[0], current[1] + block_hours)
        return teacher_of, externals

    external_subjects: set[int] = set()
    teacher_of, externals = staff(external_subjects)
    for subject in technical_order:
        if len(externals) >= EXTERNAL_SHARE * len(set(teacher_of.values())):
            break
        external_subjects.add(subject)
        teacher_of, externals = staff(external_subjects)

    # Rooms: type counts follow the yearly demand; the rest are Normal rooms.
    room_hours = len(days) * len(SLOT_STARTS) * ROOM_PLANNING_SHARE
    demand: dict[str, int] = defaultdict(int)
    for subject, members, block_hours in blocks:
        kind = _room_type(subject)
        demand[LARGE if kind == NORMAL and len(members) > 1 else kind] += block_hours
    counts = {kind: max(1, ceil(demand[kind] / room_hours)) for kind in (LARGE, LAB, WORKSHOP, GYM)}
    counts[NORMAL] = ROOM_COUNT - sum(counts.values())
    if counts[NORMAL] * room_hours < demand[NORMAL]:
        raise ValueError("48 rooms cannot hold the Normal-room demand of the realistic pilot.")
    rooms: list[tuple[int, str, int]] = []
    for kind in (NORMAL, LARGE, LAB, WORKSHOP, GYM):
        for _ in range(counts[kind]):
            rooms.append((len(rooms) + 1, kind, ROOM_CAPACITY[kind]))

    def eligible(subject: int, members: tuple[int, ...]) -> frozenset[int]:
        kind = _room_type(subject)
        size = sum(_class_size(identity // 100) for identity in members)
        kinds = {kind, LARGE} if kind == NORMAL else {kind}
        chosen = frozenset(
            room for room, room_kind, capacity in rooms if room_kind in kinds and capacity >= size
        )
        if not chosen:
            raise ValueError(f"No {kind} room fits subject {subject} for {size} students.")
        return chosen

    plans = []
    rooms_of: dict[int, frozenset[int]] = {}
    for index, (subject, members, _block_hours) in enumerate(blocks):
        for identity in members:
            class_id = identity // 100
            rooms_of[identity] = eligible(subject, members)
            plans.append(
                AssignmentPlan(
                    assignment_id=identity,
                    class_id=class_id,
                    subject_id=subject,
                    teacher_id=teacher_of[index],
                    student_count=_class_size(class_id),
                    modules=modules_of[identity],
                    executed_minutes={},
                )
            )
    groups = tuple(
        JointGroupPlan(
            group_id=group_id,
            subject_id=subject,
            member_assignment_ids=(first, second),
            module_ids=tuple(module.module_id for module in modules_of[first]),
        )
        for group_id, (subject, first, second) in enumerate(joint_members, start=1)
    )
    unit_plan = build_teaching_units(plans, groups, set())
    assignments = tuple(
        Assignment(
            assignment_id=unit.unit_id,
            class_ids=unit.class_ids,
            subject_id=unit.subject_id,
            teacher_id=unit.teacher_id,
            eligible_room_ids=rooms_of[by_class_subject[(unit.class_ids[0], unit.subject_id)]],
            modules=unit.modules,
        )
        for unit in unit_plan.units
    )

    # Availability, from teacher and class indexes.
    teachers = sorted(set(teacher_of.values()))
    soft: list[Unavailability] = []
    hard: list[Unavailability] = []
    for position, teacher in enumerate(teachers):
        for day in days:
            if position % 3 == 0 and day.weekday() == position % 5:
                soft.append(_block(UnavailableResource.TEACHER, teacher, day, *AFTERNOON))
            if position % 5 == 1:
                soft.append(_block(UnavailableResource.TEACHER, teacher, day, *AFTERNOON))
            if position % 8 == 2 and day.weekday() == (position // 8) % 5:
                hard.append(_block(UnavailableResource.TEACHER, teacher, day, time(9), time(18)))
    class_ids = [_class_id(course, year) for course in range(COURSES) for year in range(len(YEARS))]
    for class_id in class_ids:
        if class_id % 4 == 0:
            soft.extend(
                _block(UnavailableResource.CLASS, class_id, day, *AFTERNOON)
                for day in days
                if day.weekday() == 4
            )
    presence = tuple(
        TeacherPresenceRule(
            teacher_id=teacher,
            minimum_minutes=120 if order % 2 == 0 else 180,
            max_gap_minutes=60,
        )
        for order, teacher in enumerate(sorted(externals))
    )
    normal_rooms = [room for room, kind, _capacity in rooms if kind == NORMAL]
    home_rooms = tuple(
        HomeRoom(class_id, room) for class_id, room in zip(class_ids, normal_rooms, strict=False)
    )

    snapshot = PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=SCHOOL_YEAR_START,
        preferred_end_date=PREFERRED_END,
        hard_end_date=HARD_END,
        timezone_name=TIMEZONE,
        grid_slots=_grid(days),
        assignments=assignments,
        executed_minutes={},
        blocked_dates=frozenset(
            day
            for day in _school_days(SCHOOL_YEAR_START, HARD_END)
            if day.weekday() < 5 and _blocked(day)
        ),
        unavailable=tuple(hard),
        soft_unavailable=tuple(soft),
        precedences=unit_plan.precedences,
        lunch_rule=LUNCH,
        teacher_presence=presence,
        home_rooms=home_rooms,
    )
    labels = {
        "classes": {
            str(_class_id(course, year)): f"{COURSE_NAMES[course]} {YEARS[year]}"
            for course in range(COURSES)
            for year in range(len(YEARS))
        },
        "subjects": {
            str(subject): GENERAL_NAMES.get(subject)
            or f"{COURSE_NAMES[(subject - 100) // 10]} T{subject % 10}"
            for subject in sorted({row[2] for row in rows})
        },
        "teachers": {
            str(teacher): f"{'Externo' if teacher in externals else 'Professor'} {teacher}"
            for teacher in teachers
        },
        "rooms": {str(room): f"{kind} {room}" for room, kind, _capacity in rooms},
    }
    return RealisticPilot(snapshot, periods, labels, frozenset(externals))


def _block(resource: UnavailableResource, identity: int, day: date, start: time, end: time):
    return Unavailability(resource, identity, normalize_period(day, start, end, TIMEZONE))
