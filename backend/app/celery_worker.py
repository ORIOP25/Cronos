from celery import Celery

from .config import settings

# Beat only publishes task names, so this module imports no task modules.
# Each worker imports the modules whose tasks it executes.
celery_app = Celery(
    "cronos_worker",
    broker=settings.CELERY_BROKER_URL,
)

celery_app.conf.update(
    task_ignore_result=True,
    result_backend=None,
    task_serializer="json",
    accept_content=["json"],
    timezone="Europe/Lisbon",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "members-scheduled-reconciliation-hourly": {
            "task": "members.run_scheduled_reconciliation",
            "schedule": 3600.0,
        },
        "privacy-maintenance-daily": {
            "task": "privacy.run_maintenance",
            "schedule": 86400.0,
        },
        # The supervisor must run outside the solving worker: a blocked solve
        # cannot delay the recovery of an abandoned attempt.
        "scheduler-v1-supervise": {
            "task": "scheduler.v1.supervise",
            "schedule": 60.0,
            "options": {"queue": "scheduler-supervisor"},
        },
    },
)

if __name__ == "__main__":
    celery_app.start()
