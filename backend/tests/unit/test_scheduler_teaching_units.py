"""Joint teaching units: segmentation, keys, deficit and precedence (WBS 2.2)."""

from __future__ import annotations

import pytest

from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.domain.teaching_units import (
    AssignmentPlan,
    JointGroupPlan,
    JointTeacherMismatch,
    build_teaching_units,
)

SUBJECT = 1
TEACHER = 7
REQUIRED = 1500

# Reference example from the tech spec: Portugues, M1..M4 joint.
MKT_MODULES = (
    ModuleRequirement(1, 1, REQUIRED),
    ModuleRequirement(2, 2, REQUIRED),
    ModuleRequirement(3, 3, REQUIRED),
    ModuleRequirement(4, 4, REQUIRED),
    ModuleRequirement(5, 5, REQUIRED),
)
MAS_MODULES = (
    ModuleRequirement(1, 1, REQUIRED),
    ModuleRequirement(2, 2, REQUIRED),
    ModuleRequirement(3, 3, REQUIRED),
    ModuleRequirement(4, 4, REQUIRED),
    ModuleRequirement(6, 6, REQUIRED),
)


def assignment(
    assignment_id,
    class_id,
    modules,
    *,
    executed=None,
    subject_id=SUBJECT,
    teacher_id=TEACHER,
    students=20,
):
    return AssignmentPlan(
        assignment_id,
        class_id,
        subject_id,
        teacher_id,
        students,
        tuple(modules),
        dict(executed or {}),
    )


def group(group_id, module_ids, members, *, subject_id=SUBJECT):
    return JointGroupPlan(group_id, subject_id, tuple(members), tuple(module_ids))


def reference_group():
    return (
        (assignment(1, 10, MKT_MODULES), assignment(2, 20, MAS_MODULES)),
        (group(1, (1, 2, 3, 4), (1, 2)),),
    )


def reference_plan(*, mkt_executed=None, mas_executed=None, published=frozenset()):
    _, groups = reference_group()
    return build_teaching_units(
        (
            assignment(1, 10, MKT_MODULES, executed=mkt_executed),
            assignment(2, 20, MAS_MODULES, executed=mas_executed),
        ),
        groups,
        published,
    )


def unit_by_key(plan, key):
    return next(unit for unit in plan.units if unit.key == key)


def test_ungrouped_assignment_keeps_its_assignment_identifier():
    plan = build_teaching_units((assignment(4, 10, MKT_MODULES),), (), frozenset())

    assert plan.unit_ids == {"A:4": 4}
    unit = plan.units[0]
    assert unit.unit_id == 4
    assert unit.key == "A:4"
    assert unit.class_ids == (10,)
    assert [module.module_id for module in unit.modules] == [1, 2, 3, 4, 5]
    assert plan.accounting_assignments == {4: (4,)}
    assert plan.precedences == ()


def test_reference_example_splits_shared_and_separate_segments():
    plan = build_teaching_units(*reference_group(), frozenset())

    assert {unit.key for unit in plan.units} == {"J:1:1", "S:1:5", "S:2:6"}
    joint = unit_by_key(plan, "J:1:1")
    assert joint.class_ids == (10, 20)
    assert [module.module_id for module in joint.modules] == [1, 2, 3, 4]
    assert [module.module_id for module in unit_by_key(plan, "S:1:5").modules] == [5]
    assert [module.module_id for module in unit_by_key(plan, "S:2:6").modules] == [6]
    assert plan.precedences == (
        (plan.unit_ids["J:1:1"], plan.unit_ids["S:1:5"]),
        (plan.unit_ids["J:1:1"], plan.unit_ids["S:2:6"]),
    )


