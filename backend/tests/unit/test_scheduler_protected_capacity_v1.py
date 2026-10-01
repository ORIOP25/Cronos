"""Recovery capacity checks inspect only frozen lessons on the relevant day."""

from app.scheduler.domain.capacity import available_rooms
from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment, lesson, plan
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period


def test_room_checks_do_not_scan_the_entire_frozen_window(monkeypatch):
    from app.scheduler.domain import capacity

    periods = tuple(period(day) for day in range(17))
    assignments = [assignment(identity, identity, identity, {1}, 60) for identity in range(1, 18)]
    protected = tuple(
        lesson(identity, identity, periods[identity - 1], 1) for identity in range(1, 17)
    )
    target = plan(periods, assignments, protected_lessons=protected)
    comparisons = 0
    original = capacity._overlaps

    def observed(left, right):
        nonlocal comparisons
        comparisons += 1
        return original(left, right)

    monkeypatch.setattr(capacity, "_overlaps", observed)

    assert available_rooms(target, assignments[-1], periods[-1]) == (1,)
    assert comparisons == 0
    assert available_rooms(target, assignments[-1], periods[0]) == ()
    assert comparisons == 1
