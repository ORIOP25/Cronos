from app.celery_worker import celery_app


class CelerySchedulerTaskDispatcher:
    def dispatch(self, *, organization_id: int, job_id: int, task_id: str) -> None:
        celery_app.send_task(
            "scheduler.run_generation_job",
            args=[organization_id, job_id],
            task_id=task_id,
        )
