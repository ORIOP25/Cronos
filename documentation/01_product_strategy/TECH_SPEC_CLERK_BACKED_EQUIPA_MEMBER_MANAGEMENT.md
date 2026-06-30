# Technical Architecture Spec - Clerk-Backed Equipa Member Management

## Status And Authority
- Type: technical architecture specification.
- Source of product truth: `PRD_CLERK_TEACHER_USER_CREATION.md`.
- Scope: implementation architecture for Clerk-backed `Equipa` member management, the `/members` admin API, invitation/access lifecycle, account and membership persistence, webhook reconciliation, authorization, migration, cleanup, and tests.
- Legacy policy: any visible admin staff-management behavior based on `/teachers`, `Novo Professor`, `create_user_account`, local password setup, local `User.is_active` access labels, or active login identities without a Clerk user id must be rewritten, quarantined, or deleted when it conflicts with this spec and the PRD.
- Stack target: FastAPI, SQLAlchemy, Alembic, PostgreSQL-compatible relational storage, existing tenant helpers, Clerk Backend API, Clerk webhooks with Svix verification, React/Vite, Clerk React, React Query, CoreUI.

This document does not redefine product behavior. It translates the closed PRD into buildable backend, database, Clerk, frontend, authorization, migration, observability, and test design.

## 1. Architecture Overview

### 1.1 Architectural Principles
The implementation must be:
- PRD-driven: the PRD is the source of truth when this spec and the PRD disagree.
- member-first: the visible admin workspace is `Equipa`, and the canonical admin API resource is `/members`.
- Clerk-backed: Clerk owns authentication identity, password/account setup, invitation acceptance, and current Clerk organization membership.
- locally precise: Cronos owns product capabilities, teacher profiles, lifecycle/archive state, scheduler history, and the `Equipa` member view.
- capability-based: a member can be `teacher`, `admin`, or both.
- transactionally honest: modal saves either fully succeed or leave the visible member table unchanged.
- access-ledgered: no Clerk invitation, membership, or role side effect can be created before a durable local access-operation record exists.
- conservative: unmatched or externally changed Clerk state must not silently grant Cronos product permissions.
- route-boundary clean: teacher self-service/domain endpoints may remain teacher-specific, but admin staff management moves away from visible `/teachers` CRUD.
- launch-lean: no bulk import, custom invitation acceptance page, billing enforcement, support dashboard, or advanced webhook replay UI is required for this baseline.

### 1.2 Bounded Contexts
The implementation should be split into these service boundaries.

1. `MemberService`
   - owns create, edit, remove, archive, restore, resend, retry, and view-model assembly;
   - validates capabilities, teacher access mode, editable fields, email rules, last-active-admin guardrail, and sync-error blockers;
   - is the only service used by the admin `Equipa` surface for staff management.

2. `AccountService`
   - owns global account lookup and creation by normalized email;
   - links a real `clerk_user_id` only from verified Clerk session, Backend API, or webhook reconciliation;
   - never creates a local active login identity without Clerk.

3. `OrganizationMembershipService`
   - owns organization-scoped capabilities, lifecycle state, access state, current invitation state, expected Clerk role, and allowed action flags;
   - enforces one membership per `(organization_id, account_id)`;
   - computes active-admin eligibility.

4. `TeacherProfileService`
   - owns organization-scoped teacher profile creation, subject competency links, and operational-history dependency checks;
   - preserves scheduler, lesson, timesheet, absence, and audit history;
   - keeps teacher-domain operations separate from platform access.

5. `MemberAccessOperationService`
   - creates and persists an access-operation record before each Clerk side effect;
   - stores idempotency keys, intended state, Clerk identifiers, error categories, compensation status, and support-required flags;
   - blocks duplicate or unsafe access changes while an unresolved operation exists.

6. `ClerkAccessService`
   - wraps Clerk Backend API operations for organization invitations, invitation revocation, membership revocation, and role changes;
   - maps local capabilities to Clerk roles;
   - returns provider-neutral result and error categories to the application layer.

7. `ClerkWebhookReconciliationService`
   - verifies, deduplicates, and reconciles Clerk webhook events;
   - links events by invitation id, Clerk organization id, Clerk user id, verified email, local membership, and access-operation records;
   - rejects ambiguous events into `sync_error` or support-required reconciliation without granting capabilities.

8. `MemberAuthorizationService`
   - resolves the current account and current organization membership for each request;
   - authorizes by local membership capability and access state, not by Clerk role exclusivity;
   - denies access immediately after revocation or sync-error.

9. `EquipaFrontend`
   - renders the unified member table and transactional modal;
   - sends only `/members` admin mutations;
   - invalidates member/session state after successful access or capability changes;
   - exposes a sidebar mode switcher for mixed-role members.

### 1.3 High-Level Flow
```text
Admin opens Equipa
  -> frontend calls GET /api/v1/members
  -> backend returns one unified member view model per organization membership

Admin clicks Adicionar Membro
  -> frontend opens transactional draft modal
  -> admin selects capabilities, email, name, teacher access mode, competencies
  -> frontend sends POST /api/v1/members
  -> backend validates draft and guardrails
  -> if access is required, backend creates a durable access-operation record
  -> backend calls Clerk synchronously
  -> backend commits account, membership, teacher profile, invitation state, and operation outcome
  -> frontend closes modal, updates table, and shows a toast

Invited member accepts through Clerk
  -> Clerk returns the member to Cronos with a valid session and organization context
  -> request auth resolves account/membership from local state
  -> if webhook state has not arrived, auth performs synchronous Clerk Backend API reconciliation
  -> local account receives clerk_user_id and membership access becomes active only after Clerk membership is confirmed
  -> webhooks still reconcile asynchronously and idempotently after the fact
  -> first app visit routes only after confirmed Clerk membership and local capabilities are reconciled
```

### 1.4 Current Legacy Behavior To Remove Or Rewrite
The implementation must remove or neutralize:
- visible navigation label `Professores` for admin staff management;
- frontend route `/teachers` as the admin staff-management page;
- `Teachers.jsx` as the canonical admin CRUD surface;
- `TeacherForm` password state and password input;
- `create_user_account` in launch member create/update schemas;
- `Conta Ativa`/`Inativo` labels derived from local `User.is_active`;
- admin create/update/delete mutations to `/api/v1/teachers/`;
- local `user_service.create_user()` calls from teacher creation that create `clerk_user_id = null` login stubs;
- best-effort Clerk invitation that logs failure but still commits misleading local access;
- route guards that treat Clerk `org:member` as the only teacher product permission and Clerk `org:admin` as incompatible with teacher mode;
- tests that assert admin-entered password or active local login behavior.

Teacher self-service endpoints such as `/teachers/me/availability`, `/teachers/me/progress`, teacher availability writes, and scheduler/domain use of `teacher_id` remain valid when they operate on the authenticated member's local `teacher` capability and teacher profile.

## 2. Domain Model And Schema

### 2.1 Schema Strategy
Use explicit account, organization membership, teacher profile, and access operation concepts. The current physical table names may be preserved only when their semantic role matches the model below.

Physical schema decision for launch: reuse the existing physical `user` table as the semantic global `Account` table, because many operational audit columns already reference `user.id`. Do not create a second `account` table for launch. Throughout this document, `account_id` means the migrated global account row stored in `user.id`.

The `user` table must be migrated away from organization-bound auth semantics:
- `organization_id`;
- `role`;
- `teacher_id`;
- `is_active`.

Those columns may remain temporarily for compatibility during the cutover, but they must be nullable/deprecated and must not drive launch authorization, route guards, `Equipa`, access labels, or RLS auth resolution. Their concepts move to `organization_membership`, `organization_membership_capability`, access status fields, and the teacher profile relation.

