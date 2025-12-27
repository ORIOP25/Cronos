from celery import Celery
from app.db.database import SessionLocal
from app.services import (
    schedule_service, 
    teacher_service, 
    class_service, 
    subject_service, 
    room_service
)
from .config import settings

# 1. Cria a instância do Celery
celery_app = Celery(
    "horario_zen_worker",  # Nome do nosso worker
    broker=settings.CELERY_BROKER_URL, # Onde está o "Carteiro" (Redis)
    backend=settings.CELERY_BROKER_URL  # Onde guardar os resultados (usamos o Redis para ambos)
)

# 2. Configurações adicionais
celery_app.conf.update(
    task_track_started=True, # Para podermos ver tarefas em progresso
)

# 3. Diz ao Celery onde encontrar as nossas "tarefas"
# Vamos criar este ficheiro 'app.solver_tasks' a seguir
celery_app.autodiscover_tasks(['app.solver_tasks'])

if __name__ == "__main__":
    celery_app.start()