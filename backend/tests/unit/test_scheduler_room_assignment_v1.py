"""S11 (R17-R22): the room pass by home-room policy, without changing times."""

import random
from dataclasses import replace
from datetime import date, time, timedelta

import app.scheduler.infrastructure.search as search_module
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    HomeRoom,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.home_rooms import avoidable_room_changes, home_room_misses
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice
from app.scheduler.domain.recovery import measure_disruption
from app.scheduler.infrastructure.constructive import construct_schedule
from app.scheduler.infrastructure.room_assignment import assign_rooms_by_period
from tests.unit.test_scheduler_generation_quality_v1 import home_room_fixture
from tests.unit.test_scheduler_recovery_v1 import POLICY

ORIGIN = date(2026, 9, 21)
TZ = "Europe/Lisbon"
GRID = tuple(
    GridSlot(weekday, time(hour), time(hour + 1)) for weekday in range(7) for hour in range(8, 18)
)
NORMAL_1, NORMAL_2, GYM = 1, 2, 3
LAB_1, LAB_2 = 10, 11


def _assignment(assignment_id, class_ids, rooms, *, subject_id=None, special=False, lessons=1):
    return Assignment(
        assignment_id=assignment_id,
        class_ids=tuple(class_ids),
        subject_id=assignment_id if subject_id is None else subject_id,
        teacher_id=assignment_id,
        eligible_room_ids=frozenset(rooms),
        modules=(ModuleRequirement(assignment_id, 1, 60 * lessons),),
        needs_special_room=special,
    )


def _lesson(lesson_id, assignment_id, room, hour, *, day=0, offset=0) -> ScheduledLesson:
    period = normalize_period(ORIGIN + timedelta(days=day), time(hour), time(hour + 1), TZ)
    return ScheduledLesson(
        lesson_id=lesson_id,
        assignment_id=assignment_id,
        period=period,
        room_id=room,
        credit_minutes=60,
        slices=(ModuleSlice(lesson_id, assignment_id, offset, 60),),
    )


def _snapshot(assignments, home_rooms=()) -> PlanningSnapshot:
    return PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=ORIGIN + timedelta(days=20),
        hard_end_date=ORIGIN + timedelta(days=30),
        timezone_name=TZ,
        grid_slots=GRID,
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=(),
        home_rooms=tuple(home_rooms),
    )


def _rooms_by_lesson(candidate: CandidateSchedule) -> dict[int, int]:
    return {row.lesson_id: row.room_id for row in candidate.lessons}


def test_r17_a_home_room_wins_the_morning_alternative_at_the_same_hour():
    """❌ R17: A tem sala N1; B usou N1 de manhã; ambas Normal às 10h: A fica em N1."""
    snapshot = _snapshot(
        [
            _assignment(1, (1,), {NORMAL_1, NORMAL_2}),  # A, Português
            _assignment(2, (2,), {NORMAL_1, NORMAL_2}),  # B, sem sala da turma
        ],
        home_rooms=[HomeRoom(class_id=1, room_id=NORMAL_1)],
    )
    candidate = CandidateSchedule(
        (
            _lesson(1, 2, NORMAL_1, 9),
            _lesson(2, 1, NORMAL_1, 10),
            _lesson(3, 2, NORMAL_2, 10),
        )
    )

    result = _rooms_by_lesson(assign_rooms_by_period(snapshot, candidate))

    assert result[2] == NORMAL_1
    assert result[3] == NORMAL_2


def test_r17_when_the_home_room_is_taken_by_a_special_lesson_another_class_may_use_it():
    """❌ R17: com A no ginásio, B pode usar N1 às 10h."""
    snapshot = _snapshot(
        [
            _assignment(1, (1,), {GYM}, special=True),  # A, Educação Física
            _assignment(2, (2,), {NORMAL_1, NORMAL_2}),  # B, sem sala da turma
        ],
        home_rooms=[HomeRoom(class_id=1, room_id=NORMAL_1)],
    )
    candidate = CandidateSchedule(
        (
            _lesson(1, 2, NORMAL_1, 9),
            _lesson(2, 1, GYM, 10),
            _lesson(3, 2, NORMAL_2, 10),
        )
    )

    result = _rooms_by_lesson(assign_rooms_by_period(snapshot, candidate))

    assert result[3] == NORMAL_1


