from dataclasses import dataclass

@dataclass
class LessonInput:
    """Dados de uma lição para o solver (Class + Subject + Teacher)."""
    lesson_id: int
    class_id: int
    subject_id: int
    teacher_id: int
    required_room_type: str    # Ex: "normal", "lab", "gym"
    remaining_minutes: int     # Total de minutos restantes em todos os módulos
    target_weekly_minutes: int = 60  # Meta mínima semanal para terminar no horizonte

@dataclass
class TimeslotInput:
    """Bloco horário semanal."""
    ts_id: int
    day_of_week: int          # 0=Segunda … 4=Sexta (igual a date.weekday())
    duration_minutes: int
    start_minutes: int = 0
    end_minutes: int = 0

@dataclass
class RoomInput:
    """Sala disponível."""
    room_id: int
    room_type: str             # Deve corresponder a LessonInput.required_room_type

@dataclass
class ScheduledAssignment:
    """Resultado do solver: lição X vai à sala Y no timeslot Z toda a semana."""
    lesson_id: int
    ts_id: int
    room_id: int
    day_of_week: int
    duration_minutes: int


class ScheduleEngine:
    """Small legacy weekly solver kept for old draft-lifecycle tests.

    Production scheduling uses ScheduleEngineV2. This compatibility engine
    assigns each lesson to the first feasible room/timeslot, preferring a
    previous published timeslot when repair-mode tests provide one.
    """

    def __init__(
        self,
        *,
        lessons: list[LessonInput],
        timeslots: list[TimeslotInput],
        rooms: list[RoomInput],
        availability_map: dict[tuple[int, int], int] | None = None,
        previous_pattern: dict[tuple[int, int], int] | None = None,
    ) -> None:
        self.lessons = lessons
        self.timeslots = timeslots
        self.rooms = rooms
        self.availability_map = availability_map or {}
        self.previous_pattern = previous_pattern or {}

    def solve(self) -> list[ScheduledAssignment]:
        assignments: list[ScheduledAssignment] = []
        used_teacher_slots: set[tuple[int, int]] = set()
        used_class_slots: set[tuple[int, int]] = set()
        used_room_slots: set[tuple[int, int]] = set()

        for lesson in self.lessons:
            room = next((r for r in self.rooms if r.room_type == lesson.required_room_type), None)
            if room is None and self.rooms:
                room = self.rooms[0]
            if room is None:
                continue

            ordered_slots = sorted(
                self.timeslots,
                key=lambda ts: 0 if self.previous_pattern.get((lesson.lesson_id, ts.ts_id)) else 1,
            )
            for timeslot in ordered_slots:
                if self.availability_map.get((lesson.teacher_id, timeslot.ts_id)) == -1:
                    continue
                if (lesson.teacher_id, timeslot.ts_id) in used_teacher_slots:
                    continue
                if (lesson.class_id, timeslot.ts_id) in used_class_slots:
                    continue
                if (room.room_id, timeslot.ts_id) in used_room_slots:
                    continue

                used_teacher_slots.add((lesson.teacher_id, timeslot.ts_id))
                used_class_slots.add((lesson.class_id, timeslot.ts_id))
                used_room_slots.add((room.room_id, timeslot.ts_id))
                assignments.append(
                    ScheduledAssignment(
                        lesson_id=lesson.lesson_id,
                        ts_id=timeslot.ts_id,
                        room_id=room.room_id,
                        day_of_week=timeslot.day_of_week,
                        duration_minutes=timeslot.duration_minutes,
                    )
                )
                break

        return assignments
