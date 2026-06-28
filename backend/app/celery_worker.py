from celery import Celery
from .config import settings

# 1. Cria a instância do Celery
celery_app = Celery(
    "cronos_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
)

# 2. Configurações adicionais
celery_app.conf.update(
    task_track_started=True,
    # Serialização segura
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Lisbon",
    enable_utc=True,
    # ----------------------------------------------------------------
    # Celery Beat — Tarefas periódicas (Sprint 2)
    # ----------------------------------------------------------------
    beat_schedule={},
    imports=("app.scheduler_worker",),
)

# 3. Diz ao Celery onde encontrar as tarefas
celery_app.autodiscover_tasks(["app.scheduler_worker"])

if __name__ == "__main__":
    celery_app.start()
