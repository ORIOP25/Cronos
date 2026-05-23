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