All new foreign keys that refer to an authenticated person should refer to the migrated global account row (`user.id`), not to an organization-scoped member row. Organization-specific permissions are always joined through `organization_membership`.

### 2.2 `account`
Global identity mirror for one person.

Required fields:
- `id`
- `email`, normalized and globally unique
- `clerk_user_id`, unique and nullable
- `clerk_primary_email_id`, nullable
- `clerk_profile_name`, nullable
- `created_at`, `updated_at`
- `last_clerk_sync_at`, nullable

Invariants:
- one normalized email maps to at most one account;
- `clerk_user_id` is required for platform access status `active`;
- an account can belong to multiple organizations through memberships;
- account profile names from Clerk do not overwrite the Cronos organization-scoped display name.

### 2.2A Identity And Email Conflict Rules
Email is globally unique in Cronos and identifies one account mirror.

Conflict handling:
- if a normalized email already belongs to an account with the same `clerk_user_id`, reuse that account;
- if a normalized email belongs to an unlinked account and Clerk confirms the signed-in/invited user owns a verified matching email, link that existing account rather than creating a duplicate;
- if a normalized email belongs to an account linked to a different `clerk_user_id`, do not merge accounts, do not disclose external account existence, and fail the save or sync with `member_identity_conflict`;
- if a Clerk `user.updated` event changes the primary email to an unclaimed verified normalized email, update `account.email` and `clerk_primary_email_id`;
- if a Clerk `user.updated` event changes the primary email to a normalized email already claimed by another account, keep the existing local email, mark affected active memberships `sync_error` with category `identity_conflict`, and require support reconciliation;
- if Clerk removes or un-verifies the email Cronos stores for an active access account, keep access decisions based on current Clerk organization membership, but mark the account for safe profile sync review; do not silently relink by an unverified email.

Support may resolve identity conflicts only by verifying Clerk user ids, verified email ownership, organization membership, and local history before merging, relinking, or changing account email. Automated webhook or login reconciliation must fail closed when the target account is ambiguous.

### 2.3 `organization_membership`
One current product member record inside an organization.

Required fields:
- `id`
- `organization_id`
- `account_id`
- `organization_display_name`
- `lifecycle_status`: `active` or `archived`
- `access_status`: `none`, `pending_invite`, `invite_expired`, `active`, `blocked`, or `sync_error`
- `teacher_access_mode`: `platform` or `scheduler_only`, nullable unless the membership has `teacher` capability
- `expected_clerk_role`: `org:member`, `org:admin`, or null
- `clerk_membership_id`, nullable
- `clerk_invitation_id`, nullable
- `clerk_invitation_status`: `pending`, `accepted`, `revoked`, `expired`, or null
- `invitation_expires_at`, nullable
- `access_error_category`, nullable
- `access_error_safe_message`, nullable
- `access_block_reason`, nullable
- `created_by_user_id`, nullable
- `updated_by_user_id`, nullable
- `created_at`, `updated_at`
- `lock_version` or equivalent optimistic concurrency token

Invariants:
- unique `(organization_id, account_id)`;
- lifecycle archive is organization-scoped and does not disable the global account in other organizations;
- `access_status = active` requires account `clerk_user_id`, valid current Clerk organization membership, lifecycle `active`, and no unresolved sync error;
- `admin` capability requires platform access intent and expected Clerk role `org:admin`;
- scheduler-only teachers have `access_status = none` and no usable Clerk invitation or membership for that organization;
- archived members cannot sign in to that organization.

### 2.4 `organization_membership_capability`
Portable capability set for a membership.

Required fields:
- `organization_membership_id`
- `capability`: `teacher` or `admin`

Invariants:
- unique `(organization_membership_id, capability)`;
- at least one capability is required for active non-deleted memberships;
- `teacher` capability requires a linked teacher profile unless the save is blocked before commit;
- `admin` capability participates in last-active-admin checks.

### 2.5 `teacher`
Organization-scoped teacher profile and scheduling resource.

The existing `teacher` table remains the teacher-domain profile, with these launch additions:
- `organization_membership_id`, unique and nullable during migration only;
- `organization_display_name` or continued `name` synchronized from membership display name;
- `archived_at`, optional only if needed for teacher-domain filtering, while lifecycle source remains the membership.

Invariants:
- a teacher profile belongs to one organization;
- a launch-created teacher profile links to exactly one membership with `teacher` capability;
- subject competency links remain in `teacher_subject_link`;
- scheduler-only teachers use the same account, membership, and teacher profile model as platform-access teachers;
- removing `teacher` capability is allowed only when the teacher profile has no operational-history blockers.

### 2.6 `member_access_operation`
Durable ledger for every Clerk side effect.

Required fields:
- `id`
- `organization_id`
- `membership_id`, nullable for pre-member create operations
- `account_id`, nullable until known
- `target_email`
- `operation_type`: `create_invitation`, `revoke_invitation`, `revoke_membership`, `change_role`, `resend_invitation`, `restore_access`, `block_access`
- `operation_status`: `pending`, `clerk_succeeded`, `local_committed`, `failed`, `compensated`, `compensation_failed`, `support_required`
- `idempotency_key`, unique
- `intended_capabilities_json`
- `intended_clerk_role`, nullable
- `previous_access_snapshot_json`, nullable
- `draft_payload_json`, nullable for create/edit replay context
- `clerk_org_id`, nullable
- `clerk_user_id`, nullable
- `clerk_membership_id`, nullable
- `clerk_invitation_id`, nullable
- `provider_error_category`, nullable
- `provider_error_safe_message`, nullable
- `provider_error_reference`, nullable and non-sensitive
- `compensation_attempted_at`, nullable
- `support_required_at`, nullable
- `support_resolution_action`, nullable
- `support_resolved_by_user_id`, nullable
- `support_resolved_at`, nullable
- `support_resolution_note`, nullable and non-sensitive
- `created_by_user_id`
- `created_at`, `updated_at`

Invariants:
- a Clerk side effect must not be attempted before this record is durably committed;
- failed visible member saves may leave an access-operation record, but must not leave a misleading member table row;
- duplicate retry/resend for the same organization/email/member must resolve or reuse an existing unresolved operation first;
- support-required operations block risky access changes for the same organization/email/member until resolved.
- support-required operations are not terminal dead ends; they must be resolvable through the support runbook in section 5.6.

### 2.7 `clerk_webhook_event`
Webhook idempotency and diagnostics.

Required fields:
- `id`
- `svix_id`, unique
- `event_type`
- `clerk_object_id`, nullable
- `clerk_org_id`, nullable
- `clerk_user_id`, nullable
- `payload_json`, sanitized raw event payload
- `processing_status`: `received`, `processing`, `processed`, `ignored`, `retryable_failed`, `sync_error`, or `dead_letter`
- `error_category`, nullable
- `attempt_count`
- `last_attempt_at`, nullable
- `next_retry_at`, nullable
- `created_at`, `processed_at`

Invariants:
- `processed`, `ignored`, `sync_error`, and `dead_letter` are terminal for automatic processing of that exact `svix_id`;
- `received`, `processing`, and `retryable_failed` are retryable and must not be ignored merely because the `svix_id` already exists;
- repeated events with the same `svix_id` return success only after a terminal safe state exists or the duplicate is locked and reprocessed safely;
- malformed events do not grant access;
- ignored unmatched membership events are observable with safe identifiers;
- a stale `processing` row older than the configured processing timeout is treated as `retryable_failed` and may be retried by the next duplicate delivery or scheduled reconciliation.

## 3. Capabilities, Roles, And Status Mapping

### 3.1 Capabilities
Cronos capabilities are product permissions.

| Product label | Stored capabilities | Teacher profile | Platform access |
| --- | --- | --- | --- |
| `Professor` | `teacher` | Required | Optional |
| `Administrador` | `admin` | Not shown | Required |
| `Professor + Administrador` | `teacher`, `admin` | Required | Required |

