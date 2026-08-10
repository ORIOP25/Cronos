# Professional Education Domain

## Purpose
This document specifies domain rules and legal invariants for Portuguese Professional Education (*Ensino Profissional*).

## Intended Reader
This document targets software engineers and product specialists.

## Prerequisites
Read the [Project Overview](../00_getting_started/PROJECT_OVERVIEW.md) and [Glossary](../00_getting_started/GLOSSARY.md).

## What the System Does
Cronos structures educational data into courses (*Cursos*), student cohorts (*Turmas*), subjects (*Disciplinas*), and modules (*Módulos*).

### Structural Hierarchy
1. **Course**: Educational track (e.g., *Técnico de Informática*). Belongs to an Organization.
2. **Class (*Turma*)**: Cohort of students enrolled in a course (e.g., *10º ANO - INFO*).
3. **Subject**: Curriculum area (e.g., *Programação e Sistemas de Informação*).
4. **Module (*Módulo*)**: Independent instructional unit with mandatory total hours (e.g., *Módulo 1 - Algoritmos*, 25 hours).
5. **Class-Subject Link**: Grade-specific assignment binding a Class, Subject, and optional Teacher.

## Why the Behavior Exists
Portuguese professional secondary education does not follow fixed annual subject schedules. Courses execute sequentially or concurrently by modules. Students complete credit hours per module. Schedule generation must track module credit progress and prevent scheduling classes beyond required module hours.

## Module Progress Calculations
- **Total Required Hours**: Total instructional credit hours assigned to a module.
- **Completed Hours**: Sum of `completed_minutes_delta` values in the progress ledger.
- **Debt Hours**: Sum of unresolved `debt_minutes_delta` values in the progress ledger.
- **Remaining Hours**: Required minutes minus completed minutes, bounded at zero.

## Contracts and Invariants
- Manual progress updates clamp completed time to the module requirement.
- A class cannot have two scheduled lesson blocks in the same timeslot.
- A teacher cannot teach two different classes in the same timeslot.

## Failure Modes
- Invalid Module Update: The API rejects progress changes for modules outside the class curriculum.

## Verification Procedure
Inspect class details page at `/courses/:courseId/classes/:classId/subjects`. Verify module list and hour counters.

## Source Map
- Models: `backend/app/models.py` (`Course`, `Class`, `Subject`, `Module`, `ClassSubjectLink`)
- Progress Calculation: `backend/app/services/class_service.py`, `backend/app/services/occurrence_service.py`

## Related Documents
- [Members and Access](MEMBERS_AND_ACCESS.md)
- [Lesson Execution](../04_operational_features/LESSON_EXECUTION.md)
