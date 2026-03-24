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
    Com 2 lições e apenas 1 slot, o solver mantém viabilidade e agenda no máximo 1.
    """
    lessons = [
        _make_lesson(1, class_id=1, subject_id=1, teacher_id=1),
        _make_lesson(2, class_id=1, subject_id=2, teacher_id=2),
    ]
    timeslots = [_make_ts(1)]
    rooms = [_make_room(1), _make_room(2)]

    engine = ScheduleEngine(lessons, timeslots, rooms, availability_map={})
    result = engine.solve()

    assert result is not None
    assert len(result) == 1


def test_solver_lunch_window_keeps_minimum_break_for_class():
    """HC8: Com janela 12-14 e pausa mínima 60, só 1 dos 2 slots de almoço pode ficar ocupado por turma."""
    lessons = [
        _make_lesson(1, class_id=1, subject_id=1, teacher_id=1),
        _make_lesson(2, class_id=1, subject_id=2, teacher_id=2),
    ]
    timeslots = [
        _make_ts(1, day_of_week=0, duration=60),  # 12:00-13:00 almoço
        _make_ts(2, day_of_week=0, duration=60),  # 13:00-14:00 almoço
        _make_ts(3, day_of_week=0, duration=60),  # fora de almoço
    ]
    timeslots[0].start_minutes = 12 * 60
    timeslots[0].end_minutes = 13 * 60
    timeslots[1].start_minutes = 13 * 60
    timeslots[1].end_minutes = 14 * 60
    timeslots[2].start_minutes = 10 * 60
    timeslots[2].end_minutes = 11 * 60
    rooms = [_make_room(1)]

    engine = ScheduleEngine(
        lessons,
        timeslots,
        rooms,
        availability_map={},
        lunch_window_start_minutes=12 * 60,
        lunch_window_end_minutes=14 * 60,
        lunch_min_duration_minutes=60,
    )
    result = engine.solve()

    assert result is not None
    lunch_ts_ids = {1, 2}
    occupied_lunch_count = sum(1 for row in result if row.ts_id in lunch_ts_ids)
    assert occupied_lunch_count <= 1


def test_solver_only_lunch_slots_still_uses_part_of_window_with_min_break():
    """HC8: Com dois slots de almoço e pausa mínima 60, um slot pode ser usado e o outro fica livre."""
    lessons = [_make_lesson(1, class_id=1, subject_id=1, teacher_id=1)]
    timeslots = [
        _make_ts(1, day_of_week=0, duration=60),
        _make_ts(2, day_of_week=0, duration=60),
    ]
    timeslots[0].start_minutes = 12 * 60
    timeslots[0].end_minutes = 13 * 60
    timeslots[1].start_minutes = 13 * 60
    timeslots[1].end_minutes = 14 * 60
    rooms = [_make_room(1)]

    engine = ScheduleEngine(
        lessons,
        timeslots,
        rooms,
        availability_map={},
        lunch_window_start_minutes=12 * 60,
        lunch_window_end_minutes=14 * 60,
        lunch_min_duration_minutes=60,
    )
    result = engine.solve()

    assert result is not None
    assert len(result) == 1


def test_solver_rewards_high_fill_when_feasible():
    """Objetivo de preenchimento: com 3 slots livres, a lição tende a ocupar os 3."""
    lessons = [_make_lesson(1, class_id=1, subject_id=1, teacher_id=1)]
    timeslots = [
        _make_ts(1, day_of_week=0, duration=60),
        _make_ts(2, day_of_week=0, duration=60),
        _make_ts(3, day_of_week=0, duration=60),
    ]
    timeslots[0].start_minutes = 8 * 60
    timeslots[0].end_minutes = 9 * 60
    timeslots[1].start_minutes = 9 * 60
    timeslots[1].end_minutes = 10 * 60
    timeslots[2].start_minutes = 10 * 60
    timeslots[2].end_minutes = 11 * 60
    rooms = [_make_room(1)]

    engine = ScheduleEngine(lessons, timeslots, rooms, availability_map={})
    result = engine.solve()

    assert result is not None
    assert len(result) == 3