### 3.2 Clerk Role Mapping
Clerk roles are coarse organization membership roles.

| Local capabilities and access mode | Clerk role |
| --- | --- |
| `teacher` with platform access | `org:member` |
| `admin` | `org:admin` |
| `teacher` and `admin` | `org:admin` |
| `teacher` scheduler-only | none |

Authorization uses local capabilities. Clerk role is not treated as the product teacher role because mixed-role members use Clerk `org:admin` while still having local `teacher` capability.

### 3.3 Lifecycle Status
| Stored value | Product label | Meaning |
| --- | --- | --- |
| `active` | `Ativo` | Member is part of the current organization view. |
| `archived` | `Arquivado` | Member is hidden by default, preserved for history/support, and cannot sign in. |

### 3.4 Access Status
| Stored value | Product label | Meaning |
| --- | --- | --- |
| `none` | `Sem acesso` | No platform sign-in access for the organization. |
| `pending_invite` | `Convite pendente` | Clerk-backed invitation/access flow exists and has not been accepted. |
| `invite_expired` | `Convite expirado` | Previous invitation is unusable and must be recreated. |
| `active` | `Com acesso` | Member can sign in to the organization. |
| `blocked` | `Acesso bloqueado` | Access was revoked, disabled, or externally removed while preserving history. |
| `sync_error` | `Erro de sincronização` | Local/Clerk state requires retry or support reconciliation. |

Failed create/edit saves are modal errors. They are not persisted as row states.

## 4. Backend API

### 4.1 Route Boundary
Canonical admin member management routes:
- `GET /api/v1/members`
- `POST /api/v1/members`
- `GET /api/v1/members/{member_id}`
- `PATCH /api/v1/members/{member_id}`
- `POST /api/v1/members/{member_id}/resend-invitation`
- `POST /api/v1/members/{member_id}/retry-sync`
- `POST /api/v1/members/{member_id}/remove`
- `POST /api/v1/members/{member_id}/restore`
- `GET /api/v1/members/me`

Non-canonical legacy route handling:
- remove admin create/update/delete from `/api/v1/teachers`;
- keep teacher self-service routes under `/teachers/me/...`;
- keep or introduce teacher-domain read endpoints only where scheduler/resource workflows need teacher profile ids;
- do not use `/import/teachers` as the `Equipa` table source.

### 4.2 `GET /members`
Query parameters:
- `include_archived`: boolean, default `false`;
- `q`: optional search over organization display name and email;
- `capability`: optional `teacher` or `admin`;
- `access_status`: optional access-status filter;
- `limit`, `offset` if pagination is added before launch.

Response:
```json
{
  "items": [
    {
      "id": 101,
      "account_id": 55,
      "organization_id": 7,
      "name": "Joana Silva",
      "email": "joana@escola.pt",
      "capabilities": ["teacher", "admin"],
      "lifecycle_status": "active",
      "lifecycle_label": "Ativo",
      "access_status": "pending_invite",
      "access_label": "Convite pendente",
      "teacher_access_mode": "platform",
      "teacher_profile_id": 88,
      "subject_ids": [1, 2],
      "subjects": [{"id": 1, "name": "Matemática"}],
      "competency_status": "ready",
      "invitation_status": "pending",
      "seat_counted": false,
      "safe_status_message": null,
      "provider_state": "confirmed",
      "remove_effect": "archive",
      "allowed_actions": {
        "can_edit": true,
        "can_edit_email": true,
        "can_remove": true,
        "can_restore": false,
        "can_resend_invite": true,
        "can_retry_sync": false,
        "can_remove_admin": true
      }
    }
  ],
  "total": 1
}
```

`can_remove` is the only removal action flag. The frontend must not expose separate remove and archive actions. `remove_effect` tells the modal copy what the backend will do if `/remove` is submitted:
- `hard_delete`: no blockers and no accepted/past access history;
- `archive`: blockers or accepted/past access require preservation;
- `blocked`: the endpoint is not currently allowed and `can_remove` must be `false`.

`provider_state` is `confirmed`, `unconfirmed`, or `not_required`. Pending invitations that require a Clerk lookup but hit a provider outage must return `provider_state = unconfirmed`, a safe status message, and disabled resend until the state is confirmed.

### 4.3 `POST /members`
Request:
```json
{
  "name": "Joana Silva",
  "email": "joana@escola.pt",
  "capabilities": ["teacher"],
  "teacher_access_mode": "scheduler_only",
  "subject_ids": [1, 2]
}
```

Validation:
- `name`, `email`, and at least one capability are required;
- no `password`, local credential, or `create_user_account` field is accepted;
- `teacher_access_mode` is required when `teacher` capability is present;
- `teacher_access_mode = scheduler_only` is invalid when `admin` capability is present;
- `subject_ids` are accepted only when `teacher` capability is present;
- email uniqueness and same-organization membership uniqueness are enforced without leaking cross-organization account existence.

Response:
- returns the complete member view model after successful commit;
- returns a safe modal error and no visible member row after failed validation or failed Clerk operation.

### 4.4 `PATCH /members/{member_id}`
Request fields are optional but validated as one draft:
```json
{
  "name": "Joana Costa",
  "email": "joana.costa@escola.pt",
  "capabilities": ["teacher", "admin"],
  "teacher_access_mode": "platform",
  "subject_ids": [1, 3]
}
```

Rules:
- edits are transactional and apply only on save;
- email can be changed only before access status `active`;
- active-user email changes are handled by Clerk/user account management or support;
- removing `admin` requires last-active-admin guardrail;
- removing `teacher` requires dependency checks;
- risky edits are blocked while access status is `sync_error`;
- access and role changes trigger synchronous Clerk operations.

### 4.5 Access Action Endpoints
`POST /members/{id}/resend-invitation`:
- allowed only for `pending_invite` or `invite_expired`;
- for pending invitations, revoke the current pending Clerk invitation when possible, then create a new one;
- revocation must pass the current admin Clerk user id as Clerk `requesting_user_id` or equivalent;
- stores the new invitation id/status on the same membership;
- does not create duplicate members or memberships;
- if revocation fails and the old invitation is still pending, keep the old local invitation state and return a safe retry/support error;
- if revocation succeeds but new invitation creation fails, update the same membership to `access_status = invite_expired`, set the old `clerk_invitation_status = revoked`, clear any usable pending invitation, mark the operation `failed`, and return a safe retryable error. The table must not continue showing `Convite pendente` for an invitation Cronos just revoked.

`POST /members/{id}/retry-sync`:
- allowed only for `sync_error`;
- attempts safe reconciliation from stored operation state and Clerk identifiers;
- returns the correct normal state on success;
- leaves support-required state and blocks risky edits if unresolved.

`POST /members/{id}/remove`:
- hard deletes only when no operational-history blockers exist;
- revokes pending invitations before hard delete or archive, passing the current admin Clerk user id as Clerk `requesting_user_id` or equivalent;
- revokes active Clerk organization membership before archive for accepted or currently active access members;
- archives accepted, past-access, blocked, sync-error, support-required, or operational-history members;
- final state after archived accepted/past access is `lifecycle_status = archived`, `access_status = blocked`, and no usable local Clerk membership for that organization;
- final state after archived pending access with successful invitation revoke is `lifecycle_status = archived`, `access_status = none`, `clerk_invitation_status = revoked`, and no usable pending invitation;
- respects last-active-admin guardrail.

`POST /members/{id}/restore`:
- restore is a saved modal action;
- scheduler-only teacher restore returns lifecycle to `active` with access `none`;
- teacher-only platform restore must either start or restore the Clerk-backed access flow in the same save, or restore as `teacher_access_mode = scheduler_only` with access `none` when the admin chooses that mode;
- admin-capable restore must start/restore Clerk-backed access or remove `admin` in the same save when guardrails allow.

