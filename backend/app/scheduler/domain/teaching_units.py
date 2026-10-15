"""Pure planning units for joint lessons (JOINT_LESSONS WBS 2.2.1-2.2.4).

The builder turns per-class assignment plans and joint-group plans into the
units the scheduler plans. It owns no database, framework or solver: the same
input always produces the same units, keys, identifiers and precedences.

A unit replaces the role of an ``Assignment``: it carries one or more classes,
the subject, the teacher, the modules still open and the minutes already
executed. Joint modules credit every member class with the joint progress, the
largest executed count across the group. A class left behind gets a deficit
unit whose requirement is that joint progress.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from types import MappingProxyType

from app.scheduler.domain.projection import ModuleRequirement


class JointTeacherMismatch(ValueError):
    """Joint member classes do not share one teacher (JOINT_TEACHER_MISMATCH)."""

    code = "JOINT_TEACHER_MISMATCH"


def _positive(value: object, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")


def _frozen_minutes(values: Mapping[int, int]) -> Mapping[int, int]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class AssignmentPlan:
    """One class-subject assignment before joint segmentation."""

    assignment_id: int
    class_id: int
    subject_id: int
    teacher_id: int
    student_count: int
    modules: tuple[ModuleRequirement, ...]
    executed_minutes: Mapping[int, int]

    def __post_init__(self) -> None:
        for name in ("assignment_id", "class_id", "subject_id", "teacher_id"):
            _positive(getattr(self, name), name)
        if type(self.student_count) is not int or self.student_count < 0:
            raise ValueError("student_count must be a nonnegative integer.")
        modules = tuple(self.modules)
        if not modules or any(type(module) is not ModuleRequirement for module in modules):
            raise ValueError("An assignment plan needs at least one ModuleRequirement.")
        if len({module.module_id for module in modules}) != len(modules):
            raise ValueError("Module IDs must be unique within an assignment.")
        if len({module.sequence for module in modules}) != len(modules):
            raise ValueError("Module sequences must be unique within an assignment.")
        if not isinstance(self.executed_minutes, Mapping):
            raise ValueError("Executed minutes must be a mapping.")
        required = {module.module_id: module.required_minutes for module in modules}
        for module_id, minutes in self.executed_minutes.items():
            if module_id not in required:
                raise ValueError("Executed minutes reference an unknown module.")
            if type(minutes) is not int or not 0 <= minutes <= required[module_id]:
                raise ValueError("Executed minutes are outside the module requirement.")
        object.__setattr__(self, "modules", modules)
        object.__setattr__(self, "executed_minutes", _frozen_minutes(self.executed_minutes))


@dataclass(frozen=True)
class JointGroupPlan:
    """One joint group: a subject, its member assignments and its joint modules."""

    group_id: int
    subject_id: int
    member_assignment_ids: tuple[int, ...]
    module_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        _positive(self.group_id, "group_id")
        _positive(self.subject_id, "subject_id")
        members = tuple(self.member_assignment_ids)
        if len(members) < 2 or len(set(members)) != len(members):
            raise ValueError("A joint group needs at least two distinct member assignments.")
        if any(type(member) is not int or member <= 0 for member in members):
            raise ValueError("Member assignment IDs must be positive integers.")
        module_ids = tuple(self.module_ids)
        if not module_ids or len(set(module_ids)) != len(module_ids):
            raise ValueError("A joint group needs distinct joint module IDs.")
        if any(type(module_id) is not int or module_id <= 0 for module_id in module_ids):
            raise ValueError("Joint module IDs must be positive integers.")
        object.__setattr__(self, "member_assignment_ids", members)
        object.__setattr__(self, "module_ids", module_ids)


@dataclass(frozen=True)
class TeachingUnit:
    """One planning unit: classes, subject, teacher, modules and executed minutes."""

    unit_id: int
    key: str
    subject_id: int
    teacher_id: int
    class_ids: tuple[int, ...]
    modules: tuple[ModuleRequirement, ...]
    executed_minutes: Mapping[int, int]

    def __post_init__(self) -> None:
        _positive(self.unit_id, "unit_id")
        if not isinstance(self.key, str) or not self.key:
            raise ValueError("A teaching unit needs a non-empty key.")
        _positive(self.subject_id, "subject_id")
        _positive(self.teacher_id, "teacher_id")
        class_ids = tuple(self.class_ids)
        if not class_ids or len(set(class_ids)) != len(class_ids):
            raise ValueError("A teaching unit needs distinct class IDs.")
        if any(type(class_id) is not int or class_id <= 0 for class_id in class_ids):
            raise ValueError("Class IDs must be positive integers.")
        if tuple(sorted(class_ids)) != class_ids:
            raise ValueError("Class IDs must be sorted.")
        modules = tuple(self.modules)
        if any(type(module) is not ModuleRequirement for module in modules):
            raise ValueError("Teaching unit modules must be ModuleRequirement values.")
        if len({module.module_id for module in modules}) != len(modules):
            raise ValueError("Teaching unit module IDs must be unique.")
        executed = dict(self.executed_minutes)
        if any(type(minutes) is not int or minutes < 0 for minutes in executed.values()):
            raise ValueError("Executed minutes must be nonnegative integers.")
        object.__setattr__(self, "class_ids", class_ids)
        object.__setattr__(self, "modules", modules)
        object.__setattr__(self, "executed_minutes", _frozen_minutes(executed))

    @property
    def residual_minutes(self) -> int:
        """Minutes still to plan: requirement minus executed on every module."""
        return sum(
            module.required_minutes - self.executed_minutes.get(module.module_id, 0)
            for module in self.modules
        )


@dataclass(frozen=True)
class TeachingUnitPlan:
    """The units, their precedences and the accounting and identity maps."""

    units: tuple[TeachingUnit, ...]
    precedences: tuple[tuple[int, int], ...]
    accounting_assignments: Mapping[int, tuple[int, ...]]
    unit_ids: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "units", tuple(self.units))
        object.__setattr__(self, "precedences", tuple(self.precedences))
        object.__setattr__(
            self,
            "accounting_assignments",
            MappingProxyType(
                {unit_id: tuple(payers) for unit_id, payers in self.accounting_assignments.items()}
            ),
        )
        object.__setattr__(self, "unit_ids", MappingProxyType(dict(self.unit_ids)))


@dataclass(frozen=True)
class _UnitSeed:
    key: str
    class_ids: tuple[int, ...]
    subject_id: int
    teacher_id: int
    modules: tuple[ModuleRequirement, ...]
    executed_minutes: Mapping[int, int]
    assignment_id: int | None = None


@dataclass(frozen=True)
class _GroupBuild:
    seeds: tuple[_UnitSeed, ...]
    stage_keys: Mapping[int, tuple[tuple[str, ...], ...]]
    accounting: Mapping[str, tuple[int, ...]]


def _ordered_modules(assignment: AssignmentPlan) -> tuple[ModuleRequirement, ...]:
    return tuple(sorted(assignment.modules, key=lambda module: (module.sequence, module.module_id)))


def _executed_map(
    assignment: AssignmentPlan, modules: Sequence[ModuleRequirement]
) -> dict[int, int]:
    return {
        module.module_id: assignment.executed_minutes.get(module.module_id, 0) for module in modules
    }


def _index_assignments(assignments: Sequence[AssignmentPlan]) -> dict[int, AssignmentPlan]:
    indexed: dict[int, AssignmentPlan] = {}
    for assignment in assignments:
        if type(assignment) is not AssignmentPlan:
            raise ValueError("Assignments must be AssignmentPlan values.")
        if assignment.assignment_id in indexed:
            raise ValueError("Assignment IDs must be unique.")
        indexed[assignment.assignment_id] = assignment
    if not indexed:
        raise ValueError("At least one assignment is required.")
    return indexed


def _index_groups(
    groups: Sequence[JointGroupPlan], by_id: Mapping[int, AssignmentPlan]
) -> dict[int, JointGroupPlan]:
    by_assignment: dict[int, JointGroupPlan] = {}
    seen: set[int] = set()
    for group in groups:
        if type(group) is not JointGroupPlan:
            raise ValueError("Groups must be JointGroupPlan values.")
        if group.group_id in seen:
            raise ValueError("Joint group IDs must be unique.")
        seen.add(group.group_id)
        for assignment_id in group.member_assignment_ids:
            member = by_id.get(assignment_id)
            if member is None:
                raise ValueError("A joint group references an unknown assignment.")
            if member.subject_id != group.subject_id:
                raise ValueError("A joint group member does not share the group subject.")
            if assignment_id in by_assignment:
                raise ValueError("An assignment belongs to more than one joint group.")
            by_assignment[assignment_id] = group
    return by_assignment


def _shared_teacher(members: Sequence[AssignmentPlan]) -> int:
    teachers = {member.teacher_id for member in members}
    if len(teachers) != 1:
        raise JointTeacherMismatch(
            "JOINT_TEACHER_MISMATCH: joint member classes must share one teacher."
        )
    return members[0].teacher_id


def _joint_segments(
    members: Sequence[AssignmentPlan], joint_ids: Set[int]
) -> list[list[ModuleRequirement]]:
    """Split the joint modules into segments at any member's separate module."""
    reference = _ordered_modules(members[0])
    joint_modules = [module for module in reference if module.module_id in joint_ids]
    if len(joint_modules) != len(joint_ids):
        raise ValueError("A joint module is not selected by every member class.")
    for member in members:
        selected = {module.module_id: module for module in member.modules}
        for module in joint_modules:
            other = selected.get(module.module_id)
            if other is None:
                raise ValueError("A joint module is not selected by every member class.")
            if other != module:
                raise ValueError("A joint module differs across member classes.")

    segments: list[list[ModuleRequirement]] = [[joint_modules[0]]]
    for previous, following in zip(joint_modules, joint_modules[1:], strict=False):
        if _has_separate_between(members, joint_ids, previous.sequence, following.sequence):
            segments.append([following])
        else:
            segments[-1].append(following)
    return segments