def test_separate_module_between_shared_modules_creates_a_boundary():
    assignments = (
        assignment(
            1,
            10,
            (
                ModuleRequirement(1, 1, REQUIRED),
                ModuleRequirement(2, 2, REQUIRED),
                ModuleRequirement(3, 3, REQUIRED),
            ),
        ),
        assignment(2, 20, (ModuleRequirement(1, 1, REQUIRED), ModuleRequirement(3, 3, REQUIRED))),
    )

    plan = build_teaching_units(assignments, (group(1, (1, 3), (1, 2)),), frozenset())

    assert {unit.key for unit in plan.units} == {"J:1:1", "J:1:3", "S:1:2"}
    assert [m.module_id for m in unit_by_key(plan, "J:1:1").modules] == [1]
    assert [m.module_id for m in unit_by_key(plan, "J:1:3").modules] == [3]
    assert set(plan.precedences) == {
        (plan.unit_ids["J:1:1"], plan.unit_ids["S:1:2"]),
        (plan.unit_ids["S:1:2"], plan.unit_ids["J:1:3"]),
        (plan.unit_ids["J:1:1"], plan.unit_ids["J:1:3"]),
    }


def test_retired_module_outside_the_inputs_creates_no_boundary():
    assignments = (
        assignment(1, 10, (ModuleRequirement(1, 1, REQUIRED), ModuleRequirement(3, 3, REQUIRED))),
        assignment(2, 20, (ModuleRequirement(1, 1, REQUIRED), ModuleRequirement(3, 3, REQUIRED))),
    )

    plan = build_teaching_units(assignments, (group(1, (1, 3), (1, 2)),), frozenset())

    assert {unit.key for unit in plan.units} == {"J:1:1"}
    assert [m.module_id for m in unit_by_key(plan, "J:1:1").modules] == [1, 3]


def test_absent_class_creates_a_deficit_unit_with_the_exact_minutes():
    plan = reference_plan(mkt_executed={1: REQUIRED}, mas_executed={1: REQUIRED - 50})

    deficit = unit_by_key(plan, "D:2:1")
    assert deficit.class_ids == (20,)
    assert [module.module_id for module in deficit.modules] == [1]
    assert deficit.modules[0].required_minutes == REQUIRED
    assert dict(deficit.executed_minutes) == {1: REQUIRED - 50}
    assert "D:1:1" not in {unit.key for unit in plan.units}
    joint_unit = unit_by_key(plan, "J:1:1")
    assert dict(joint_unit.executed_minutes) == {1: REQUIRED, 2: 0, 3: 0, 4: 0}


def test_correction_ahead_creates_the_deficit_on_the_other_class():
    plan = reference_plan(mkt_executed={1: REQUIRED})

    deficit = unit_by_key(plan, "D:2:1")
    assert deficit.modules[0].required_minutes == REQUIRED
    assert dict(deficit.executed_minutes) == {1: 0}
    assert "D:1:1" not in {unit.key for unit in plan.units}


def test_deficit_and_joint_segments_have_no_within_stage_precedence():
    plan = reference_plan(mkt_executed={1: REQUIRED}, mas_executed={1: REQUIRED - 50})

    joint_id = plan.unit_ids["J:1:1"]
    deficit_id = plan.unit_ids["D:2:1"]
    assert (joint_id, deficit_id) not in plan.precedences
    assert (deficit_id, joint_id) not in plan.precedences
    assert (deficit_id, plan.unit_ids["S:2:6"]) in plan.precedences


def test_completed_unit_creates_no_precedence_and_the_chain_skips_it():
    assignments = (
        assignment(1, 10, MKT_MODULES, executed={2: REQUIRED}),
        assignment(
            2,
            20,
            (ModuleRequirement(1, 1, REQUIRED), ModuleRequirement(3, 3, REQUIRED)),
        ),
    )

    plan = build_teaching_units(assignments, (group(1, (1, 3), (1, 2)),), frozenset())

    completed = unit_by_key(plan, "S:1:2")
    residual = sum(
        module.required_minutes - completed.executed_minutes[module.module_id]
        for module in completed.modules
    )
    assert residual == 0
    assert all(completed.unit_id not in edge for edge in plan.precedences)
    assert set(plan.precedences) == {
        (plan.unit_ids["J:1:1"], plan.unit_ids["J:1:3"]),
        (plan.unit_ids["J:1:3"], plan.unit_ids["S:1:4"]),
    }


