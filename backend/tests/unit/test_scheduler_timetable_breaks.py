from datetime import time

import pytest

from app.scheduler.domain.timetable import (
    BreakOverride,
    TimetableConfigError,
    build_daily_slots,
)


def _pairs(slots) -> list[tuple[str, str]]:
    return [(slot.start.strftime("%H:%M"), slot.end.strftime("%H:%M")) for slot in slots]


def test_builds_the_variable_break_sequence_from_the_contract_example():
    slots = build_daily_slots(
        opening_time=time(9, 0),
        closing_time=time(11, 45),
        slot_duration_minutes=50,
        break_duration_minutes=10,
        break_overrides=(BreakOverride(after_slot=2, duration_minutes=5),),
    )

    assert _pairs(slots) == [
        ("09:00", "09:50"),
        ("10:00", "10:50"),
        ("10:55", "11:45"),
    ]
    assert [slot.break_after_minutes for slot in slots] == [10, 5, 0]
    assert [slot.index for slot in slots] == [1, 2, 3]


def test_zero_break_stacks_lessons_back_to_back():
    slots = build_daily_slots(
        opening_time=time(8, 0),
        closing_time=time(10, 0),
        slot_duration_minutes=50,
        break_duration_minutes=0,
    )

    assert _pairs(slots) == [("08:00", "08:50"), ("08:50", "09:40")]


def test_thirty_minute_break_pushes_following_lessons():
    slots = build_daily_slots(
        opening_time=time(8, 0),
        closing_time=time(10, 30),
        slot_duration_minutes=50,
        break_duration_minutes=30,
    )

    assert _pairs(slots) == [("08:00", "08:50"), ("09:20", "10:10")]


def test_generated_count_depends_on_the_breaks_in_effect():
    without_override = build_daily_slots(
        opening_time=time(9, 0),
        closing_time=time(12, 0),
        slot_duration_minutes=50,
        break_duration_minutes=10,
    )
    with_override = build_daily_slots(
        opening_time=time(9, 0),
        closing_time=time(12, 0),
        slot_duration_minutes=50,
        break_duration_minutes=10,
        break_overrides=(BreakOverride(after_slot=1, duration_minutes=60),),
    )

    assert _pairs(without_override) == [
        ("09:00", "09:50"),
        ("10:00", "10:50"),
        ("11:00", "11:50"),
    ]
    assert _pairs(with_override) == [("09:00", "09:50"), ("10:50", "11:40")]


def test_closing_without_room_for_another_lesson_keeps_the_last_one():
    slots = build_daily_slots(
        opening_time=time(9, 0),
        closing_time=time(10, 0),
        slot_duration_minutes=50,
        break_duration_minutes=10,
    )

    assert _pairs(slots) == [("09:00", "09:50")]
    assert slots[-1].break_after_minutes == 0


def test_rejects_an_override_without_a_following_lesson():
    with pytest.raises(TimetableConfigError) as excinfo:
        build_daily_slots(
            opening_time=time(9, 0),
            closing_time=time(9, 50),
            slot_duration_minutes=50,
            break_duration_minutes=10,
            break_overrides=(BreakOverride(after_slot=1, duration_minutes=5),),
        )

    assert excinfo.value.code == "timetable.unused_break_override"
    assert "1" in str(excinfo.value)


def test_rejects_an_override_that_loses_its_lesson_after_a_longer_break():
    with pytest.raises(TimetableConfigError) as excinfo:
        build_daily_slots(
            opening_time=time(9, 0),
            closing_time=time(12, 0),
            slot_duration_minutes=50,
            break_duration_minutes=10,
            break_overrides=(
                BreakOverride(after_slot=1, duration_minutes=60),
                BreakOverride(after_slot=3, duration_minutes=5),
            ),
        )

    assert excinfo.value.code == "timetable.unused_break_override"
    assert "3" in str(excinfo.value)


def test_rejects_duplicate_and_non_positive_override_positions():
    with pytest.raises(TimetableConfigError) as duplicate:
        build_daily_slots(
            opening_time=time(9, 0),
            closing_time=time(12, 0),
            slot_duration_minutes=50,
            break_overrides=(
                BreakOverride(after_slot=1, duration_minutes=5),
                BreakOverride(after_slot=1, duration_minutes=10),
            ),
        )
    assert duplicate.value.code == "timetable.duplicate_override_position"

    with pytest.raises(TimetableConfigError) as non_positive:
        build_daily_slots(
            opening_time=time(9, 0),
            closing_time=time(12, 0),
            slot_duration_minutes=50,
            break_overrides=(BreakOverride(after_slot=0, duration_minutes=5),),
        )
    assert non_positive.value.code == "timetable.invalid_override_position"


@pytest.mark.parametrize("minutes", [-1, 61])
def test_rejects_override_durations_outside_the_allowed_range(minutes):
    with pytest.raises(TimetableConfigError) as excinfo:
        build_daily_slots(
            opening_time=time(9, 0),
            closing_time=time(12, 0),
            slot_duration_minutes=50,
            break_overrides=(BreakOverride(after_slot=1, duration_minutes=minutes),),
        )
    assert excinfo.value.code == "timetable.invalid_override_duration"


@pytest.mark.parametrize("minutes", [14, 121])
def test_rejects_slot_durations_outside_the_allowed_range(minutes):
    with pytest.raises(TimetableConfigError) as excinfo:
        build_daily_slots(
            opening_time=time(9, 0),
            closing_time=time(12, 0),
            slot_duration_minutes=minutes,
        )
    assert excinfo.value.code == "timetable.invalid_slot_duration"


def test_rejects_invalid_windows_and_base_break():
    with pytest.raises(TimetableConfigError) as window:
        build_daily_slots(
            opening_time=time(9, 0),
            closing_time=time(9, 0),
            slot_duration_minutes=50,
        )
    assert window.value.code == "timetable.invalid_window"

    with pytest.raises(TimetableConfigError) as base_break:
        build_daily_slots(
            opening_time=time(9, 0),
            closing_time=time(12, 0),
            slot_duration_minutes=50,
            break_duration_minutes=-1,
        )
    assert base_break.value.code == "timetable.invalid_break_duration"