def _has_separate_between(
    members: Sequence[AssignmentPlan], joint_ids: Set[int], low: int, high: int
) -> bool:
    return any(
        module.module_id not in joint_ids and low < module.sequence < high
        for member in members
        for module in member.modules
    )


def _separate_segments(
    member: AssignmentPlan, joint_ids: Set[int], segments: Sequence[Sequence[ModuleRequirement]]
) -> list[list[ModuleRequirement]]:
    """The member's separate runs ``S0, S1, ..., Sn`` between the joint segments."""
    segment_of = {
        module.module_id: index for index, segment in enumerate(segments) for module in segment
    }
    buckets: list[list[ModuleRequirement]] = [[] for _ in range(len(segments) + 1)]
    current = 0
    for module in _ordered_modules(member):
        if module.module_id in joint_ids:
            current = segment_of[module.module_id] + 1
        else:
            buckets[current].append(module)
    return buckets


def _joint_progress(
    segments: Sequence[Sequence[ModuleRequirement]], members: Sequence[AssignmentPlan]
) -> dict[int, int]:
    return {
        module.module_id: max(
            member.executed_minutes.get(module.module_id, 0) for member in members
        )
        for segment in segments
        for module in segment
    }


def _deficit_seed(
    member: AssignmentPlan,
    segment: Sequence[ModuleRequirement],
    joint_progress: Mapping[int, int],
    published_unit_keys: Set[str],
) -> _UnitSeed | None:
    key = f"D:{member.assignment_id}:{segment[0].module_id}"
    deficits = [
        joint_progress[module.module_id] - member.executed_minutes.get(module.module_id, 0)
        for module in segment
    ]
    if key not in published_unit_keys and not any(deficit > 0 for deficit in deficits):
        return None
    modules = tuple(
        ModuleRequirement(module.module_id, module.sequence, joint_progress[module.module_id])
        for module in segment
        if joint_progress[module.module_id] > 0
    )
    executed = {
        module.module_id: member.executed_minutes.get(module.module_id, 0) for module in modules
    }
    return _UnitSeed(
        key, (member.class_id,), member.subject_id, member.teacher_id, modules, executed
    )


