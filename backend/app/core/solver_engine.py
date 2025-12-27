from ortools.sat.python import cp_model
from app.models import ConstraintType

class ScheduleEngine:
    def __init__(self, lessons, timeslots, rooms, teachers, classes, constraints):
        """
        Recebe todos os dados necessários para o cálculo, desacoplados da BD.
        """
        self.lessons = lessons
        self.timeslots = timeslots
        self.rooms = rooms
        self.teachers = teachers
        self.classes = classes  # <--- CRUCIAL: Adicionado para a Regra 2
        self.constraints = constraints
        
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        
        # Variáveis de Decisão
        self.aula_agendada = {} 
        self.teacher_active = {} # <--- CRUCIAL: Para a Regra 3 e Otimização

    def solve(self):
        """Executa a lógica matemática."""
        self._create_variables()
        self._apply_hard_constraints()
        self._apply_soft_constraints() # <--- Onde está a otimização de "buracos"
        
        # Podes ajustar o tempo máximo aqui se quiseres
        # self.solver.parameters.max_time_in_seconds = 30 
        
        status = self.solver.Solve(self.model)
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            return self._format_solution(self.solver.ObjectiveValue())
        return None

    def _create_variables(self):
        # 1. Variável Principal: [Aula, Tempo, Sala] -> 0 ou 1
        for lesson in self.lessons:
            for t in self.timeslots:
                for r in self.rooms:
                    self.aula_agendada[(lesson.id, t.id, r.id)] = \
                        self.model.NewBoolVar(f'aula_{lesson.id}_{t.id}_{r.id}')

        # 2. Variável Auxiliar: [Professor, Tempo] -> Está a dar aula? (0 ou 1)
        # Lógica: Se o professor X tem alguma aula agendada no tempo T, teacher_active = 1
        for teacher in self.teachers:
            for t in self.timeslots:
                self.teacher_active[(teacher.id, t.id)] = self.model.NewBoolVar(f'prof_{teacher.id}_{t.id}')
                
                # Filtrar aulas deste professor
                lessons_of_teacher = [l for l in self.lessons if l.teacher_id == teacher.id]
                
                if lessons_of_teacher:
                    # A soma das aulas deste professor neste tempo (em todas as salas) 
                    # deve ser igual à variável teacher_active.
                    # Como na Regra 3 forçamos teacher_active <= 1, isto funciona.
                    self.model.Add(
                        sum(self.aula_agendada[(l.id, t.id, r.id)] 
                            for l in lessons_of_teacher 
                            for r in self.rooms) == self.teacher_active[(teacher.id, t.id)]
                    )
                else:
                    # Se não tem aulas, nunca está ativo
                    self.model.Add(self.teacher_active[(teacher.id, t.id)] == 0)

    def _apply_hard_constraints(self):
        # --- REGRAS BÁSICAS (HARD) ---
        
        # 1. Aulas por semana (Respeita o num_per_week)
        for lesson in self.lessons:
            self.model.Add(
                sum(self.aula_agendada[(lesson.id, t.id, r.id)] 
                    for t in self.timeslots for r in self.rooms) == lesson.num_per_week
            )
            
        # 2. Turma (max 1 aula por slot)
        # Garante que a Turma 12ºA não tem Português e Matemática ao mesmo tempo
        for timeslot in self.timeslots:
            for cls in self.classes:
                # Otimização Python: Pré-filtrar aulas da turma
                lessons_of_class = [l for l in self.lessons if l.class_id == cls.id]
                
                if lessons_of_class:
                    self.model.Add(
                        sum(self.aula_agendada[(l.id, timeslot.id, r.id)] 
                            for l in lessons_of_class 
                            for r in self.rooms) <= 1
                    )
        
        # 3. Professor (max 1 aula por slot)
        # Como já ligámos a variável teacher_active às aulas, basta limitar essa variável
        for timeslot in self.timeslots:
            for teacher in self.teachers:
                self.model.Add(self.teacher_active[(teacher.id, timeslot.id)] <= 1)
        
        # 4. Sala (max 1 aula por slot)
        for timeslot in self.timeslots:
            for room in self.rooms:
                self.model.Add(
                    sum(self.aula_agendada[(l.id, timeslot.id, room.id)] 
                        for l in self.lessons) <= 1
                )

    def _apply_soft_constraints(self):
        """Aplica preferências e otimização de compactação (evitar furos)."""
        penalties = []
        
        # A. PREFERÊNCIAS (Constraints da BD)
        for c in self.constraints:
            
            # Caso 1: Professor Indisponível (Hard na prática)
            if c.rule_type == ConstraintType.teacher_unavailable:
                tid = c.rule_payload.get("teacher_id")
                slid = c.rule_payload.get("timeslot_id")
                if tid and slid and (tid, slid) in self.teacher_active:
                    self.model.Add(self.teacher_active[(tid, slid)] == 0)

            # Caso 2: Preferência (Soft)
            elif c.rule_type == ConstraintType.teacher_preferred:
                tid = c.rule_payload.get("teacher_id")
                slid = c.rule_payload.get("timeslot_id")
                if tid and slid and (tid, slid) in self.teacher_active:
                    # Penaliza se tiver aula neste tempo (assumindo que prefere NÃO ter)
                    # Ajusta conforme a tua lógica de negócio
                    penalties.append(self.teacher_active[(tid, slid)] * 20)

        # B. OTIMIZAÇÃO DE BLOCOS (Compactação)
        # Queremos minimizar o número de vezes que um professor "começa" a dar aulas.
        # Aula-Aula-Aula = 1 início. Aula-Furo-Aula = 2 inícios.
        
        # Organizar slots por dia
        slots_by_day = {}
        for ts in self.timeslots:
            if ts.day_of_week not in slots_by_day: slots_by_day[ts.day_of_week] = []
            slots_by_day[ts.day_of_week].append(ts)
        
        # Ordenar por hora
        for day in slots_by_day:
            slots_by_day[day].sort(key=lambda x: x.start_time)

        for teacher in self.teachers:
            for day, day_slots in slots_by_day.items():
                for i in range(len(day_slots)):
                    t_curr = day_slots[i]
                    
                    curr_active = self.teacher_active[(teacher.id, t_curr.id)]
                    prev_active = 0
                    
                    if i > 0:
                        t_prev = day_slots[i-1]
                        prev_active = self.teacher_active[(teacher.id, t_prev.id)]
                    
                    # Variável is_start: É 1 se [0 -> 1] (começou um bloco)
                    is_start = self.model.NewBoolVar(f"start_{teacher.id}_{t_curr.id}")
                    self.model.Add(is_start >= curr_active - prev_active)
                    
                    penalties.append(is_start * 50)

        # C. MINIMIZAR PENALIDADES
        if penalties:
            self.model.Minimize(sum(penalties))

    def _format_solution(self, score):
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