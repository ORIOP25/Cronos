from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DemandModule:
    module_id: int
    sequence: int
    required_minutes: int


@dataclass(frozen=True)
class CompleteDemandItem:
    class_id: int
    subject_id: int
    teacher_id: int
    required_room_type: str
    eligible_room_ids: tuple[int, ...]
    modules: tuple[DemandModule, ...]
    required_minutes: int


@dataclass(frozen=True)
class CompleteDemandLedger:
    items: tuple[CompleteDemandItem, ...]
    blockers: tuple[str, ...]

    @property
    def required_minutes(self) -> int:
        return sum(item.required_minutes for item in self.items)

    @property
    def is_complete(self) -> bool:
        return bool(self.items) and not self.blockers


class CompleteDemandLedgerBuilder:
    """Build the annual curriculum demand from an immutable job snapshot."""

    def build(self, snapshot: dict[str, Any]) -> CompleteDemandLedger:
        blockers: list[str] = []
        classes = {row["id"]: row for row in snapshot.get("classes", [])}
        subjects = {row["id"]: row for row in snapshot.get("subjects", [])}
        teachers = {row["id"] for row in snapshot.get("teachers", [])}
        qualifications = {
            (row["teacher_id"], row["subject_id"])
            for row in snapshot.get("teacher_subject_eligibility", [])
        }
        rooms = snapshot.get("rooms", [])
        modules_by_subject: dict[int, list[dict[str, Any]]] = {}
        for module in snapshot.get("module_accounting", []):
            modules_by_subject.setdefault(module["subject_id"], []).append(module)

        assignments = self._assignments(snapshot, blockers)
        items: list[CompleteDemandItem] = []
        for assignment in assignments:
            class_id = assignment["class_id"]
            subject_id = assignment["subject_id"]
            teacher_id = assignment.get("teacher_id")
            class_row = classes.get(class_id)
            subject_row = subjects.get(subject_id)
            label = f"class {class_id}, subject {subject_id}"
            if class_row is None or subject_row is None:
                blockers.append(f"Missing tenant-scoped class or subject for {label}.")
                continue
            if assignment.get("grade_level") not in (None, class_row["grade_level"]):
                blockers.append(f"Grade-level assignment mismatch for {label}.")
            if teacher_id is None:
                blockers.append(f"No teacher is assigned for {label}.")
                continue
            if teacher_id not in teachers:
                blockers.append(f"Assigned teacher is missing or cross-tenant for {label}.")
                continue
            if qualifications and (teacher_id, subject_id) not in qualifications:
                blockers.append(f"Teacher {teacher_id} is not eligible for subject {subject_id}.")

            module_rows = sorted(
                modules_by_subject.get(subject_id, []),
                key=lambda row: (row["sequence"], row["id"]),
            )
            demand_modules: list[DemandModule] = []
            seen_sequences: set[int] = set()
            for module in module_rows:
                hours = module.get("hours_total", 0)
                sequence = module.get("sequence")
                if not isinstance(hours, (int, float)) or hours <= 0:
                    blockers.append(f"Module {module['id']} has no positive required hours.")
                    continue
                if not isinstance(sequence, int) or sequence <= 0 or sequence in seen_sequences:
                    blockers.append(f"Module sequence is invalid for subject {subject_id}.")
                    continue
                seen_sequences.add(sequence)
                demand_modules.append(
                    DemandModule(
                        module_id=module["id"],
                        sequence=sequence,
                        required_minutes=int(round(hours * 60)),
                    )
                )
            if not demand_modules:
                blockers.append(f"No required module demand is configured for {label}.")
                continue

            room_type = self._enum_value(subject_row["required_room_type"])
            eligible_rooms = tuple(
                sorted(
                    row["id"]
                    for row in rooms
                    if row.get("capacity", 0) >= class_row["size"]
                    and self._enum_value(row.get("type")) == room_type
                )
            )
            if not eligible_rooms:
                blockers.append(f"No eligible room exists for {label}.")
            items.append(
                CompleteDemandItem(
                    class_id=class_id,
                    subject_id=subject_id,
                    teacher_id=teacher_id,
                    required_room_type=room_type,
                    eligible_room_ids=eligible_rooms,
                    modules=tuple(demand_modules),
                    required_minutes=sum(row.required_minutes for row in demand_modules),
                )
            )

        if not assignments:
            blockers.append("No class-subject curriculum assignments are configured.")
        return CompleteDemandLedger(
            items=tuple(sorted(items, key=lambda row: (row.class_id, row.subject_id))),
            blockers=tuple(dict.fromkeys(blockers)),
        )

    @staticmethod
    def _assignments(
        snapshot: dict[str, Any],
        blockers: list[str],
    ) -> list[dict[str, Any]]:
        canonical = snapshot.get("class_subject_requirements", [])
        if canonical:
            return list(canonical)
        grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for row in snapshot.get("legacy_lesson_assignments", []):
            grouped.setdefault((row["class_id"], row["subject_id"]), []).append(row)
        assignments = []
        for (class_id, subject_id), rows in sorted(grouped.items()):
            teacher_ids = {row["teacher_id"] for row in rows}
            if len(teacher_ids) != 1:
                blockers.append(
                    f"Legacy assignments are ambiguous for class {class_id}, subject {subject_id}."
                )
                continue
            assignments.append(
                {
                    "class_id": class_id,
                    "subject_id": subject_id,
                    "teacher_id": next(iter(teacher_ids)),
                    "grade_level": None,
                }
            )
        return assignments

    @staticmethod
    def _enum_value(value: Any) -> str:
        return str(getattr(value, "value", value))
