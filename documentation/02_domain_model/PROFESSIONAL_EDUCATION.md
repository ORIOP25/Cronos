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

A joint lesson group (*Junção*, "Aula conjunta") joins two or more class-subject links of one subject for a set of joint modules.
The member links share one teacher, and the scheduler plans the joint modules once for all member classes.
A link belongs to at most one group per subject, and a joint module must be selected on every member class.
Changing a joint group records one scheduler change and requires a new generation.
The interface configures it in "Disciplinas e Professores"; the glossary defines *Junção* and *Aula conjunta*.

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
| Scheduler v1 curriculum | `backend/app/scheduler/infrastructure/models.py` (`CurricularAssignment`, `CurricularRequirement`, `CurricularExecution`, `CurricularDebt`) |
| Curriculum UI | `frontend/src/pages/Courses.jsx`, `CourseDetails.jsx`, `ClassDetails.jsx`, `ClassSubjects.jsx` |

## Data or Request Flow

1. An administrator creates a course and class.
2. An administrator creates subjects and ordered modules.
3. An administrator links subjects to a class and assigns a teacher.
4. An administrator selects which modules the class takes, per class and school year.
5. The scheduler reads the selected module minutes and execution ledger values.
6. Lesson logs and recovery delivery append ledger deltas.
7. The UI reports completed minutes, debt minutes, and percentage.

## Contracts and Invariants

- Module `required_minutes` must be greater than zero.
- Module order is unique within an organization and subject.
- A curricular requirement sequence is unique per assignment and greater than zero.
- Curricular requirement and debt minutes must be greater than zero.
- Remaining demand starts at the first incomplete module.
- Completed minutes cannot exceed the module requirement in progress views.
- Ledger entries use idempotency keys and preserve source evidence.
- A new subject on a class selects all its modules. A new module is not selected on any class.
- A selected module belongs to the subject of its class link.
- The scheduler projects one requirement per selected module with `sequence = order + 1`.
- Deselecting a module without executed credits deletes its requirement. Deselecting a module with credits keeps `planned = false` and closes it at the executed minutes.
- Deselecting is always allowed, including the last selected module. Generation then blocks with `CLASS_SUBJECT_WITHOUT_MODULES` until at least one module is selected.
- Re-selecting a module restores its catalogue minutes and counts its history again.
- A joint lesson group has at least two member classes of the same subject, and all member links share one teacher.
- A joint module is selected on every member class. Deselecting a joint module returns `409 JOINT_MODULE_LOCKED` until it leaves the group.
- A module or class with executed minutes cannot enter or leave a joint group (`409 JOINT_MODULE_STARTED` or `JOINT_CLASS_STARTED`).
- A member link belongs to at most one joint group per subject. A class/subject link, a member class and a joint module in use return `409 resource_in_use`.

## States and Transitions

Progress moves from required minutes to completed minutes or debt minutes.
Recovery delivery reduces outstanding debt through a linked execution record.

## Failure Modes

- Invalid module order or minutes return validation errors.
- A class cannot update progress for a module outside its curriculum, including a deselected module.
- A module of another subject returns `400 bad_request`. A module of another organization returns `404 resource_not_found`.
- A class subject without a selected module blocks generation with `CLASS_SUBJECT_WITHOUT_MODULES`.
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
- Tests: `backend/tests/integration/committed/test_module_progress.py`, `backend/tests/integration/committed/test_class_subjects.py`

## Related Documents

- [School Configuration](SCHOOL_CONFIGURATION.md)
- [Lesson Execution](../04_operational_features/LESSON_EXECUTION.md)
- [Data Model](../01_system_architecture/DATA_MODEL.md)
