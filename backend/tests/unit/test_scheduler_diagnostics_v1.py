"""Cgroup parsing, thread-context propagation and phase ordering for diagnostics."""

from __future__ import annotations

import asyncio

import pytest
import structlog
from ortools.sat.python import cp_model
from structlog.testing import capture_logs

from app.scheduler.infrastructure import diagnostics
from app.scheduler.infrastructure.placement_model import solve_placement
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period, snapshot

SNAPSHOT_FIELDS = {
    "container_memory_current_bytes",
    "container_memory_peak_bytes",
    "container_memory_limit_bytes",
    "container_oom_kill_count",
}


def test_memory_snapshot_parses_the_container_files(tmp_path):
    (tmp_path / "memory.current").write_text("123456\n")
    (tmp_path / "memory.peak").write_text("654321\n")
    (tmp_path / "memory.max").write_text("8000000000\n")
    (tmp_path / "memory.events").write_text("low 0\nhigh 0\nmax 0\noom 0\noom_kill 1\n")

    assert diagnostics.memory_snapshot(str(tmp_path)) == {
        "container_memory_current_bytes": 123456,
        "container_memory_peak_bytes": 654321,
        "container_memory_limit_bytes": 8000000000,
        "container_oom_kill_count": 1,
    }


def test_an_unlimited_memory_max_is_reported_as_unknown(tmp_path):
    (tmp_path / "memory.max").write_text("max\n")

    assert diagnostics.memory_limit_bytes(str(tmp_path)) is None


def test_invalid_memory_values_are_reported_as_unknown(tmp_path):
    (tmp_path / "memory.current").write_text("not-a-number\n")
    (tmp_path / "memory.max").write_text("also-not-a-number\n")
    (tmp_path / "memory.events").write_text("oom_kill nope\n")

    assert diagnostics.memory_current_bytes(str(tmp_path)) is None
    assert diagnostics.memory_limit_bytes(str(tmp_path)) is None
    assert diagnostics.oom_kill_count(str(tmp_path)) is None


def test_a_missing_cgroup_reports_every_field_as_unknown(tmp_path):
    snapshot_fields = diagnostics.memory_snapshot(str(tmp_path / "missing"))

    assert set(snapshot_fields) == SNAPSHOT_FIELDS
    assert all(value is None for value in snapshot_fields.values())


def test_the_bound_context_reaches_the_worker_thread():
    async def scenario():
        with structlog.contextvars.bound_contextvars(job_id=31, organization_id=27):
            return await asyncio.to_thread(structlog.contextvars.get_contextvars)

    seen = asyncio.run(scenario())

    assert seen["job_id"] == 31
    assert seen["organization_id"] == 27


def test_the_context_is_cleared_after_the_attempt():
    with structlog.contextvars.bound_contextvars(job_id=31):
        assert structlog.contextvars.get_contextvars()["job_id"] == 31

    assert "job_id" not in structlog.contextvars.get_contextvars()


def test_a_started_event_precedes_a_failing_solve(monkeypatch):
    when = period(0)

    def fail(self, model, *args, **kwargs):
        raise RuntimeError("simulated worker loss")

    monkeypatch.setattr(cp_model.CpSolver, "Solve", fail)

    with capture_logs() as logs:
        with pytest.raises(RuntimeError):
            solve_placement(snapshot((when,)), (when,), time_limit_seconds=60)

    started = [row for row in logs if row.get("event") == diagnostics.PHASE_STARTED]
    phases = {row.get("phase") for row in started}
    assert "PLACEMENT" in phases
    assert "PLACEMENT_SOLVE" in phases
    solve_start = next(row for row in started if row.get("phase") == "PLACEMENT_SOLVE")
    assert set(solve_start) >= SNAPSHOT_FIELDS