def test_r18_two_classes_with_the_same_home_room_share_it_and_the_other_keeps_its_alternative():
    """❌ R18: A e B com N1 às 9h: uma fica em N1; a outra usa a mesma alternativa às 10h."""
    snapshot = _snapshot(
        [
            _assignment(1, (1,), {NORMAL_1, NORMAL_2, GYM}),  # A
            _assignment(2, (2,), {NORMAL_1, NORMAL_2, GYM}),  # B
            _assignment(3, (1,), {NORMAL_1, NORMAL_2, GYM}),  # A, 10h
            _assignment(4, (2,), {NORMAL_1, NORMAL_2, GYM}),  # B, 10h
        ],
        home_rooms=[HomeRoom(class_id=1, room_id=NORMAL_1), HomeRoom(class_id=2, room_id=NORMAL_1)],
    )
    candidate = CandidateSchedule(
        (
            _lesson(1, 1, NORMAL_1, 9),
            _lesson(2, 2, NORMAL_1, 9),
            _lesson(3, 3, NORMAL_1, 10),
            _lesson(4, 4, NORMAL_1, 10),
        )
    )

    result = assign_rooms_by_period(snapshot, candidate)
    rooms = _rooms_by_lesson(result)

    assert rooms[1] == NORMAL_1
    assert rooms[3] == NORMAL_1
    assert rooms[2] == rooms[4] == NORMAL_2
    assert home_room_misses(snapshot, result) == 2
    assert avoidable_room_changes(snapshot, result) == 0


def test_r19_a_joint_lesson_takes_the_home_room_of_a_member_class_when_all_fit():
    """❌ R19: A+B conjunta com N1 de A e lugares para todos: vai para N1."""
    snapshot = _snapshot(
        [_assignment(1, (1, 2), {NORMAL_1, NORMAL_2})],
        home_rooms=[HomeRoom(class_id=1, room_id=NORMAL_1)],
    )
    candidate = CandidateSchedule((_lesson(1, 1, NORMAL_2, 9),))

    assert _rooms_by_lesson(assign_rooms_by_period(snapshot, candidate)) == {1: NORMAL_1}


def test_r19_a_joint_lesson_without_room_for_everyone_takes_another_room():
    """❌ R19: sem lugares para todos, N1 não é elegível; a conjunta vai para outra sala (N2)."""
    snapshot = _snapshot(
        [_assignment(1, (1, 2), {NORMAL_2, GYM})],
        home_rooms=[HomeRoom(class_id=1, room_id=NORMAL_1)],
    )
    candidate = CandidateSchedule((_lesson(1, 1, GYM, 9),))

    assert _rooms_by_lesson(assign_rooms_by_period(snapshot, candidate)) == {1: NORMAL_2}


def test_r20_a_special_subject_keeps_the_same_lab_in_every_lesson_when_it_is_free():
    """❌ R20: Programação da turma A fica no mesmo laboratório em todas as aulas."""
    snapshot = _snapshot([_assignment(1, (1,), {LAB_1, LAB_2}, special=True, lessons=3)])
    candidate = CandidateSchedule(
        (
            _lesson(1, 1, LAB_2, 9, offset=0),
            _lesson(2, 1, LAB_1, 10, offset=60),
            _lesson(3, 1, LAB_2, 11, offset=120),
        )
    )

    result = assign_rooms_by_period(snapshot, candidate)

    assert set(_rooms_by_lesson(result).values()) == {LAB_1}


def test_r22_the_pass_returns_the_same_lessons_in_the_same_times_and_a_valid_candidate():
    """❌ R22: só room_id muda; o validador aceita o resultado."""
    snapshot = _snapshot([_assignment(1, (1,), {LAB_1, LAB_2}, special=True, lessons=3)])
    candidate = CandidateSchedule(
        (
            _lesson(1, 1, LAB_2, 9, offset=0),
            _lesson(2, 1, LAB_1, 10, offset=60),
            _lesson(3, 1, LAB_2, 11, offset=120),
        )
    )

    result = assign_rooms_by_period(snapshot, candidate)

    assert [replace(row, room_id=LAB_1) for row in result.lessons] == [
        replace(row, room_id=LAB_1) for row in candidate.lessons
    ]
    assert validate_candidate(snapshot, result).valid


def test_r22_a_date_with_partly_overlapping_lessons_keeps_the_construction_rooms():
    """❌ R22/T13: sobreposição parcial numa data mantém as salas da construção."""
    snapshot = _snapshot(
        [
            _assignment(1, (1,), {NORMAL_1, NORMAL_2}),
            _assignment(2, (2,), {NORMAL_1, NORMAL_2}),
        ],
        home_rooms=[HomeRoom(class_id=1, room_id=NORMAL_1)],
    )
    early = normalize_period(ORIGIN, time(9), time(10), TZ)
    late = normalize_period(ORIGIN, time(9, 30), time(10, 30), TZ)
    candidate = CandidateSchedule(
        (
            replace(_lesson(1, 1, NORMAL_2, 9), period=early),
            replace(_lesson(2, 2, NORMAL_1, 9), period=late),
        )
    )

    result = assign_rooms_by_period(snapshot, candidate)

    assert _rooms_by_lesson(result) == {1: NORMAL_2, 2: NORMAL_1}


