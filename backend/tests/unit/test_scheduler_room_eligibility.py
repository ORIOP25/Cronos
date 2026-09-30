"""Pure room eligibility: the single decision shared by snapshot and preflight."""

from app.scheduler.domain.constraint_policy import (
    RoomEligibilityReason,
    assess_room_eligibility,
)

GYM = "gym"
NORMAL = "normal"


def test_capacity_below_class_size_is_insufficient():
    eligibility = assess_room_eligibility(
        [(1, GYM, 25), (2, GYM, 26)],
        required_room_type=GYM,
        required_capacity=27,
    )

    assert eligibility.eligible_room_ids == frozenset()
    assert eligibility.max_available_capacity == 26
    assert eligibility.reason is RoomEligibilityReason.INSUFFICIENT_CAPACITY


def test_capacity_equal_to_class_size_is_eligible():
    eligibility = assess_room_eligibility(
        [(1, GYM, 25), (2, GYM, 27)],
        required_room_type=GYM,
        required_capacity=27,
    )

    assert eligibility.eligible_room_ids == frozenset({2})
    assert eligibility.max_available_capacity == 27
    assert eligibility.reason is None


def test_wrong_type_has_no_room_of_type_and_no_capacity():
    eligibility = assess_room_eligibility(
        [(1, NORMAL, 40)],
        required_room_type=GYM,
        required_capacity=10,
    )

    assert eligibility.eligible_room_ids == frozenset()
    assert eligibility.max_available_capacity is None
    assert eligibility.reason is RoomEligibilityReason.NO_ROOM_OF_TYPE


def test_specific_room_restriction_excludes_capacity_eligible_rooms():
    eligibility = assess_room_eligibility(
        [(1, GYM, 30), (2, GYM, 31)],
        required_room_type=GYM,
        required_capacity=20,
        allowed_room_ids=frozenset({1, 2}),
    )

    assert eligibility.eligible_room_ids == frozenset({1, 2})
    assert eligibility.reason is None

    excluded = assess_room_eligibility(
        [(1, GYM, 30), (2, GYM, 31)],
        required_room_type=GYM,
        required_capacity=20,
        allowed_room_ids=frozenset({3}),
    )

    assert excluded.eligible_room_ids == frozenset()
    assert excluded.max_available_capacity == 31
    assert excluded.reason is RoomEligibilityReason.SPECIFIC_ROOM_RESTRICTION


def test_empty_allowed_set_still_blocks_assignment():
    eligibility = assess_room_eligibility(
        [(1, GYM, 40)],
        required_room_type=GYM,
        required_capacity=10,
        allowed_room_ids=frozenset(),
    )

    assert eligibility.eligible_room_ids == frozenset()
    assert eligibility.reason is RoomEligibilityReason.SPECIFIC_ROOM_RESTRICTION