### 4.6 `GET /members/me`
Returns the current account and current organization membership context:
- account id;
- organization membership id;
- capabilities;
- access status;
- lifecycle status;
- teacher profile id when present;
- default experience: `admin` for admin-only or mixed, `teacher` for teacher-only;
- whether the sidebar mode switcher is available.

The frontend uses this endpoint for product navigation and mode switching. It must not infer product capabilities only from Clerk `membership.role`.

### 4.7 API Error Contract
All `/members` endpoints must return a stable error shape:
```json
{
  "error": {
    "code": "member_access_provider_failed",
    "message": "Nao foi possivel enviar o convite. Tente novamente.",
    "category": "transient",
    "retryable": true,
    "support_required": false,
    "fields": {},
    "correlation_id": "req_abc123"
  }
}
```

Status-code policy:
- `400`: syntactically valid request that asks for an impossible action, such as scheduler-only admin access.
- `401`: unauthenticated request.
- `403`: authenticated but missing local capability, active access, lifecycle, or tenant permission.
- `404`: member/profile/resource not found in the current organization.
- `409`: guardrail or current-state conflict, such as last active admin, duplicate current-organization membership, unresolved access operation, or sync-error blocker.
- `422`: field validation errors, with `fields` keyed by request field.
- `424`: required Clerk access operation failed after local validation passed.
- `502` or `503`: Clerk/service dependency unavailable before a safe local decision can be made.

Error code enum for launch:
- `member_validation_failed`;
- `member_current_org_duplicate`;
- `member_identity_conflict`;
- `member_email_active_identity_locked`;
- `member_last_admin_blocked`;
- `member_teacher_history_blocked`;
- `member_sync_error_blocked`;
- `member_access_operation_unresolved`;
- `member_access_provider_failed`;
- `member_access_compensation_required`;
- `member_provider_state_unconfirmed`;
- `member_session_refresh_required`;
- `member_not_found`;
- `member_forbidden`.

The frontend must use `message`, `fields`, `retryable`, and `support_required` only. It must not branch on raw Clerk provider responses.

### 4.8 Operational-History Blocker Queries
Before hard delete or removing `teacher` capability, the service must check concrete blockers in the current organization. The first launch implementation must include at least:

| Area | Table / column check | Blocks hard delete | Blocks removing `teacher` |
| --- | --- | --- | --- |
| Competencies only | `teacher_subject_link.teacher_id` with no other blocker | No | No |
| Availability planning | `availability.teacher_id` | Yes | Yes |
| Class assignment | `class_subject_link.teacher_id` | Yes | Yes |
| Lesson demand | `lesson.teacher_id` | Yes | Yes |
| Generated schedule output | `schedule_output.lesson_id -> lesson.teacher_id` | Yes | Yes |
| Scheduler jobs and drafts | `schedule_generation_job.requested_by_user_id`; `schedule_drafts.created_by_user_id`; `schedule_drafts.decided_by_user_id`; `schedule_draft_blocks.teacher_id`; `schedule_diff_entries.teacher_id`; `active_schedule_blocks.teacher_id`; `planned_recovery_links.teacher_id` | Yes | Yes for teacher columns; No for account-only actor columns |
| Scheduler lifecycle audit | `scheduler_school_year_state.reset_by_user_id`; `scheduler_state_version_events.changed_by_user_id`; `scheduler_state_version_events.entity_type = 'teacher'` with `entity_id = teacher.id` as text | Yes | Yes only for teacher entity rows |
| Operational schedule blocks | `operational_schedule_block.teacher_id`; `operational_schedule_block.created_by_user_id` | Yes | Yes for `teacher_id`; No for account-only actor columns |
| Weekly closure | `teacher_weekly_timesheet.teacher_id` | Yes | Yes |
| Occurrences/substitutions | `lesson_occurrence.planned_teacher_id`; `lesson_occurrence.executed_teacher_id`; `lesson_occurrence.substitute_teacher_id`; `lesson_occurrence.created_by_user_id`; `lesson_occurrence.decided_by_user_id`; `lesson_occurrence.revoked_by_user_id`; `substitutions.original_teacher_id`; `substitutions.substitute_teacher_id` | Yes | Yes for teacher columns; No for account-only actor columns |
| Lesson records | `lesson_log.schedule_output_id -> schedule_output.lesson_id -> lesson.teacher_id`; `lesson_log.active_schedule_block_id -> active_schedule_blocks.teacher_id`; `lesson_log.operational_block_id -> operational_schedule_block.teacher_id`; `lesson_log.logged_by_user_id` | Yes | Yes for linked teacher blocks; No for account-only logger rows |
| Operational events | `occurrence_operational_event.actor_user_id`; `occurrence_operational_event.occurrence_id -> lesson_occurrence teacher columns`; `occurrence_operational_event.schedule_output_id -> schedule_output.lesson_id -> lesson.teacher_id`; `teacher_endpoint_operational_event.actor_user_id`; `progress_ledger_entry.created_by_user_id` | Yes | Yes only when linked through teacher profile columns |
| Clerk/access history | accepted, active, blocked, sync-error, support-required, or historical access-operation rows for the membership/account | Yes | No, unless teacher access/profile is part of the operation |

If a blocker check cannot be completed safely, the operation must fail closed with `member_teacher_history_blocked` or `member_access_operation_unresolved`, not hard delete.

## 5. Save Semantics And Clerk Operations

### 5.1 Create Without Platform Access
For a teacher scheduler resource:
1. Validate admin and current organization.
2. Normalize email.
3. Create or reuse account by email.
4. Create organization membership with capability `teacher`, lifecycle `active`, access `none`, teacher access mode `scheduler_only`.
5. Create teacher profile and subject links.
6. Record scheduler state change if competencies/profile affect scheduler readiness.
7. Commit and return the member view model.

No Clerk invitation is created.

### 5.2 Create With Platform Access
For teacher platform, admin-only, or mixed members:
1. Validate admin, current organization, form draft, guardrails, and Clerk org id.
2. Normalize email and compute intended capabilities and Clerk role.
3. Create and commit a `member_access_operation` with a stable idempotency key and draft payload before calling Clerk.
4. Call Clerk synchronously to create an organization invitation for the current Clerk organization.
5. On Clerk failure, update the operation as `failed`, return a safe modal error, and do not create a visible member row.
6. On Clerk success, create or reuse account, create membership, create teacher profile when applicable, store invitation id/status, attach operation identifiers, and commit.
7. If local commit fails after Clerk success, attempt compensation by revoking the just-created invitation.
8. If compensation succeeds, mark operation `compensated` and return a safe modal error.
9. If compensation fails, mark operation `support_required`, block duplicate access changes for that organization/email/member context, log safe identifiers, and return a safe modal error.

### 5.3 Edit With Access Changes
For enable, disable, role downgrade/upgrade, resend, archive, or restore:
1. Validate the editable draft and guardrails.
2. Check unresolved operations or sync errors.
3. Persist an access-operation record with previous and intended state.
4. Call Clerk synchronously.
5. Commit local state only after the required Clerk operation succeeds.
6. Attempt compensation on local commit failure.
7. Refresh or invalidate frontend member/session state after success.

### 5.3A Resend Invitation Semantics
Resend is a two-Clerk-operation workflow for `pending_invite` memberships and a one-Clerk-operation workflow for `invite_expired` memberships.

For `pending_invite`:
1. Persist a `resend_invitation` access operation with the old invitation id.
2. Revoke the old pending invitation with the current admin Clerk user id as `requesting_user_id` or the SDK equivalent.
3. If revoke fails and Clerk still reports the old invitation as pending, leave local membership unchanged, mark the operation `failed`, and return a safe error.
4. If revoke succeeds, immediately update the operation with `old_invitation_revoked = true`.
5. Create the new invitation.
6. If create succeeds, replace the membership's invitation id/status and keep `access_status = pending_invite`.
7. If create fails, the old invitation is no longer usable. The membership must be committed as `access_status = invite_expired`, `clerk_invitation_status = revoked`, with no usable pending invitation id, and the operation is marked `failed` or `support_required` according to the error. This is an honest persisted access-state change, not a partial table update.

