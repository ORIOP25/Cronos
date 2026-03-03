"""CP-SAT Solver Engine para Horário Zen — Ensino Profissional.

Fase 1 (este módulo): Encontra o padrão semanal ótimo, ou seja, em que
timeslots e salas cada lição ocorre *todas as semanas*.

Fase 2 (solver_tasks.py): Expande esse padrão para datas absolutas,
tendo em conta feriados e a conclusão progressiva dos módulos.
"""
from dataclasses import dataclass
from collections import defaultdict

from ortools.sat.python import cp_model
import structlog

logger = structlog.get_logger()

# Constantes SonarQube S1192
MAX_HOURS_PER_WEEK_MINUTES = 900   # 15 horas × 60 minutos
PENALTY_AVOID = 20
PENALTY_PREFERRED_MISSING = 10
PENALTY_REPAIR_CHANGE = 50         # Reparação: custo de mudar um slot em relação ao horário ativo
SOLVER_MAX_SECONDS = 300           # 5 minutos — sem artificial time limit de qualidade


# ---------------------------------------------------------------------------
# Tipos de Entrada / Saída
# ---------------------------------------------------------------------------

@dataclass
class LessonInput:
    """Dados de uma lição para o solver (Class + Subject + Teacher)."""
    lesson_id: int
    class_id: int
    subject_id: int
    teacher_id: int
    required_room_type: str    # Ex: "normal", "lab", "gym"
    remaining_minutes: int     # Total de minutos restantes em todos os módulos


@dataclass
class TimeslotInput:
    """Bloco horário semanal."""
    ts_id: int
    day_of_week: int          # 0=Segunda … 4=Sexta (igual a date.weekday())
    duration_minutes: int


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


# ---------------------------------------------------------------------------
# Motor CP-SAT
# ---------------------------------------------------------------------------

