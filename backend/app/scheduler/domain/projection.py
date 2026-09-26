"""Exact curricular projection over future lessons of one assignment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date


def _integer(value: int, name: str, *, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer of at least {minimum}.")


@dataclass(frozen=True)
class ModuleRequirement:
    module_id: int
    sequence: int
    required_minutes: int

    def __post_init__(self) -> None:
        _integer(self.module_id, "module_id", minimum=1)
        _integer(self.sequence, "sequence", minimum=1)
        _integer(self.required_minutes, "required_minutes", minimum=1)


@dataclass(frozen=True)
class FutureLesson:
    lesson_id: int
    school_date: date
    start_minute: int
    duration_minutes: int
    credit_minutes: int

    def __post_init__(self) -> None:
        _integer(self.lesson_id, "lesson_id", minimum=1)
        if type(self.school_date) is not date:
            raise ValueError("school_date must be a date.")
        _integer(self.start_minute, "start_minute")
        _integer(self.duration_minutes, "duration_minutes", minimum=1)
        _integer(self.credit_minutes, "credit_minutes", minimum=1)
        if self.start_minute + self.duration_minutes > 24 * 60:
            raise ValueError("Lesson must end within its school date.")
        if self.credit_minutes > self.duration_minutes:
            raise ValueError("Curricular credit cannot exceed physical duration.")


@dataclass(frozen=True)
class ModuleSlice:
    lesson_id: int
    module_id: int
    offset_minutes: int
    credit_minutes: int

    def __post_init__(self) -> None:
        _integer(self.lesson_id, "lesson_id", minimum=1)
        _integer(self.module_id, "module_id", minimum=1)
        _integer(self.offset_minutes, "offset_minutes")
        _integer(self.credit_minutes, "credit_minutes", minimum=1)


def project_module_slices(
    modules: Sequence[ModuleRequirement],
    *,
    completed_minutes: Mapping[int, int],
    lessons: Sequence[FutureLesson],
) -> tuple[ModuleSlice, ...]:
    """Allocate exact residual minutes in module and lesson chronology."""
    ordered_modules = sorted(modules, key=lambda module: (module.sequence, module.module_id))
    if not ordered_modules:
        raise ValueError("At least one module is required.")
    if len({module.module_id for module in ordered_modules}) != len(ordered_modules):
        raise ValueError("Module IDs must be unique.")
    if len({module.sequence for module in ordered_modules}) != len(ordered_modules):
        raise ValueError("Module sequences must be unique.")
    if set(completed_minutes) - {module.module_id for module in ordered_modules}:
        raise ValueError("Progress references an unknown module.")

    offsets = {}
    remaining = {}
    for module in ordered_modules:
        completed = completed_minutes.get(module.module_id, 0)
        _integer(completed, "completed_minutes")
        if completed > module.required_minutes:
            raise ValueError("Completed minutes exceed the module requirement.")
        offsets[module.module_id] = completed
        remaining[module.module_id] = module.required_minutes - completed

    ordered_lessons = sorted(
        lessons, key=lambda lesson: (lesson.school_date, lesson.start_minute, lesson.lesson_id)
    )
    if len({lesson.lesson_id for lesson in ordered_lessons}) != len(ordered_lessons):
        raise ValueError("Lesson IDs must be unique.")
    if sum(lesson.credit_minutes for lesson in ordered_lessons) != sum(remaining.values()):
        raise ValueError("Future curricular credit must equal residual demand.")

    slices = []
    module_index = 0
    for lesson in ordered_lessons:
        unallocated = lesson.credit_minutes
        while unallocated:
            module = ordered_modules[module_index]
            if remaining[module.module_id] == 0:
                module_index += 1
                continue
            credit = min(unallocated, remaining[module.module_id])
            slices.append(
                ModuleSlice(lesson.lesson_id, module.module_id, offsets[module.module_id], credit)
            )
            offsets[module.module_id] += credit
            remaining[module.module_id] -= credit
            unallocated -= credit
    return tuple(slices)