For `invite_expired`:
1. Persist a `resend_invitation` access operation.
2. Create a new invitation.
3. On success, replace invitation id/status and set `access_status = pending_invite`.
4. On failure, leave `access_status = invite_expired` and return a safe retry/support error.

### 5.4 Clerk Invitation Policy
Every platform-access invitation:
- targets the current Clerk organization only;
- uses the current authenticated admin's Clerk user id as inviter;
- must be implemented through a Clerk SDK or REST Backend API path that supports passing the inviter. If the chosen SDK wrapper cannot pass `inviterUserId`, Clerk REST `inviter_user_id`, or equivalent, use the REST Backend API directly or block launch implementation until this requirement is satisfied;
- must not use system/null inviter behavior for normal `Equipa` member creation;
- uses role `org:member` for teacher-only platform access;
- uses role `org:admin` for admin-only and mixed members;
- stores Clerk invitation id and status locally;
- includes only safe metadata, such as local organization id, access-operation id, membership id when known, and teacher profile id when applicable;
- never includes passwords, secrets, raw tokens, or cross-organization information.

Launch uses Clerk's default invitation acceptance flow. Cronos does not implement a custom `/accept-invite` flow.

Every invitation revoke:
- targets only the current Clerk organization;
- passes the current authenticated admin's Clerk user id as Clerk REST `requesting_user_id` or equivalent;
- must be used for resend, remove, archive, and compensation flows that revoke pending organization invitations;
- must not use system/null revoker behavior for normal `Equipa` member management.

### 5.5 Error Categories
Provider and sync errors are mapped to safe product categories:
- `transient`: ask the admin to retry;
- `invalid_email`: ask the admin to check or edit the email;
- `provider_permission`: ask the admin to contact support;
- `provider_configuration`: ask the admin to contact support;
- `current_org_duplicate`: explain the email is already a member of this organization without disclosing external account state;
- `sync_mismatch`: offer retry, then support if unresolved;
- `unknown`: offer safe retry or support escalation.

Raw Clerk errors, stack traces, secrets, and cross-organization account existence must not appear in admin UI responses.

### 5.6 Support-Required Recovery
The PRD excludes a support dashboard, but `support_required` must have a launch recovery path.

Minimum recovery surface:
- an internal support-only CLI command or protected admin-only maintenance endpoint, not visible to school admins;
- ability to inspect one `member_access_operation` by id with safe identifiers, previous state, intended state, Clerk ids, and compensation status;
- ability to run a dry-run reconciliation against Clerk current state before mutation;
- ability to retry the failed compensation or local commit step when idempotency keys prove it is safe;
- ability to mark an operation resolved only after local membership/account/access state matches Clerk current state;
- structured audit fields: `support_resolution_action`, `support_resolved_by_user_id`, `support_resolved_at`, and a non-sensitive note or ticket reference.

Allowed support actions:
- `confirm_already_compensated`: Clerk no longer has the side effect, so mark the operation `compensated` and unblock;
- `retry_compensation`: revoke invitation, revoke membership, or restore role according to the stored previous snapshot;
- `commit_confirmed_clerk_state`: local commit failed but Clerk side effect is correct and desired, so apply the intended local state;
- `force_sync_error`: state remains ambiguous; keep access denied and leave admin-facing recovery as support escalation.

Rules:
- support recovery must never create product capabilities from unmatched Clerk state;
- support recovery must enforce the last-active-admin guardrail unless the operator is performing explicit emergency bootstrap documented in the migration runbook;
- after resolution, duplicate create/resend/retry operations for the same organization/email/member may proceed only when no unresolved `pending`, `clerk_succeeded`, `compensation_failed`, or `support_required` operation remains.

## 6. Webhook Reconciliation

### 6.1 Verification And Idempotency
The `/api/v1/webhooks/clerk` endpoint must:
- verify Svix headers and signature;
- reject invalid signatures;
- acquire a row lock on `clerk_webhook_event.svix_id` before applying side effects;
- insert new events as `processing` with `attempt_count = 1` in the same transaction that applies local side effects;
- commit the event and all local side effects together as `processed`, `ignored`, or `sync_error`;
- return 2xx for terminal `processed`, `ignored`, or `sync_error` states;
- return non-2xx for transient dependency or database failures after recording `retryable_failed` when possible, so Clerk/Svix retry delivery can occur;
- reprocess duplicate deliveries when the existing row is `received`, stale `processing`, or `retryable_failed`;
- never skip a duplicate only because `svix_id` exists unless that row is terminal.

Terminal states:
- `processed`: event applied or confirmed already applied.
- `ignored`: event is valid but intentionally has no product target, with safe reason recorded.
- `sync_error`: event is valid but local/Clerk state is ambiguous or conflicting; access is denied or blocked as needed.
- `dead_letter`: repeated retryable failures exceeded the configured attempt limit and require support inspection.

Retry states:
- `received`: stored but not yet processed by a worker.
- `processing`: currently locked by a handler or worker; if older than the processing timeout, it is stale and retryable.
- `retryable_failed`: transient provider/database/lock failure; next duplicate delivery or scheduled reconciliation can process it again.

The scheduled reconciliation task must include stale `processing`, `retryable_failed`, and `dead_letter` summaries in logs/metrics. It may reprocess retryable rows, but it must not mutate terminal rows except through explicit support recovery.

### 6.2 Required Events
The feature requires handling:
- `organizationMembership.created`;
- `organizationMembership.updated`;
- `organizationMembership.deleted`;
- `organizationInvitation.created`;
- `organizationInvitation.accepted`;
- `organizationInvitation.revoked`;
- `user.created`;
- `user.updated`;
- `user.deleted`;
- `organization.created`;
- `organization.updated`;
- `organization.deleted`.

### 6.3 Reconciliation Order
Invitation events:
1. Match by stored `clerk_invitation_id`.
2. Validate Clerk organization id against local organization.
3. Update invitation status and derived access status.
4. If accepted, wait for or fetch membership/user identifiers before marking access `active`.

Membership events:
1. Match by stored `clerk_membership_id` when available.
2. Match by `clerk_invitation_id` through invitation/access operation when available.
3. Match by Clerk org id, Clerk user id, verified email, and pending local membership/access-operation record.
4. Validate the expected Clerk role against local capabilities.
5. Link account `clerk_user_id` and membership only when the target is unique.
6. Mark `active`, `blocked`, or `sync_error` as appropriate.

User events:
1. Update an existing linked account by `clerk_user_id`.
2. If no linked account exists, match only through verified email plus a valid pending membership/access-operation context.
3. If the new Clerk primary verified email collides with another local account, do not merge; mark affected memberships `sync_error` with `identity_conflict`.
4. Do not create orphan product users from `user.created` alone.

Organization events:
1. Sync local organization mirror by Clerk organization id.
2. Deactivation must not hard delete member, teacher, or scheduler history.

### 6.4 External Clerk Drift
Changes made directly in Clerk outside Cronos are reconciled conservatively:
- unmatched Clerk memberships do not create product capabilities;
- role mismatches become `sync_error`;
- direct membership removal becomes `blocked` or `sync_error` and backend authorization denies access;
- direct Clerk role upgrades do not grant Cronos admin capability;
- direct Clerk role downgrades do not remove Cronos capability, but they can block access until reconciled;
- last-active-admin checks do not count blocked, mismatched, pending, archived, sync-error, or no-Clerk-id admin-capable members.

### 6.5 Invitation Expiry Detection
Cronos must not depend on an `organizationInvitation.expired` webhook.

