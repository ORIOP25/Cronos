# Ficheiro: backend/app/solver_tasks.py

import datetime
import redis
import structlog
from celery import Task
from .celery_worker import celery_app
from app.db.database import SessionLocalSync
from app.config import settings

# Serviços para buscar dados
from app.services import (
    teacher_service, 
    class_service, 
    room_service, 
    schedule_service
)

# O Motor Matemático (Onde a magia acontece)
from app.core.solver_engine import ScheduleEngine

logger = structlog.get_logger()

@celery_app.task(bind=True)
def generate_schedule_task(self: Task, org_id: int):
    """
    Orquestrador de Geração de Horários.
    Função:
    1. Ler dados da BD (Input).
    2. Chamar o ScheduleEngine (Processamento).
    3. Gravar resultados na BD (Output).
    """
    logger.info("Iniciando tarefa de geração", org_id=org_id)
    gen_id = f"gen_{datetime.datetime.now().isoformat()}"
    
    # Usamos sessão síncrona porque o Celery/OR-Tools bloqueiam a thread de qualquer forma
    db = SessionLocalSync()
    
    try:
        # --- 1. FETCH (Ler dados) ---
        self.update_state(state='FETCHING', meta={'detail': 'A ler dados...'})
        
        # Dados Base
        lessons = schedule_service.get_lessons_by_org_sync(db, org_id)
        timeslots = schedule_service.get_timeslots_by_org_sync(db, org_id)
        rooms = room_service.get_rooms_by_org_sync(db, org_id)
        teachers = teacher_service.get_teachers_by_org_sync(db, org_id)
        classes = class_service.get_classes_by_org_sync(db, org_id)
        constraints = schedule_service.get_constraints_by_org_sync(db, org_id)
        availabilities = schedule_service.get_availabilities_by_org_sync(db, org_id)

        # --- LOGS DE DEBUG (PARA APANHAR O ERRO) ---
        logger.info(f"📊 DADOS CARREGADOS PARA ORG {org_id}:")
        logger.info(f"   - Aulas: {len(lessons)}")
        logger.info(f"   - Timeslots: {len(timeslots)}")
        logger.info(f"   - Professores: {len(teachers)}")
        logger.info(f"   - Disponibilidades: {len(availabilities)}") # <--- ISTO VAI SER CRÍTICO
        
        if availabilities:
            # Mostra a primeira regra para ver se o formato está ok
            a = availabilities[0]
            logger.info(f"   - Exemplo Disponibilidade: Prof {a.teacher_id} no Slot {a.timeslot_id} = Score {a.score}")
        else:
            logger.warning("⚠️ ALERTA: Nenhuma disponibilidade encontrada! O horário será gerado sem preferências.")
        
        if not lessons or not timeslots:
            return {'status': 'Error', 'message': "Faltam dados base (Aulas ou Horários)."}

        # --- 2. SOLVE (Processamento) ---
        self.update_state(state='SOLVING', meta={'detail': 'A otimizar horário...'})
        
        # Instanciamos o motor com TODOS os dados
        # NOTA: O Engine vai precisar de atualização no próximo passo para aceitar 'availabilities'
        engine = ScheduleEngine(
            lessons=lessons,
            timeslots=timeslots,
            rooms=rooms,
            teachers=teachers,
            classes=classes,
            constraints=constraints,
            availabilities=availabilities # <--- Passamos os dados novos aqui
        )
        
        # O motor devolve uma lista de dicionários ou None
        solution = engine.solve()

        # --- 3. SAVE (Gravar Resultados) ---
        if solution:
            self.update_state(state='SAVING', meta={'detail': 'A gravar solução...'})
            
            # Limpar horário antigo
            schedule_service.clear_schedule_sync(db, org_id)
            
            # Gravar novo horário
            count = 0
            for item in solution:
                schedule_service.create_schedule_output_sync(
                    db, 
                    lesson_id=item['lesson_id'], 
                    timeslot_id=item['timeslot_id'], 
                    room_id=item['room_id'], 
                    org_id=org_id, 
                    gen_id=gen_id
                )
                count += 1
            
            db.commit()
            
            # Invalidação de Cache (Redis)
            try:
                r = redis.Redis.from_url(str(settings.REDIS_URL))
                CACHE_KEY = f"schedule_latest_data_{org_id}"
                r.delete(CACHE_KEY)
                logger.info("Cache invalidated", key=CACHE_KEY)
            except Exception as e:
                logger.warning("Cache invalidation failed", error=str(e))

            logger.info("Geração concluída com sucesso", count=count)
            return {
                'status': 'Success', 
                'generation_id': gen_id, 
                'count': count
            }
        
        else:
            logger.info("Impossível gerar horário", org_id=org_id)
            return {
                'status': 'Impossible', 
                'message': "Não foi possível encontrar uma solução válida com as restrições atuais."
            }

    except Exception as e:
        db.rollback()
        logger.error("Erro crítico na geração", error=str(e), exc_info=True)
        return {'status': 'Error', 'message': str(e)}
    
    finally:
        db.close()