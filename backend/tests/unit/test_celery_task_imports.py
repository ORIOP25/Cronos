"""Celery wiring: Beat loads no execution modules, and each worker registers its own tasks.

Every probe runs in a fresh interpreter so module caches cannot leak between tests.
"""

from __future__ import annotations

import functools
import json
import subprocess
import sys
from pathlib import Path

from app.celery_worker import celery_app

BACKEND = Path(__file__).resolve().parents[2]
SOLVER_MODULE = "app.scheduler_v1_worker"
SUPERVISOR_MODULE = "app.scheduler_recovery_worker"
MEMBER_MODULE = "app.member_reconciliation_worker"
PRIVACY_MODULE = "app.privacy_maintenance_worker"
WATCHED_MODULES = (
    MEMBER_MODULE,
    PRIVACY_MODULE,
    SUPERVISOR_MODULE,
    SOLVER_MODULE,
    "sqlalchemy",
    "ortools",
)
SOLVER_TASKS = {
    "members.run_scheduled_reconciliation",
    "privacy.run_maintenance",
    "scheduler.v1.run_next_job",
}

PROBE = """
import json
import sys

from app.celery_worker import celery_app

{load}

watched = {watched!r}
loaded = sorted(
    name
    for name in sys.modules
    if any(name == root or name.startswith(root + ".") for root in watched)
)
print(json.dumps({{"tasks": sorted(celery_app.tasks), "loaded": loaded}}))
"""


def _probe(load: str) -> dict[str, list[str]]:
    result = subprocess.run(
        [sys.executable, "-c", PROBE.format(load=load, watched=WATCHED_MODULES)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.splitlines()[-1])


@functools.cache
def _beat_probe() -> dict[str, list[str]]:
    return _probe("celery_app.loader.import_default_modules()")


@functools.cache
def _worker_probe(module: str) -> dict[str, list[str]]:
    return _probe(f"import {module}")


def test_beat_loads_no_execution_or_database_modules() -> None:
    assert _beat_probe()["loaded"] == []


def test_solver_worker_registers_the_tasks_it_executes() -> None:
    assert SOLVER_TASKS <= set(_worker_probe(SOLVER_MODULE)["tasks"])


def test_supervisor_registers_recovery_without_member_or_privacy_modules() -> None:
    probe = _worker_probe(SUPERVISOR_MODULE)

    assert "scheduler.v1.supervise" in probe["tasks"]
    assert not {MEMBER_MODULE, PRIVACY_MODULE} & set(probe["loaded"])


def test_each_beat_task_is_registered_by_the_worker_that_consumes_its_queue() -> None:
    workers = {
        celery_app.conf.task_default_queue: SOLVER_MODULE,
        "scheduler-supervisor": SUPERVISOR_MODULE,
    }
    registered = {module: set(_worker_probe(module)["tasks"]) for module in workers.values()}

    for entry in celery_app.conf.beat_schedule.values():
        queue = entry.get("options", {}).get("queue", celery_app.conf.task_default_queue)
        owner = workers[queue]
        assert entry["task"] in registered[owner], (entry["task"], owner)
        for module in workers.values():
            if module != owner:
                assert entry["task"] not in registered[module], (entry["task"], module)


DEPLOYMENT_FILES = (
    BACKEND / "railway" / "supervisor.json",
    BACKEND.parent / "docker-compose.yml",
    BACKEND.parent / "docker-compose.ci.yml",
    BACKEND.parent / "docker-compose.test.yml",
)


def _supervisor_command_lines(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if f"--include={SUPERVISOR_MODULE}" in line
    ]


def test_supervisor_command_uses_the_solo_pool_in_every_deployment_file() -> None:
    """The supervisor is one lightweight task: solo pool, with no prefork child to hold memory."""
    for path in DEPLOYMENT_FILES:
        command_lines = _supervisor_command_lines(path)
        assert command_lines, path
        for line in command_lines:
            assert "--pool=solo" in line, (path.name, line)


def test_beat_runs_embedded_in_the_supervisor_and_nowhere_else() -> None:
    """One idle process less: the supervisor publishes the schedule, so no service runs Beat alone."""
    assert not (BACKEND / "railway" / "beat.json").exists()
    for path in DEPLOYMENT_FILES:
        for line in _supervisor_command_lines(path):
            assert "--beat" in line, (path.name, line)
        text = path.read_text(encoding="utf-8")
        assert '"beat",' not in text and "celery_app beat" not in text, path.name
