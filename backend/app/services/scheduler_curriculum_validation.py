"""Pure curriculum coverage checks shared by generation and approval."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.scheduler.domain.contracts import DraftBlockSpec
from app.services.scheduler_complete_demand import CompleteDemandLedger


@dataclass(frozen=True)
class CurriculumCoverageViolation:
    """One deterministic curriculum coverage violation."""

    message: str


def validate_curriculum_coverage(
    ledger: CompleteDemandLedger,
    specs: Iterable[DraftBlockSpec],
    *,
    select: Callable[[DraftBlockSpec], bool] | None = None,
    slot_start_values: Mapping[int | str, str] | None = None,
) -> tuple[CurriculumCoverageViolation, ...]:
    """Validate exact module minutes and chronological module order.

    ``select`` permits adaptive validation to inspect only newly added curriculum blocks.
    The function does not mutate the ledger or target specifications.
    """

    predicate = select or (lambda _spec: True)
    items = {(item.class_id, item.subject_id): item for item in ledger.items}
    expected = {
        (item.class_id, item.subject_id, module.sequence): module.required_minutes
        for item in ledger.items
        for module in item.modules
        if module.required_minutes > 0
    }
    actual: dict[tuple[int, int, int], int] = {}
    selected: list[DraftBlockSpec] = []
    violations: list[CurriculumCoverageViolation] = []
    for spec in specs:
        if not predicate(spec):
            continue
        selected.append(spec)
        item = items.get((spec.class_id, spec.subject_id))
        if item is None:
            violations.append(
                CurriculumCoverageViolation(
                    "Curriculum block references demand outside the ledger."
                )
            )
            continue
        valid_sequences = {
            module.sequence for module in item.modules if module.required_minutes > 0
        }
        if spec.module_sequence_index not in valid_sequences:
            violations.append(
                CurriculumCoverageViolation(
                    "Curriculum block module sequence is unknown or has no remaining demand."
                )
            )
            continue
        key = (spec.class_id, spec.subject_id, spec.module_sequence_index)
        actual[key] = actual.get(key, 0) + spec.duration_minutes

    for key in sorted(set(expected) | set(actual)):
        if actual.get(key, 0) != expected.get(key, 0):
            class_id, subject_id, sequence = key
            violations.append(
                CurriculumCoverageViolation(
                    f"Curriculum demand Module {sequence} for class {class_id}, subject {subject_id} "
                    f"requires {expected.get(key, 0)} minutes but target has {actual.get(key, 0)}."
                )
            )

    starts = slot_start_values or {}
    chronology: dict[tuple[int, int], list[tuple[Any, Any, str, int]]] = {}
    for spec in selected:
        if spec.module_sequence_index is None:
            continue
        chronology.setdefault((spec.class_id, spec.subject_id), []).append(
            (
                spec.date,
                starts.get(spec.timeslot_id, starts.get(str(spec.timeslot_id), "")),
                spec.stable_block_key,
                spec.module_sequence_index,
            )
        )
    for pair, rows in sorted(chronology.items()):
        ordered = [
            sequence
            for _date, _start, _stable_key, sequence in sorted(rows, key=lambda row: row[:3])
        ]
        if ordered != sorted(ordered):
            violations.append(
                CurriculumCoverageViolation(
                    f"Curriculum modules for class {pair[0]}, subject {pair[1]} "
                    "are not chronological."
                )
            )

    return tuple(violations)


def curriculum_coverage_messages(
    ledger: CompleteDemandLedger,
    specs: Iterable[DraftBlockSpec],
    *,
    select: Callable[[DraftBlockSpec], bool] | None = None,
    slot_start_values: Mapping[int | str, str] | None = None,
) -> tuple[str, ...]:
    """Return only violation messages for callers that expose string errors."""

    return tuple(
        violation.message
        for violation in validate_curriculum_coverage(
            ledger,
            specs,
            select=select,
            slot_start_values=slot_start_values,
        )
    )


__all__ = [
    "CurriculumCoverageViolation",
    "curriculum_coverage_messages",
    "validate_curriculum_coverage",
]
