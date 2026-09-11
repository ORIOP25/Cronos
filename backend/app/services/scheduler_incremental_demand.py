"""Pure incremental curriculum demand contracts for adaptive scheduling."""

from dataclasses import dataclass, replace
from typing import Any

from app.services.scheduler_complete_demand import (
    CompleteDemandItem,
    CompleteDemandLedgerBuilder,
)


@dataclass(frozen=True)
class IncrementalDemandLedger:
    """Remaining curriculum demand for class-subject assignments absent from the schedule."""

    items: tuple[CompleteDemandItem, ...]
    blockers: tuple[str, ...]
    # (class_id, subject_id, module_sequence, excess_minutes)
    excess_by_module: tuple[tuple[int, int, int, int], ...] = ()
    # Active future rows which can be removed because they exceed current demand.
    omitted_block_ids: tuple[int, ...] = ()

    @property
    def required_minutes(self) -> int:
        return sum(item.required_minutes for item in self.items)

    @property
    def is_complete(self) -> bool:
        return not self.blockers


class IncrementalDemandLedgerBuilder:
    """Build curriculum demand introduced after a published schedule exists."""

    def build(
        self,
        snapshot: dict[str, Any],
        *,
        immutable_block_ids: set[int] | frozenset[int] = frozenset(),
    ) -> IncrementalDemandLedger:
        active_pairs = {
            (row["class_id"], row["subject_id"]) for row in snapshot.get("active_schedule", [])
        }
        configured_subjects = {
            row.get("subject_id") for row in snapshot.get("module_accounting", [])
        }
        reconciled_pairs = {
            (row["class_id"], row["subject_id"])
            for row in snapshot.get("active_schedule", [])
            if (
                "duration_minutes" in row
                and not row.get("is_recovery_block")
                and row["subject_id"] in configured_subjects
            )
        }
        assignments = [
            row
            for row in snapshot.get("class_subject_requirements", [])
            if (row["class_id"], row["subject_id"]) not in active_pairs
            or (row["class_id"], row["subject_id"]) in reconciled_pairs
        ]
        ledger = CompleteDemandLedgerBuilder().build_for_assignments(
            snapshot,
            assignments,
            allow_empty=True,
            ignore_zero_remaining=True,
        )
        planned, excess_by_module, omitted_block_ids, reduction_blockers = (
            self._planned_minutes_by_module(
                snapshot,
                ledger,
                immutable_block_ids=immutable_block_ids,
            )
        )
        items = []
        for item in ledger.items:
            modules = tuple(
                replace(
                    module,
                    required_minutes=max(
                        0,
                        module.required_minutes
                        - planned.get((item.class_id, item.subject_id, module.sequence), 0),
                    ),
                )
                for module in item.modules
            )
            modules = tuple(module for module in modules if module.required_minutes > 0)
            remaining = sum(module.required_minutes for module in modules)
            if remaining <= 0:
                continue
            items.append(replace(item, modules=modules, required_minutes=remaining))
        return IncrementalDemandLedger(
            items=tuple(items),
            blockers=tuple(dict.fromkeys((*ledger.blockers, *reduction_blockers))),
            excess_by_module=tuple(excess_by_module),
            omitted_block_ids=tuple(omitted_block_ids),
        )

    @staticmethod
    def _planned_minutes_by_module(
        snapshot: dict[str, Any],
        ledger,
        *,
        immutable_block_ids: set[int] | frozenset[int],
    ) -> tuple[
        dict[tuple[int, int, int], int],
        tuple[tuple[int, int, int, int], ...],
        tuple[int, ...],
        tuple[str, ...],
    ]:
        """Credit only unexecuted, non-recovery active blocks to their module demand."""

        items = {(item.class_id, item.subject_id): item for item in ledger.items}
        grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for row in snapshot.get("active_schedule", []):
            pair = (row.get("class_id"), row.get("subject_id"))
            if pair not in items or row.get("is_recovery_block"):
                continue
            if row.get("recovery_source_occurrence_id") is not None:
                continue
            if str(
                getattr(row.get("lesson_log_status"), "value", row.get("lesson_log_status"))
            ) in {
                "COMPLETED",
                "OCCURRENCE",
            }:
                continue
            grouped.setdefault(pair, []).append(row)

        planned: dict[tuple[int, int, int], int] = {}
        excess: dict[tuple[int, int, int], int] = {}
        omitted: list[int] = []
        protected: dict[tuple[int, int], list[int]] = {}
        identity_blockers: list[str] = []
        for pair, rows in grouped.items():
            item = items[pair]
            modules = {module.sequence: module for module in item.modules}
            offset = 0
            retained_by_module: dict[int, int] = {}
            for row in sorted(
                rows,
                key=lambda value: (
                    value.get("date", ""),
                    value.get("timeslot_id", 0),
                    value.get("id", 0),
                ),
            ):
                minutes = max(0, int(row.get("duration_minutes", 0)))
                sequence = row.get("module_sequence_index")
                if sequence is None:
                    sequence = IncrementalDemandLedgerBuilder._sequence_for_offset(item, offset)
                module = modules.get(sequence)
                if module is None:
                    identity_blockers.append(
                        f"Active block {row.get('id')} for class {pair[0]}, subject {pair[1]} "
                        f"references unknown module sequence {sequence}."
                    )
                    continue
                key = (*pair, sequence)
                required = module.required_minutes
                retained = retained_by_module.get(sequence, 0)
                if retained + minutes <= required:
                    retained_by_module[sequence] = retained + minutes
                    planned[key] = planned.get(key, 0) + minutes
                    offset += minutes
                    continue
                excess[key] = excess.get(key, 0) + minutes
                block_id = row.get("id")
                if block_id is not None and int(block_id) in immutable_block_ids:
                    protected.setdefault(pair, []).append(int(block_id))
                elif block_id is not None:
                    omitted.append(int(block_id))

        reduction_blockers = tuple(
            "Reduced curriculum demand leaves excess immutable future blocks for "
            f"class {class_id}, subject {subject_id}; block IDs: "
            + ", ".join(str(block_id) for block_id in sorted(block_ids))
            + ". Remove or reschedule those protected blocks before reducing demand."
            for (class_id, subject_id), block_ids in sorted(protected.items())
        )
        excess_by_module = tuple(
            (*key, minutes) for key, minutes in sorted(excess.items()) if minutes > 0
        )
        return (
            planned,
            excess_by_module,
            tuple(sorted(set(omitted))),
            (*identity_blockers, *reduction_blockers),
        )

    @staticmethod
    def _sequence_for_offset(item: CompleteDemandItem, offset: int) -> int:
        cumulative = 0
        fallback = item.modules[-1].sequence
        for module in item.modules:
            if module.required_minutes <= 0:
                continue
            cumulative += module.required_minutes
            if offset < cumulative:
                return module.sequence
        return fallback


# Keep the domain wording available to callers without duplicating the implementation.
IncrementalCurriculumDemandLedger = IncrementalDemandLedger
IncrementalCurriculumDemandLedgerBuilder = IncrementalDemandLedgerBuilder

__all__ = [
    "IncrementalCurriculumDemandLedger",
    "IncrementalCurriculumDemandLedgerBuilder",
    "IncrementalDemandLedger",
    "IncrementalDemandLedgerBuilder",
]
