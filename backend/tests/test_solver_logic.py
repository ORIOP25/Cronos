import pytest
from app.core.solver_engine import ScheduleEngine, LessonInput, TimeslotInput, RoomInput


def _make_lesson(lesson_id, class_id, subject_id, teacher_id, room_type="normal", remaining=3000):
    return LessonInput(
        lesson_id=lesson_id,
        class_id=class_id,
        subject_id=subject_id,
        teacher_id=teacher_id,
        required_room_type=room_type,
        remaining_minutes=remaining,
    )


def _make_ts(ts_id, day_of_week=0, duration=90):
    return TimeslotInput(ts_id=ts_id, day_of_week=day_of_week, duration_minutes=duration)


def _make_room(room_id, room_type="normal"):
    return RoomInput(room_id=room_id, room_type=room_type)


def test_solver_simple_case_with_classes():
    """HC1-HC3: Uma lição, um timeslot, uma sala — deve ser agendada."""
    lessons = [_make_lesson(1, class_id=1, subject_id=1, teacher_id=1)]
    timeslots = [_make_ts(1)]
    rooms = [_make_room(1)]

    engine = ScheduleEngine(lessons, timeslots, rooms, availability_map={})
    result = engine.solve()

    assert result is not None
    assert len(result) == 1
    assert result[0].lesson_id == 1
    assert result[0].ts_id == 1
    assert result[0].room_id == 1


def test_solver_conflict_class():
    """HC3: A mesma turma não pode ter 2 aulas ao mesmo tempo.
    Com 2 lições da turma 1 e apenas 1 timeslot, o modelo é infeasible
    porque HC7 exige que ambas as lições tenham ≥ 1 sessão/semana.
    """
    lessons = [
        _make_lesson(1, class_id=1, subject_id=1, teacher_id=1),
        _make_lesson(2, class_id=1, subject_id=2, teacher_id=2),
    ]
    timeslots = [_make_ts(1)]
    rooms = [_make_room(1), _make_room(2)]

    engine = ScheduleEngine(lessons, timeslots, rooms, availability_map={})
    result = engine.solve()

    assert result is None