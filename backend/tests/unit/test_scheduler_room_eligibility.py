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


LAB = "lab"
HOME_LAB = 2


def test_normal_subject_may_use_the_home_room_of_any_type():
    """❌ R12: Português da turma pode ir para a sala da turma de laboratório."""
    eligibility = assess_room_eligibility(
        [(1, NORMAL, 30), (HOME_LAB, LAB, 30)],
        required_room_type=NORMAL,
        required_capacity=20,
        home_room_ids=frozenset({HOME_LAB}),
        subject_is_normal=True,
    )

    assert eligibility.eligible_room_ids == frozenset({1, HOME_LAB})
    assert eligibility.reason is None


def test_non_normal_subject_never_uses_a_home_room_of_another_type():
    """❌ R12: Educação Física da turma não pode ir para a sala da turma de laboratório."""
    eligibility = assess_room_eligibility(
        [(1, GYM, 30), (HOME_LAB, LAB, 30)],
        required_room_type=GYM,
        required_capacity=20,
        home_room_ids=frozenset({HOME_LAB}),
        subject_is_normal=False,
    )

    assert eligibility.eligible_room_ids == frozenset({1})


def test_home_room_of_another_class_is_not_offered_to_a_normal_subject():
    """❌ R12: Português de outra turma não pode ir para a sala de laboratório desta."""
    eligibility = assess_room_eligibility(
        [(1, NORMAL, 30), (HOME_LAB, LAB, 30)],
        required_room_type=NORMAL,
        required_capacity=20,
        home_room_ids=frozenset(),
        subject_is_normal=True,
    )

    assert eligibility.eligible_room_ids == frozenset({1})


def test_joint_unit_uses_a_home_room_only_when_it_fits_every_student():
    """❌ R12: a sala da turma de uma aula conjunta só entra se couberem todos os alunos."""
    rooms = [(1, NORMAL, 30), (HOME_LAB, LAB, 25)]

    with_everyone = assess_room_eligibility(
        rooms,
        required_room_type=NORMAL,
        required_capacity=27,
        home_room_ids=frozenset({HOME_LAB}),
        subject_is_normal=True,
    )
    fits_everyone = assess_room_eligibility(
        rooms,
        required_room_type=NORMAL,
        required_capacity=25,
        home_room_ids=frozenset({HOME_LAB}),
        subject_is_normal=True,
    )

    assert with_everyone.eligible_room_ids == frozenset({1})
    assert fits_everyone.eligible_room_ids == frozenset({1, HOME_LAB})


def test_specific_room_restriction_cuts_the_home_room():
    """❌ R13: com uma restrição específica para outra sala, a sala da turma sai do conjunto."""
    eligibility = assess_room_eligibility(
        [(1, NORMAL, 30), (HOME_LAB, LAB, 30)],
        required_room_type=NORMAL,
        required_capacity=20,
        allowed_room_ids=frozenset({1}),
        home_room_ids=frozenset({HOME_LAB}),
        subject_is_normal=True,
    )

    assert eligibility.eligible_room_ids == frozenset({1})
    assert eligibility.reason is None


def test_home_room_missing_from_the_active_rooms_is_ignored():
    """❌ R09/D13: uma sala arquivada ou de outra escola não entra por ser sala da turma."""
    eligibility = assess_room_eligibility(
        [(1, NORMAL, 30)],
        required_room_type=NORMAL,
        required_capacity=20,
        home_room_ids=frozenset({99}),
        subject_is_normal=True,
    )

    assert eligibility.eligible_room_ids == frozenset({1})
