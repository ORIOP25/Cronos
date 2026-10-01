from datetime import date

import pytest

from app.scheduler.domain.projection import (
    FutureLesson,
    ModuleRequirement,
    ModuleSlice,
    project_module_slices,
)

MODULES = (
    ModuleRequirement(module_id=1, sequence=1, required_minutes=75),
    ModuleRequirement(module_id=2, sequence=2, required_minutes=75),
)


def lesson(lesson_id: int, day: int, start_minute: int, credit_minutes: int = 50):
    return FutureLesson(
        lesson_id,
        date(2026, 9, day),
        start_minute,
        credit_minutes,
        credit_minutes,
    )


def test_t01_two_75_minute_modules_cross_three_50_minute_lessons():
    slices = project_module_slices(
        MODULES,
        completed_minutes={},
        lessons=(lesson(30, 24, 9 * 60), lesson(10, 22, 9 * 60), lesson(20, 23, 9 * 60)),
    )

    assert slices == (
        ModuleSlice(10, 1, 0, 50),
        ModuleSlice(20, 1, 50, 25),
        ModuleSlice(20, 2, 0, 25),
        ModuleSlice(30, 2, 25, 50),
    )


def test_t02_cancelling_tuesday_changes_wednesdays_modules_without_moving_it():
    before = project_module_slices(
        MODULES,
        completed_minutes={},
        lessons=(lesson(10, 22, 9 * 60), lesson(20, 23, 9 * 60), lesson(30, 24, 9 * 60)),
    )
    wednesday = lesson(20, 23, 9 * 60)
    after = project_module_slices(
        MODULES,
        completed_minutes={},
        lessons=(wednesday, lesson(30, 24, 9 * 60), lesson(40, 24, 10 * 60)),
    )

    assert [part for part in before if part.lesson_id == wednesday.lesson_id] == [
        ModuleSlice(20, 1, 50, 25),
        ModuleSlice(20, 2, 0, 25),
    ]
    assert [part for part in after if part.lesson_id == wednesday.lesson_id] == [
        ModuleSlice(20, 1, 0, 50)
    ]
    assert sum(part.credit_minutes for part in after) == 150


def test_partial_progress_and_mixed_durations_preserve_exact_minutes():
    slices = project_module_slices(
        MODULES,
        completed_minutes={1: 40},
        lessons=(lesson(10, 22, 9 * 60, 30), lesson(20, 23, 9 * 60, 80)),
    )

    assert slices == (
        ModuleSlice(10, 1, 40, 30),
        ModuleSlice(20, 1, 70, 5),
        ModuleSlice(20, 2, 0, 75),
    )


def test_incomplete_published_future_can_be_reprojected_without_crediting_missing_hours():
    slices = project_module_slices(
        MODULES,
        completed_minutes={1: 50},
        lessons=(lesson(20, 23, 9 * 60),),
        require_complete=False,
    )

    assert slices == (ModuleSlice(20, 1, 50, 25), ModuleSlice(20, 2, 0, 25))


def test_partial_projection_still_rejects_excess_credit():
    with pytest.raises(ValueError, match="residual demand"):
        project_module_slices(
            MODULES,
            completed_minutes={1: 75, 2: 50},
            lessons=(lesson(20, 23, 9 * 60),),
            require_complete=False,
        )


@pytest.mark.parametrize(
    ("completed", "lessons"),
    [
        ({1: -1}, (lesson(1, 22, 9 * 60), lesson(2, 23, 9 * 60), lesson(3, 24, 9 * 60))),
        ({1: 76}, (lesson(1, 22, 9 * 60), lesson(2, 23, 9 * 60))),
        ({}, (lesson(1, 22, 9 * 60),)),
    ],
)
def test_invalid_progress_or_incomplete_coverage_is_rejected(completed, lessons):
    with pytest.raises(ValueError):
        project_module_slices(MODULES, completed_minutes=completed, lessons=lessons)


def test_credit_cannot_exceed_physical_duration():
    with pytest.raises(ValueError):
        FutureLesson(1, date(2026, 9, 22), 9 * 60, 50, 51)
    with pytest.raises(ValueError):
        FutureLesson(1, date(2026, 9, 22), 9 * 60, 50, 0)


def test_curricular_values_reject_invalid_minute_amounts():
    with pytest.raises(ValueError):
        ModuleRequirement(1, 1, 0)
    with pytest.raises(ValueError):
        ModuleSlice(1, 1, -1, 50)
    with pytest.raises(ValueError):
        ModuleSlice(1, 1, 0, 0)


def test_t07_protected_future_credit_cannot_be_silently_removed_after_adjustment():
    with pytest.raises(ValueError, match="residual demand"):
        project_module_slices(
            (ModuleRequirement(1, 1, 150),),
            completed_minutes={1: 100},
            lessons=(lesson(20, 23, 9 * 60, 100),),
        )