def _build_group(
    group: JointGroupPlan,
    by_id: Mapping[int, AssignmentPlan],
    published_unit_keys: Set[str],
) -> _GroupBuild:
    members = sorted(
        (by_id[assignment_id] for assignment_id in group.member_assignment_ids),
        key=lambda member: member.assignment_id,
    )
    teacher_id = _shared_teacher(members)
    joint_ids = set(group.module_ids)
    segments = _joint_segments(members, joint_ids)
    joint_progress = _joint_progress(segments, members)
    class_ids = tuple(sorted(member.class_id for member in members))

    seeds: list[_UnitSeed] = []
    accounting: dict[str, tuple[int, ...]] = {}
    joint_keys: list[str] = []
    for segment in segments:
        key = f"J:{group.group_id}:{segment[0].module_id}"
        joint_keys.append(key)
        seeds.append(
            _UnitSeed(
                key,
                class_ids,
                group.subject_id,
                teacher_id,
                tuple(segment),
                {module.module_id: joint_progress[module.module_id] for module in segment},
            )
        )
        accounting[key] = tuple(member.assignment_id for member in members)

    stage_keys: dict[int, tuple[tuple[str, ...], ...]] = {}
    for member in members:
        separate = _separate_segments(member, joint_ids, segments)
        stages: list[list[str]] = []
        if separate[0]:
            key = f"S:{member.assignment_id}:{separate[0][0].module_id}"
            seeds.append(
                _UnitSeed(
                    key,
                    (member.class_id,),
                    member.subject_id,
                    teacher_id,
                    tuple(separate[0]),
                    _executed_map(member, separate[0]),
                )
            )
            accounting[key] = (member.assignment_id,)
            stages.append([key])
        for index, segment in enumerate(segments):
            stage = [joint_keys[index]]
            deficit = _deficit_seed(member, segment, joint_progress, published_unit_keys)
            if deficit is not None:
                seeds.append(deficit)
                accounting[deficit.key] = (member.assignment_id,)
                stage.append(deficit.key)
            stages.append(stage)
            if separate[index + 1]:
                key = f"S:{member.assignment_id}:{separate[index + 1][0].module_id}"
                seeds.append(
                    _UnitSeed(
                        key,
                        (member.class_id,),
                        member.subject_id,
                        teacher_id,
                        tuple(separate[index + 1]),
                        _executed_map(member, separate[index + 1]),
                    )
                )
                accounting[key] = (member.assignment_id,)
                stages.append([key])
        stage_keys[member.assignment_id] = tuple(tuple(stage) for stage in stages)

    return _GroupBuild(tuple(seeds), stage_keys, accounting)


