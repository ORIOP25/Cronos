# Ficheiro: backend/app/core/solver_engine.py

from ortools.sat.python import cp_model
from app.models import ConstraintType, PreferenceLevel
import logging

logger = logging.getLogger(__name__)

class ScheduleEngine:
    def __init__(self, lessons, timeslots, rooms, teachers, classes, constraints, availabilities):
        """
        O Motor Matemático.
        Recebe dados puros (Listas de objetos) e devolve a solução.
        """
        self.lessons = lessons
        self.timeslots = timeslots
        self.rooms = rooms
        self.teachers = teachers
        self.classes = classes
        self.constraints = constraints
        
        # Mapa de Disponibilidade Otimizado (Hash Map)
        # Chave: (teacher_id, timeslot_id) -> Valor: Score (-1, 0, 1, 2)
        # Se não existir entrada, assumimos 1 (Neutro)
        self.availability_map = {
            (a.teacher_id, a.timeslot_id): a.score 
            for a in availabilities
        }
        
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        self.last_score = 0
        
        # Variáveis de Decisão
        self.aula_agendada = {}   # (lesson_id, timeslot_id, room_id) -> Bool
        self.teacher_active = {}  # (teacher_id, timeslot_id) -> Bool

    def solve(self):
        logger.info(f"🧠 Engine a iniciar... {len(self.availability_map)} regras de disponibilidade carregadas.")
        """Executa a lógica de resolução."""
        self._create_variables()
        self._apply_hard_constraints()
        self._apply_soft_constraints()
        
        # Configuração do Solver
        self.solver.parameters.max_time_in_seconds = 60
        self.solver.parameters.linearization_level = 0
        
        status = self.solver.Solve(self.model)
        
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            self.last_score = self.solver.ObjectiveValue()
            return self._format_solution()
        return None

    def _link_teacher_active_var(self, teacher, t):
        """Liga a variável teacher_active[…] às variáveis de aulas desse professor."""
        lessons_of_teacher = [l for l in self.lessons if l.teacher_id == teacher.id]
        relevant_vars = []
        for l in lessons_of_teacher:
            for r in self.rooms:
                relevant_vars.append(self.aula_agendada[(l.id, t.id, r.id)])
        if relevant_vars:
            self.model.Add(self.teacher_active[(teacher.id, t.id)] == sum(relevant_vars))
        else:
            self.model.Add(self.teacher_active[(teacher.id, t.id)] == 0)

    def _create_variables(self):
        """Cria as variáveis do problema (X_ltr)."""

        # 1. Variável Principal: Aula L ocorre no Tempo T na Sala R?
        for l in self.lessons:
            for t in self.timeslots:
                for r in self.rooms:
                    self.aula_agendada[(l.id, t.id, r.id)] = self.model.NewBoolVar(
                        f"aula_{l.id}_{t.id}_{r.id}"
                    )

        # 2. Variável Auxiliar: Professor P está a trabalhar no Tempo T?
        for teacher in self.teachers:
            for t in self.timeslots:
                self.teacher_active[(teacher.id, t.id)] = self.model.NewBoolVar(
                    f"teacher_active_{teacher.id}_{t.id}"
                )
                self._link_teacher_active_var(teacher, t)

    def _apply_impossible_availability_constraints(self):
        """Regra 5: Bloqueia slots onde o professor marcou IMPOSSÍVEL (-1)."""
        for teacher in self.teachers:
            for t in self.timeslots:
                score = self.availability_map.get((teacher.id, t.id), 1)
                if score == -1:
                    self.model.Add(self.teacher_active[(teacher.id, t.id)] == 0)

    def _apply_hard_constraints(self):
        """Regras que NÃO podem ser quebradas (Vermelho)."""

        # Regra 1: Cada aula tem de acontecer exatamente X vezes
        for l in self.lessons:
            slots_per_week = getattr(l, 'num_per_week', 1)
            self.model.Add(
                sum(self.aula_agendada[(l.id, t.id, r.id)]
                    for t in self.timeslots
                    for r in self.rooms) == slots_per_week
            )

        # Regra 2: Turma não pode estar em dois sítios ao mesmo tempo
        for c in self.classes:
            lessons_of_class = [l for l in self.lessons if l.class_id == c.id]
            for t in self.timeslots:
                self.model.Add(
                    sum(self.aula_agendada[(l.id, t.id, r.id)]
                        for l in lessons_of_class
                        for r in self.rooms) <= 1
                )

        # Regra 3: Professor não pode estar em dois sítios
        for teacher in self.teachers:
            for t in self.timeslots:
                self.model.Add(self.teacher_active[(teacher.id, t.id)] <= 1)

        # Regra 4: Sala não pode ter duas turmas
        for r in self.rooms:
            for t in self.timeslots:
                self.model.Add(
                    sum(self.aula_agendada[(l.id, t.id, r.id)]
                        for l in self.lessons) <= 1
                )

        # Regra 5: Disponibilidade IMPOSSÍVEL (-1)
        self._apply_impossible_availability_constraints()

    def _get_slots_by_day(self):
        """Agrupa e ordena os timeslots por dia da semana."""
        slots_by_day = {}
        for t in self.timeslots:
            if t.day_of_week not in slots_by_day:
                slots_by_day[t.day_of_week] = []
            slots_by_day[t.day_of_week].append(t)
        for day in slots_by_day:
            slots_by_day[day].sort(key=lambda x: x.start_time)
        return slots_by_day

    def _apply_availability_preferences(self, teacher, penalties):
        """Adiciona penalidades por AVOID e recompensas por PREFERRED."""
        for t in self.timeslots:
            score = self.availability_map.get((teacher.id, t.id), 1)
            if score == 0:  # AVOID
                penalties.append(self.teacher_active[(teacher.id, t.id)] * 20)
            if score == 2:  # PREFERRED
                is_missing = self.model.NewBoolVar(f"missing_{teacher.id}_{t.id}")
                self.model.Add(is_missing == 1 - self.teacher_active[(teacher.id, t.id)])
                penalties.append(is_missing * 10)

    def _apply_gap_penalties(self, teacher, day_slots, penalties):
        """Adiciona penalidades por buracos no horário do professor."""
        for i in range(len(day_slots)):
            t_curr = day_slots[i]
            curr_active = self.teacher_active[(teacher.id, t_curr.id)]
            prev_active = 0
            if i > 0:
                t_prev = day_slots[i - 1]
                prev_active = self.teacher_active[(teacher.id, t_prev.id)]
            is_start = self.model.NewBoolVar(f"start_{teacher.id}_{t_curr.id}")
            self.model.Add(is_start >= curr_active - prev_active)
            penalties.append(is_start * 50)

    def _apply_soft_constraints(self):
        """Regras que custam pontos (Laranja e Buracos)."""
        penalties = []
        slots_by_day = self._get_slots_by_day()

        for teacher in self.teachers:
            self._apply_availability_preferences(teacher, penalties)
            for day_slots in slots_by_day.values():
                self._apply_gap_penalties(teacher, day_slots, penalties)

        if penalties:
            self.model.Minimize(sum(penalties))

    def _format_solution(self):
        solution = []
        for l in self.lessons:
            for t in self.timeslots:
                for r in self.rooms:
                    if self.solver.Value(self.aula_agendada[(l.id, t.id, r.id)]) == 1:
                        solution.append({
                            "lesson_id": l.id,
                            "timeslot_id": t.id,
                            "room_id": r.id
                        })
        return solution