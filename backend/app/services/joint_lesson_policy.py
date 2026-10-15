"""Pure configuration rules for joint lesson groups (J03-J06, J19).

The service loads the data and calls these functions, each of which returns the
first violated rule or ``None``. No SQLAlchemy, FastAPI or framework import lives
here, so the rules are covered by fast unit tests.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

JOINT_TOO_FEW_CLASSES = "JOINT_TOO_FEW_CLASSES"
JOINT_CLASS_WITHOUT_SUBJECT = "JOINT_CLASS_WITHOUT_SUBJECT"
JOINT_CLASS_ALREADY_JOINED = "JOINT_CLASS_ALREADY_JOINED"
JOINT_NO_MODULES = "JOINT_NO_MODULES"
JOINT_MODULE_NOT_SELECTED = "JOINT_MODULE_NOT_SELECTED"
JOINT_TEACHER_NOT_ELIGIBLE = "JOINT_TEACHER_NOT_ELIGIBLE"
JOINT_MODULE_STARTED = "JOINT_MODULE_STARTED"
JOINT_CLASS_STARTED = "JOINT_CLASS_STARTED"

UNKNOWN_MODULE_NAME = "?"


@dataclass(frozen=True)
class JointRuleViolation:
    code: str
    message: str


@dataclass(frozen=True)
class JointClassFacts:
    """Everything the pure rules need to know about one candidate class."""

    class_id: int
    class_name: str
    has_subject: bool
    selected_module_ids: frozenset[int]
    started_module_ids: frozenset[int]
    joined_group_id: int | None


def validate_two_classes(class_ids: Sequence[int]) -> JointRuleViolation | None:
    if len(set(class_ids)) < 2:
        return JointRuleViolation(JOINT_TOO_FEW_CLASSES, "Escolha pelo menos duas turmas.")
    return None


def validate_classes_have_subject(
    subject_name: str, classes: Sequence[JointClassFacts]
) -> JointRuleViolation | None:
    for facts in classes:
        if not facts.has_subject:
            return JointRuleViolation(
                JOINT_CLASS_WITHOUT_SUBJECT,
                f"A turma {facts.class_name} não tem {subject_name} este ano.",
            )
    return None


def validate_classes_not_joined(
    subject_name: str,
    classes: Sequence[JointClassFacts],
    ignore_group_id: int | None = None,
) -> JointRuleViolation | None:
    for facts in classes:
        if facts.joined_group_id is not None and facts.joined_group_id != ignore_group_id:
            return JointRuleViolation(
                JOINT_CLASS_ALREADY_JOINED,
                f"A turma {facts.class_name} já tem {subject_name} em conjunto com outras turmas.",
            )
    return None


def validate_has_modules(module_ids: Sequence[int]) -> JointRuleViolation | None:
    if not module_ids:
        return JointRuleViolation(JOINT_NO_MODULES, "Escolha pelo menos um módulo conjunto.")
    return None


def validate_modules_selected(
    subject_name: str,
    classes: Sequence[JointClassFacts],
    module_ids: Sequence[int],
    module_names: Mapping[int, str],
) -> JointRuleViolation | None:
    selected = set(module_ids)
    for facts in classes:
        missing = sorted(selected - facts.selected_module_ids)
        if missing:
            name = module_names.get(missing[0], UNKNOWN_MODULE_NAME)
            return JointRuleViolation(
                JOINT_MODULE_NOT_SELECTED,
                f"O módulo {name} não está marcado na turma {facts.class_name}.",
            )
    return None


def validate_teacher_eligible(
    teacher_id: int | None, eligible_teacher_ids: frozenset[int]
) -> JointRuleViolation | None:
    if teacher_id is None or teacher_id not in eligible_teacher_ids:
        return JointRuleViolation(
            JOINT_TEACHER_NOT_ELIGIBLE,
            "O professor indicado não tem competência na disciplina.",
        )
    return None


def validate_modules_not_started(
    previous_module_ids: Sequence[int],
    next_module_ids: Sequence[int],
    started_module_ids: frozenset[int],
    module_names: Mapping[int, str],
) -> JointRuleViolation | None:
    changed = set(previous_module_ids) ^ set(next_module_ids)
    started = sorted(changed & set(started_module_ids))
    if started:
        name = module_names.get(started[0], UNKNOWN_MODULE_NAME)
        return JointRuleViolation(
            JOINT_MODULE_STARTED,
            f"O módulo {name} já começou e não pode entrar nem sair da aula conjunta.",
        )
    return None


def validate_classes_not_started(
    previous_class_ids: Sequence[int],
    next_class_ids: Sequence[int],
    joint_module_started: bool,
) -> JointRuleViolation | None:
    if set(previous_class_ids) != set(next_class_ids) and joint_module_started:
        return JointRuleViolation(
            JOINT_CLASS_STARTED,
            "A aula conjunta já começou. Não pode juntar nem retirar turmas.",
        )
    return None


def validate_joint_configuration(
    *,
    subject_name: str,
    class_ids: Sequence[int],
    classes: Sequence[JointClassFacts],
    module_ids: Sequence[int],
    module_names: Mapping[int, str],
    teacher_id: int | None,
    eligible_teacher_ids: frozenset[int],
    previous_module_ids: Sequence[int] = (),
    previous_class_ids: Sequence[int] = (),
    previous_joint_module_started: bool = False,
    ignore_group_id: int | None = None,
) -> JointRuleViolation | None:
    """Return the first violated rule, following the spec table order."""
    started = frozenset().union(*(facts.started_module_ids for facts in classes))
    checks = (
        lambda: validate_two_classes(class_ids),
        lambda: validate_classes_have_subject(subject_name, classes),
        lambda: validate_classes_not_joined(subject_name, classes, ignore_group_id),
        lambda: validate_has_modules(module_ids),
        lambda: validate_modules_selected(subject_name, classes, module_ids, module_names),
        lambda: validate_teacher_eligible(teacher_id, eligible_teacher_ids),
        lambda: validate_classes_not_started(
            previous_class_ids, class_ids, previous_joint_module_started
        ),
        lambda: validate_modules_not_started(
            previous_module_ids, module_ids, started, module_names
        ),
    )
    for check in checks:
        violation = check()
        if violation is not None:
            return violation
    return None
