# Repository Map

## Purpose

This document maps the repository file tree, component boundaries, and directory ownership.

## Intended Reader

This document targets all developers working on the Cronos codebase.

## Prerequisites

Read the [Project Overview](PROJECT_OVERVIEW.md).

## What the System Does

Cronos organizes source into backend, frontend, documentation, workflow, and agent-skill areas.

## Repository Tree Structure

```text
MeuProjeto/
├── .agents/                      # AI agent skills and configuration
│   ├── README.md                 # Agent suite documentation
│   └── skills/                   # Skill sources: Cronos skills, tracked ponytail, ignored imported skills
├── .claude/
│   └── skills/                   # Claude Code adapters that point to .agents/skills
├── .github/                      # GitHub Action workflows and agent definitions
│   ├── agents/                   # Agent_Cronos.md router
│   ├── workflows/                # ci.yml and deploy-check.yml
│   └── dependabot.yml            # Automated dependency update configuration
├── backend/                      # Python FastAPI application
│   ├── alembic/                  # Linear chain from the frozen 0001_scheduler_v1_baseline (currently 0004_joint_lesson_groups)
│   ├── app/                      # Backend application source
│   │   ├── api/                  # API routers (v1 endpoints)
│   │   ├── contact/              # Contact service, ports, and provider gateways
│   │   ├── core/                 # Authentication, exceptions, logging, and rate limits
│   │   ├── db/                   # Database engine and tenant context
│   │   ├── middleware/           # Request body limit middleware
│   │   ├── ops/                  # Database provisioning operations
│   │   ├── models.py             # SQLAlchemy ORM models
│   │   ├── schemas.py            # Pydantic data schemas
│   │   ├── services/             # Business logic and domain services
│   │   └── scheduler/            # Scheduler domain and infrastructure adapters
│   ├── railway/                  # Railway service deployment definitions
│   │   └── *.json                # api, beat, bootstrap, supervisor, and worker services
│   ├── scripts/                  # Database provisioning, audits, privacy, and E2E preparation
│   ├── tests/                    # Pytest test suite
│   ├── Dockerfile                # Multi-stage BuildKit backend image file
│   └── README.md                 # Backend workspace documentation
├── frontend/                    # React 19 + Vite frontend application
│   ├── e2e/                      # Playwright end-to-end tests
│   ├── public/                   # Static graphics and response headers
│   ├── scripts/                  # Marketing build, legal contract, and production verification scripts
│   ├── src/                      # React source code
│   │   ├── components/           # Reusable UI components
│   │   ├── features/             # Feature-specific logic and hooks
│   │   ├── hooks/                # Custom React hooks
│   │   ├── pages/                # Top-level page views
│   │   ├── styles/               # Page and component style sheets
│   │   ├── test/                 # Vitest unit and component tests
│   │   ├── utils/                # Shared browser utility modules
│   │   ├── App.jsx               # Route definitions and layout router
│   │   ├── index.css             # Global design tokens and styles
│   │   └── main.jsx              # React entry point
│   ├── Dockerfile                # Multi-stage Nginx / Node frontend image file
│   ├── nginx.conf                # Production Nginx SPA server configuration
│   ├── nginx.ci.conf             # Nginx configuration for the CI and local images
│   └── README.md                 # Frontend workspace documentation
├── documentation/                # Controlled ASD-STE100 technical documentation
│   ├── 00_getting_started/       # Onboarding and repository guides
│   │   ├── COMMAND_REFERENCE.md  # Every setup, test, and inspection command
│   │   ├── ONBOARDING.md         # Canonical Foundation and tutorial contract
│   ├── 01_system_architecture/   # System architecture and data models
│   ├── 02_domain_model/          # Professional education domain rules
│   ├── 03_scheduler_engine/      # Scheduler engine documentation
│   ├── 04_operational_features/  # Operational workflows and timesheets
│   ├── 05_backend_api/           # REST API reference and standards
│   ├── 06_frontend_ux/           # UI architecture, routes, design tokens
│   ├── 07_data_and_seed/         # Seed scenarios and test data
│   │   └── sample_import_48_classes/ # Sample CSV import set (48 classes, 16 courses)
│   ├── 08_security_quality/      # Security controls, RLS, and CI workflows
│   └── 09_ops_observability/     # Local runtime, cloud operations, and runbooks
├── scripts/                      # Root test and quality runners
│   ├── test.mjs                  # Unified local and CI test runner
│   ├── loc-report.mjs            # Measured lines-of-code report
│   └── sanitize-test-artifacts.mjs # Test artifact sanitizer
├── .env.example                  # Template root environment variable file
├── docker-compose.yml             # Production-like local Compose deployment
├── docker-compose.dev.yml         # Development override for Vite hot reload
├── docker-compose.ci.yml          # CI workflow Compose deployment
├── docker-compose.test.yml        # Isolated test Compose deployment
├── README.md                      # Root repository quick start guide
├── skills-lock.json               # Version lockfile for AI skills
└── .sonarcloud.properties         # SonarQube Cloud automatic analysis scope
```

