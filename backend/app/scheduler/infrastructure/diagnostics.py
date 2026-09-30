"""Phase, model-size and cgroup-memory diagnostics for the scheduler.

The annual, placement and worker adapters emit the same structured events, so
a job killed before its completion can still be reconstructed from its logs.
Memory values come from the container cgroup: a missing, unreadable, invalid or
unlimited value is reported as ``null`` and never invented.
"""

from __future__ import annotations

from time import monotonic
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

CGROUP_ROOT = "/sys/fs/cgroup"

PHASE_STARTED = "scheduler_v1_phase_started"
PHASE_MODEL_BUILT = "scheduler_v1_model_built"
PHASE_FINISHED = "scheduler_v1_phase_finished"


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="ascii") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _read_int(path: str) -> int | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def memory_current_bytes(root: str = CGROUP_ROOT) -> int | None:
    return _read_int(f"{root}/memory.current")


def memory_peak_bytes(root: str = CGROUP_ROOT) -> int | None:
    return _read_int(f"{root}/memory.peak")


def memory_limit_bytes(root: str = CGROUP_ROOT) -> int | None:
    text = _read_text(f"{root}/memory.max")
    if text is None or text == "max":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def oom_kill_count(root: str = CGROUP_ROOT) -> int | None:
    text = _read_text(f"{root}/memory.events")
    if text is None:
        return None
    for line in text.splitlines():
        key, _, value = line.partition(" ")
        if key == "oom_kill":
            try:
                return int(value)
            except ValueError:
                return None
    return None


def memory_snapshot(root: str = CGROUP_ROOT) -> dict[str, int | None]:
    return {
        "container_memory_current_bytes": memory_current_bytes(root),
        "container_memory_peak_bytes": memory_peak_bytes(root),
        "container_memory_limit_bytes": memory_limit_bytes(root),
        "container_oom_kill_count": oom_kill_count(root),
    }


def _model_sizes(model: Any | None) -> dict[str, int]:
    if model is None:
        return {}
    proto = model.Proto()
    return {"variables": len(proto.variables), "constraints": len(proto.constraints)}


def _scope_fields(window: int | None, stage: str | None) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if window is not None:
        fields["window"] = window
    if stage is not None:
        fields["stage"] = stage
    return fields


def emit(
    event: str,
    *,
    phase: str,
    window: int | None = None,
    stage: str | None = None,
    model: Any | None = None,
    started_at: float | None = None,
    status: str | None = None,
    **extra: Any,
) -> None:
    fields: dict[str, Any] = {
        "phase": phase,
        **memory_snapshot(),
        **_scope_fields(window, stage),
        **_model_sizes(model),
        **extra,
    }
    if started_at is not None:
        fields["elapsed_ms"] = int((monotonic() - started_at) * 1000)
    if status is not None:
        fields["status"] = status
    logger.info(event, **fields)


def phase_started(phase: str, *, window: int | None = None, stage: str | None = None) -> None:
    emit(PHASE_STARTED, phase=phase, window=window, stage=stage)


def model_built(
    phase: str, model: Any, *, window: int | None = None, stage: str | None = None
) -> None:
    emit(PHASE_MODEL_BUILT, phase=phase, window=window, stage=stage, model=model)


def phase_finished(
    phase: str,
    *,
    window: int | None = None,
    stage: str | None = None,
    started_at: float | None = None,
    status: str | None = None,
) -> None:
    emit(
        PHASE_FINISHED,
        phase=phase,
        window=window,
        stage=stage,
        started_at=started_at,
        status=status,
    )
