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
A class-subject link also selects which modules of the subject the class takes.

## Why the Behavior Exists

Module-level minutes represent modular execution more accurately than a fixed annual subject total.
The scheduler uses remaining module minutes when it builds demand.
A class follows its own module plan for the current grade level.
The selection is stored on the class-subject link, which is keyed by grade level.

## Components and Ownership

| Responsibility | Implementation |
| :--- | :--- |
| Curriculum models | `backend/app/models.py` (`Course`, `Class`, `Subject`, `Module`) |
| Curriculum API | `backend/app/api/v1/endpoints/courses.py`, `classes.py`, `subjects.py` |
| Progress ledger | `backend/app/models.py` (`ProgressLedgerEntry`) |
| Progress services | `backend/app/services/class_service.py`, `teacher_service.py` |
| Module selection storage | `backend/app/models.py` (`class_subject_module`); `backend/app/scheduler/infrastructure/models.py` (`CurricularRequirement.planned`) |
| Module selection read and write | `backend/app/services/class_service.py` |
| Retired-module rule | `backend/app/scheduler/domain/demand.py` (`close_retired_modules`) |
| Curricular projection | `backend/app/scheduler/infrastructure/curriculum.py` |
| Scheduler v1 curriculum | `backend/app/scheduler/infrastructure/models.py` (`CurricularAssignment`, `CurricularRequirement`, `CurricularExecution`, `CurricularDebt`) |
| Curriculum UI | `frontend/src/pages/Courses.jsx`, `CourseDetails.jsx`, `ClassDetails.jsx`, `ClassSubjects.jsx` |

## Data or Request Flow

1. An administrator creates a course and class.
2. An administrator creates subjects and ordered modules.
3. An administrator links subjects to a class, assigns a teacher, and marks the class modules.
4. The scheduler reads module minutes and execution ledger values.
5. Lesson logs and recovery delivery append ledger deltas.
6. The UI reports completed minutes, debt minutes, and percentage.

## Contracts and Invariants

- Module `required_minutes` must be greater than zero.
- Module order is unique within an organization and subject.
- A curricular requirement sequence is unique per assignment and greater than zero.
- Curricular requirement and debt minutes must be greater than zero.
- Remaining demand starts at the first incomplete module.
- Completed minutes cannot exceed the module requirement in progress views.
- Ledger entries use idempotency keys and preserve source evidence.
- Each class-subject link selects modules per grade level.
- A new class subject and a CSV assignment select every module of the subject.
- The migration selects every module for the existing links.
- A new module in a subject is not selected in any class.
- A deselected module with execution credit stays as a `planned = false` requirement.
- History replay uses the catalogue module minutes, so a retired module stays valid.
- A link without a selected module never reaches the solver.
- Class and teacher progress count only the selected modules.

## States and Transitions

Progress moves from required minutes to completed minutes or debt minutes.
Recovery delivery reduces outstanding debt through a linked execution record.
A module moves between selected and unselected on the class-subject link.
Deselecting a module without credit drops its requirement at the next projection.
Deselecting a module with credit keeps the requirement closed at its executed minutes.
Reselecting a module restores its catalogue minutes and counts its history again.
Planning and progress reads use the live selection, so a change applies before the next projection.

## Failure Modes

- Invalid module order or minutes return validation errors.
- A class cannot update progress for a module outside its curriculum.
- A class-subject link without a selected module returns the `CLASS_SUBJECT_WITHOUT_MODULES` blocker.
- Deselecting a module never erases its execution history.
- A cross-organization relationship fails scoped validation.

## Verification Procedure

1. Open `/courses` as an administrator.
2. Create or open a class.
3. Open `/courses/:courseId/classes/:classId/subjects`.
4. Inspect module totals and progress counters.

## Source Map

- Models: `backend/app/models.py`
- Scheduler v1 models: `backend/app/scheduler/infrastructure/models.py`
- Schemas: `backend/app/schemas.py`
- Curriculum endpoints: `backend/app/api/v1/endpoints/classes.py`, `courses.py`, `subjects.py`
- Curricular projection: `backend/app/scheduler/infrastructure/curriculum.py`
- Retired-module rule: `backend/app/scheduler/domain/demand.py`
- Tests: `backend/tests/integration/committed/test_module_progress.py`, `backend/tests/integration/committed/test_class_subjects.py`, `backend/tests/integration/committed/test_scheduler_v1_class_module_selection.py`

## Related Documents

- [School Configuration](SCHOOL_CONFIGURATION.md)
- [Lesson Execution](../04_operational_features/LESSON_EXECUTION.md)
- [Data Model](../01_system_architecture/DATA_MODEL.md)
