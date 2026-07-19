from typing import Protocol


class SchedulerTaskDispatcher(Protocol):
    def dispatch(self, *, organization_id: int, job_id: int, task_id: str) -> None: ...