Expiry is detected through three mechanisms:
- store `invitation_expires_at` when Clerk returns an expiration timestamp;
- on `GET /members`, convert pending invitations with `invitation_expires_at <= now()` to `access_status = invite_expired` before rendering;
- when no expiration timestamp is available or a pending invite is older than the configured reconciliation threshold, perform a Clerk Backend API lookup before rendering `Convite pendente`, before resending, and in a scheduled reconciliation task.

Launch reconciliation task:
- runs at least hourly in production-like environments;
- checks pending invitations older than the configured threshold;
- updates revoked/expired/accepted state using Clerk's current invitation or membership state;
- marks ambiguous provider responses as `sync_error` only when the local state cannot be safely classified as pending or expired.

If `GET /members` needs a Clerk lookup to avoid rendering a stale pending invite and Clerk is unavailable:
- return the member row from local state instead of failing the whole table request;
- keep `access_status = pending_invite` only as local unconfirmed state;
- set `provider_state = unconfirmed`;
- set `safe_status_message` to a non-technical confirmation warning;
- set `allowed_actions.can_resend_invite = false` until current invitation state is confirmed;
- do not mutate the membership to `sync_error` solely because Clerk was temporarily unavailable.

`Reenviar convite` must always perform a current-state check before mutating Clerk state.

## 7. Authorization

### 7.1 Request Context
Replace role-only auth resolution with a member context:
- verify Clerk session token;
- resolve current Clerk organization id from the token;
- resolve local organization by `clerk_org_id`;
- resolve account by `clerk_user_id`;
- resolve organization membership by `(organization_id, account_id)`;
- require lifecycle `active`;
- require access status `active` for platform routes;
- verify current Clerk organization membership when local state is missing, pending, stale, or role-mismatched;
- require expected Clerk role compatibility only after current Clerk membership has been checked through fresh session claims or Backend API;
- set tenant context from membership organization id.

### 7.1A First-Login Synchronous Reconciliation
The first authenticated request after Clerk invitation acceptance must not depend on webhook delivery.

When a signed-in Clerk user reaches Cronos and local membership is still `pending_invite`, missing `clerk_user_id`, or missing `clerk_membership_id`, the auth path must:
1. Use the current Clerk session claims to obtain `sub`, Clerk organization id, and session role.
2. Resolve the local organization by Clerk organization id.
3. Call Clerk Backend API for the current user's organization membership when local state is incomplete or stale.
4. Match the Clerk user to a pending local membership by stored invitation id, access-operation id, verified email, organization id, and expected role.
5. Link `user.clerk_user_id`, `organization_membership.clerk_membership_id`, invitation status, and access status in the same local transaction.
6. Return the resolved member context for routing.

Required Clerk Backend API reads for first-login reconciliation:
- `GET /v1/organizations/{organization_id}/memberships?user_id[]={clerk_user_id}&limit=2`;
- fallback `GET /v1/users/{user_id}` when verified email or primary email id is needed;
- fallback `GET /v1/organizations/{organization_id}/memberships?email_address[]={normalized_email}&limit=2` only after the email has been verified on the Clerk user;
- `GET /v1/organizations/{organization_id}/invitations/{invitation_id}` when a local pending membership stores `clerk_invitation_id`;
- optional `GET /v1/users/{user_id}/organization_invitations?status=accepted|pending|revoked|expired` when invitation state is missing locally and the user endpoint is available in the installed Clerk SDK/API client.

Fields Cronos must consume:
- session claims: Clerk user id `sub`, Clerk organization id, and session organization role;
- organization membership response: `id`, `role`, `organization.id`, `public_user_data.user_id`, `public_user_data.identifier`, `public_metadata`, `private_metadata`, `created_at`, and `updated_at`;
- invitation response: `id`, `email_address`, `role`, `organization_id`, `status`, `expires_at`, `inviter_id`, `public_metadata`, and `private_metadata`;
- user response: `id`, `primary_email_address_id`, `email_addresses[].id`, `email_addresses[].email_address`, and `email_addresses[].verification.status`.

Matching precedence:
1. `organization_membership.private_metadata.access_operation_id` or `public_metadata.access_operation_id` equals the stored local access-operation id.
2. `organization_membership.private_metadata.membership_id` or `public_metadata.membership_id` equals the local membership id.
3. Stored local `clerk_invitation_id` resolves to an accepted invitation whose metadata, email, role, and organization match the local pending membership.
4. Verified Clerk primary email, Clerk organization id, expected role, and exactly one pending local membership/access operation match.

If more than one local target matches, or if the Clerk membership role conflicts with the expected role after fresh Backend API lookup, reconciliation must fail closed. Do not infer a product member from Clerk membership alone.

If the synchronous lookup confirms the user has Clerk organization membership but no unique local pending membership/operation can be matched, deny product access and mark or log `sync_error`; do not create product capabilities silently.

If Clerk Backend API is temporarily unavailable during first login, return `503` with `member_access_provider_failed` and `retryable = true`. Do not leave the user as locally active without confirmed Clerk membership.

### 7.1B Session Role Freshness
A mismatch between Clerk session role claims and local expected role is not, by itself, a durable sync error.

Handling:
- if the token role is stale but Backend API confirms the expected current Clerk role, authorize from local capabilities and return a response/header flag that tells the frontend to refresh Clerk/session/member state;
- if Backend API confirms the role mismatch, mark membership `sync_error` and deny risky actions until retry/support reconciliation;
- if Backend API cannot be reached, deny the current privileged action with `member_session_refresh_required` or retryable provider error, but do not persist `sync_error`;
- after local role-changing saves, the frontend must refresh organization/session/member state where Clerk supports it.

### 7.2 Admin Authorization
Admin endpoints require:
- local `admin` capability;
- lifecycle `active`;
- access status `active`;
- linked account `clerk_user_id`;
- current organization membership;
- no blocked or sync-error state.

The last-active-admin guardrail counts only memberships that satisfy that same active-admin definition.

### 7.3 Teacher Authorization
Teacher self-service endpoints require:
- local `teacher` capability;
- lifecycle `active`;
- access status `active`;
- linked account `clerk_user_id`;
- linked teacher profile id;
- current organization membership.

Mixed-role members with Clerk `org:admin` and local `teacher` capability must pass teacher authorization when they are using teacher features.

### 7.4 Backend Is Authoritative
Frontend state can be stale. Backend authorization must deny revoked, blocked, archived, or sync-error access on the next API request even if the UI has not refreshed.

### 7.5 RLS And `app_security` Replacement
The current database auth helpers are organization-bound to `user.organization_id`, `user.role`, `user.teacher_id`, and `user.is_active`. They must be replaced in the same migration that introduces memberships.

Replace or rewrite:
- `app_security.resolve_auth_context(clerk_user_id, clerk_org_id)`;
- `app_security.ensure_user(...)`;
- `app_security.update_user_profile(...)`;
- `app_security.deactivate_user(...)`;
- any helper, RLS policy, trigger, or test fixture that treats `public."user".organization_id`, `role`, `teacher_id`, or `is_active` as the source of auth truth.

New helper requirements:
- `resolve_member_auth_context(clerk_user_id, clerk_org_id)` returns `account_id`, `organization_id`, `membership_id`, `lifecycle_status`, `access_status`, capabilities, `teacher_profile_id`, `expected_clerk_role`, and safe denial reason;
- `ensure_account_from_clerk(clerk_user_id, email, profile_name)` upserts the global account only and never grants organization capabilities by itself;
- `link_membership_from_clerk(...)` links a verified Clerk membership to one existing local membership/access-operation and refuses ambiguous matches;
- `deactivate_clerk_user_access(clerk_user_id)` blocks or sync-errors affected memberships without deleting teacher history or disabling the global account across all organizations.

