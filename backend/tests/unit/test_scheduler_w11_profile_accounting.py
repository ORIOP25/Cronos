"""W11.2 profiling: phase statistics accumulate across feedback rounds."""

from app.scheduler.infrastructure.search import _merge_statistics


def test_statistics_accumulate_build_solve_and_room_time():
    totals: dict[str, int] = {}

    _merge_statistics(totals, {"build_ms": 100, "solve_ms": 900, "room_ms": 10, "windows": 3})
    _merge_statistics(totals, {"build_ms": 50, "solve_ms": 400, "room_ms": 5, "windows": 2})

    assert totals == {"build_ms": 150, "solve_ms": 1300, "room_ms": 15, "windows": 5}


def test_statistics_ignore_missing_and_non_integer_values():
    totals: dict[str, int] = {"build_ms": 10}

    _merge_statistics(totals, None)
    _merge_statistics(totals, {"solve_ms": 5, "note": "not-a-number"})

    assert totals == {"build_ms": 10, "solve_ms": 5}