def test_r21_a_new_home_room_moves_future_editable_lessons_at_no_disruption_cost():
    """❌ R21/T09: a sala nova da turma leva as aulas editáveis; a protegida fica; custo 0."""
    base = _snapshot([_assignment(1, (1,), {NORMAL_1, NORMAL_2}, lessons=3)])
    protected = _lesson(1, 1, NORMAL_1, 8, offset=0)
    snapshot = replace(
        base,
        protected_lessons=(protected,),
        home_rooms=(HomeRoom(class_id=1, room_id=NORMAL_2),),
    )
    baseline = CandidateSchedule(
        (protected, _lesson(2, 1, NORMAL_1, 9, offset=60), _lesson(3, 1, NORMAL_1, 10, offset=120))
    )
    candidate = CandidateSchedule(
        (protected, _lesson(2, 1, NORMAL_1, 9, offset=60), _lesson(3, 1, NORMAL_1, 10, offset=120))
    )

    result = assign_rooms_by_period(snapshot, candidate, baseline=baseline, policy=POLICY)
    metrics = measure_disruption(snapshot, baseline, result, POLICY)

    assert _rooms_by_lesson(result) == {1: NORMAL_1, 2: NORMAL_2, 3: NORMAL_2}
    assert metrics.room_changes == 2
    assert metrics.total_cost == 0


def _random_normal_day(seed: int):
    """Three classes without home rooms, Normal subjects, one lesson per hour in four rooms."""
    rng = random.Random(seed)
    rooms = (1, 2, 3, 4)
    assignments = [_assignment(class_id, (class_id,), rooms) for class_id in (1, 2, 3)]
    lessons = []
    lesson_id = 1
    for hour in range(9, 13):
        for class_id, room in zip((1, 2, 3), rng.sample(rooms, 3), strict=True):
            lessons.append(_lesson(lesson_id, class_id, room, hour))
            lesson_id += 1
    return _snapshot(assignments), CandidateSchedule(tuple(lessons))


def test_i09_a_class_without_home_room_and_only_normal_subjects_never_gets_more_avoidable_changes():
    """❌ I09: o passe não piora mudanças evitáveis de turmas sem sala e só Normal."""
    for seed in range(40):
        snapshot, candidate = _random_normal_day(seed)

        result = assign_rooms_by_period(snapshot, candidate)

        assert avoidable_room_changes(snapshot, result) <= avoidable_room_changes(
            snapshot, candidate
        ), f"seed {seed}"


def _exact_path_candidate():
    """Construction of the R23 instance with class 1 in home room 1 (T11, T12)."""
    fixture = home_room_fixture()
    snapshot = replace(fixture.snapshot, home_rooms=(HomeRoom(class_id=1, room_id=NORMAL_1),))
    certified = construct_schedule(snapshot, fixture.periods)
    assert certified is not None
    return snapshot, certified


def test_r16_on_the_exact_path_a_room_pass_that_worsens_the_vector_is_refused(monkeypatch):
    """❌ R16: no caminho exato, um passe que piora o vetor é recusado; o certificado fica."""
    snapshot, certified = _exact_path_candidate()
    profile = search_module._SearchProfile()
    first = min(
        (row for row in certified.lessons if row.assignment_id == 1),
        key=lambda row: row.period.start_utc,
    )
    other_room = NORMAL_2 if first.room_id == NORMAL_1 else NORMAL_1
    worse = CandidateSchedule(
        tuple(
            replace(row, room_id=other_room) if row is first else row for row in certified.lessons
        )
    )
    assert profile.vector(snapshot, worse) > profile.vector(snapshot, certified)
    monkeypatch.setattr(search_module, "assign_rooms_by_period", lambda *_a, **_k: worse)

    assert search_module._room_pass(snapshot, profile, certified, guarded=True) is certified
    assert search_module._room_pass(snapshot, profile, certified, guarded=False) is worse


def test_r16_on_the_exact_path_a_room_pass_that_does_not_worsen_the_vector_is_kept():
    """❌ R16: no caminho exato, um passe que não piora o vetor fica."""
    snapshot, certified = _exact_path_candidate()
    profile = search_module._SearchProfile()
    passed = assign_rooms_by_period(snapshot, certified)
    assert profile.vector(snapshot, passed) <= profile.vector(snapshot, certified)

    assert search_module._room_pass(snapshot, profile, certified, guarded=True) == passed