RLS policy requirements:
- tenant policies continue to use `app.current_organization_id`;
- the application sets tenant context only after `resolve_member_auth_context` returns an active membership for that organization;
- global account reads are limited to the resolved account or service-owned reconciliation paths;
- organization-scoped tables remain protected by `organization_id = app_security.current_organization_id()`;
- tests must prove that replacing the auth helper does not allow cross-tenant account, membership, teacher profile, schedule, or audit reads.

## 8. Frontend Architecture

### 8.1 Routes And Navigation
Launch navigation:
- admin staff-management label: `Equipa`;
- admin staff-management route: `/members`;
- admin creation action: `Adicionar Membro`;
- old visible `/teachers` admin page removed or redirected away from launch navigation.

Teacher self-service routes remain:
- `/my-availability`;
- `/my-schedules`;
- `/my-progress`.

### 8.2 Equipa Page
The page renders:
- unified member table;
- search by name/email;
- filters by capability and access status;
- `Mostrar arquivados` filter;
- lifecycle and access chips;
- competency summary and visible `Sem competências` warning for teachers without competencies;
- practical empty state when only the current admin exists;
- no password field or local credential copy.

### 8.3 Member Modal
The modal draft includes:
- organization display name;
- email;
- capability selector: `Professor`, `Administrador`, `Professor + Administrador`;
- teacher access mode when `Professor` is selected: `Com acesso a plataforma` or `Apenas recurso de horário`;
- `?` help for scheduler-only teachers;
- teacher competencies when `Professor` is selected;
- admin access confirmation when `Administrador` is selected;
- action-specific content for resend, retry, restore, and the single remove action using `remove_effect` to explain hard delete vs archive.

Rules:
- draft changes are discarded on cancel, close, or dismiss;
- `Guardar` is the only confirmation step;
- validation errors keep the modal open;
- failed Clerk operations keep the modal open and table unchanged;
- successful saves close the modal, update the table, and show a short toast.

### 8.4 Mixed-Role Mode Switcher
Mixed-role members:
- land in admin mode by default;
- see a sidebar mode switcher;
- can switch to teacher mode without signing out or changing Clerk account/org;
- use local capabilities and `GET /members/me` to determine available modes.

Single-role members do not see the switcher.

### 8.5 Frontend Data Hooks
Add member hooks:
- `useMembers(filters)`;
- `useMember(memberId)`;
- `useCurrentMember()`;
- `useCreateMember()`;
- `useUpdateMember()`;
- `useRemoveMember()`;
- `useRestoreMember()`;
- `useResendMemberInvitation()`;
- `useRetryMemberSync()`.

Deprecate `useCreateEntity('teachers')`, `useUpdateEntity('teachers')`, and `useDeleteEntity('teachers')` for staff management.

## 9. Migration And Cleanup

### 9.1 Pre-Launch Cutover
Because the app has not launched, prefer a clean cutover over backwards compatibility.

Required migration steps:
1. Add membership/capability/access-operation/webhook-event schema and migrate the physical `user` table into global account semantics.
2. Replace RLS/auth helpers that depend on `user.organization_id`, `role`, `teacher_id`, or `is_active`.
3. Bootstrap existing active admins first: for every current local admin with a Clerk user id and organization, create a global account, an organization membership with `admin` capability, lifecycle `active`, access `active`, expected Clerk role `org:admin`, and a verified current Clerk organization membership.
4. Refuse migration completion for any organization that would have zero active admins after bootstrap.
5. Transform existing local teacher users into global accounts where valid.
6. Transform existing teacher rows into teacher profiles linked to memberships.
7. Create memberships for existing valid teacher resources.
8. Convert scheduler-only teacher stubs to access `none`.
9. Convert valid pending invite stubs only when the Clerk side can be verified.
10. Delete duplicate/invalid local stubs when no operational history exists.
11. Archive instead of delete any record with operational-history blockers.
12. Add a regression that no `access_status = active` membership exists without account `clerk_user_id`.

Admin bootstrap fallback:
- if a current admin exists locally but cannot be verified in Clerk, do not silently grant active admin access;
- create a support-required migration report with organization id, local user id, email, and missing Clerk condition;
- block launch cutover for that organization until the admin is verified or explicitly recreated through Clerk.

### 9.2 Code Cleanup
Remove or rewrite:
- `frontend/src/pages/Teachers.jsx` as launch navigation surface;
- `frontend/src/components/Forms/TeacherForm.jsx` password and `create_user_account` behavior;
- frontend tests that assert password or local account switch behavior;
- backend `TeacherCreate.create_user_account` and `TeacherUpdate.create_user_account` from canonical member APIs;
- `/api/v1/teachers/` admin create/update/delete;
- teacher creation calls to `user_service.create_user(... clerk_user_id=None ...)`;
- best-effort `invite_teacher_to_clerk` behavior that swallows failure;
- auth code that mutates local product role from Clerk token role as the source of product permissions;
- SQL functions `app_security.resolve_auth_context`, `ensure_user`, `update_user_profile`, and `deactivate_user` in their current organization-bound form.

Retain or adapt:
- teacher self-service endpoints;
- scheduler/domain teacher profile reads;
- `teacher_subject_link`;
- teacher availability, schedule, progress, lesson, timesheet, and occurrence history.

### 9.3 Documentation Cleanup
Documentation must use:
- `Equipa` for the visible staff-management area;
- `/members` for the admin API resource;
- `teachers` only for teacher self-service, teacher profile, scheduler/domain, or historical context.

Any document that presents `/teachers` admin CRUD, password setup, or local active teacher users as launch behavior must be updated or marked historical.

## 10. Observability

Minimum structured log events:
- member create requested;
- member created;
- teacher profile created;
- member invite requested;
- access-operation created;
- Clerk invitation created;
- Clerk invitation failed;
- Clerk side-effect compensation succeeded or failed;
- support-required operation resolved or still blocked;
- webhook linked account/membership/teacher profile;
- webhook ignored due to invalid or missing reconciliation context;
- webhook retryable failure, stale processing recovery, and dead-letter transition;
- access blocked or deactivated;
- sync error created;
- identity conflict detected;
- provider state unconfirmed during invitation expiry lookup;
- sync retry attempted and resolved/unresolved;
- last-active-admin guardrail blocked an action.

Minimum counter-ready metrics:
- invite success count;
- invite failure count;
- pending invites older than threshold;
- webhook link success count;
- webhook retryable failure count;
- webhook dead-letter count;
- webhook sync-error count;
- identity-conflict count;
- provider-state-unconfirmed count;
- support-required access-operation count;
- login failures caused by missing teacher profile for local `teacher` capability.

Logs must include safe identifiers when available:
- organization id;
- account id;
- membership id;
- teacher profile id;
- access-operation id;
- Clerk user id;
- Clerk organization id;
- Clerk invitation id;
- Clerk membership id;
- event type;
- non-sensitive error category.

## 11. Testing

### 11.1 Backend Service Tests
Required coverage:
- create teacher-only scheduler resource;
- create teacher-only platform member;
- create admin-only member;
- create mixed member;
- migrate/bootstrap existing active admin into account plus membership without relying on legacy `user.role`;
- replace auth/RLS helper behavior for account, membership, capability, and tenant context resolution;
- edit name, email before active access, capabilities, access mode, and competencies;
- remove `teacher` capability with and without blockers;
- operational-history blocker checks cover every table/column listed in section 4.8;
- remove `admin` capability with last-active-admin guardrail;
- self-edit guardrails;
- remove hard-deletes when eligible and archives when `remove_effect = archive`;
- remove active accepted members revokes Clerk organization membership before archive;
- remove pending members revokes Clerk invitation with the current admin as `requesting_user_id`;
- restore scheduler-only, teacher-only platform, admin-only, and mixed archived members;
- resend pending and expired invitations, including revoke-success/create-failure state;
- resend revoke calls include the current admin as `requesting_user_id`;
- invitation expiry detection through timestamp, on-read lookup, and scheduled reconciliation;
- invitation expiry lookup provider outage returns local row with `member_provider_state_unconfirmed`, disables resend, and does not mark `sync_error`;
- identity conflict handling for duplicate normalized email, conflicting `clerk_user_id`, and Clerk primary email collision;
- support-required operation recovery through the launch CLI or internal maintenance endpoint;
- retry sync errors;
- no active access without `clerk_user_id`;
- no duplicate account/membership/teacher profile on retry.

