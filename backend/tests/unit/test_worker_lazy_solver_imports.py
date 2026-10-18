"""The solver worker parent loads no numerical solver; the executing child loads it on first use.

The prefork parent only registers tasks. Only the forked child runs a solve, so OR-Tools,
NumPy and pandas must load when a job runs, not when the module is imported.
Each probe runs in a fresh interpreter so module caches cannot leak between tests.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

from app.scheduler.domain.candidate import SchedulingStrategy

BACKEND = Path(__file__).resolve().parents[2]
NUMERICAL_ROOTS = ("ortools", "numpy", "pandas")
SOLVER_TASKS = {
    "members.run_scheduled_reconciliation",
    "privacy.run_maintenance",
    "scheduler.v1.run_next_job",
}

PROBE = """
import json
import sys

import app.scheduler_v1_worker
from app.celery_worker import celery_app

loaded = sorted(
    name
    for name in sys.modules
    if any(name == root or name.startswith(root + ".") for root in {roots!r})
)
print(json.dumps({{"tasks": sorted(celery_app.tasks), "loaded": loaded}}))
"""


def _parent_probe() -> dict[str, list[str]]:
    result = subprocess.run(
        [sys.executable, "-c", PROBE.format(roots=NUMERICAL_ROOTS)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.splitlines()[-1])


def test_solver_worker_parent_loads_no_numerical_solver_packages() -> None:
    assert _parent_probe()["loaded"] == []


def test_solver_worker_parent_still_registers_its_tasks() -> None:
    assert SOLVER_TASKS <= set(_parent_probe()["tasks"])


def test_run_search_resolves_the_generation_solver_from_composition(monkeypatch) -> None:
    from app import scheduler_v1_worker as worker
    from app.scheduler import composition

    calls: list[tuple[object, object]] = []
    sentinel = object()

    def fake_generate_schedule(snapshot, periods, **_options):
        calls.append((snapshot, periods))
        return sentinel

    monkeypatch.setattr(composition, "generate_schedule", fake_generate_schedule)
    claim = SimpleNamespace(job_id="job", strategy=SchedulingStrategy.COMPLETE_GENERATION)
    bundle = SimpleNamespace(snapshot="snapshot", periods=("period",))

    result = worker._run_search(claim, bundle, threading.Event())

    assert result is sentinel
    assert calls == [("snapshot", ("period",))]
