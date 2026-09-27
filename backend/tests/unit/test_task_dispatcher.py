from app.scheduler.infrastructure import task_dispatcher


def test_dispatch_wakes_the_v1_executor_task(monkeypatch):
    calls = []

    def send_task(name, **kwargs):
        calls.append((name, kwargs))

    monkeypatch.setattr(task_dispatcher.celery_app, "send_task", send_task)

    task_dispatcher.CelerySchedulerTaskDispatcher().dispatch(
        organization_id=7,
        job_id=42,
        task_id="scheduler-job-42",
    )

    assert calls == [
        ("scheduler.v1.run_next_job", {"task_id": "scheduler-job-42"}),
    ]