## Component Ownership and Boundaries

| Workspace | Primary Languages | Boundary Rule |
| :--- | :--- | :--- |
| `backend/` | Python | Handles data persistence, authentication checks, business logic, and solver computation. |
| `frontend/` | JavaScript, JSX, CSS | Handles user interfaces, client routing, API requests, and state management. |
| `documentation/` | Markdown | Maintains technical guides following ASD-STE100 rules. |
| `.agents/`, `.claude/` | Markdown | Define agent skills; `.claude/skills/` only points to `.agents/skills/`. |

## Feature Change Paths

Use this section to find every layer of a feature before you search the code.
Each path runs: page -> data hook -> endpoint -> service or domain -> persistence -> tests -> guide.
Frontend paths are under `frontend/src/`. Backend paths are under `backend/app/`. Backend tests are under `backend/tests/`.

### Team, invitations, and permissions

| Layer | Location |
| :--- | :--- |
| Page and guards | `pages/Members.jsx` (`/members`); `routeGuards.jsx`; `roleAccess.js` |
| Hooks | `features/members/data.js`; `features/onboarding/useOnboardingCompletion.js` |
| Endpoints | `api/v1/endpoints/members.py`, `webhooks.py` (`POST /webhooks/clerk`), `session.py`; actors in `api/deps.py` |
| Services | `services/member_service.py`; Clerk saga in `member_access_operation_service.py` and `clerk_access_service.py`; `member_webhook_service.py`; `member_reconciliation_service.py` (hourly Beat task) |
| Persistence | `organization_membership`, `member_access_operation`, `clerk_webhook_event`, `user`, `teacher` |
| Tests | `integration/committed/test_members_api.py`, `test_webhooks.py`; `unit/test_member_capability_policy.py`, `test_member_saga_coordinator.py`; `frontend/src/test/Members.test.jsx`; `frontend/e2e/members/invitations.spec.js` |
| Guide | [Members and Access](../02_domain_model/MEMBERS_AND_ACCESS.md) |

Invariants: Clerk role and invitation changes go through the saga ledger; the membership webhook locks the membership row before the account; the server enforces capabilities.

### Foundation and school configuration

| Layer | Location |
| :--- | :--- |
| Pages | `pages/Foundation.jsx` (`/foundation`), `FoundationWaiting.jsx`, `SchoolConfig.jsx` (`/config`) |
| Hooks and model | `features/foundation/foundationData.js`, `foundationModel.js`, `features/foundation/components/FoundationWizard.jsx`; `features/schoolConfig/data.js`, `SchoolConfigSections.jsx` |
| Endpoints | `api/v1/endpoints/foundation.py`, `org_settings.py` (`/school/...`), `timeslots.py` (read-only) |
| Services | `services/foundation_service.py`, `settings_service.py`, `grid_change_service.py`, `grid_version_service.py`, `timeslot_service.py`; pure rules in `scheduler/domain/timetable.py`, `grid_versions.py`, `calendar.py` |
| Persistence | `organization.foundation_status`, `organization_foundation_draft`, `organization_settings`, `organization_grid_settings`, `school_calendar_event`, `grid_version`, `timeslot` |
| Tests | `contracts/test_foundation_service.py`, `test_foundation_endpoints.py`; `integration/committed/test_org_settings_endpoints.py`, `test_grid_change_proposal.py`; `frontend/src/test/Foundation.test.jsx`, `foundationModel.test.js`; `frontend/e2e/foundation/` |
| Guides | [School Configuration](../02_domain_model/SCHOOL_CONFIGURATION.md), [Director Onboarding](ONBOARDING.md) |

Invariants: Foundation writes use optimistic `expected_version` and row locks; normal routes return `409 FOUNDATION_REQUIRED` until completion; grid writes happen only through Foundation, grid regeneration, or grid changes.

