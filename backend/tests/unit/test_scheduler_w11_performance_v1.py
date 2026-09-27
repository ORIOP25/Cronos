"""W11 performance harness: interleaving, aggregation and serialization."""

from app.scheduler.lab.performance import (
    RunSample,
    interleaved_schedule,
    report_to_dict,
    summarize_workers,
)


def _sample(workers: int, repeat: int, wall: float, cpu: float, outcome: str = "COMPLETE"):
    return RunSample(
        case_id="case",
        family="C18",
        workers=workers,
        repeat=repeat,
        seed=1,
        outcome=outcome,
        valid=outcome == "COMPLETE",
        wall_seconds=wall,
        search_seconds=wall,
        cpu_seconds=cpu,
        peak_python_bytes=1024,
        phases={"build_ms": 1, "solve_ms": 2},
        metrics={"objective_days": 10},
    )


def test_configurations_interleave_to_reduce_warmup_bias():
    assert interleaved_schedule((1, 2, 4, 8), 2) == (
        (1, 0),
        (2, 0),
        (4, 0),
        (8, 0),
        (1, 1),
        (2, 1),
        (4, 1),
        (8, 1),
    )


def test_summary_reports_medians_cpu_and_failures():
    samples = (
        _sample(1, 0, 10.0, 9.0),
        _sample(1, 1, 20.0, 19.0),
        _sample(2, 0, 6.0, 11.0),
        _sample(2, 1, 8.0, 15.0, outcome="INCONCLUSIVE"),
    )

    summaries = summarize_workers(samples)

    by_workers = {summary.workers: summary for summary in summaries}
    assert by_workers[1].valid == 2
    assert by_workers[1].median_wall_seconds == 15.0
    assert by_workers[1].total_cpu_seconds == 28.0
    assert by_workers[2].valid == 1
    assert by_workers[2].median_wall_seconds == 7.0
    assert by_workers[2].failures == 1


def test_report_serializes_every_sample_and_summary():
    samples = (_sample(1, 0, 10.0, 9.0),)

    data = report_to_dict("worker-matrix", "abc", samples)

    assert data["campaign_id"] == "worker-matrix"
    assert data["commit"] == "abc"
    assert len(data["samples"]) == 1
    assert data["samples"][0]["workers"] == 1
    assert data["summaries"][0]["workers"] == 1
    assert data["summaries"][0]["runs"] == 1


def test_phase_summary_identifies_the_dominant_observed_cost():
    samples = (
        _sample(1, 0, 10.0, 9.0),
        _sample(1, 1, 12.0, 11.0),
    )

    data = report_to_dict("worker-matrix", "abc", samples)

    phases = data["phases"]
    assert phases["build_ms"] == 2
    assert phases["solve_ms"] == 4
    assert phases["dominant_phase"] == "solve_ms"
    assert phases["total_ms"] == 6
