from celery import Celery
from celery.schedules import crontab
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
    beat_schedule={
        # Corre todos os dias às 23:59 (hora de Lisboa) para confirmar
        # automaticamente as aulas que decorreram hoje sem registo manual.
        "auto-confirm-occurrences-daily": {
            "task": "app.solver_tasks.auto_confirm_occurrences_task",
            "schedule": crontab(hour=23, minute=59),
        },
    },
)

# 3. Diz ao Celery onde encontrar as tarefas
celery_app.autodiscover_tasks(["app.solver_tasks"])

if __name__ == "__main__":
    celery_app.start()