class ScheduleEngine:
    """
    Motor CP-SAT que determina o padrão semanal ótimo para todas as turmas
    ativas de uma organização.

    Hard Constraints (HC1-HC7):
        HC1  Sala com no máximo uma lição de cada vez.
        HC2  Professor sem sobreposição de horário.
        HC3  Turma sem sobreposição de horário.
        HC4  Lição só em sala do tipo correto (ex: Informática → sala lab).
        HC5  Professor não dá aulas em slots marcados como IMPOSSÍVEL (-1).
        HC6  Limite de 15 h (900 min) por lição por semana.
        HC7  Lições com horas pendentes têm ≥ 1 sessão/semana;
             lições já completas não são agendadas.

    Soft Constraints (função objetivo):
        - Penalizar slots marcados como EVITAR (score=0).
        - Penalizar a ausência de sessão em slots PREFERIDOS (score=2).
    """

    def __init__(
        self,
        lessons: list[LessonInput],
        timeslots: list[TimeslotInput],
        rooms: list[RoomInput],
        availability_map: dict,           # (teacher_id, ts_id) -> score  (-1, 0, 1, 2)
        previous_pattern: dict | None = None,  # (lesson_id, ts_id) -> 1 (repair mode)
    ) -> None:
        self.lessons = lessons
        self.timeslots = timeslots
        self.rooms = rooms
        self.availability_map = availability_map
        self.previous_pattern: dict = previous_pattern or {}

        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # Variáveis de decisão — criadas em _create_variables()
        # x[(lesson_id, ts_id, room_id)] = BoolVar
        self.x: dict = {}
        # lesson_at_ts[(lesson_id, ts_id)] = BoolVar (agendada neste slot, qualquer sala)
        self.lesson_at_ts: dict = {}

    # ------------------------------------------------------------------
    # Ponto de entrada público
    # ------------------------------------------------------------------

    def solve(self) -> list[ScheduledAssignment] | None:
        """Resolve o modelo e retorna os assignments ou None se impossível."""
        logger.info(
            "🧠 Motor CP-SAT a iniciar",
            lessons=len(self.lessons),
            timeslots=len(self.timeslots),
            rooms=len(self.rooms),
        )

        self._create_variables()
        self._apply_hard_constraints()

        soft_penalties = self._build_soft_penalties()
        if soft_penalties:
            self.model.Minimize(sum(soft_penalties))

        self.solver.parameters.max_time_in_seconds = SOLVER_MAX_SECONDS
        self.solver.parameters.num_search_workers = 4
        self.solver.parameters.log_search_progress = False

        status = self.solver.Solve(self.model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            logger.info("✅ Solver: solução encontrada", objective=self.solver.ObjectiveValue())
            return self._extract_assignments()

        logger.warning("❌ Solver: sem solução viável", status=status)
        return None

    # ------------------------------------------------------------------
    # Criação de variáveis
    # ------------------------------------------------------------------

    def _create_variables(self) -> None:
        """Cria variáveis de decisão x e variáveis auxiliares lesson_at_ts."""
        for lesson in self.lessons:
            for ts in self.timeslots:
                room_vars = []
                for room in self.rooms:
                    var = self.model.NewBoolVar(
                        f"x_{lesson.lesson_id}_{ts.ts_id}_{room.room_id}"
                    )
                    self.x[(lesson.lesson_id, ts.ts_id, room.room_id)] = var
                    room_vars.append(var)

                # Auxiliar: lição agendada neste timeslot (independentemente da sala)
                lat = self.model.NewBoolVar(f"lat_{lesson.lesson_id}_{ts.ts_id}")
                self.model.Add(sum(room_vars) == lat)
                self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)] = lat

    # ------------------------------------------------------------------
    # Hard Constraints
    # ------------------------------------------------------------------

    def _apply_hard_constraints(self) -> None:
        """Aplica HC1 a HC7."""
        self._hc_room_conflict()
        self._hc_teacher_conflict()
        self._hc_class_conflict()
        self._hc_room_type_match()
        self._hc_teacher_availability()
        self._hc_max_hours_per_lesson()
        self._hc_active_lessons_need_sessions()

    def _hc_room_conflict(self) -> None:
        """HC1: Sala com no máximo uma lição de cada vez."""
        for room in self.rooms:
            for ts in self.timeslots:
                self.model.Add(
                    sum(
                        self.x[(lesson.lesson_id, ts.ts_id, room.room_id)]
                        for lesson in self.lessons
                    ) <= 1
                )

    def _hc_teacher_conflict(self) -> None:
        """HC2: Professor sem sobreposição de horário."""
        teacher_lessons: dict[int, list[LessonInput]] = defaultdict(list)
        for lesson in self.lessons:
            teacher_lessons[lesson.teacher_id].append(lesson)

        for t_lessons in teacher_lessons.values():
            for ts in self.timeslots:
                self.model.Add(
                    sum(
                        self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)]
                        for lesson in t_lessons
                    ) <= 1
                )

    def _hc_class_conflict(self) -> None:
        """HC3: Turma sem sobreposição de horário."""
        class_lessons: dict[int, list[LessonInput]] = defaultdict(list)
        for lesson in self.lessons:
            class_lessons[lesson.class_id].append(lesson)

        for c_lessons in class_lessons.values():
            for ts in self.timeslots:
                self.model.Add(
                    sum(
                        self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)]
                        for lesson in c_lessons
                    ) <= 1
                )

    def _hc_room_type_match(self) -> None:
        """HC4: Lição só em sala do tipo correto."""
        for lesson in self.lessons:
            for ts in self.timeslots:
                for room in self.rooms:
                    if room.room_type != lesson.required_room_type:
                        self.model.Add(
                            self.x[(lesson.lesson_id, ts.ts_id, room.room_id)] == 0
                        )

    def _hc_teacher_availability(self) -> None:
        """HC5: Bloqueia slots marcados como IMPOSSÍVEL (-1)."""
        for lesson in self.lessons:
            for ts in self.timeslots:
                score = self.availability_map.get((lesson.teacher_id, ts.ts_id), 1)
                if score == -1:
                    self.model.Add(
                        self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)] == 0
                    )

    def _hc_max_hours_per_lesson(self) -> None:
        """HC6: Lição não pode exceder 15 h (900 min) por semana."""
        for lesson in self.lessons:
            self.model.Add(
                sum(
                    self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)] * ts.duration_minutes
                    for ts in self.timeslots
                ) <= MAX_HOURS_PER_WEEK_MINUTES
            )

    def _hc_active_lessons_need_sessions(self) -> None:
        """HC7: Lições ativas ≥ 1 sessão/semana; lições completas = 0 sessões."""
        for lesson in self.lessons:
            total = sum(
                self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)]
                for ts in self.timeslots
            )
            if lesson.remaining_minutes > 0:
                self.model.Add(total >= 1)
            else:
                self.model.Add(total == 0)

    # ------------------------------------------------------------------
    # Soft Constraints (função objetivo)
    # ------------------------------------------------------------------

    def _build_soft_penalties(self) -> list:
        """Penalidades por preferências de disponibilidade e modo de reparação."""
        penalties: list = []
        for lesson in self.lessons:
            for ts in self.timeslots:
                self._add_availability_penalty(lesson, ts, penalties)
                if self.previous_pattern:
                    self._add_repair_penalty(lesson, ts, penalties)
        return penalties

    def _add_availability_penalty(
        self,
        lesson: LessonInput,
        ts: TimeslotInput,
        penalties: list,
    ) -> None:
        """Penaliza EVITAR (score=0); penaliza ausência em PREFERIDO (score=2)."""
        score = self.availability_map.get((lesson.teacher_id, ts.ts_id), 1)
        lat = self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)]

        if score == 0:    # EVITAR
            penalties.append(lat * PENALTY_AVOID)
        elif score == 2:  # PREFERIDO — penalizar ausência
            not_lat = self.model.NewBoolVar(f"noplat_{lesson.lesson_id}_{ts.ts_id}")
            self.model.Add(not_lat == 1 - lat)
            penalties.append(not_lat * PENALTY_PREFERRED_MISSING)

    def _add_repair_penalty(
        self,
        lesson: LessonInput,
        ts: TimeslotInput,
        penalties: list,
    ) -> None:
        """Repair mode: penaliza qualquer desvio em relação ao horário ativo anterior."""
        was_scheduled = self.previous_pattern.get((lesson.lesson_id, ts.ts_id), 0)
        lat = self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)]
        if was_scheduled == 1:
            # Era agendado — penalizar se agora não está
            not_lat = self.model.NewBoolVar(f"rp_removed_{lesson.lesson_id}_{ts.ts_id}")
            self.model.Add(not_lat == 1 - lat)
            penalties.append(not_lat * PENALTY_REPAIR_CHANGE)
        else:
            # Não era agendado — penalizar se agora está (nova adição)
            penalties.append(lat * PENALTY_REPAIR_CHANGE)

    # ------------------------------------------------------------------
    # Extração da solução
    # ------------------------------------------------------------------

    def _extract_assignments(self) -> list[ScheduledAssignment]:
        """Extrai os assignments vencedores do solver."""
        assignments = []
        for lesson in self.lessons:
            for ts in self.timeslots:
                for room in self.rooms:
                    key = (lesson.lesson_id, ts.ts_id, room.room_id)
                    if self.solver.Value(self.x[key]) == 1:
                        assignments.append(
                            ScheduledAssignment(
                                lesson_id=lesson.lesson_id,
                                ts_id=ts.ts_id,
                                room_id=room.room_id,
                                day_of_week=ts.day_of_week,
                                duration_minutes=ts.duration_minutes,
                            )
                        )
        return assignments