### Teacher availability

| Layer | Location |
| :--- | :--- |
| Pages | `pages/MyAvailability.jsx` (`/my-availability`); admin modal `components/TeacherAvailabilityModal.jsx` from `Members.jsx` |
| Hooks | `useMyAvailability`, `useSaveAvailability`, `useTeacherAvailability`, `useSaveTeacherAvailability` in `features/operations/data.js`; draft state in `hooks/useAvailabilityDraft.js` |
| Endpoints | `api/v1/endpoints/teachers.py` (`/teachers/me/availability`, `/teachers/{id}/availability`) |
| Services | `services/teacher_service.py`, `availability_matrix_service.py`; every write calls `scheduler_state_service.record_scheduler_change` |
| Persistence | `availability` (score per teacher and timeslot; a missing row means neutral) |
| Tests | `integration/committed/test_teacher_role_regression.py`, `test_grid_version_readers.py`; `frontend/src/test/MyAvailability.test.jsx`; `frontend/e2e/foundation/teacher-self-service-availability.spec.js` |
| Guide | [API Reference](../05_backend_api/API_REFERENCE.md) |

Invariants: `PUT` replaces the whole set for the resolved grid; `/me/...` routes stay above `/{teacher_id}/...`; a write for a scheduled teacher bumps scheduler revisions.

### Class availability

| Layer | Location |
| :--- | :--- |
| Pages | `pages/ClassDetails.jsx` (`/courses/{course_id}/classes/{class_id}`); modal `components/ClassAvailabilityModal.jsx` |
| Hooks | `useClassAvailability`, `useSaveClassAvailability`, `useCopyClassAvailability` in `features/catalog/data.js`; shared editor `components/AvailabilityEditorModal.jsx` |
| Endpoints | `api/v1/endpoints/classes.py` (`/classes/{class_id}/availability`, `/availability/copy`) |
| Services | `services/class_availability_service.py`; reads in `scheduler/infrastructure/snapshot.py` |
| Persistence | `class_availability` (score per class and timeslot; a missing row means neutral) |
| Tests | `integration/committed/test_class_availability.py`, `unit/test_scheduler_class_capacity_v1.py`, `unit/test_scheduler_snapshot_preferences_v1.py`; `frontend/src/test/ClassAvailabilityModal.test.jsx`; `frontend/e2e/readiness/class-availability.spec.js` |
| Guides | [Class Availability Tech Spec](../02_domain_model/CLASS_AVAILABILITY_TECH_SPEC.md), [School Configuration](../02_domain_model/SCHOOL_CONFIGURATION.md) |

Invariants: `PUT` replaces the whole set for the resolved grid; a missing row means Neutro; writing, copying or importing a class grid bumps scheduler revisions; only an administrator reads or writes it.

### Schedule generation and approval

| Layer | Location |
| :--- | :--- |
| Pages | `pages/Schedules.jsx` (`/schedules`), `MySchedules.jsx`; `components/schedules/DraftPanel.jsx`, `GenerationStatusPanel.jsx` |
| Hooks | `features/scheduling/data.js`; `features/readiness/data.js` |
| Endpoints | `api/v1/endpoints/scheduler.py` (`/scheduler/generate`, `/jobs/{id}`, `/drafts/{id}/approve`, `/reject`, `/diff`); `schedule.py` (`/schedule/week`) |
| Engine | `scheduler/domain/`, `application/`, `infrastructure/` (`jobs.py`, `proposals.py`, `snapshot.py`, `search.py`, `placement_model.py`), `composition.py` |
| Processes | `scheduler_v1_worker.py` (solver), `scheduler_recovery_worker.py` (supervisor), `celery_worker.py` (Beat) |
| Persistence | `scheduler_job_v1`, `scheduler_proposal_v1`, `scheduler_version_v1`, `scheduler_lesson_v1`, `scheduler_school_year_state` |
| Tests | `unit/test_scheduler_*.py` (several run real CP-SAT); `integration/committed/test_scheduler_v1_api.py`, `test_scheduler_v1_lifecycle.py`, `test_worker_process_recovery.py`; `frontend/src/test/SchedulesSchedulerFlow.test.jsx`; `frontend/e2e/scheduler/generation.spec.js` |
| Guides | [Scheduler Engine](../03_scheduler_engine/README.md), [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md) |

