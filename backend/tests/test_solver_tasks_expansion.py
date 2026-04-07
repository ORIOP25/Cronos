from datetime import date
from types import SimpleNamespace

from app.core.solver_engine import ScheduledAssignment
from app.solver_tasks import expand_to_dates, _resolve_hard_end_date


def test_expand_to_dates_respects_hard_end_date_limit():
    assignments = [
        ScheduledAssignment(
            lesson_id=1,
            ts_id=100,
            room_id=10,
            day_of_week=0,
            duration_minutes=60,
        )
    ]

    blocks, remaining_minutes = expand_to_dates(
        assignments=assignments,
        school_start_date=date(2025, 9, 15),
        school_target_end_date=date(2026, 6, 15),
        school_hard_end_date=date(2026, 7, 31),
        blocked_dates=set(),
        remaining_map={1: 100000},
    )

    assert blocks
    assert max(block.output_date for block in blocks) <= date(2026, 7, 31)
    assert remaining_minutes > 0


def test_resolve_hard_end_date_falls_back_to_july_31_of_target_year():
    org_settings = SimpleNamespace(
        school_hard_end_date=None,
        school_target_end_date=date(2026, 6, 15),
        academic_year="2025/2026",
    )

    assert _resolve_hard_end_date(org_settings) == date(2026, 7, 31)
