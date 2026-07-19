from celery import Celery

from .config import settings

# 1. Cria a instância do Celery
celery_app = Celery(
    "cronos_worker",
    broker=settings.CELERY_BROKER_URL,
)

# 2. Configurações adicionais
celery_app.conf.update(
    task_ignore_result=True,
    result_backend=None,
    # Serialização segura
    task_serializer="json",
    accept_content=["json"],
    timezone="Europe/Lisbon",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    # ----------------------------------------------------------------
    # Celery Beat — Tarefas periódicas (Sprint 2)
    # ----------------------------------------------------------------
    beat_schedule={
        "members-scheduled-reconciliation-hourly": {
            "task": "members.run_scheduled_reconciliation",
            "schedule": 3600.0,
        },
    },
    imports=("app.scheduler_worker", "app.member_reconciliation_worker"),
)

if __name__ == "__main__":
    celery_app.start()