def test_published_zero_deficit_deficit_key_is_retained():
    executed = {module_id: REQUIRED for module_id in (1, 2, 3, 4)}
    plan = reference_plan(
        mkt_executed=executed,
        mas_executed=executed,
        published=frozenset({"D:2:1"}),
    )

    deficit = unit_by_key(plan, "D:2:1")
    assert [module.module_id for module in deficit.modules] == [1, 2, 3, 4]
    assert [module.required_minutes for module in deficit.modules] == [REQUIRED] * 4
    assert dict(deficit.executed_minutes) == executed
    assert plan.unit_ids["D:2:1"] in {unit.unit_id for unit in plan.units}


def test_retired_deficit_key_without_execution_is_not_created():
    executed = {module_id: REQUIRED for module_id in (1, 2, 3, 4)}
    plan = reference_plan(mkt_executed=executed, mas_executed=executed)

    assert "D:2:1" not in {unit.key for unit in plan.units}


def test_identifiers_are_deterministic_and_above_the_max_assignment_id():
    inputs = reference_group()

    first = build_teaching_units(*inputs, frozenset())
    second = build_teaching_units(*inputs, frozenset())

    assert first == second
    other_keys = sorted(key for key in first.unit_ids if not key.startswith("A:"))
    assert [first.unit_ids[key] for key in other_keys] == [3, 4, 5]
    assert {unit.key: unit.unit_id for unit in first.units} == dict(first.unit_ids)


def test_accounting_assignments_map_every_unit_to_its_payer_classes():
    plan = build_teaching_units(*reference_group(), frozenset())

    assert plan.accounting_assignments[plan.unit_ids["J:1:1"]] == (1, 2)
    assert plan.accounting_assignments[plan.unit_ids["S:1:5"]] == (1,)
    assert plan.accounting_assignments[plan.unit_ids["S:2:6"]] == (2,)


def test_units_are_immutable():
    plan = build_teaching_units((assignment(4, 10, MKT_MODULES),), (), frozenset())

    with pytest.raises(TypeError):
        plan.units[0].executed_minutes[1] = 10  # type: ignore[index]


def test_teacher_mismatch_raises_a_named_domain_error():
    assignments = (
        assignment(1, 10, MKT_MODULES),
        assignment(2, 20, MAS_MODULES, teacher_id=99),
    )

    with pytest.raises(JointTeacherMismatch) as failure:
        build_teaching_units(assignments, (group(1, (1, 2), (1, 2)),), frozenset())

    assert failure.value.code == "JOINT_TEACHER_MISMATCH"


def test_unknown_member_assignment_is_rejected_not_dropped():
    with pytest.raises(ValueError):
        build_teaching_units(
            (assignment(1, 10, MKT_MODULES),),
            (group(1, (1, 2), (1, 9)),),
            frozenset(),
        )


def test_joint_module_missing_from_a_member_is_rejected():
    assignments = (
        assignment(1, 10, MKT_MODULES),
        assignment(2, 20, (ModuleRequirement(1, 1, REQUIRED),)),
    )

    with pytest.raises(ValueError):
        build_teaching_units(assignments, (group(1, (1, 2), (1, 2)),), frozenset())


def test_group_subject_must_match_every_member():
    assignments = (
        assignment(1, 10, MKT_MODULES),
        assignment(2, 20, MAS_MODULES, subject_id=2),
    )

    with pytest.raises(ValueError):
        build_teaching_units(assignments, (group(1, (1, 2), (1, 2)),), frozenset())


def test_assignment_cannot_join_two_groups():
    assignments = (
        assignment(1, 10, MKT_MODULES),
        assignment(2, 20, MAS_MODULES),
        assignment(3, 30, MAS_MODULES),
    )
    groups = (group(1, (1, 2), (1, 2)), group(2, (1, 2), (1, 3)))

    with pytest.raises(ValueError):
        build_teaching_units(assignments, groups, frozenset())


def test_duplicate_assignment_identifiers_are_rejected():
    with pytest.raises(ValueError):
        build_teaching_units(
            (assignment(1, 10, MKT_MODULES), assignment(1, 20, MAS_MODULES)),
            (),
            frozenset(),
        )