### 11.2 API Contract Tests
Required coverage:
- `/members` list view model contains all fields needed by `Equipa`;
- `POST /members` rejects password and `create_user_account`;
- `POST /members` validates teacher access mode;
- `POST /members` does not leak external account existence;
- `/members` errors follow the stable error envelope, status-code policy, and field error format;
- Clerk failure keeps modal-save response failed and visible table unchanged;
- resend failure after old invite revocation returns `invite_expired`, not stale `pending_invite`;
- invitation expiry lookup outage returns `provider_state = unconfirmed` and disables resend;
- `GET /members` exposes one removal action via `can_remove` plus `remove_effect`, with no separate `can_archive`;
- action flags reflect backend guardrails;
- teacher-only members cannot access `Equipa`;
- admin-capable members can access `Equipa`;
- mixed-role members can access both admin and teacher product areas through local capabilities.

### 11.3 Webhook Tests
Required coverage:
- Svix signature rejection;
- duplicate `svix-id` idempotency for terminal rows;
- duplicate `svix-id` reprocessing for `received`, stale `processing`, and `retryable_failed` rows;
- retryable webhook failure returns non-2xx and later duplicate delivery reprocesses safely;
- `dead_letter` is observable and not automatically mutated without support recovery;
- `organizationInvitation.created/accepted/revoked`;
- `organizationMembership.created/updated/deleted`;
- `user.created/updated/deleted`;
- membership event without invitation metadata still reconciles safely when local records uniquely match;
- first-login reconciliation uses Clerk organization membership, invitation, and user fields listed in section 7.1A;
- unmatched membership does not create product capabilities;
- role mismatch becomes `sync_error`;
- primary email collision becomes identity-conflict `sync_error`;
- stale session role mismatch does not become `sync_error` until Backend API confirms real drift;
- direct membership removal becomes blocked or sync-error;
- repeated webhooks do not create duplicates.

### 11.4 Frontend Tests
Required coverage:
- `Equipa` table renders lifecycle and access chips;
- member modal has no password field;
- teacher-only scheduler creation sends no access operation intent;
- teacher platform creation sends access intent;
- admin-only and mixed creation require platform access;
- teacher fields hide for admin-only members;
- admin-specific confirmation appears for admin capability;
- transactional modal discards on cancel/close;
- failed save keeps modal open;
- `Reenviar convite` visibility only for pending/expired invites;
- remove modal uses one action and explains hard delete vs archive from `remove_effect`;
- `Erro de sincronização` shows retry and blocks risky edits;
- mixed-role mode switcher appears only for mixed members.

### 11.5 End-To-End Tests
Required coverage:
- admin creates scheduler-only teacher and sees `Sem acesso`;
- admin creates teacher with platform access and sees `Convite pendente`;
- invited teacher accepts through Clerk default flow and lands in teacher experience after returning to Cronos;
- invited teacher first login succeeds when Clerk webhooks are delayed but Backend API membership lookup succeeds;
- invited admin accepts and can access `Equipa`;
- invited mixed member accepts, lands in admin experience, and can switch to teacher mode;
- access revocation is enforced by backend on next request;
- last-active-admin destructive action is blocked.

## 12. Launch Definition Of Done

Launch is blocked unless:
1. `Equipa` replaces visible `Professores` admin CRUD.
2. `/members` is the canonical admin staff-management API.
3. No member create/edit UI asks for a password.
4. No canonical member create/update schema accepts `create_user_account`.
5. Existing active admins are migrated into verified account plus organization membership records before teacher/member cutover completes.
6. RLS/auth helpers are replaced so `user.organization_id`, `role`, `teacher_id`, and `is_active` no longer drive launch authorization.
7. Scheduler-only teachers can be created with access `none`.
8. Platform-access teachers are invited through Clerk as `org:member`.
9. Admin-only and mixed members are invited through Clerk as `org:admin`.
10. Normal invitations use the current authenticated admin's Clerk user id as inviter.
11. Normal invitation revokes use the current authenticated admin's Clerk user id as `requesting_user_id`.
12. First login after Clerk invitation acceptance works when webhooks are delayed, through synchronous Clerk Backend API reconciliation using the fields listed in section 7.1A.
13. Invitation expiry is detected before rendering stale pending states or resending, and provider outages use `member_provider_state_unconfirmed`.
14. Resend invitation cannot leave a revoked old invitation displayed as `Convite pendente`.
15. Remove/archive flows revoke the applicable pending invitation or active Clerk organization membership before preserving local history.
16. Restore covers scheduler-only, teacher-only platform, admin-only, and mixed archived members.
17. Invitation/access failures are visible and do not persist misleading access.
18. Clerk side effects have durable access-operation records and compensation/support-required handling.
19. Support-required operations have a documented CLI or protected maintenance recovery path.
20. Webhook reconciliation is verified, idempotent, retry-aware, and conservative.
21. Identity conflicts are detected and do not silently merge different Clerk users.
22. Backend authorization uses local membership capabilities and access state.
23. Session role mismatch handles stale tokens before persisting `sync_error`.
24. Mixed-role members can access teacher features even when Clerk role is `org:admin`.
25. Last-active-admin guardrail is enforced.
26. Old visible `/teachers` admin CRUD is removed from launch navigation and canonical API use.
27. Required tests for teacher-only, admin-only, and mixed-role members pass.

Not required for first launch:
- custom invitation acceptance page;
- bulk import;
- billing or seat-limit enforcement;
- support dashboard;
- advanced webhook replay UI;
- full audit-log UI.

## 13. Implementation Sequence

1. Add schema and migrations for memberships, capabilities, access operations, webhook events, and teacher profile membership link while migrating the physical `user` table into account semantics.
2. Replace `app_security` auth/RLS helpers and backend dependencies with membership-aware auth context resolution.
3. Bootstrap current admins and block cutover for organizations without a verified active admin.
4. Add repositories and services for account, membership, teacher profile, access operation, Clerk access, first-login reconciliation, and member authorization.
5. Implement `/members` API contract, stable error envelope, and `GET /members/me`.
6. Implement Clerk access operations, mandatory inviter/revoker handling, resend failure semantics, and invitation expiry reconciliation.
7. Implement support-required CLI or protected maintenance recovery for unresolved access operations.
8. Implement webhook reconciliation against the new model, including retryable statuses, stale processing recovery, and dead-letter observability.
9. Implement first-login reconciliation using Clerk organization membership, invitation, and user reads.
10. Update backend authorization to use local membership capabilities and access state.
11. Migrate or reset pre-launch local stubs.
12. Build `Equipa` frontend route, table, modal, hooks, and mode switcher.
13. Remove old visible `/teachers` admin CRUD and password/account-switch UI.
14. Update tests from teacher CRUD/password assumptions to member/access lifecycle assumptions.
15. Run backend, frontend, and E2E validation against all launch member types.

## 14. Explicit Non-Goals

Do not implement in this baseline:
- student users;
- custom teacher sign-up;
- admin-set passwords;
- CSV/XLSX bulk member import;
- mass invitations;
- billing checkout, plan gating, seat-limit blocking, or Clerk Billing;
- custom invitation acceptance/welcome/profile-confirmation flow;
- internal support dashboard;
- advanced webhook replay UI.
