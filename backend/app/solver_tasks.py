# Ficheiro: app/solver_tasks.py (Versão 6 - Com Otimização de Blocos)

import datetime
import json
import redis
import traceback
import structlog
from celery import Task
from ortools.sat.python import cp_model
from .celery_worker import celery_app
from app.db.database import SessionLocalSync
from app.services import (
    teacher_service, 
    class_service, 
    subject_service, 
    room_service, 
    schedule_service
)
from app.models import ConstraintType
from app.config import settings

logger = structlog.get_logger()

@celery_app.task(bind=True)
def generate_schedule_task(self: Task, org_id: int):
    logger.info("Iniciando tarefa de geração", org_id=org_id)
    gen_id = f"gen_{datetime.datetime.now().isoformat()}"
    
    db = SessionLocalSync()
    
    try:
        # --- FETCH (Ler dados) ---
        self.update_state(state='FETCHING', meta={'detail': 'A ler dados...'})
        
        all_lessons = schedule_service.get_lessons_by_org_sync(db, org_id)
        all_timeslots = schedule_service.get_timeslots_by_org_sync(db, org_id)
        all_rooms = room_service.get_rooms_by_org_sync(db, org_id)
        all_constraints = schedule_service.get_constraints_by_org_sync(db, org_id)
        all_teachers = teacher_service.get_teachers_by_org_sync(db, org_id)
        all_classes = class_service.get_classes_by_org_sync(db, org_id)
        
        if not all_lessons or not all_timeslots:
            return {'status': 'Error', 'message': "Faltam dados base."}

        # --- MODELING (Criar Modelo Matemático) ---
        self.update_state(state='MODELLING', meta={'detail': 'A aplicar regras...'})
        
        model = cp_model.CpModel()
        
        # Variável Principal: aula_agendada[(lesson, timeslot, room)]
        aula_agendada = {}
        for lesson in all_lessons:
            for timeslot in all_timeslots:
                for room in all_rooms:
                    var_name = f"l{lesson.id}_t{timeslot.id}_r{room.id}"
                    aula_agendada[(lesson.id, timeslot.id, room.id)] = model.NewBoolVar(var_name)

        # Variável Auxiliar: teacher_active[(teacher, timeslot)]
        # Será 1 se o professor estiver a dar QUALQUER aula neste slot
        teacher_active = {}
        for teacher in all_teachers:
            for timeslot in all_timeslots:
                teacher_active[(teacher.id, timeslot.id)] = model.NewBoolVar(f"teach_{teacher.id}_t{timeslot.id}")
                
                # Ligação: teacher_active é a soma das aulas dele neste slot
                # (Como ele só pode dar 1 aula, a soma será 0 ou 1)
                model.Add(
                    teacher_active[(teacher.id, timeslot.id)] == sum(
                        aula_agendada[(l.id, timeslot.id, r.id)]
                        for l in all_lessons if l.teacher_id == teacher.id
                        for r in all_rooms
                    )
                )

        # --- REGRAS BÁSICAS (HARD) ---
        # 1. Aulas por semana
        for lesson in all_lessons:
            model.Add(sum(aula_agendada[(lesson.id, t.id, r.id)] for t in all_timeslots for r in all_rooms) == lesson.num_per_week)
        
        # 2. Turma (max 1 aula por slot)
        for timeslot in all_timeslots:
            for lesson_class in all_classes:
                model.Add(sum(aula_agendada[(l.id, timeslot.id, r.id)] for l in all_lessons if l.class_id == lesson_class.id for r in all_rooms) <= 1)
        
        # 3. Professor (max 1 aula por slot) - Já garantido pela variavel teacher_active <= 1
        for timeslot in all_timeslots:
            for teacher in all_teachers:
                model.Add(teacher_active[(teacher.id, timeslot.id)] <= 1)
        
        # 4. Sala (max 1 aula por slot)
        for timeslot in all_timeslots:
            for room in all_rooms:
                model.Add(sum(aula_agendada[(l.id, timeslot.id, room.id)] for l in all_lessons) <= 1)

        # --- PONTUAÇÃO (OBJETIVO) ---
        penalties = []

        # ==========================================
        # A. PREFERÊNCIAS & REGRAS (Constraints da BD)
        # ==========================================
        for constraint in all_constraints:
            
            # --- CASO 1: Professor Indisponível (Regra Rígida/Hard) ---
            if constraint.rule_type == ConstraintType.teacher_unavailable:
                teacher_id = constraint.rule_payload.get("teacher_id")
                timeslot_id = constraint.rule_payload.get("timeslot_id")
                
                # Só aplicamos se os dados existirem e se as variáveis existirem no modelo
                if teacher_id and timeslot_id:
                    if (teacher_id, timeslot_id) in teacher_active:
                        # Força a atividade a 0 (Não pode dar aula)
                        model.Add(teacher_active[(teacher_id, timeslot_id)] == 0)

            # --- CASO 2: Preferência do Professor (Regra Suave/Soft) ---
            elif constraint.rule_type == ConstraintType.teacher_preferred:
                teacher_id = constraint.rule_payload.get("teacher_id")
                timeslot_id = constraint.rule_payload.get("timeslot_id")
                
                if teacher_id and timeslot_id:
                    if (teacher_id, timeslot_id) in teacher_active:
                        # Se o professor NÃO estiver a dar aula neste tempo, paga multa.
                        # (Ou seja, ele PREFERE dar aula aqui, logo queremos que seja 1)
                        # Se teacher_active for 0, somamos penalidade.
                        # Nota: A tua lógica original estava a penalizar se ele TIVESSE aula (active * 20).
                        # Vou assumir que 'preferred' significa "Prefere NÃO dar aula"? 
                        # Se for "Prefere TER aula", a lógica seria (1 - active) * 20.
                        # MANTIVE A TUA LÓGICA ORIGINAL: Penaliza se tiver aula.
                        penalties.append(teacher_active[(teacher_id, timeslot_id)] * 20)

        # ==========================================
        # B. OTIMIZAÇÃO DE BLOCOS (Agrupar aulas)
        # ==========================================
        # Objetivo: Evitar "buracos" no horário dos professores.
        
        # 1. Organizar os tempos por dia
        slots_by_day = {}
        for timeslot in all_timeslots:
            if timeslot.day_of_week not in slots_by_day:
                slots_by_day[timeslot.day_of_week] = []
            slots_by_day[timeslot.day_of_week].append(timeslot)
        
        # Ordenar cronologicamente (08:30, 09:30, 10:30...)
        for day in slots_by_day:
            slots_by_day[day].sort(key=lambda x: x.start_time)

        # 2. Calcular penalidades de "furos" para cada professor
        for teacher in all_teachers:
            for day, day_slots in slots_by_day.items():
                
                # Percorrer todos os tempos do dia
                for i in range(len(day_slots)):
                    current_slot = day_slots[i]
                    
                    # Verificar se o professor tem aula AGORA
                    current_is_active = teacher_active[(teacher.id, current_slot.id)]
                    
                    # Verificar se o professor tinha aula ANTES (Previous)
                    if i > 0:
                        previous_slot = day_slots[i-1]
                        previous_is_active = teacher_active[(teacher.id, previous_slot.id)]
                    else:
                        # Se for o primeiro tempo do dia, antes era "nada" (0)
                        previous_is_active = 0
                    
                    # --- LÓGICA DE INÍCIO DE BLOCO ---
                    # is_start será 1 se: Agora tem aula (1) E antes não tinha (0). 
                    # Diferença: 1 - 0 = 1.
                    # Se for aula contínua (1 e 1), diferença é 0.
                    # Se for buraco (0 e 0), diferença é 0.
                    # Se for fim de aula (0 e 1), diferença é -1.
                    
                    is_start_var = model.NewBoolVar(f"start_block_{teacher.id}_{current_slot.id}")
                    
                    # Restrição: is_start >= atual - anterior
                    model.Add(is_start_var >= current_is_active - previous_is_active)
                    
                    # Penalidade: Cada vez que um professor "começa" a dar aulas num dia, paga 50 pontos.
                    # Se ele der 3 aulas seguidas, só "começa" 1 vez (Paga 50).
                    # Se ele der Aula, Furo, Aula, ele "começa" 2 vezes (Paga 100).
                    penalties.append(is_start_var * 50)

        # ==========================================
        # C. OBJETIVO FINAL
        # ==========================================
        if penalties:
            model.Minimize(sum(penalties))

        # --- SOLVE ---
        self.update_state(state='SOLVING', meta={'detail': 'A resolver...'})
        solver = cp_model.CpSolver()
        # solver.parameters.max_time_in_seconds = 30 # Opcional: timeout
        status = solver.Solve(model)

        # --- SAVE ---
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            self.update_state(state='SAVING', meta={'detail': 'A guardar...'})
            
            schedule_service.clear_schedule_sync(db, org_id)
            
            count = 0
            for lesson in all_lessons:
                for timeslot in all_timeslots:
                    for room in all_rooms:
                        if solver.Value(aula_agendada[(lesson.id, timeslot.id, room.id)]) == 1:
                            schedule_service.create_schedule_output_sync(
                                db, lesson.id, timeslot.id, room.id, org_id, gen_id
                            )
                            count += 1
            
            db.commit() # <--- Dados gravados na base de dados

            # === [MUDANÇA: CACHE INVALIDATION COM LOGS] ===
            try:
                # [LOG] Informação de contexto
                logger.info("Invalidating schedule cache", org_id=org_id)
                
                r = redis.Redis.from_url(str(settings.REDIS_URL))
                CACHE_KEY = f"schedule_latest_data_{org_id}" 
                r.delete(CACHE_KEY)
                
                # [LOG] Sucesso
                logger.info("Cache invalidated successfully", key=CACHE_KEY)
                
            except Exception as cache_e:
                # [LOG] Warning (Amarelo) - Não parte a app, mas avisa
                logger.warning("Failed to invalidate cache", error=str(cache_e))
            # === [FIM DA MUDANÇA] ===

            return {'status': 'Success', 'generation_id': gen_id, 'score': solver.ObjectiveValue()}
        
        else:
            logger.info("Solver failed to find solution", org_id=org_id) # [LOG] Info útil
            return {'status': 'Impossible', 'message': "Não foi possível gerar um horário com estas restrições."}

    except Exception as e:
        db.rollback()
        error_msg = f"{str(e)}"
        
        # [LOG] Erro Crítico (Vermelho) com Traceback automático
        logger.error("Critical task failure", error=error_msg, exc_info=True)
        
        return {'status': 'Error', 'message': error_msg}
    
    finally:
        db.close()