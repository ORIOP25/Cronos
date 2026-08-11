# Professional Education Domain

## Purpose

This document describes the curriculum hierarchy and progress rules implemented by Cronos.

## Intended Reader

This document targets domain engineers, backend engineers, and product specialists.

## Prerequisites

Read the [Project Overview](../00_getting_started/PROJECT_OVERVIEW.md) and [Glossary](../00_getting_started/GLOSSARY.md).

## What the System Does

Cronos models an organization, course (*Curso*), class (*Turma*), subject (*Disciplina*), and ordered module (*Módulo*).

Each module stores `required_minutes` and an `order` within its subject.
A class-subject link binds a class, subject, grade level, and optional teacher.

## Why the Behavior Exists

Module-level minutes represent modular execution more accurately than a fixed annual subject total.
The scheduler uses remaining module minutes when it builds demand.

## Components and Ownership

| Responsibility | Implementation |
| :--- | :--- |
| Curriculum models | `backend/app/models.py` (`Course`, `Class`, `Subject`, `Module`) |
| Curriculum API | `backend/app/api/v1/endpoints/courses.py`, `classes.py`, `subjects.py` |
| Progress ledger | `backend/app/models.py` (`ProgressLedgerEntry`) |
| Progress services | `backend/app/services/class_service.py`, `teacher_service.py` |
| Curriculum UI | `frontend/src/pages/Courses.jsx`, `CourseDetails.jsx`, `ClassDetails.jsx` |

## Data or Request Flow

1. An administrator creates a course and class.
2. An administrator creates subjects and ordered modules.
3. An administrator links subjects to a class and assigns a teacher.
4. The scheduler reads module minutes and execution ledger values.
5. Lesson logs and recovery delivery append ledger deltas.
6. The UI reports completed minutes, debt minutes, and percentage.

## Contracts and Invariants

- Module `required_minutes` must be greater than zero.
- Module order is unique within an organization and subject.
- Remaining demand starts at the first incomplete module.
- Completed minutes cannot exceed the module requirement in progress views.
- Ledger entries use idempotency keys and preserve source evidence.

## States and Transitions

Progress moves from required minutes to completed minutes or debt minutes.
Recovery delivery reduces outstanding debt through a linked execution record.

## Failure Modes

- Invalid module order or minutes return validation errors.
- A class cannot update progress for a module outside its curriculum.
- A cross-organization relationship fails scoped validation.

## Verification Procedure

1. Open `/courses` as an administrator.
2. Create or open a class.
3. Open `/courses/:courseId/classes/:classId/subjects`.
4. Inspect module totals and progress counters.

## Source Map

- Models: `backend/app/models.py`
- Schemas: `backend/app/schemas.py`
- Curriculum endpoints: `backend/app/api/v1/endpoints/classes.py`, `courses.py`, `subjects.py`
- Tests: `backend/tests/test_module_progress.py`, `test_class_subjects.py`

## Related Documents

- [School Configuration](SCHOOL_CONFIGURATION.md)
- [Lesson Execution](../04_operational_features/LESSON_EXECUTION.md)
- [Data Model](../01_system_architecture/DATA_MODEL.md)
