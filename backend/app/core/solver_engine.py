"""CP-SAT Solver Engine para Cronos — Ensino Profissional.

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
PENALTY_CLASS_DAY_SPREAD = 3       # Penaliza turmas espalhadas por muitos dias
PENALTY_CLASS_GAP = 15             # Penaliza furos internos nas turmas
PENALTY_TEACHER_GAP = 10           # Penaliza furos internos dos professores
REWARD_SCHEDULED_SESSION = 3       # Recompensa por cada sessão agendada (empurra preenchimento)
PENALTY_WEEKLY_SHORTAGE = 40       # Penaliza falta de minutos semanais face ao objetivo
PENALTY_CLASS_TARGET_SHORTAGE = 18  # Penaliza desvio negativo da meta agregada da turma
PENALTY_CLASS_TARGET_EXCESS = 4     # Penaliza excesso semanal agregado da turma
PENALTY_CLASS_FAIRNESS_SPREAD = 1   # Penaliza diferenças normalizadas entre turmas
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
           HC7  Lições já completas não são agendadas.
        HC8  Cada turma e professor têm pausa mínima dentro da janela de almoço.

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
        lunch_window_start_minutes: int | None = None,
        lunch_window_end_minutes: int | None = None,
        lunch_min_duration_minutes: int = 60,
    ) -> None:
        self.lessons = lessons
        self.timeslots = timeslots
        self.rooms = rooms
        self.availability_map = availability_map
        self.previous_pattern: dict = previous_pattern or {}
        self.lunch_window_start_minutes = lunch_window_start_minutes
        self.lunch_window_end_minutes = lunch_window_end_minutes
        self.lunch_min_duration_minutes = max(1, lunch_min_duration_minutes)

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
        self._hc_lunch_break_inside_window()

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
        """HC7: Lições completas não são agendadas; lições ativas ficam livres para otimização."""
        for lesson in self.lessons:
            total_sessions = sum(
                self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)]
                for ts in self.timeslots
            )
            if lesson.remaining_minutes <= 0:
                self.model.Add(total_sessions == 0)

    def _hc_lunch_break_inside_window(self) -> None:
        """HC8: Garante pausa mínima de almoço dentro da janela para turmas e professores."""
        if self.lunch_window_start_minutes is None or self.lunch_window_end_minutes is None:
            return

        class_lessons: dict[int, list[LessonInput]] = defaultdict(list)
        teacher_lessons: dict[int, list[LessonInput]] = defaultdict(list)
        for lesson in self.lessons:
            class_lessons[lesson.class_id].append(lesson)
            teacher_lessons[lesson.teacher_id].append(lesson)

        self._apply_lunch_break_for_entities(class_lessons)
        self._apply_lunch_break_for_entities(teacher_lessons)

    def _apply_lunch_break_for_entities(self, entity_lessons: dict[int, list[LessonInput]]) -> None:
        days = sorted({ts.day_of_week for ts in self.timeslots})

        for entity_id, lessons in entity_lessons.items():
            for day in days:
                lunch_slots = [
                    ts
                    for ts in self.timeslots
                    if ts.day_of_week == day
                    and ts.start_minutes < self.lunch_window_end_minutes
                    and ts.end_minutes > self.lunch_window_start_minutes
                ]
                if not lunch_slots:
                    continue

                overlap_by_slot = {
                    ts.ts_id: self._slot_lunch_overlap_minutes(ts)
                    for ts in lunch_slots
                }
                total_overlap = sum(overlap_by_slot.values())
                required_break = min(self.lunch_min_duration_minutes, total_overlap)
                if required_break <= 0:
                    continue

                occupied_lunch_minutes = sum(
                    self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)] * overlap_by_slot[ts.ts_id]
                    for lesson in lessons
                    for ts in lunch_slots
                )
                max_occupied = total_overlap - required_break
                self.model.Add(occupied_lunch_minutes <= max_occupied)

    def _slot_lunch_overlap_minutes(self, ts: TimeslotInput) -> int:
        overlap_start = max(ts.start_minutes, self.lunch_window_start_minutes)
        overlap_end = min(ts.end_minutes, self.lunch_window_end_minutes)
        return max(0, overlap_end - overlap_start)

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
        penalties.extend(self._build_class_day_spread_penalties())
        penalties.extend(self._build_gap_penalties())
        penalties.extend(self._build_fill_rewards())
        penalties.extend(self._build_weekly_shortage_penalties())
        penalties.extend(self._build_class_fairness_penalties())
        return penalties

    def _build_class_fairness_penalties(self) -> list:
        """Penaliza desequilíbrios de carga semanal entre turmas (fairness explícito)."""
        penalties: list = []

        class_lessons: dict[int, list[LessonInput]] = defaultdict(list)
        for lesson in self.lessons:
            if lesson.remaining_minutes > 0:
                class_lessons[lesson.class_id].append(lesson)

        if len(class_lessons) < 2:
            return penalties

        class_target_map = {
            class_id: self._compute_class_target_minutes(lessons)
            for class_id, lessons in class_lessons.items()
        }
        max_class_minutes = sum(ts.duration_minutes for ts in self.timeslots)
        if max_class_minutes <= 0:
            return penalties

        class_actual_vars = self._build_class_actual_minute_vars(class_lessons, max_class_minutes)
        penalties.extend(
            self._build_class_target_deviation_penalties(
                class_target_map,
                class_actual_vars,
                max_class_minutes,
            )
        )
        penalties.extend(
            self._build_interclass_spread_penalties(
                class_target_map,
                class_actual_vars,
                max_class_minutes,
            )
        )
        return penalties

    def _compute_class_target_minutes(self, lessons: list[LessonInput]) -> int:
        return int(round(sum(
            min(float(lesson.remaining_minutes), float(lesson.target_weekly_minutes))
            for lesson in lessons
        )))

    def _build_class_actual_minute_vars(self, class_lessons: dict[int, list[LessonInput]], max_class_minutes: int) -> dict[int, cp_model.IntVar]:
        actual_vars: dict[int, cp_model.IntVar] = {}
        for class_id, lessons in class_lessons.items():
            actual = self.model.NewIntVar(0, max_class_minutes, f"class_{class_id}_weekly_minutes")
            self.model.Add(
                actual == sum(
                    self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)] * ts.duration_minutes
                    for lesson in lessons
                    for ts in self.timeslots
                )
            )
            actual_vars[class_id] = actual
        return actual_vars

    def _build_class_target_deviation_penalties(
        self,
        class_target_map: dict[int, int],
        class_actual_vars: dict[int, cp_model.IntVar],
        max_class_minutes: int,
    ) -> list:
        penalties: list = []
        for class_id, target_minutes in class_target_map.items():
            target_minutes = int(round(target_minutes))
            if target_minutes <= 0:
                continue

            actual = class_actual_vars[class_id]
            shortage = self.model.NewIntVar(0, target_minutes, f"class_{class_id}_shortage")
            excess = self.model.NewIntVar(0, max_class_minutes, f"class_{class_id}_excess")

            self.model.Add(shortage >= target_minutes - actual)
            self.model.Add(excess >= actual - target_minutes)

            penalties.append(shortage * PENALTY_CLASS_TARGET_SHORTAGE)
            penalties.append(excess * PENALTY_CLASS_TARGET_EXCESS)
        return penalties

    def _build_interclass_spread_penalties(
        self,
        class_target_map: dict[int, int],
        class_actual_vars: dict[int, cp_model.IntVar],
        max_class_minutes: int,
    ) -> list:
        penalties: list = []
        class_ids = sorted(class_actual_vars.keys())

        for idx, first_class_id in enumerate(class_ids):
            first_actual = class_actual_vars[first_class_id]

            for second_class_id in class_ids[idx + 1:]:
                second_actual = class_actual_vars[second_class_id]

                _ = (class_target_map, first_class_id, second_class_id)
                pair_gap = self.model.NewIntVar(
                    0,
                    max_class_minutes,
                    f"class_pair_gap_{first_class_id}_{second_class_id}",
                )
                spread_expr = first_actual - second_actual
                self.model.Add(pair_gap >= spread_expr)
                self.model.Add(pair_gap >= -spread_expr)
                penalties.append(pair_gap * PENALTY_CLASS_FAIRNESS_SPREAD)

        return penalties

    def _build_weekly_shortage_penalties(self) -> list:
        """Penaliza minutos em falta por lição, mas sem tornar o modelo infeasible."""
        penalties: list = []
        for lesson in self.lessons:
            if lesson.remaining_minutes <= 0:
                continue

            target_minutes = int(round(min(float(lesson.remaining_minutes), float(lesson.target_weekly_minutes))))
            if target_minutes <= 0:
                continue
            total_minutes = sum(
                self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)] * ts.duration_minutes
                for ts in self.timeslots
            )
            shortage = self.model.NewIntVar(0, target_minutes, f"weekly_shortage_{lesson.lesson_id}")
            self.model.Add(shortage >= target_minutes - total_minutes)
            penalties.append(shortage * PENALTY_WEEKLY_SHORTAGE)

        return penalties

    def _build_gap_penalties(self) -> list:
        """Penaliza furos internos (slots vazios entre slots ocupados) por turma e professor."""
        penalties: list = []

        class_lessons: dict[int, list[LessonInput]] = defaultdict(list)
        teacher_lessons: dict[int, list[LessonInput]] = defaultdict(list)
        for lesson in self.lessons:
            class_lessons[lesson.class_id].append(lesson)
            teacher_lessons[lesson.teacher_id].append(lesson)

        penalties.extend(self._build_entity_gap_penalties("class", class_lessons, PENALTY_CLASS_GAP))
        penalties.extend(self._build_entity_gap_penalties("teacher", teacher_lessons, PENALTY_TEACHER_GAP))
        return penalties

    def _build_entity_gap_penalties(self, label: str, entities: dict[int, list[LessonInput]], weight: int) -> list:
        """Cria penalidades de furos para uma entidade (turma/professor)."""
        penalties: list = []
        days = sorted({ts.day_of_week for ts in self.timeslots})

        for entity_id, lessons in entities.items():
            for day in days:
                day_slots = self._get_day_slots(day)
                if len(day_slots) < 3:
                    continue

                occupied_by_slot = self._build_entity_occupancy_vars(label, entity_id, day, day_slots, lessons)
                penalties.extend(
                    self._build_day_gap_penalties(label, entity_id, day, occupied_by_slot, weight)
                )

        return penalties

    def _get_day_slots(self, day: int) -> list[TimeslotInput]:
        return sorted(
            [ts for ts in self.timeslots if ts.day_of_week == day],
            key=lambda ts: ts.start_minutes,
        )

    def _build_entity_occupancy_vars(
        self,
        label: str,
        entity_id: int,
        day: int,
        day_slots: list[TimeslotInput],
        lessons: list[LessonInput],
    ) -> list:
        occupied_by_slot: list = []
        for ts in day_slots:
            occupied = self.model.NewBoolVar(f"{label}_{entity_id}_{day}_{ts.ts_id}_occ")
            self.model.Add(
                occupied == sum(self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)] for lesson in lessons)
            )
            occupied_by_slot.append(occupied)
        return occupied_by_slot

    def _build_day_gap_penalties(
        self,
        label: str,
        entity_id: int,
        day: int,
        occupied_by_slot: list,
        weight: int,
    ) -> list:
        penalties: list = []
        for idx in range(1, len(occupied_by_slot) - 1):
            has_before = self._build_or_var(
                f"{label}_{entity_id}_{day}_{idx}_before",
                occupied_by_slot[:idx],
            )
            has_after = self._build_or_var(
                f"{label}_{entity_id}_{day}_{idx}_after",
                occupied_by_slot[idx + 1:],
            )
            is_gap = self._build_gap_var(label, entity_id, day, idx, occupied_by_slot[idx], has_before, has_after)
            penalties.append(is_gap * weight)
        return penalties

    def _build_or_var(self, name: str, vars_list: list):
        or_var = self.model.NewBoolVar(name)
        for var in vars_list:
            self.model.Add(or_var >= var)
        self.model.Add(or_var <= sum(vars_list))
        return or_var

    def _build_gap_var(self, label: str, entity_id: int, day: int, idx: int, occupied, has_before, has_after):
        is_empty = self.model.NewBoolVar(f"{label}_{entity_id}_{day}_{idx}_empty")
        self.model.Add(is_empty == 1 - occupied)

        is_gap = self.model.NewBoolVar(f"{label}_{entity_id}_{day}_{idx}_gap")
        self.model.Add(is_gap <= has_before)
        self.model.Add(is_gap <= has_after)
        self.model.Add(is_gap <= is_empty)
        self.model.Add(is_gap >= has_before + has_after + is_empty - 2)
        return is_gap

    def _build_fill_rewards(self) -> list:
        """Recompensa sessões válidas para aumentar preenchimento semanal viável."""
        rewards: list = []
        for lesson in self.lessons:
            if lesson.remaining_minutes <= 0:
                continue
            for ts in self.timeslots:
                rewards.append(-self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)] * REWARD_SCHEDULED_SESSION)
        return rewards

    def _build_class_day_spread_penalties(self) -> list:
        """Penaliza horários excessivamente dispersos por muitos dias da semana."""
        penalties: list = []

        class_lessons: dict[int, list[LessonInput]] = defaultdict(list)
        for lesson in self.lessons:
            class_lessons[lesson.class_id].append(lesson)

        days = sorted({ts.day_of_week for ts in self.timeslots})

        for class_id, lessons in class_lessons.items():
            for day in days:
                day_slots = [
                    self.lesson_at_ts[(lesson.lesson_id, ts.ts_id)]
                    for lesson in lessons
                    for ts in self.timeslots
                    if ts.day_of_week == day
                ]
                if not day_slots:
                    continue

                day_active = self.model.NewBoolVar(f"class_{class_id}_day_{day}_active")
                for var in day_slots:
                    self.model.Add(day_active >= var)
                self.model.Add(day_active <= sum(day_slots))
                penalties.append(day_active * PENALTY_CLASS_DAY_SPREAD)

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