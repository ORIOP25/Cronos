import pytest
from app.core.solver_engine import ScheduleEngine
from app.models import ConstraintType

# Um Mock mais robusto que aceita qualquer atributo
class MockObj:
    def __init__(self, id, **kwargs):
        self.id = id
        self.__dict__.update(kwargs)

def test_solver_simple_case_with_classes():
    # 1. Preparar Dados Falsos (Compatíveis com a nova Engine)
    
    # Aula: ID 1, Professor 1, Turma 1, 1 vez por semana
    lessons = [
        MockObj(id=1, teacher_id=1, class_id=1, num_per_week=1)
    ]
    
    # 1 Tempo, 1 Sala, 1 Professor, 1 Turma
    timeslots = [MockObj(id=1, day_of_week="Segunda", start_time="08:30")]
    rooms = [MockObj(id=1)]
    teachers = [MockObj(id=1)]
    classes = [MockObj(id=1)] # <--- Engine agora exige isto
    
    constraints = []

    # 2. Inicializar a Engine
    engine = ScheduleEngine(lessons, timeslots, rooms, teachers, classes, constraints)

    # 3. Resolver
    result = engine.solve()

    # 4. Verificar Sucesso
    assert result is not None
    assert len(result) == 1
    assert result[0]["lesson_id"] == 1
    assert result[0]["timeslot_id"] == 1
    assert result[0]["room_id"] == 1

def test_solver_conflict_class():
    """Testa a Regra 2: A mesma turma não pode ter 2 aulas ao mesmo tempo."""
    
    # Duas aulas para a MESMA turma (class_id=1)
    # Mas só há 1 Tempo disponível.
    lessons = [
        MockObj(id=1, teacher_id=1, class_id=1, num_per_week=1),
        MockObj(id=2, teacher_id=2, class_id=1, num_per_week=1) 
    ]
    
    timeslots = [MockObj(id=1, day_of_week="Segunda", start_time="08:30")]
    rooms = [MockObj(id=1), MockObj(id=2)] # Há salas suficientes
    teachers = [MockObj(id=1), MockObj(id=2)] # Há professores suficientes
    classes = [MockObj(id=1)] # Só há 1 turma
    
    constraints = []

    engine = ScheduleEngine(lessons, timeslots, rooms, teachers, classes, constraints)
    result = engine.solve()

    # Deve falhar (None) porque a turma não se pode dividir em dois
    assert result is None