def _assign_ids(seeds: Sequence[_UnitSeed], max_assignment_id: int) -> dict[str, int]:
    unit_ids: dict[str, int] = {}
    other_keys: list[str] = []
    for seed in seeds:
        if seed.assignment_id is not None:
            unit_ids[seed.key] = seed.assignment_id
        else:
            other_keys.append(seed.key)
    next_id = max_assignment_id + 1
    for key in sorted(other_keys):
        unit_ids[key] = next_id
        next_id += 1
    return unit_ids


def _precedences(
    units: Sequence[TeachingUnit],
    stage_keys: Mapping[int, tuple[tuple[str, ...], ...]],
    unit_ids: Mapping[str, int],
) -> tuple[tuple[int, int], ...]:
    residual = {unit.unit_id: unit.residual_minutes for unit in units}
    edges: set[tuple[int, int]] = set()
    for stages in stage_keys.values():
        remaining = [
            [unit_ids[key] for key in stage if residual[unit_ids[key]] > 0] for stage in stages
        ]
        remaining = [stage for stage in remaining if stage]
        for earlier, later in zip(remaining, remaining[1:], strict=False):
            for source in earlier:
                for target in later:
                    edges.add((source, target))
    return tuple(sorted(edges))


def build_teaching_units(
    assignments: Sequence[AssignmentPlan],
    groups: Sequence[JointGroupPlan],
    published_unit_keys: Set[str],
) -> TeachingUnitPlan:
    """Split class assignments into planning units with strict precedence.

    ``assignments`` carries every class-subject assignment in the planning view.
    ``groups`` carries the joint groups over those assignments. ``published_unit_keys``
    keeps a deficit unit alive after its published lessons made the deficit zero.
    """
    by_id = _index_assignments(tuple(assignments))
    group_by_assignment = _index_groups(tuple(groups), by_id)

    seeds: list[_UnitSeed] = []
    stage_keys: dict[int, tuple[tuple[str, ...], ...]] = {}
    accounting: dict[str, tuple[int, ...]] = {}
    for assignment in sorted(by_id.values(), key=lambda member: member.assignment_id):
        if assignment.assignment_id in group_by_assignment:
            continue
        modules = _ordered_modules(assignment)
        key = f"A:{assignment.assignment_id}"
        seeds.append(
            _UnitSeed(
                key,
                (assignment.class_id,),
                assignment.subject_id,
                assignment.teacher_id,
                modules,
                _executed_map(assignment, modules),
                assignment.assignment_id,
            )
        )
        accounting[key] = (assignment.assignment_id,)

    groups_by_id = {group.group_id: group for group in group_by_assignment.values()}
    for group in sorted(groups_by_id.values(), key=lambda item: item.group_id):
        build = _build_group(group, by_id, published_unit_keys)
        seeds.extend(build.seeds)
        stage_keys.update(build.stage_keys)
        accounting.update(build.accounting)

    unit_ids = _assign_ids(seeds, max(by_id))
    units = tuple(
        sorted(
            (
                TeachingUnit(
                    unit_ids[seed.key],
                    seed.key,
                    seed.subject_id,
                    seed.teacher_id,
                    seed.class_ids,
                    seed.modules,
                    seed.executed_minutes,
                )
                for seed in seeds
            ),
            key=lambda unit: unit.unit_id,
        )
    )
    precedences = _precedences(units, stage_keys, unit_ids)
    accounting_by_id = {unit_ids[key]: payers for key, payers in accounting.items()}
    return TeachingUnitPlan(units, precedences, accounting_by_id, unit_ids)
