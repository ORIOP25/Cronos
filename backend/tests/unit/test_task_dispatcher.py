from app.scheduler.infrastructure import task_dispatcher


def test_dispatch_sends_named_scheduler_task(monkeypatch):
    calls = []

    def send_task(name, *, args, task_id):
        calls.append((name, args, task_id))

    monkeypatch.setattr(task_dispatcher.celery_app, "send_task", send_task)

    task_dispatcher.CelerySchedulerTaskDispatcher().dispatch(
        organization_id=7,
        job_id=42,
        task_id="scheduler-job-42",
    )

    assert calls == [
        ("scheduler.run_generation_job", [7, 42], "scheduler-job-42"),
    ]
