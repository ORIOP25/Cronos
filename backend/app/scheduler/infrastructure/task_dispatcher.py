from app.celery_worker import celery_app

V1_EXECUTOR_TASK = "scheduler.v1.run_next_job"


class CelerySchedulerTaskDispatcher:
    """Wake the global scheduler v1 executor; the database decides the job."""

    def dispatch(self, *, organization_id: int, job_id: int, task_id: str) -> None:
        celery_app.send_task(V1_EXECUTOR_TASK, task_id=task_id)
