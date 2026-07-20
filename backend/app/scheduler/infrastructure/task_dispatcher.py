from app.scheduler_worker import run_schedule_generation_job_task


class CelerySchedulerTaskDispatcher:
    def dispatch(self, *, organization_id: int, job_id: int, task_id: str) -> None:
        run_schedule_generation_job_task.apply_async(
            args=[organization_id, job_id],
            task_id=task_id,
        )
