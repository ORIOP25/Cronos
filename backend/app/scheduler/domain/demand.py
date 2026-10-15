"""Append-only curricular credit and exact residual demand."""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.scheduler.domain.projection import ModuleRequirement


@dataclass(frozen=True)
class ModuleCredit:
    module_id: int
    minutes: int

    def __post_init__(self) -> None:
        if type(self.module_id) is not int or self.module_id <= 0:
            raise ValueError("module_id must be positive.")
        if type(self.minutes) is not int or self.minutes == 0:
            raise ValueError("Credit delta must be a nonzero integer of minutes.")


@dataclass(frozen=True)
class ExecutionEntry:
    origin: str
    revision: int
    author_id: int
    reason: str
    credits: tuple[ModuleCredit, ...]
    reversal_of: tuple[str, int] | None = None
    recorded_at: datetime = field(kw_only=True)

    def __post_init__(self) -> None:
        if not self.origin or not self.reason:
            raise ValueError("Execution origin and reason are required.")
        if type(self.revision) is not int or self.revision <= 0:
            raise ValueError("Execution revision must be positive.")
        if type(self.author_id) is not int or self.author_id <= 0:
            raise ValueError("Execution author must be positive.")
        if (
            type(self.credits) is not tuple
            or not self.credits
            or len({credit.module_id for credit in self.credits}) != len(self.credits)
        ):
            raise ValueError("Execution needs distinct module credits.")
        if self.reversal_of == (self.origin, self.revision):
            raise ValueError("An execution cannot reverse itself.")
        if type(self.recorded_at) is not datetime or self.recorded_at.utcoffset() != timedelta(0):
            raise ValueError("Execution audit instant must be UTC with timezone.")

    @property
    def key(self) -> tuple[str, int]:
        return self.origin, self.revision


def completed_by_module(
    modules: Sequence[ModuleRequirement], entries: Sequence[ExecutionEntry]
) -> dict[int, int]:
    required = {module.module_id: module.required_minutes for module in modules}
    if len(required) != len(modules):
        raise ValueError("Module IDs must be unique.")
    completed = dict.fromkeys(required, 0)
    seen = {}
    reversed_minutes: dict[tuple[tuple[str, int], int], int] = {}
    for entry in entries:
        if entry.key in seen:
            raise ValueError("Execution origin and revision must be unique.")
        if entry.reversal_of is not None:
            original = seen.get(entry.reversal_of)
            if original is None:
                raise ValueError("Reversal must reference an earlier execution.")
            original_credits = {credit.module_id: credit.minutes for credit in original.credits}
            for credit in entry.credits:
                original_minutes = original_credits.get(credit.module_id)
                if original_minutes is None or credit.minutes * original_minutes >= 0:
                    raise ValueError("Reversal must oppose credit from the referenced entry.")
                key = (entry.reversal_of, credit.module_id)
                reversed_minutes[key] = reversed_minutes.get(key, 0) + abs(credit.minutes)
                if reversed_minutes[key] > abs(original_minutes):
                    raise ValueError("Reversal exceeds the referenced credit.")
        for credit in entry.credits:
            if credit.module_id not in required:
                raise ValueError("Execution references an unknown module.")
            completed[credit.module_id] += credit.minutes
            if not 0 <= completed[credit.module_id] <= required[credit.module_id]:
                raise ValueError("Executed minutes are outside the module requirement.")
        seen[entry.key] = entry
    return completed


def append_execution(
    entries: tuple[ExecutionEntry, ...],
    entry: ExecutionEntry,
    modules: Sequence[ModuleRequirement],
) -> tuple[ExecutionEntry, ...]:
    for existing in entries:
        if existing.key == entry.key:
            if existing != entry:
                raise ValueError("Conflicting replay of an execution origin and revision.")
            completed_by_module(modules, entries)
            return entries
    updated = (*entries, entry)
    completed_by_module(modules, updated)
    return updated


def remaining_minutes(
    modules: Sequence[ModuleRequirement], entries: Sequence[ExecutionEntry]
) -> int:
    completed = completed_by_module(modules, entries)
    return sum(module.required_minutes - completed[module.module_id] for module in modules)


def frontier_credit(
    modules: Sequence[ModuleRequirement],
    completed: Mapping[int, int],
    minutes: int,
) -> tuple[ModuleCredit, ...]:
    """Sequential residual credit for one subject, without rounding."""
    credits: list[ModuleCredit] = []
    remaining = minutes
    for module in sorted(modules, key=lambda row: row.sequence):
        capacity = module.required_minutes - completed.get(module.module_id, 0)
        if capacity <= 0:
            continue
        take = min(remaining, capacity)
        credits.append(ModuleCredit(module.module_id, take))
        remaining -= take
        if remaining <= 0:
            break
    if remaining > 0:
        raise ValueError("Not enough residual curricular minutes for the credit.")
    return tuple(credits)


def joint_frontier_credit(
    modules: Sequence[ModuleRequirement],
    completed_by_class: Mapping[int, Mapping[int, int]],
    minutes: int,
) -> tuple[ModuleCredit, ...]:
    """Sequential credit over the joint progress, equal for every class (WBS 5.3.1).

    The joint progress of a module is the largest executed count across the
    member classes. The credit follows the strict sequence over that frontier,
    so every present class receives the same module credit and it never exceeds
    the residual of any member class.
    """
    if not completed_by_class:
        raise ValueError("Joint credit needs at least one class.")
    progress = {
        module.module_id: max(
            completed.get(module.module_id, 0) for completed in completed_by_class.values()
        )
        for module in modules
    }
    return frontier_credit(modules, progress, minutes)


def close_retired_modules(
    modules: Sequence[ModuleRequirement],
    retired: Set[int],
    completed: Mapping[int, int],
) -> tuple[tuple[ModuleRequirement, ...], dict[int, int]]:
    """Planning view: a retired module is closed at its executed minutes.

    A planned module keeps its catalogue requirement. A retired module with
    executed minutes is closed at those minutes, so it receives no new credit
    and no future lesson. A retired module without executed minutes leaves the
    planning view. The returned minutes are limited to the modules that remain.
    """
    planned: list[ModuleRequirement] = []
    closed_completed: dict[int, int] = {}
    for module in modules:
        executed = completed.get(module.module_id, 0)
        if module.module_id in retired:
            if executed <= 0:
                continue
            planned.append(ModuleRequirement(module.module_id, module.sequence, executed))
            closed_completed[module.module_id] = executed
            continue
        planned.append(module)
        closed_completed[module.module_id] = executed
    return tuple(planned), closed_completed
