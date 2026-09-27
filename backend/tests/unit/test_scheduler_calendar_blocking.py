from datetime import date

from app.scheduler.domain.calendar import (
    blocked_dates_by_class,
    blocked_dates_for_class,
    event_blocks_class,
)

MONDAY = date(2026, 9, 21)
TUESDAY = date(2026, 9, 22)


def test_general_events_block_every_class():
    events = [
        {
            "start_date": "2026-09-21",
            "end_date": "2026-09-22",
            "event_type": "national_holiday",
        }
    ]

    assert blocked_dates_for_class(events, 1) == {MONDAY, TUESDAY}
    assert blocked_dates_for_class(events, 2) == {MONDAY, TUESDAY}
    assert blocked_dates_by_class(events, [1, 2]) == {
        1: {MONDAY, TUESDAY},
        2: {MONDAY, TUESDAY},
    }


def test_internship_flow_blocks_only_its_classes_inclusive_of_both_dates():
    events = [
        {
            "start_date": "2026-09-21",
            "end_date": "2026-09-22",
            "event_type": "internship_flow",
            "class_ids": [2],
        }
    ]

    assert blocked_dates_for_class(events, 1) == set()
    assert blocked_dates_for_class(events, 2) == {MONDAY, TUESDAY}
    assert blocked_dates_by_class(events, [1, 2, 3]) == {1: set(), 2: {MONDAY, TUESDAY}, 3: set()}


def test_internship_flow_without_classes_blocks_nothing():
    events = [
        {
            "start_date": date(2026, 9, 21),
            "end_date": date(2026, 9, 22),
            "event_type": "internship_flow",
            "class_ids": [],
        }
    ]

    assert event_blocks_class(events[0], 1) is False
    assert blocked_dates_for_class(events, 1) == set()
    assert blocked_dates_by_class(events, [1]) == {1: set()}


def test_overlapping_events_are_unioned_per_class():
    events = [
        {
            "start_date": "2026-09-21",
            "end_date": "2026-09-21",
            "event_type": "school_break",
        },
        {
            "start_date": "2026-09-21",
            "end_date": "2026-09-22",
            "event_type": "internship_flow",
            "class_ids": [7],
        },
    ]

    assert blocked_dates_for_class(events, 7) == {MONDAY, TUESDAY}
    assert blocked_dates_for_class(events, 8) == {MONDAY}


def test_events_accept_generic_mappings_and_date_values():
    events = [
        {
            "start_date": "2026-09-21",
            "end_date": "2026-09-21",
            "event_type": "other",
            "class_ids": [],
        }
    ]

    assert blocked_dates_by_class(events, [1]) == {1: {MONDAY}}


def test_event_type_enum_values_are_supported():
    from app.models import CalendarEventType

    flow = {
        "start_date": "2026-09-21",
        "end_date": "2026-09-21",
        "event_type": CalendarEventType.internship_flow,
        "class_ids": [1],
    }
    holiday = {
        "start_date": "2026-09-21",
        "end_date": "2026-09-21",
        "event_type": CalendarEventType.national_holiday,
    }

    assert event_blocks_class(flow, 1) is True
    assert event_blocks_class(flow, 2) is False
    assert event_blocks_class(holiday, 2) is True