Invariants: one solver at a time; lock school state before job or proposal; approval revalidates and never runs the solver; the API never imports OR-Tools.

### Lesson logs, occurrences, and substitutions

| Layer | Location |
| :--- | :--- |
| Pages | `pages/Occurrences.jsx` (`/absences`), `MySchedules.jsx`; `components/LessonLogModal.jsx`, `WeekGrid.jsx` |
| Hooks | `useOccurrences`, `useUpdateOccurrence`, `useCancelOccurrence`, `useUpsertLessonLog`, `useDebts` in `features/operations/data.js` |
| Endpoints | `api/v1/endpoints/occurrences.py`; lesson log routes in `schedule.py` |
| Services | `scheduler/infrastructure/occurrences.py`, `operations.py`, `progress.py`; pure rule `scheduler/domain/lesson_time.py` |
| Persistence | `scheduler_lesson_log_v1` (the occurrence row), `operational_schedule_block`, `lesson_log`, `curricular_debt` |
| Tests | `integration/committed/test_scheduler_v1_occurrences.py`, `test_scheduler_v1_operations.py`; `unit/test_lesson_time_rule.py`; `frontend/src/test/OccurrencesTabs.test.jsx`, `LessonLogModal.test.jsx`; `frontend/e2e/operations/weekly-operations.spec.js` |
| Guides | [Lesson Execution](../04_operational_features/LESSON_EXECUTION.md), [Occurrences and Substitutions](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md), [Occurrence Reconciliation](../09_ops_observability/OCCURRENCE_RECONCILIATION.md) |

Invariants: only `GAP` or `SUBSTITUTED` creates debt; execution only after the lesson ends; a submitted week is frozen.

### Hour debt, progress, and timesheets

| Layer | Location |
| :--- | :--- |
| Pages | `pages/Timesheets.jsx` (`/timesheets`), `MyProgress.jsx` (`/my-progress`); debt tab in `Occurrences.jsx` |
| Hooks | `useMyTimesheet`, `useSubmitMyTimesheet`, `useTimesheets`, `useUpdateTimesheetStatus`, `useTeacherProgress` in `features/operations/data.js` |
| Endpoints | `api/v1/endpoints/timesheets.py`; `teachers.py` (`/me/progress`); `classes.py` (`/{id}/progress`); `occurrences.py` (`/debts`) |
| Services | `services/timesheet_service.py`, `teacher_service.py`, `class_service.py`; `scheduler/domain/debt.py`; `scheduler/infrastructure/progress.py` |
| Persistence | `teacher_weekly_timesheet`; v1 `curricular_execution`, `curricular_debt`, `curricular_debt_revision`, `curricular_debt_settlement`; legacy `progress_ledger_entry` |
| Tests | `integration/committed/test_timesheets_v1.py`, `test_scheduler_v1_progress.py`; `unit/test_scheduler_debt_domain.py`, `test_scheduler_progress_domain.py`; `frontend/src/test/weekSubmission.test.js` |
| Guide | [Timesheets and Progress](../04_operational_features/TIMESHEETS_AND_PROGRESS.md) |

Invariants: `OPEN` -> `SUBMITTED` -> `APPROVED`, admins reopen; history is append-only; settlement is oldest-origin-first.

### Curriculum catalog

| Layer | Location |
| :--- | :--- |
| Pages | `pages/Rooms.jsx`, `Subjects.jsx`, `Courses.jsx`, `CourseDetails.jsx`, `ClassDetails.jsx`, `ClassSubjects.jsx`; forms in `components/Forms/` |
| Hooks | `features/catalog/data.js` (generic entity hooks plus course and class-subject hooks) |
| Endpoints | `api/v1/endpoints/rooms.py`, `subjects.py`, `courses.py` (class edits use `/courses/{course_id}/classes/{class_id}`), `classes.py` |
| Services | `services/room_service.py`, `subject_service.py`, `course_service.py`, `class_service.py`, `resource_removal.py` |
| Persistence | `room`, `subject`, `module`, `course`, `class`, `class_subject_link`, `class_subject_module`, `course_subject_link`, `teacher_subject_link` |
| Tests | `integration/committed/test_rooms_crud.py`, `test_subjects_crud.py`, `test_courses_endpoints.py`, `test_classes_crud.py`, `test_resource_removal.py`; `frontend/src/test/RoomForm.test.jsx` |
| Guides | [Professional Education](../02_domain_model/PROFESSIONAL_EDUCATION.md), [Resource Removal](../05_backend_api/RESOURCE_REMOVAL.md) |

