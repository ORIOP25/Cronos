# Feedback Message Matrix

## Purpose

This document records the channel and owner for each feedback message.
The feedback contracts live in [Frontend Architecture](FRONTEND_ARCHITECTURE.md) and [Accessibility](ACCESSIBILITY.md).

## Intended Reader

This document targets frontend engineers and reviewers.

## Prerequisites

Read the [Frontend Architecture](FRONTEND_ARCHITECTURE.md).

## Classification Rules

1. Page states and structured content stay in the content area.
2. Field validation stays next to the field or group.
3. Business blocks stay in context while the condition exists.
4. Short action results and transient failures use toasts.

A transient failure is a network error or an HTTP `429` or `5xx` response.
Other client responses stay in context.

## Message Matrix

| Operation | Trigger | Known code | Channel | Owner | Recovery |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Save schedule priorities | Success | — | Status message in Configuração | `SchedulePrioritiesSection` | Values apply to the next generation or update |
| Save schedule priorities | Invalid level set | `schedule_priorities_invalid` | Banner in Configuração: "Escolha um nível de 0 a 4 em cada critério." | `SchedulePrioritiesSection` | Select one valid level for each criterion |
| Review schedule proposal | Constructive priorities were not followed | `priorities_followed: false` | Warning in the proposal: "Não foi possível seguir as prioridades definidas pela escola nesta proposta. Experimente baixar alguns critérios e gerar outra proposta." | `DraftPanel` | Lower some priorities and generate another proposal |
| Save availability | Success | — | Toast, 4 s | `MyAvailability` | — |
| Save availability | Transient failure | Network, 429, 5xx | Toast, 6 s | `MyAvailability` | Draft stays, retry |
| Save availability | Context changed before the response | — | No feedback | `useAttemptScope` guard | Retry in the new context |
| Save class availability | Success | — | Toast, 4 s | `ClassAvailabilityModal` | — |
| Save class availability | Transient failure | Network, 429, 5xx | Toast, 6 s | `ClassAvailabilityModal` | Draft stays, retry |
| Save class availability | Server block | `bad_request`, `duplicate_timeslot` | Banner in the modal | `ClassAvailabilityModal` | Fix the grid |
| Save teacher presence and grid | Partial failure | — | Banner in the modal naming the unsaved part | `TeacherAvailabilityModal` | Fix or retry the unsaved part |
| Save teacher presence | Server block | `bad_request` and others | Banner in the modal | `TeacherAvailabilityModal` | Fix the rule |
| Load teacher presence | Failure | — | Banner with retry | `TeacherPresenceSection` | Retry |
| Validate teacher presence | Invalid integer or unpaired fields | Local validator | Field feedback and banner | `TeacherPresenceSection` | Fix the value |
| Generate or update a timetable | Impossible teacher presence | `TEACHER_PRESENCE_IMPOSSIBLE` | Banner naming affected teachers, with an Equipa link | `Schedules` | Fix the presence rule or availability |
| Cancel generation | Request accepted, worker still stopping | `cancellation_requested` | Disabled “A cancelar…” button until a terminal result | `Schedules` | Wait for cancellation |
| Apply class availability to other classes | Success | — | Toast, 4 s | `ClassAvailabilityModal` | — |
| Apply class availability to other classes | Server block | `bad_request`, `resource_not_found` | Banner in the modal | `ClassAvailabilityModal` | Fix the selection |
| Apply class availability to other classes | Transient failure | Network, 429, 5xx | Toast, 6 s | `ClassAvailabilityModal` | Retry |
| Remove or archive a row | Success | — | Toast, 4 s | `SmartTable` | — |
| Remove a row | Business block | `resource_in_use`, `course_has_classes` | Banner in context | `SmartTable` | Fix and retry |
| Remove a row | Transient failure | Network, 429, 5xx | Toast, 6 s | `SmartTable` | Retry |
| Create or edit a catalog record | Success | — | Toast, 4 s | Page | — |
| Create or edit a catalog record | Transient failure | Network, 429, 5xx | Toast, 6 s | Page | Form stays open |
| Create, rename, or remove a room type | Success | — | Toast, 4 s | `RoomTypesModal` | — |
| Create or rename a room type | Invalid, duplicate, or fixed name | `validation_error`, `room_type_name_taken`, `room_type_fixed` | Field feedback in the modal: "Escreva um nome de tipo com até 60 caracteres.", "Já existe um tipo de sala com este nome.", "O tipo Normal é fixo: não pode mudar de nome nem ser removido." | `RoomTypesModal` | Fix the name |
| Create or rename a room type | Not found | `resource_not_found` | Field feedback in the modal: "Tipo de sala não encontrado." | `RoomTypesModal` | Reopen the window |
| Remove a room type | Business block | `resource_in_use` | Banner in the modal: "Este tipo é usado por: salas {salas}; disciplinas {disciplinas}. Mude-lhes o tipo primeiro." | `RoomTypesModal` | Change the rooms and subjects first |
| Remove a room type | Not found or fixed | `resource_not_found`, `room_type_fixed` | Banner in the modal: "Tipo de sala não encontrado." or the fixed-type message | `RoomTypesModal` | Reopen the window |
| Save or remove a room type | Transient failure | Network, 429, 5xx | Toast, 6 s | `RoomTypesModal` | Retry |
| Save a class home room | Room not found | `resource_not_found` with context `resource: room` | Field feedback under "Sala da turma": "Sala não encontrada." | `ClassDetails` | Choose another room |
| Save a class | Class not found | `resource_not_found` without a room context | Toast with the generic not-found message | `ClassDetails` | Reopen the course |
| Save a class home room | Capacity | `home_room_capacity` | Field feedback under "Sala da turma": "A sala {nome} tem {c} lugares e a turma tem {n} alunos." | `ClassDetails` | Choose a room with enough seats or Automática |
| Edit a class home room | Rooms cannot load | Network, 429, 5xx | Field feedback under "Sala da turma": "Não foi possível carregar as salas." with a "Tentar novamente" button; Automática and the current room stay selectable | `ClassDetails` | Retry |
| Show a class above its home room capacity | Warning | — | Banner in the class header: "A sala {nome} tem {c} lugares e a turma tem {n} alunos. Até corrigir, o Cronos escolhe a sala." | `ClassDetails` | Choose a larger room or correct the class size |
| Remove a room that is a class home room | Confirmation | — | Added to the removal confirmation: "É a sala da turma de {turmas}. Essas turmas passam a Automática." | `Rooms` | Confirm or cancel |
| Assign a teacher | Missing competency | `teacher_competency_missing` | Field feedback | `ClassSubjects` | Choose an eligible teacher |
| Assign a teacher | Transient failure | Network, 429, 5xx | Toast, 6 s | `ClassSubjects` | Retry |
| Update a class subject's modules | Success | — | Toast, 4 s, one fixed `id` | `ClassSubjects` | — |
| Update a class subject's modules | Transient failure | Network, 429, 5xx | Toast, 6 s | `ClassSubjects` | Retry |
| Update a class subject's modules | Server block | `bad_request` and others | Feedback near the checklist | `ClassSubjects` | Fix the selection |
| Create or edit a joint group | Success | — | Toast, 4 s | `ClassSubjects` | — |
| Create or edit a joint group | Transient failure | Network, 429, 5xx | Toast, 6 s | `ClassSubjects` | Retry |
| Create or edit a joint group | Configuration block | `JOINT_TOO_FEW_CLASSES` and others | Feedback in the modal | `ClassSubjects` | Fix the class or module choice |
| Undo a joint group | Success | — | Toast, 4 s | `ClassSubjects` | Generate the schedule again |
| Change the teacher of a joint discipline | Success | — | Toast, 4 s | `ClassSubjects` | — |
| Save a joint lesson log with absent classes | Success | — | Toast, 4 s | `LessonLogModal` | — |
| Save a joint lesson log | Server block | 422, all classes absent | Banner in the modal | `LessonLogModal` | Register an occurrence |
| Decide a joint occurrence for all classes | Success | — | Toast, 4 s | `Occurrences` | — |
| Decide a class of a joint occurrence | Success | — | Toast, 4 s | `Occurrences` | — |
| Decide a joint occurrence | Transient failure | Network, 429, 5xx | Toast, 6 s | `Occurrences` | Retry |
| Edit a subject with a new module | Success | — | Toast, 4 s | `Subjects` | Mark the new modules in each class |
| Edit a subject that gains a new module | Success with a warning | — | Toast, 4 s | `Subjects` | Mark the module in the classes that need it |
| Save an internship flow | Success | — | Toast, 4 s | `CalendarSection` | — |
| Save an internship flow | Stale preview | `CALENDAR_EVENT_STALE` | Persistent banner | `CalendarSection` | Repeat the preview |
| Save an internship flow | Transient failure | Network, 429, 5xx | Toast, 6 s | `CalendarSection` | Retry |
| Save the school period | Success | — | Toast, 4 s | `SettingsEditor` | — |
| Sync automatic holidays | Failure with recovery | `HOLIDAY_SYNC_FAILED` | Banner with action | `SettingsEditor` | Disable holidays and save |
| Validate school dates | Invalid group | Local validator | Banner near the group | `SettingsEditor` | Fix the dates |
| Preview a grid change | Success | — | State in context | `GridEditor` | — |
| Propose a grid change | Stale analysis | `GRID_CHANGE_STALE` | Persistent banner | `GridEditor` | Repeat the preview |
| Validate the grid | Invalid form | Local validator | Banner near the action | `GridEditor` | Fix the values |
| Regenerate the grid | Success | — | Toast, 4 s | `GridEditor` | — |
| Save a lesson log | Success | — | Toast, 4 s | `LessonLogModal` | — |
| Save a lesson log | Transient failure | Network, 429, 5xx | Toast, 6 s | `LessonLogModal` | Retry |
| Save a lesson log | Server block | `lesson_not_finished`, 409 | Banner in the modal | `LessonLogModal` | Fix or consult |
| Reopen a week | Success | — | Toast, 4 s | `LessonLogModal`, `Timesheets` | — |
| Submit a week | Success | — | Toast, 4 s | `MySchedules` | — |
| Submit a week | Transient failure | Network, 429, 5xx | Toast, 6 s | `MySchedules` | Retry |
| Submit a week | Server block | 400 | Banner in context | `MySchedules` | Fix the blockers |
| Approve or reopen a timesheet | Success | — | Toast, 4 s | `Timesheets` | — |
| Change a timesheet state | Server block | 400 | Banner in context | `Timesheets` | Consult the week |
| Decide or revert an occurrence | Success | — | Toast, 4 s | `Occurrences` | — |
| Decide or revert an occurrence | Transient failure | Network, 429, 5xx | Toast, 6 s | `Occurrences` | Retry |
| Decide an occurrence | Server conflict | 409 | Banner in the modal | `Occurrences` | Refresh the data |
| Request generation | Accepted | — | Toast, 4 s | `Schedules` | Follow the panel |
| Preview the pending proposal in the week grid | Preview on | — | Info banner above the week grid: "Está a ver a proposta pendente. Nada muda no horário publicado até a aprovar." | `Schedules` | Choose "Horário publicado" or decide the proposal |
| Show a proposal's home-room misses | Metric reported | — | Metrics row: "{N} aula fora da sala da turma" for 1, otherwise "{N} aulas fora da sala da turma" | `DraftPanel` | — |
| Show a proposal's preference cost | Metric reported | — | Metrics row: "{H} h em blocos a evitar", with at most one decimal in hours | `DraftPanel` | — |
| Approve or reject a proposal | Success | — | Toast, 4 s | `Schedules` | — |
| Approve a proposal | Stale proposal | `proposal_stale` | Persistent banner | `Schedules` | Generate a new proposal |
| Generation failure | Known failure | `NO_ELIGIBLE_ROOM` and others | `FailureState` in context | `Schedules` | Retry or open rooms |
| Generation failure | Joint classes share no free time | `JOINT_NO_COMMON_TIME` | Banner in context: "As turmas {turmas} não têm horas livres em comum para {disciplina}." The generic message replaces it when a class or subject name is unresolved | `Schedules` | Review class and teacher availability |
| Generation failure | Joint room too small for the sum of classes | `JOINT_ROOM_CAPACITY` | Banner in context | `Schedules` | Adjust rooms |
| Generation failure | Hard availability overlaps a protected lesson | `PROTECTED_AVAILABILITY_CONFLICT` | Banner in context | `GenerationStatusPanel` | Review availability or the protection window in Configuração |
| Generation failure | Proven per-class deficit | `INSUFFICIENT_CLASS_TIME`, `INSUFFICIENT_INTERSECTION` | `FailureState` in context | `Schedules` | Review class availability |
| Generation failure | Proven per-teacher deficit, before the search | `INSUFFICIENT_TEACHER_TIME` | `GenerationStatusPanel` list under "Professores sem tempo suficiente:", one line per named teacher, with the closing sentence "Reveja a disponibilidade destes professores, das suas turmas ou as atribuições." | `Schedules` | Open the member's availability panel (`/members?teacher_id={id}&panel=availability`) |
| Generation pre-check | Teacher with no possible presence | `TEACHER_PRESENCE_IMPOSSIBLE` | Banner in context. Use the shared [error presentations](../../frontend/src/utils/apiErrors.js) and [generation guidance](../../frontend/src/components/schedules/GenerationStatusPanel.jsx). | `Schedules` | Open the member's availability panel (`/members?teacher_id={id}&panel=availability`) |
| Generation failure | Teachers with a minimum may not fit | `TEACHER_PRESENCE_RULES` | Banner in context: "Não foi possível cumprir as regras de presença. Professores com mínimo de horas: {nomes}. Experimente baixar o mínimo, aumentar o furo máximo ou alargar a disponibilidade." with "Abrir Equipa" on `INFEASIBLE`, `FAILED` and `INCONCLUSIVE` | `GenerationStatusPanel` | Lower the minimum, raise the maximum gap or widen availability |
| Validate or commit an import | Success | — | Toast, 4 s | `BulkImport` | — |
| Validate or commit an import | Transient failure | Network, 429, 5xx | Toast, 6 s | `BulkImport` | Retry |
| Import issues | Structured list | — | List panel | `BulkImport` | Consult each issue |
| Class availability import issue | Cell error | `level_invalid` and others | List panel; the field is the hour column title | `BulkImport` | Fix the cell |
| Teacher availability import issue | Row or cell error | `level_invalid`, `teacher_reference_missing`, `teacher_inactive`, `duplicate_teacher_day` | List panel; the field is the teacher email or the hour column title | `BulkImport` | Fix the row or cell |
| Invite, sync, or restore a member | Success | — | Toast, 4 s | `Members` | — |
| Member action | Transient failure | Network, 429, 5xx | Toast, 6 s | `Members` | Retry |
| Member action | Access block | `member_sync_error` and others | Banner in context | `Members` | Resolve the sync |
| Load the team | Failure | — | Banner with retry | `Members` | Retry |
| Submit a form | Invalid field or group | Local validator | Field feedback and focus | Form component | Fix the value |
| Prevalidate a generation | Blockers or warnings | — | List panel | `Schedules` | Consult each item |

The home room sentences above depend on the room name. When the name already starts with "Sala" (for example "Sala 101"), they read "A {nome} tem …" and the header reads "{nome}", so "Sala" never appears twice. Otherwise the header reads "Sala {nome}" and the sentences keep "A sala {nome}".

## Justified Exceptions

`CAlert` remains only in `BulkImport.jsx` and `Schedules.jsx`, for structured lists.
The import issues and warnings in `BulkImport` need per-line reading.
The generation prevalidation list in `Schedules` links to the affected configuration.
These panels keep their hierarchy, actions, and keyboard access.

## Ownership Rules

- One attempt produces one result message.
- The component that starts the request owns the feedback.
- Mutation callbacks are guarded with `useAttemptScope`.
- Visible toasts are cleared when the user or organization changes.
- The guide clears simulated messages when its context ends.

## Related Documents

- [Frontend Architecture](FRONTEND_ARCHITECTURE.md).
- [Accessibility](ACCESSIBILITY.md).
