"""Unit tests for the pure joint-lesson configuration rules (WBS 4.1)."""

from app.services import joint_lesson_policy as policy
from app.services.joint_lesson_policy import JointClassFacts


def _facts(
    class_id: int = 1,
    *,
    name: str | None = None,
    has_subject: bool = True,
    selected: tuple[int, ...] = (1, 2),
    started: tuple[int, ...] = (),
    joined: int | None = None,
) -> JointClassFacts:
    return JointClassFacts(
        class_id=class_id,
        class_name=name or f"Turma {class_id}",
        has_subject=has_subject,
        selected_module_ids=frozenset(selected),
        started_module_ids=frozenset(started),
        joined_group_id=joined,
    )


MODULE_NAMES = {1: "M1", 2: "M2", 3: "M3"}


def test_fewer_than_two_classes_is_rejected():
    violation = policy.validate_two_classes([1])
    assert violation is not None
    assert violation.code == policy.JOINT_TOO_FEW_CLASSES
    assert violation.message == "Escolha pelo menos duas turmas."


def test_class_without_subject_is_rejected():
    violation = policy.validate_classes_have_subject(
        "Português", [_facts(1), _facts(2, has_subject=False)]
    )
    assert violation is not None
    assert violation.code == policy.JOINT_CLASS_WITHOUT_SUBJECT
    assert "Turma 2" in violation.message
    assert "Português" in violation.message


def test_class_already_joined_is_rejected():
    violation = policy.validate_classes_not_joined("Português", [_facts(1, joined=7), _facts(2)])
    assert violation is not None
    assert violation.code == policy.JOINT_CLASS_ALREADY_JOINED


def test_empty_module_list_is_rejected():
    violation = policy.validate_has_modules([])
    assert violation is not None
    assert violation.code == policy.JOINT_NO_MODULES


def test_module_not_selected_in_a_class_is_rejected():
    violation = policy.validate_modules_selected(
        "Português",
        [_facts(1, selected=(1,)), _facts(2, selected=(1, 2))],
        [1, 2],
        MODULE_NAMES,
    )
    assert violation is not None
    assert violation.code == policy.JOINT_MODULE_NOT_SELECTED
    assert "M2" in violation.message


def test_ineligible_teacher_is_rejected():
    violation = policy.validate_teacher_eligible(9, frozenset({1, 2}))
    assert violation is not None
    assert violation.code == policy.JOINT_TEACHER_NOT_ELIGIBLE


def test_missing_teacher_is_rejected():
    violation = policy.validate_teacher_eligible(None, frozenset({1, 2}))
    assert violation is not None
    assert violation.code == policy.JOINT_TEACHER_NOT_ELIGIBLE


def test_module_started_entering_the_joint_set_is_rejected():
    violation = policy.validate_modules_not_started(
        previous_module_ids=[1],
        next_module_ids=[1, 2],
        started_module_ids=frozenset({2}),
        module_names=MODULE_NAMES,
    )
    assert violation is not None
    assert violation.code == policy.JOINT_MODULE_STARTED
    assert "M2" in violation.message


def test_module_started_that_stays_with_the_same_classes_is_allowed():
    violation = policy.validate_modules_not_started(
        previous_module_ids=[1, 2],
        next_module_ids=[1, 2],
        started_module_ids=frozenset({1, 2}),
        module_names=MODULE_NAMES,
    )
    assert violation is None


def test_changing_classes_after_joint_start_is_rejected():
    violation = policy.validate_classes_not_started(
        previous_class_ids=[1, 2], next_class_ids=[1, 2, 3], joint_module_started=True
    )
    assert violation is not None
    assert violation.code == policy.JOINT_CLASS_STARTED


def test_same_classes_after_joint_start_is_allowed():
    assert (
        policy.validate_classes_not_started(
            previous_class_ids=[1, 2], next_class_ids=[2, 1], joint_module_started=True
        )
        is None
    )


def test_valid_configuration_returns_none():
    violation = policy.validate_joint_configuration(
        subject_name="Português",
        class_ids=[1, 2],
        classes=[_facts(1), _facts(2)],
        module_ids=[1, 2],
        module_names=MODULE_NAMES,
        teacher_id=5,
        eligible_teacher_ids=frozenset({5}),
    )
    assert violation is None