Invariants: removal returns `409 resource_in_use`, archives with history, or deletes; every write records a scheduler change; module order is contiguous from 0; a class-subject link selects its modules per grade level.

### CSV bulk import

| Layer | Location |
| :--- | :--- |
| Page | `pages/BulkImport.jsx` (`/imports`) |
| Hooks | `features/imports/data.js` |
| Endpoints | `api/v1/endpoints/imports.py` (`/imports/templates/{resource}`, `/validate`, `/commit`; 8 MiB body limit in `main.py`) |
| Services | Pure policy `services/bulk_import_policy.py`; orchestration `services/bulk_import_service.py`, which reuses the catalog and member services |
| Persistence | No own tables; writes catalog and member rows in one transaction |
| Tests | `unit/test_bulk_import_policy.py`; `integration/committed/test_bulk_import.py`; `frontend/src/test/BulkImport.test.jsx` |
| Guide | [Bulk Import CSV](../07_data_and_seed/BULK_IMPORT_CSV.md); samples in `documentation/07_data_and_seed/sample_import_48_classes/` |

Invariants: commit revalidates on the server and is all-or-nothing; validation writes nothing; imported teachers are `scheduler_only`, so no Clerk invitation is sent.

### Contact form and email delivery

| Layer | Location |
| :--- | :--- |
| Page | `pages/marketing/ContactPage.jsx` (`/contacto`, `/contact`) |
| Frontend | `features/contact/components/ContactQuestionnaire.jsx`, `TurnstileWidget.jsx`; `questionnaireModel.js`; `data.js` (native `fetch`) |
| Endpoint | `api/v1/endpoints/contact.py` (`POST /contact`, `204`, rate limited, 16 KiB body limit) |
| Service and adapters | `contact/service.py`, `ports.py`, `turnstile_verifier.py`, `resend_gateway.py`, `dependencies.py` |
| Persistence | None. The only output is the Resend email. |
| Tests | `unit/test_contact_service.py`, `test_contact_endpoint.py`, `test_resend_gateway.py`, `test_turnstile_verifier.py`; `frontend/src/test/ContactQuestionnaire.test.jsx` |
| Guides | [Runtime Flows](../01_system_architecture/RUNTIME_FLOWS.md), [Cloud Operations](../09_ops_observability/CLOUD_OPERATIONS.md) |

Invariants: Turnstile is verified before any send; the honeypot returns `204` silently; logs contain no PII.

### Reference implementations

| Need | Copy |
| :--- | :--- |
| New CRUD resource | Rooms: `api/v1/endpoints/rooms.py`, `services/room_service.py`, `pages/Rooms.jsx`, `components/Forms/RoomForm.jsx`, `integration/committed/test_rooms_crud.py` |
| New external provider | `backend/app/contact/` (port, adapter, constructor injection) |
| New pure rule | `scheduler/domain/lesson_time.py` with `unit/test_lesson_time_rule.py` |
| Pure validation plus thin service | `services/bulk_import_policy.py` with `services/bulk_import_service.py` |
| Provider side effect with compensation | `services/member_access_operation_service.py` |

## Source Map

- Backend entry: `backend/app/main.py`
- Frontend entry: `frontend/src/main.jsx`
- Onboarding routes: `frontend/src/App.jsx`, `frontend/src/routeGuards.jsx`
- Foundation feature: `frontend/src/features/foundation/`
- Tutorial feature: `frontend/src/features/tutorial/`
- Onboarding API: `backend/app/api/v1/endpoints/session.py`, `backend/app/api/v1/endpoints/foundation.py`, `backend/app/api/v1/endpoints/readiness.py`
- Onboarding services: `backend/app/services/foundation_service.py`, `backend/app/services/school_readiness_service.py`, `backend/app/services/dashboard_service.py`
- Compose configurations: `docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.ci.yml`, `docker-compose.test.yml`
- Railway service definitions: `backend/railway/*.json` (supervisor is a dashboard reference)
- Sample CSV import set: `documentation/07_data_and_seed/sample_import_48_classes/`

## Related Documents

- [Director Onboarding](ONBOARDING.md)
- [Project Overview](PROJECT_OVERVIEW.md)
- [Local Runtime Guide](../09_ops_observability/LOCAL_RUNTIME.md)
- [Command Reference](COMMAND_REFERENCE.md)
