"""S10 (R15, T08, T09): falhas de sala da turma e mudanças de sala evitáveis."""

from datetime import date, time, timedelta

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
from app.scheduler.domain.home_rooms import (
    avoidable_room_changes,
    home_room_misses,
    is_justified_room_change,
)
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice

ORIGIN = date(2026, 9, 21)
TZ = "Europe/Lisbon"
GRID = tuple(
    GridSlot(weekday, time(hour), time(hour + 1)) for weekday in range(7) for hour in range(8, 18)
)


def _assignment(assignment_id, class_ids, rooms, *, special=False) -> Assignment:
    return Assignment(
        assignment_id=assignment_id,
        class_ids=class_ids,
        subject_id=assignment_id,
        teacher_id=assignment_id,
        eligible_room_ids=frozenset(rooms),
        modules=(ModuleRequirement(assignment_id, 1, 60),),
        needs_special_room=special,
    )


def _lesson(lesson_id, assignment_id, room, hour, day=0) -> ScheduledLesson:
    period = normalize_period(ORIGIN + timedelta(days=day), time(hour), time(hour + 1), TZ)
    return ScheduledLesson(
        lesson_id=lesson_id,
        assignment_id=assignment_id,
        period=period,
        room_id=room,
        credit_minutes=60,
        slices=(ModuleSlice(lesson_id, assignment_id, 0, 60),),
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


def test_spec_example_class_a_has_one_miss_and_one_avoidable_change():
    """❌ R15: Turma A com sala N1 — 1 falha de sala da turma e 1 mudança evitável."""
    snapshot = _snapshot(
        [
            _assignment(1, (1,), {1, 2}),  # Português
            _assignment(2, (1,), {1, 2}),  # Matemática
            _assignment(3, (1,), {3}, special=True),  # Educação Física (ginásio)
            _assignment(4, (1,), {1, 2}),  # Inglês
        ],
        home_rooms=[HomeRoom(class_id=1, room_id=1)],
    )
    candidate = CandidateSchedule(
        (
            _lesson(1, 1, room=1, hour=9),
            _lesson(2, 2, room=2, hour=10),
            _lesson(3, 3, room=3, hour=11),
            _lesson(4, 4, room=1, hour=12),
        )
    )

    assert home_room_misses(snapshot, candidate) == 1
    assert avoidable_room_changes(snapshot, candidate) == 1


def test_spec_example_tgpsi_counts_the_programming_lab_but_not_the_change_to_portuguese():
    """❌ R15: Programação (laboratório) fora de L-03 conta; a troca para Português não é evitável."""
    snapshot = _snapshot(
        [
            _assignment(1, (2,), {10, 1}),  # Português, pode ir para L-03 (D12)
            _assignment(2, (2,), {10, 11}, special=True),  # Programação (laboratório)
        ],
        home_rooms=[HomeRoom(class_id=2, room_id=10)],
    )
    candidate = CandidateSchedule(
        (
            _lesson(1, 2, room=11, hour=9),
            _lesson(2, 1, room=10, hour=10),
        )
    )

    assert home_room_misses(snapshot, candidate) == 1
    assert avoidable_room_changes(snapshot, candidate) == 0


def test_a_joint_lesson_counts_a_miss_for_each_of_its_classes():
    """❌ R15: uma aula conjunta conta uma falha por cada turma com sala da turma."""
    snapshot = _snapshot(
        [_assignment(1, (1, 2), {1, 2, 3})],
        home_rooms=[HomeRoom(class_id=1, room_id=1), HomeRoom(class_id=2, room_id=2)],
    )
    candidate = CandidateSchedule((_lesson(1, 1, room=3, hour=9),))

    assert home_room_misses(snapshot, candidate) == 2


def test_classes_without_a_home_room_have_no_misses_and_changes_on_other_days_do_not_pair():
    """❌ T08: sem sala da turma não há falhas; aulas de dias diferentes não formam pares."""
    snapshot = _snapshot([_assignment(1, (1,), {1, 2}), _assignment(2, (3,), {1, 2})])
    candidate = CandidateSchedule(
        (
            _lesson(1, 1, room=1, hour=9, day=0),
            _lesson(2, 1, room=2, hour=9, day=1),
            _lesson(3, 2, room=2, hour=10, day=0),
        )
    )

    assert home_room_misses(snapshot, candidate) == 0
    assert avoidable_room_changes(snapshot, candidate) == 0


def test_a_change_into_or_out_of_a_home_room_is_justified():
    """❌ T09: entrar na sala da turma, ou sair da sala de outra turma, é mudança justificada."""
    snapshot = _snapshot(
        [_assignment(1, (1,), {1, 2, 5, 6}), _assignment(2, (2,), {1, 2, 5, 6})],
        home_rooms=[HomeRoom(class_id=1, room_id=1), HomeRoom(class_id=2, room_id=2)],
    )

    assert is_justified_room_change(snapshot, (1,), previous_room=5, new_room=1)
    assert is_justified_room_change(snapshot, (1,), previous_room=2, new_room=5)
    assert is_justified_room_change(snapshot, (1, 2), previous_room=5, new_room=1)
    assert not is_justified_room_change(snapshot, (1,), previous_room=5, new_room=6)
    assert not is_justified_room_change(snapshot, (1,), previous_room=1, new_room=5)
