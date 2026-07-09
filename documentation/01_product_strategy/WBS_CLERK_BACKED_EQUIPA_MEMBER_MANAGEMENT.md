# WBS - Clerk-Backed Equipa Member Management Implementation

## 0. Authority And How To Use This File

This work breakdown structure is the implementation execution plan for Clerk-backed `Equipa` member management.

Source of truth:

1. `PRD_CLERK_TEACHER_USER_CREATION.md`.
2. `TECH_SPEC_CLERK_BACKED_EQUIPA_MEMBER_MANAGEMENT.md`.

Do not use any other document to change product behavior. If older code, tests, copy, routes, or documentation conflict with those two files, update, quarantine, or delete the conflicting item during the relevant WBS task.

This app is pre-launch. Prefer a clean cutover over compatibility shims when legacy behavior conflicts with the new baseline.

Implementation order is mandatory. Do not build the `Equipa` frontend before the `/members` backend contract and view model are stable. Do not remove the legacy admin teacher CRUD from navigation until the new `/members` route can cover launch staff management.

## 1. Non-Negotiable Baseline Rules

### 1.1 Naming And Route Boundary

Implementation requirements:

1. Use `Equipa` as the visible admin staff-management label.
2. Use `/members` as the frontend admin staff-management route.
3. Use `/api/v1/members` as the canonical backend admin staff-management API.
4. Keep `/teachers/me/...` only for teacher self-service.
5. Keep teacher profile and `teacher_id` usage only for scheduler/domain operations.
6. Do not use `/api/v1/teachers` as canonical admin member CRUD.
7. Do not use `/api/v1/import/teachers` as the `Equipa` table data source.
8. Remove visible `Professores`, `Novo Professor`, `Conta Ativa`, and `Inativo` behavior from the launch staff-management surface.

Acceptance:

1. Admin navigation contains `Equipa`, not visible admin CRUD `Professores`.
2. Admin member create, edit, remove, restore, resend, and retry actions call `/api/v1/members...`.
3. Teacher self-service routes still work through local `teacher` capability and teacher profile.

### 1.2 Identity And Permissions Boundary

Implementation requirements:

1. Clerk owns authentication identity, passwords, invitation acceptance, and current Clerk organization membership.
2. Cronos owns product capabilities, teacher profile, lifecycle/archive state, scheduler history, and the admin-facing member record.
3. Product capabilities are local membership capabilities: `teacher`, `admin`, or both.
4. Clerk roles are only organization membership roles:
   - teacher with platform access maps to `org:member`;
   - admin-only maps to `org:admin`;
   - mixed teacher/admin maps to `org:admin`;
   - scheduler-only teacher has no Clerk role requirement.
5. Backend authorization must use local capabilities and access state. It must not treat Clerk `org:admin` as incompatible with teacher features for mixed-role members.
6. Cronos must not silently grant product capabilities from unmatched Clerk memberships or external Clerk role changes.

Acceptance:

1. A mixed-role member with Clerk `org:admin` and local `teacher` capability can use teacher features.
2. A direct Clerk role upgrade does not grant Cronos admin capability unless local membership has `admin`.
3. A direct Clerk membership removal denies product access and becomes `blocked` or `sync_error`.

### 1.3 Password And Legacy Account Stub Removal

Implementation requirements:

1. No `Equipa` create or edit UI asks an admin to set another user's password.
2. `/members` create and update schemas reject `password`, local credential fields, and `create_user_account`.
3. Staff/member creation must not create active local login identities with `clerk_user_id = null`.
4. A global account may have `clerk_user_id = null` only when the member does not have access status `active`.
5. A member cannot show `Com acesso` unless Cronos has a real Clerk user id and confirmed current Clerk organization membership.

Acceptance:

1. Tests fail if a password field appears in the member modal.
2. Tests fail if `POST /members` accepts `create_user_account`.
3. Tests fail if `access_status = active` exists with a null `clerk_user_id`.

### 1.4 Launch Non-Goals

Do not implement these in this baseline:

1. Student users.
2. Custom teacher sign-up.
3. Admin-set passwords.
4. CSV/XLSX bulk member import.
5. Mass invitations.
6. Billing checkout, plan gating, seat-limit blocking, or Clerk Billing.
7. Custom invitation acceptance, welcome, or profile-confirmation flow.
8. Internal support dashboard.
9. Advanced webhook replay UI.
10. Full audit-log UI.

Acceptance:

1. No new UI or API surface for these non-goals is introduced.
2. Any existing code that suggests these are launch behavior is removed, marked historical, or left untouched only when outside this feature boundary.

## 2. WBS 0 - Baseline Inventory And Cutover Preparation

### 2.1 Inventory Legacy Staff-Management Code

Implementation steps:

1. Search the repo for:
   - `Teachers.jsx`;
   - `TeacherForm`;
   - `create_user_account`;
   - admin `POST`, `PATCH`, or `DELETE` routes under `/teachers`;
   - `user_service.create_user`;
   - `clerk_user_id=None`;
   - `invite_teacher_to_clerk`;
   - `User.is_active`;
   - `Conta Ativa`;
   - `Inativo`;
   - visible `Professores`;
   - `Novo Professor`;
   - route guards that treat `org:member` as the only teacher permission;
   - route guards that treat `org:admin` as incompatible with teacher mode.
2. Classify each hit as one of:
   - delete during WBS 13;
   - rewrite during backend implementation;
   - rewrite during frontend implementation;
   - keep because it is teacher self-service or scheduler/domain behavior.
3. Do not change behavior in this inventory task unless the hit is documentation-only and directly contradicts the new baseline.

Deliverables:

1. A short implementation note or checklist in the implementation branch describing each legacy hit and its assigned WBS task.

Acceptance:

1. Every legacy hit has an owner WBS task.
2. Teacher self-service routes are explicitly separated from admin staff-management legacy.

### 2.2 Confirm Clerk Backend API Capabilities

Implementation steps:

1. Confirm the available Clerk SDK or REST client can create organization invitations for a specific organization.
2. Confirm invitation creation can pass the current authenticated admin's Clerk user id as inviter.
3. Confirm pending organization invitations can be revoked with the current authenticated admin's Clerk user id as `requesting_user_id` or equivalent.
4. Confirm organization membership role changes can be applied for `org:member` and `org:admin`.
5. Confirm active organization membership can be revoked for a user.
6. Confirm first-login reconciliation reads can fetch:
   - membership by Clerk user id and organization id;
   - Clerk user by user id;
   - invitation by invitation id;
   - membership or invitation details needed for metadata, email, role, and organization checks.
7. If the SDK cannot pass required inviter or revoker fields, use Clerk REST Backend API directly for those operations.

Deliverables:

1. `ClerkAccessService` design notes or tests documenting the exact Clerk client methods or REST paths used.

Acceptance:

1. Launch is blocked if normal human-initiated invitations cannot record the current authenticated admin as inviter.
2. Launch is blocked if normal invitation revokes cannot record the current authenticated admin as revoker/requesting user.

### 2.2A Verify Clerk Organization Instance Configuration

Implementation steps:

1. Verify Clerk Organizations are enabled for every launch Clerk instance:
   - local/development instance used by the team;
   - staging instance;
   - production instance.
2. Verify organization membership mode is compatible with the product baseline:
   - preferred launch mode is organization membership required because Cronos product access is organization-scoped;
   - if membership optional is used, product routes must still block any signed-in user with no active Clerk organization context.
3. Verify a signed-in member receives active organization context needed by Cronos:
   - Clerk organization id is available in session/auth claims;
   - Clerk organization role is available in session/auth claims;
   - active organization selection survives normal app reloads.
4. Verify Clerk's organization-selection behavior is acceptable for invitation acceptance:
   - users can complete Clerk's default invitation acceptance flow;
   - if Clerk requires choose-organization/session-task steps, those steps complete before Cronos routes the user;
   - Cronos does not need a custom `/accept-invite` page for launch.
5. Verify required Clerk roles exist in the instance:
   - `org:admin`;
   - `org:member`.
6. Verify `org:admin` retains organization membership-management capability in Clerk when Clerk-side permission checks are used.
7. Verify no custom Clerk role set renames or removes `org:admin` or `org:member` from the launch invitation flow.
8. Verify current admin test account is a real Clerk organization admin in the launch organization before bootstrap dry run.
9. Verify Clerk dashboard invitation settings allow organization invitations for the current organization.
10. Record the verified Clerk instance id/environment, organization settings, membership mode, role names, and test organization id in the cutover report.

Acceptance:

1. Launch is blocked if Clerk Organizations are not enabled.
2. Launch is blocked if no active Clerk organization id can be resolved after sign-in/invitation acceptance.
3. Launch is blocked if `org:admin` or `org:member` cannot be used for organization invitations.
4. Launch is blocked if membership optional mode allows authenticated product access without an active organization context.

### 2.3 Quarantine Legacy Admin Teacher Writes Before Cutover

Implementation steps:

1. Before any migration that changes `user` into global account semantics is applied to a shared environment, disable legacy admin staff-management writes under `/api/v1/teachers`.
2. Quarantine these legacy write paths:
   - admin create teacher through `POST /api/v1/teachers`;
   - admin update teacher through `PATCH` or `PUT /api/v1/teachers/{id}`;
   - admin delete teacher through `DELETE /api/v1/teachers/{id}`;
   - any frontend staff-management mutation that reaches those endpoints;
   - any service path that creates a local login stub with `clerk_user_id = null`.
3. Keep valid teacher self-service and scheduler/domain routes available:
   - `/teachers/me/...`;
   - teacher availability writes that operate on the authenticated member's own teacher profile;
   - teacher profile reads required by scheduler/domain workflows.
4. If the new `/members` implementation is not ready yet in the same branch, legacy admin writes must fail closed with a safe server response instead of creating data in the old model.
5. Do not deploy the global-account migration while old admin teacher writes can still create organization-bound `User` rows, `create_user_account` behavior, local passwords, or active login stubs.

Acceptance:

1. Legacy admin teacher write endpoints cannot create, update, or delete staff-management records after the schema/auth cutover starts.
2. Teacher self-service and scheduler/domain teacher operations remain available where they do not conflict with the new member model.
3. Tests or route assertions prove that old admin teacher writes are disabled before or in the same deployment as the migration.

## 3. WBS 1 - Database Model And Migration

This section is split into implementation work packages for readability. Deployment is not split. Schema changes, auth/RLS helper replacement, admin bootstrap validation, and legacy admin teacher write quarantine must ship as one atomic cutover unit.

### 3.0 Atomic Cutover, Dry Run, And Backout Gate

Implementation steps:

1. Create one cutover plan that includes:
   - membership/capability/access-operation/webhook-event schema;
   - `user` table migration into global account semantics;
   - teacher membership link migration;
   - replacement of auth/RLS helpers that depend on `user.organization_id`, `role`, `teacher_id`, or `is_active`;
   - admin bootstrap;
   - legacy admin teacher write quarantine;
   - post-cutover smoke tests.
2. Implement a dry-run mode for the migration/bootstrap logic that performs no writes and produces a report with:
   - organization count;
   - current admin candidates by organization;
   - verified Clerk admin count by organization;
   - organizations that would have zero active admins;
   - duplicate normalized emails;
   - duplicate Clerk user ids;
   - teacher rows that can link to memberships;
   - teacher rows that require archive/delete decision;
   - local user stubs with `clerk_user_id = null`;
   - pending invite stubs that require Clerk verification;
   - rows that would become `support_required`.
3. Define cutover failure criteria. Abort before writes if the dry run reports any of:
   - an organization with zero verified active admins after bootstrap;
   - duplicate normalized emails that cannot be resolved deterministically;
   - duplicate non-null Clerk user ids;
   - required Clerk verification unavailable for admin bootstrap;
   - legacy admin teacher write routes still enabled;
   - auth/RLS replacement tests failing;
   - webhook secret/configuration missing for environments where webhooks are enabled.
4. Take a database backup or snapshot immediately before applying the cutover in any persistent environment.
5. Record the exact application version, migration revision, timestamp, operator, and backup/snapshot id in the cutover report.
6. Open a maintenance window for every persistent shared environment, including staging if multiple people use it.
7. During the maintenance window:
   - pause user traffic at the load balancer, reverse proxy, or deployment platform when available;
   - disable all staff-management writes;
   - stop old app workers that can write old-model staff data;
   - stop old background workers that use old auth/RLS assumptions;
   - prevent old and new application versions from serving requests concurrently during the auth/RLS migration;
   - drain or pause queues that could run old staff/auth jobs.
8. Deploy the new application version and run the migration as a single-version cutover.
9. Do not resume traffic until the new version, new auth/RLS helpers, migrated schema, and quarantined legacy writes are all active together.
10. Apply the schema migration, auth/RLS helper replacement, data bootstrap, and legacy write quarantine in the same deploy window.
11. Run post-cutover verification before allowing normal staff-management testing:
   - at least one active admin per organization;
   - no `access_status = active` without account `clerk_user_id`;
   - old admin teacher writes fail closed;
   - `/members/me` resolves the current admin;
   - tenant context is set only through membership auth context;
   - teacher self-service smoke path still resolves for a valid teacher member.
12. Resume traffic only after post-cutover verification passes.
13. Backout policy before user traffic or shared testing resumes:
   - restore the database backup/snapshot;
   - redeploy the previous application version;
   - verify old login/admin access state;
   - record the failed cutover report.
14. Backout policy after any post-cutover writes have occurred:
   - do not silently restore over newer writes;
   - freeze staff-management writes;
   - use the cutover report plus access-operation logs to choose either forward fix or explicit restore with data-loss approval from the product owner.

Acceptance:

1. No persistent environment runs global-account schema with old auth/RLS helpers as the active authorization source.
2. No persistent environment runs global-account schema while legacy admin teacher writes can create old-model staff records.
3. A dry-run report exists and passes all cutover gates before the real migration writes data.
4. A backup/snapshot id is recorded before cutover.
5. Cutover failure criteria are explicit and tested.
6. Persistent shared environments use a maintenance/single-version cutover so old and new auth/RLS code do not serve concurrently.
7. Staff-management writes remain disabled until post-cutover verification passes.

### 3.1 Migrate `user` Into Global Account Semantics

Implementation steps:

1. Reuse the existing physical `user` table as the semantic global account table.
2. Ensure the account has these fields:
   - `id`;
   - normalized globally unique `email`;
   - unique nullable `clerk_user_id`;
   - nullable `clerk_primary_email_id`;
   - nullable `clerk_profile_name`;
   - `created_at`;
   - `updated_at`;
   - nullable `last_clerk_sync_at`.
3. Deprecate the current organization-bound auth meanings of:
   - `organization_id`;
   - `role`;
   - `teacher_id`;
   - `is_active`.
4. Keep deprecated columns only if required for a safe cutover. They must be nullable or ignored by launch authorization.
5. Add constraints or tests that prevent duplicate normalized email accounts.
6. Add constraints or tests that prevent duplicate non-null Clerk user ids.

Acceptance:

1. New authorization code does not read `user.organization_id`, `user.role`, `user.teacher_id`, or `user.is_active` as the source of current product access.
2. Account profile names from Clerk do not overwrite the organization-scoped Cronos display name.
3. The same account can belong to multiple organizations through memberships.

### 3.2 Add `organization_membership`

Implementation steps:

1. Create the organization-scoped membership table with these fields:
   - `id`;
   - `organization_id`;
   - `account_id`;
   - `organization_display_name`;
   - `lifecycle_status`;
   - `access_status`;
   - nullable `teacher_access_mode`;
   - nullable `expected_clerk_role`;
   - nullable `clerk_membership_id`;
   - nullable `clerk_invitation_id`;
   - nullable `clerk_invitation_status`;
   - nullable `invitation_expires_at`;
   - nullable `access_error_category`;
   - nullable `access_error_safe_message`;
   - nullable `access_block_reason`;
   - nullable `created_by_user_id`;
   - nullable `updated_by_user_id`;
   - `created_at`;
   - `updated_at`;
   - `lock_version` or the repo's existing optimistic-concurrency equivalent.
2. Enforce unique `(organization_id, account_id)`.
3. Enforce lifecycle values:
   - `active`;
   - `archived`.
4. Enforce access values:
   - `none`;
   - `pending_invite`;
   - `invite_expired`;
   - `active`;
   - `blocked`;
   - `sync_error`.
5. Enforce teacher access mode values:
   - `platform`;
   - `scheduler_only`.
6. Enforce expected Clerk role values:
   - `org:member`;
   - `org:admin`.
7. Enforce invitation status values:
   - `pending`;
   - `accepted`;
   - `revoked`;
   - `expired`.

Acceptance:

1. Archived membership is organization-scoped and does not disable the global account in other organizations.
2. Scheduler-only teachers have access `none` and no usable Clerk invitation or membership for the organization.
3. Admin-capable members require platform access intent and expected Clerk role `org:admin`.

### 3.3 Add `organization_membership_capability`

Implementation steps:

1. Create the membership capability table with:
   - `organization_membership_id`;
   - `capability`.
2. Enforce capability values:
   - `teacher`;
   - `admin`.
3. Enforce unique `(organization_membership_id, capability)`.
4. Add a service-level invariant that active non-deleted memberships must have at least one capability.

Acceptance:

1. A member can have `teacher`, `admin`, or both.
2. A mixed member appears once in `Equipa`.
3. Last-active-admin checks use membership capabilities, not legacy user role.

### 3.4 Link `teacher` To Membership

Implementation steps:

1. Keep the existing `teacher` table as the teacher-domain profile.
2. Add `organization_membership_id` as a unique nullable column during migration.
3. Synchronize the teacher display name from membership `organization_display_name`, or preserve the existing `name` column as the displayed organization-scoped name.
4. Add `archived_at` only if current teacher-domain filtering needs it. Membership lifecycle remains the source of archive truth.
5. Keep `teacher_subject_link` as the competency relation.

Acceptance:

1. A launch-created teacher profile links to exactly one membership with `teacher` capability.
2. Scheduler-only and platform-access teachers use the same account, membership, and teacher profile model.
3. Removing `teacher` capability is blocked when operational-history blockers exist.

### 3.5 Add `member_access_operation`

Implementation steps:

1. Create the access-operation table with these fields:
   - `id`;
   - `organization_id`;
   - nullable `membership_id`;
   - nullable `account_id`;
   - `target_email`;
   - `operation_type`;
   - `operation_status`;
   - unique `idempotency_key`;
   - `intended_capabilities_json`;
   - nullable `intended_clerk_role`;
   - nullable `previous_access_snapshot_json`;
   - nullable `draft_payload_json`;
   - nullable `clerk_org_id`;
   - nullable `clerk_user_id`;
   - nullable `clerk_membership_id`;
   - nullable `clerk_invitation_id`;
   - nullable `provider_error_category`;
   - nullable `provider_error_safe_message`;
   - nullable non-sensitive `provider_error_reference`;
   - nullable `compensation_attempted_at`;
   - nullable `support_required_at`;
   - nullable `support_resolution_action`;
   - nullable `support_resolved_by_user_id`;
   - nullable `support_resolved_at`;
   - nullable non-sensitive `support_resolution_note`;
   - `created_by_user_id`;
   - `created_at`;
   - `updated_at`.
2. Enforce operation types:
   - `create_invitation`;
   - `revoke_invitation`;
   - `revoke_membership`;
   - `change_role`;
   - `resend_invitation`;
   - `restore_access`;
   - `block_access`.
3. Enforce operation statuses:
   - `pending`;
   - `clerk_succeeded`;
   - `local_committed`;
   - `failed`;
   - `compensated`;
   - `compensation_failed`;
   - `support_required`.
4. Add indexes for:
   - `organization_id`;
   - `membership_id`;
   - `account_id`;
   - `target_email`;
   - unresolved operation lookup by organization plus email/member;
   - `clerk_invitation_id`;
   - `clerk_membership_id`.

Acceptance:

1. No Clerk side effect can be attempted before an access-operation row is durably committed.
2. Failed visible saves may leave an operation record but must not leave a misleading member table row.
3. Duplicate create/resend/retry for the same organization/email/member is blocked or safely reuses an unresolved operation.

### 3.6 Add `clerk_webhook_event`

Implementation steps:

1. Create the webhook event table with:
   - `id`;
   - unique `svix_id`;
   - `event_type`;
   - nullable `clerk_object_id`;
   - nullable `clerk_org_id`;
   - nullable `clerk_user_id`;
   - sanitized `payload_json`;
   - `processing_status`;
   - nullable `error_category`;
   - `attempt_count`;
   - nullable `last_attempt_at`;
   - nullable `next_retry_at`;
   - `created_at`;
   - nullable `processed_at`.
2. Enforce processing statuses:
   - `received`;
   - `processing`;
   - `processed`;
   - `ignored`;
   - `retryable_failed`;
   - `sync_error`;
   - `dead_letter`.
3. Add indexes for:
   - `svix_id`;
   - `processing_status`;
   - `next_retry_at`;
   - `clerk_org_id`;
   - `clerk_user_id`;
   - `event_type`.
4. Define the sanitized `payload_json` allow-list. It may retain only fields required for idempotent retry, reconciliation, or safe diagnostics:
   - event id/Svix id when present;
   - event type;
   - Clerk object id;
   - Clerk organization id;
   - Clerk user id;
   - Clerk invitation id;
   - Clerk membership id;
   - role;
   - status;
   - expiration timestamp;
   - created/updated timestamps;
   - invitation `email_address`;
   - user `primary_email_address_id`;
   - user `email_addresses[].id`;
   - user `email_addresses[].email_address`;
   - user `email_addresses[].verification.status`;
   - first/last/profile name fields only when used for `clerk_profile_name`;
   - metadata keys explicitly used for reconciliation: `access_operation_id`, `membership_id`, `organization_id`, `teacher_profile_id`.
5. Redact or drop all other payload fields before storage, including:
   - images and avatars;
   - phone numbers;
   - addresses;
   - raw tokens;
   - session data;
   - IP addresses;
   - user agents;
   - unrecognized public/private/unsafe metadata;
   - provider raw error bodies;
   - any secret-bearing field.
6. Store emails and profile names only because first-login/webhook retry may need them for verified-email matching and account profile sync.
7. Never include sanitized payloads in school-admin API responses.
8. Retain sanitized webhook payloads for 90 days by default, then purge or reduce them to event id, event type, Clerk object ids, processing status, error category, and timestamps.
9. Keep `dead_letter` sanitized payloads until support resolution or 180 days, whichever comes first, then purge or reduce them to the same minimal diagnostic shape.

Acceptance:

1. Duplicate webhook delivery is reprocessed for retryable states and skipped only for terminal states.
2. Malformed events cannot grant product access.
3. Ignored unmatched membership events are observable with safe identifiers.
4. Stored webhook payloads contain enough data for retry but do not preserve unnecessary raw Clerk payload fields.
5. Payload retention and purge/reduction behavior is implemented or tracked as a launch operations task.

### 3.7 Migration Bootstrap And Cleanup

Implementation steps:

1. Bootstrap current admins before migrating teacher/member data.
2. For every current local admin with a Clerk user id and organization:
   - create or reuse a global account;
   - create an organization membership;
   - add `admin` capability;
   - set lifecycle `active`;
   - set access `active`;
   - set expected Clerk role `org:admin`;
   - verify current Clerk organization membership.
3. Block migration completion for any organization that would have zero active admins after bootstrap.
4. Transform existing local teacher users into global accounts when valid.
5. Transform existing teacher rows into teacher profiles linked to memberships.
6. Create memberships for existing valid teacher resources.
7. Convert scheduler-only teacher stubs to access `none`.
8. Convert valid pending invite stubs only when the Clerk side can be verified.
9. Delete duplicate or invalid local stubs when no operational history exists.
10. Archive instead of delete any record with operational-history blockers.
11. Produce a support-required migration report for any admin that cannot be verified in Clerk.

Acceptance:

1. Migration fails closed if an organization has no verified active admin.
2. No active access membership exists without account `clerk_user_id`.
3. No duplicate account, membership, or teacher profile is created for the same person/member.

## 4. WBS 2 - Auth, RLS, And Request Context

This work is documented after the schema tasks, but it must be deployed in the same atomic cutover as the membership/account migration. Do not merge or deploy the membership schema as active launch schema while these auth/RLS replacements are absent.

### 4.1 Replace `app_security` Helpers

Implementation steps:

1. Replace or rewrite `app_security.resolve_auth_context(clerk_user_id, clerk_org_id)`.
2. Replace or rewrite `app_security.ensure_user(...)`.
3. Replace or rewrite `app_security.update_user_profile(...)`.
4. Replace or rewrite `app_security.deactivate_user(...)`.
5. Update every helper, RLS policy, trigger, or test fixture that treats these as auth truth:
   - `public."user".organization_id`;
   - `public."user".role`;
   - `public."user".teacher_id`;
   - `public."user".is_active`.

New helper requirements:

1. `resolve_member_auth_context(clerk_user_id, clerk_org_id)` returns:
   - `account_id`;
   - `organization_id`;
   - `membership_id`;
   - `lifecycle_status`;
   - `access_status`;
   - capabilities;
   - `teacher_profile_id`;
   - `expected_clerk_role`;
   - safe denial reason.
2. `ensure_account_from_clerk(clerk_user_id, email, profile_name)` upserts the global account only.
3. `link_membership_from_clerk(...)` links verified Clerk membership to one existing local membership or access operation only.
4. `deactivate_clerk_user_access(clerk_user_id)` blocks or sync-errors affected memberships without deleting teacher history or disabling the global account across organizations.

Acceptance:

1. Tenant context is set only after active membership resolution succeeds.
2. Global account reads are limited to the resolved account or service-owned reconciliation paths.
3. Organization-scoped tables remain protected by current organization id.

### 4.2 Implement Member Request Context

Implementation steps:

1. Verify the Clerk session token.
2. Resolve the current Clerk organization id from the token.
3. Resolve the local organization by `clerk_org_id`.
4. Resolve the account by `clerk_user_id`.
5. Resolve the organization membership by `(organization_id, account_id)`.
6. Require lifecycle `active`.
7. Require access status `active` for platform routes.
8. Verify current Clerk organization membership when local state is missing, pending, stale, or role-mismatched.
9. Compare expected Clerk role only after current Clerk membership has been checked through fresh session claims or Backend API.
10. Set tenant context from membership organization id.

Acceptance:

1. Revoked, blocked, archived, and sync-error members are denied on the next backend request.
2. Backend denial does not depend on frontend refresh.

### 4.3 Implement Admin Authorization

Implementation steps:

1. Require local `admin` capability.
2. Require lifecycle `active`.
3. Require access status `active`.
4. Require linked account `clerk_user_id`.
5. Require current organization membership.
6. Deny blocked or sync-error state.
7. Compute active-admin eligibility from the same criteria.

Acceptance:

1. Pending, expired, blocked, archived, sync-error, scheduler-only, and no-Clerk-id admin-capable members do not count as active admins.
2. The last-active-admin guardrail uses this active-admin definition.

### 4.4 Implement Teacher Authorization

Implementation steps:

1. Require local `teacher` capability.
2. Require lifecycle `active`.
3. Require access status `active`.
4. Require linked account `clerk_user_id`.
5. Require linked teacher profile id.
6. Require current organization membership.
7. Permit mixed-role members with Clerk `org:admin` when they have local `teacher` capability.

Acceptance:

1. Teacher-only members can use teacher self-service after accepted access.
2. Mixed-role members can use teacher self-service without signing out or changing Clerk account.
3. Scheduler-only teachers cannot sign in or use teacher self-service.

### 4.5 Handle Session Role Freshness

Implementation steps:

1. Detect mismatch between Clerk session role claims and local expected role.
2. If Backend API confirms the expected current Clerk role, authorize from local capabilities and tell the frontend to refresh session/member state.
3. If Backend API confirms role mismatch, mark membership `sync_error` and deny risky actions.
4. If Backend API is unavailable, deny the privileged action with `member_session_refresh_required` or retryable provider error.
5. Do not persist `sync_error` solely because session claims are stale.

Acceptance:

1. Stale token role mismatch does not become durable `sync_error` until Backend API confirms real drift.
2. Backend still denies actions that cannot be safely authorized.

## 5. WBS 3 - Backend Service Layer

### 5.1 Implement `AccountService`

Implementation steps:

1. Normalize email consistently before lookup or save.
2. Find or create account by normalized email.
3. Reuse account when normalized email belongs to the same Clerk user id.
4. Link an unlinked account to Clerk only when Clerk confirms the signed-in or invited user owns a verified matching email.
5. Reject account merge when email belongs to an account linked to a different Clerk user id.
6. Handle Clerk `user.updated` primary email change to an unclaimed verified email.
7. Handle Clerk primary email collision by keeping local email and marking affected active memberships `sync_error` with category `identity_conflict`.
8. Do not silently relink by an unverified Clerk email.

Acceptance:

1. Duplicate normalized email cannot create duplicate accounts.
2. Cross-organization account existence is not exposed in admin-facing errors.
3. Account creation alone never grants organization capabilities.

### 5.2 Implement `OrganizationMembershipService`

Implementation steps:

1. Create membership with lifecycle, access, expected Clerk role, and teacher access mode.
2. Enforce unique current organization membership for `(organization_id, account_id)`.
3. Store and update current invitation state on membership.
4. Store and update current Clerk membership id on membership.
5. Manage membership capabilities through `organization_membership_capability`.
6. Compute allowed actions:
   - `can_edit`;
   - `can_edit_email`;
   - `can_remove`;
   - `can_restore`;
   - `can_resend_invite`;
   - `can_retry_sync`;
   - `can_remove_admin`.
7. Compute `remove_effect`:
   - `hard_delete`;
   - `archive`;
   - `blocked`.
8. Compute `seat_counted`: true only when access status is `active`.
9. Enforce last-active-admin guardrail.
10. Block risky edits while access status is `sync_error`.

Acceptance:

1. Action flags are backend-calculated and reflect guardrails.
2. Frontend does not independently decide destructive action availability.
3. Only access status `active` counts as a future billing seat.

### 5.3 Implement `TeacherProfileService`

Implementation steps:

1. Create teacher profile when `teacher` capability is selected.
2. Link the teacher profile to organization membership.
3. Sync display name with membership organization display name.
4. Create and update `teacher_subject_link` competency rows from `subject_ids`.
5. Allow no competencies at creation.
6. Return competency status `ready` or missing warning status for teachers without competencies.
7. Preserve teacher profile, availability, schedules, lessons, timesheets, absences, and audit history on archive/access revocation.
8. Check operational-history blockers before hard delete or removing `teacher`.

Minimum blocker checks:

1. `availability.teacher_id`.
2. `class_subject_link.teacher_id`.
3. `lesson.teacher_id`.
4. `schedule_output.lesson_id -> lesson.teacher_id`.
5. Scheduler jobs and drafts:
   - `schedule_generation_job.requested_by_user_id`;
   - `schedule_drafts.created_by_user_id`;
   - `schedule_drafts.decided_by_user_id`;
   - `schedule_draft_blocks.teacher_id`;
   - `schedule_diff_entries.teacher_id`;
   - `active_schedule_blocks.teacher_id`;
   - `planned_recovery_links.teacher_id`.
6. Scheduler lifecycle audit:
   - `scheduler_school_year_state.reset_by_user_id`;
   - `scheduler_state_version_events.changed_by_user_id`;
   - `scheduler_state_version_events.entity_type = 'teacher'` and `entity_id = teacher.id` as text.
7. Operational schedule blocks:
   - `operational_schedule_block.teacher_id`;
   - `operational_schedule_block.created_by_user_id`.
8. Weekly closure:
   - `teacher_weekly_timesheet.teacher_id`.
9. Occurrences and substitutions:
   - `lesson_occurrence.planned_teacher_id`;
   - `lesson_occurrence.executed_teacher_id`;
   - `lesson_occurrence.substitute_teacher_id`;
   - `lesson_occurrence.created_by_user_id`;
   - `lesson_occurrence.decided_by_user_id`;
   - `lesson_occurrence.revoked_by_user_id`;
   - `substitutions.original_teacher_id`;
   - `substitutions.substitute_teacher_id`.
10. Lesson records:
   - `lesson_log.schedule_output_id -> schedule_output.lesson_id -> lesson.teacher_id`;
   - `lesson_log.active_schedule_block_id -> active_schedule_blocks.teacher_id`;
   - `lesson_log.operational_block_id -> operational_schedule_block.teacher_id`;
   - `lesson_log.logged_by_user_id`.
11. Operational events:
   - `occurrence_operational_event.actor_user_id`;
   - `occurrence_operational_event.occurrence_id -> lesson_occurrence teacher columns`;
   - `occurrence_operational_event.schedule_output_id -> schedule_output.lesson_id -> lesson.teacher_id`;
   - `teacher_endpoint_operational_event.actor_user_id`;
   - `progress_ledger_entry.created_by_user_id`.
12. Clerk/access history:
   - accepted access;
   - active access;
   - blocked access;
   - sync-error access;
   - support-required operations;
   - historical access-operation rows.

Acceptance:

1. Competency links alone do not block hard delete or removing `teacher`.
2. Any real operational-history blocker blocks hard delete.
3. If blocker checks cannot be completed safely, the operation fails closed.

### 5.4 Implement `MemberAccessOperationService`

Implementation steps:

1. Create operation rows before every Clerk side effect.
2. Generate stable idempotency keys per organization, member/email, operation type, and draft intent.
3. Store previous state before edit, revoke, resend, archive, restore, and role-change operations.
4. Store intended capabilities and intended Clerk role.
5. Store Clerk returned ids immediately after provider success.
6. Mark status transitions:
   - `pending`;
   - `clerk_succeeded`;
   - `local_committed`;
   - `failed`;
   - `compensated`;
   - `compensation_failed`;
   - `support_required`.
7. Block duplicate unsafe access changes while unresolved operations exist.
8. Expose support-safe operation inspection data to the recovery surface.

Acceptance:

1. A Clerk invitation, membership revoke, or role change cannot exist without local operation context.
2. Failed compensation leaves `support_required` and blocks duplicate access changes.
3. Retrying the same organization/email/member first resolves or safely reuses the operation.

### 5.5 Implement `ClerkAccessService`

Implementation steps:

1. Create organization invitations for current Clerk organization only.
2. Pass the current authenticated admin Clerk user id as inviter.
3. Use Clerk role `org:member` for teacher-only platform access.
4. Use Clerk role `org:admin` for admin-only and mixed members.
5. Store Clerk invitation id, status, and expiration when returned.
6. Include only safe metadata:
   - local organization id;
   - access-operation id;
   - membership id when known;
   - teacher profile id when applicable.
7. Never include passwords, secrets, raw tokens, or cross-organization information in metadata.
8. Revoke pending invitations for current organization only.
9. Pass current authenticated admin Clerk user id as `requesting_user_id` or equivalent for normal revokes.
10. Revoke active Clerk organization membership when access is removed or member is archived.
11. Change organization membership role for admin add/remove or mixed-role transitions.
12. Map provider errors to product categories:
   - `transient`;
   - `invalid_email`;
   - `provider_permission`;
   - `provider_configuration`;
   - `current_org_duplicate`;
   - `sync_mismatch`;
   - `unknown`.
13. Handle Clerk `429` or rate-limit responses explicitly:
   - read `Retry-After` or equivalent retry metadata when present;
   - categorize the error as `transient`;
   - set `retryable = true`;
   - store `provider_error_category = transient`;
   - store a non-sensitive `provider_error_reference`;
   - store retry timing in the access operation when a field exists, or include it in the safe operation metadata until a column is added;
   - do not mark the Clerk side effect as succeeded;
   - do not create a visible pending invite or active access row unless Clerk actually created the invitation/membership/role change.
14. Admin-facing message for rate limit must be safe and actionable, for example ask the admin to wait briefly and try again.
15. Resend loops must be rate-limited locally enough to avoid repeated Clerk `429` responses for the same organization/member.
16. Support retry commands must respect stored retry timing unless the operator explicitly uses an override flag with a support note.

Acceptance:

1. Clerk failures are not swallowed.
2. The API returns safe, provider-neutral errors.
3. Raw Clerk errors, stack traces, secrets, and cross-organization account existence never reach the admin UI.
4. Clerk `429` responses never leave misleading `Convite pendente` or `Com acesso` state.
5. Rate-limit retry timing is visible to retry/support code without exposing raw provider responses to school admins.

### 5.6 Implement `MemberService`

Implementation steps:

1. Orchestrate create, edit, remove, restore, resend, retry, and view-model assembly.
2. Validate capabilities:
   - at least one capability required;
   - valid values are `teacher` and `admin`;
   - mixed capability is one member, not two rows.
3. Validate teacher access mode:
   - required when `teacher` capability is selected;
   - `scheduler_only` invalid when `admin` capability is selected.
4. Validate `subject_ids`:
   - accepted only with `teacher` capability;
   - must belong to the current organization.
5. Validate editable email:
   - required for every member;
   - editable before access status `active`;
   - locked in `Equipa` once access status is `active`.
6. Validate current-organization duplicate membership.
7. Validate identity conflicts without external account disclosure.
8. Enforce last-active-admin guardrail.
9. Enforce self-edit guardrail:
   - admin may edit safe profile fields;
   - admin cannot remove own admin capability;
   - admin cannot revoke/block own access;
   - admin cannot archive/remove self.
10. Enforce sync-error blockers.
11. Execute all-or-nothing save semantics for Clerk-backed changes.
12. Assemble the complete member view model for list, detail, and mutation responses.

Acceptance:

1. All admin staff-management mutations go through `MemberService`.
2. Teacher self-service/domain endpoints do not become staff-management endpoints.
3. Failed validation or failed Clerk operations leave the modal open and table unchanged.

## 6. WBS 4 - `/members` API Contract

### 6.1 Add Route Module And Dependency Wiring

Implementation steps:

1. Add canonical admin member routes:
   - `GET /api/v1/members`;
   - `POST /api/v1/members`;
   - `GET /api/v1/members/{member_id}`;
   - `PATCH /api/v1/members/{member_id}`;
   - `POST /api/v1/members/{member_id}/resend-invitation`;
   - `POST /api/v1/members/{member_id}/retry-sync`;
   - `POST /api/v1/members/{member_id}/remove`;
   - `POST /api/v1/members/{member_id}/restore`;
   - `GET /api/v1/members/me`.
2. Require admin authorization for admin member-management endpoints.
3. Require member context for `/members/me`.
4. Keep stable route naming without trailing-route ambiguity, following repo standards.

Acceptance:

1. `/api/v1/members` is registered and documented in API tests.
2. Teacher-only members cannot call admin member-management endpoints.
3. Admin-capable active members can call admin member-management endpoints.

### 6.2 Implement `GET /members`

Implementation steps:

1. Accept query parameters:
   - `include_archived`, default `false`;
   - `q`, search by organization display name and email;
   - `capability`, optional `teacher` or `admin`;
   - `access_status`;
   - `limit` and `offset` only if pagination is implemented before launch.
2. Return one row per organization membership.
3. Include these fields per item:
   - `id`;
   - `account_id`;
   - `organization_id`;
   - `name`;
   - `email`;
   - `capabilities`;
   - `lifecycle_status`;
   - `lifecycle_label`;
   - `access_status`;
   - `access_label`;
   - `teacher_access_mode`;
   - `teacher_profile_id`;
   - `subject_ids`;
   - `subjects`;
   - `competency_status`;
   - `invitation_status`;
   - `seat_counted`;
   - `safe_status_message`;
   - `provider_state`;
   - `remove_effect`;
   - `allowed_actions`.
4. Include top-level `total` outside `items`.
5. Compute product labels:
   - `active` -> `Ativo`;
   - `archived` -> `Arquivado`;
   - `none` -> `Sem acesso`;
   - `pending_invite` -> `Convite pendente`;
   - `invite_expired` -> `Convite expirado`;
   - `active` access -> `Com acesso`;
   - `blocked` -> `Acesso bloqueado`;
   - `sync_error` -> `Erro de sincronização`.
6. Before rendering stale pending invites, detect invitation expiry:
   - use stored `invitation_expires_at`;
   - run current-state Clerk lookup when timestamp is missing or threshold is exceeded.
7. If Clerk lookup is required but unavailable:
   - return the table row;
   - keep local pending state as unconfirmed;
   - set `provider_state = unconfirmed`;
   - set safe warning message;
   - set `allowed_actions.can_resend_invite = false`;
   - do not mutate to `sync_error` solely due to outage.

Acceptance:

1. The frontend can render `Equipa` table from this response alone.
2. The frontend can open the common edit modal without joining unrelated resources.
3. `GET /members` exposes `can_remove` plus `remove_effect`, not separate archive/delete actions.

### 6.3 Implement `POST /members`

Implementation steps:

1. Require request fields:
   - `name`;
   - `email`;
   - `capabilities`;
   - `teacher_access_mode` when `teacher` is selected;
   - `subject_ids` only when `teacher` is selected.
2. Reject:
   - `password`;
   - local credential fields;
   - `create_user_account`.
3. Validate name and email presence.
4. Validate at least one capability.
5. Validate teacher access mode rules.
6. Validate same-organization duplicate membership.
7. Validate global account identity conflicts without external account disclosure.
8. For scheduler-only teacher:
   - create or reuse account;
   - create membership with `teacher`;
   - set lifecycle `active`;
   - set access `none`;
   - set teacher access mode `scheduler_only`;
   - create teacher profile and subject links;
   - create scheduler state change when readiness changes;
   - commit and return member view model.
9. For teacher platform, admin-only, or mixed:
   - create access-operation record first;
   - call Clerk synchronously;
   - on Clerk failure, mark operation failed and return modal error without visible row;
   - on Clerk success, create account/membership/profile/invitation state;
   - commit and return member view model;
   - compensate if local commit fails after Clerk success.

Acceptance:

1. Teacher scheduler-only create sends no Clerk invite.
2. Teacher platform create sends Clerk invitation as `org:member`.
3. Admin-only and mixed create send Clerk invitation as `org:admin`.
4. Failed Clerk create leaves the `Equipa` table unchanged.

### 6.4 Implement `PATCH /members/{member_id}`

Implementation steps:

1. Treat all supplied fields as one draft.
2. Allow editing:
   - organization display name;
   - email before access `active`;
   - capabilities;
   - teacher access mode;
   - subject competencies.
3. Block email edit once access status is `active`.
4. Enforce last-active-admin guardrail when admin capability or access changes.
5. Enforce teacher operational-history blockers when removing `teacher`.
6. Enforce sync-error blockers.
7. Trigger synchronous Clerk operations for access and role changes.
8. Commit local state only after required Clerk operation succeeds.
9. Refresh or invalidate frontend session/member state after success.

Acceptance:

1. Draft changes do not apply until `Guardar`.
2. Removing `admin` from mixed member downgrades Clerk role to `org:member` when platform teacher access remains.
3. Removing `teacher` from a mixed member does not remove admin unless explicitly changed.
4. Failed access changes leave the table unchanged and modal open.

### 6.5 Implement Access Action Endpoints

Implementation steps for `POST /members/{id}/resend-invitation`:

1. Allow only for `pending_invite` or `invite_expired`.
2. Use current member email, organization, capabilities, and current admin inviter.
3. For `pending_invite`:
   - persist `resend_invitation` operation with old invitation id;
   - revoke old pending Clerk invitation with current admin as requesting user;
   - if revoke fails and Clerk still reports old invitation pending, leave local membership unchanged and return safe error;
   - if revoke succeeds, mark old invitation revoked in operation;
   - create new invitation;
   - on success, store new invitation id/status and keep `pending_invite`;
   - on create failure after successful revoke, set `access_status = invite_expired`, set old invitation status `revoked`, clear usable pending invitation, and return safe retry/support error.
4. For `invite_expired`:
   - persist operation;
   - create new invitation;
   - on success, store new invitation id/status and set `pending_invite`;
   - on failure, keep `invite_expired`.

Implementation steps for `POST /members/{id}/retry-sync`:

1. Allow only for `sync_error`.
2. Attempt safe reconciliation from stored operation state and Clerk identifiers.
3. Return normal state on success.
4. Leave support-required state and block risky edits if unresolved.

Implementation steps for `POST /members/{id}/remove`:

1. Check operational-history blockers.
2. Check last-active-admin guardrail.
3. If no blockers and no accepted/past access history:
   - revoke pending invitation if present;
   - hard delete local setup records.
4. If blockers or accepted/past access exist:
   - revoke pending invitation or active Clerk membership first;
   - archive membership;
   - set accepted/past-access final access to `blocked`;
   - preserve account, membership, teacher profile, and history.
5. Use one backend action, not separate delete/archive endpoints.

Implementation steps for `POST /members/{id}/restore`:

1. Treat restore as a saved modal action.
2. Restore scheduler-only teacher to lifecycle `active`, access `none`.
3. Restore teacher platform member only if Clerk access is started/restored in same save, or if admin chooses scheduler-only mode.
4. Restore admin-capable member only if Clerk access is started/restored in same save, or if admin removes `admin` during restore and guardrails pass.

Acceptance:

1. Resend never creates duplicate members or memberships.
2. Resend cannot leave a revoked old invitation displayed as `Convite pendente`.
3. Remove/archive revokes relevant Clerk access before preserving local history.
4. Restore covers scheduler-only, teacher platform, admin-only, and mixed members.

### 6.6 Implement `GET /members/me`

Implementation steps:

1. Return current account id.
2. Return current organization membership id.
3. Return capabilities.
4. Return access status.
5. Return lifecycle status.
6. Return teacher profile id when present.
7. Return default experience:
   - `admin` for admin-only and mixed;
   - `teacher` for teacher-only.
8. Return whether sidebar mode switcher is available.

Acceptance:

1. Frontend product navigation and mode switching use this endpoint.
2. Frontend does not infer product capability only from Clerk `membership.role`.

### 6.7 Implement Stable Error Contract

Implementation steps:

1. Return this shape for `/members` errors:

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

2. Use status codes:
   - `400` for syntactically valid impossible actions;
   - `401` for unauthenticated;
   - `403` for authenticated but missing local capability, active access, lifecycle, or tenant permission;
   - `404` for not found in current organization;
   - `409` for guardrail or state conflict;
   - `422` for field validation errors;
   - `424` for required Clerk access operation failure after local validation;
   - `502` or `503` for Clerk/service dependency unavailable before safe local decision.
3. Implement error codes:
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

Acceptance:

1. Frontend branches only on `message`, `fields`, `retryable`, and `support_required`.
2. Frontend does not branch on raw Clerk provider responses.

## 7. WBS 5 - Save Semantics And Clerk Operation Flows

### 7.1 Scheduler-Only Teacher Create Flow

Implementation steps:

1. Validate active admin and current organization.
2. Normalize email.
3. Create or reuse account by email.
4. Create membership:
   - capability `teacher`;
   - lifecycle `active`;
   - access `none`;
   - teacher access mode `scheduler_only`;
   - expected Clerk role null.
5. Create teacher profile.
6. Create subject links.
7. Record scheduler state change if required by existing scheduler readiness behavior.
8. Commit once.
9. Return member view model.

Acceptance:

1. No Clerk invitation is created.
2. Member appears in `Equipa` with `Sem acesso`.
3. Teacher is usable by scheduling workflows.

### 7.2 Platform-Access Create Flow

Implementation steps:

1. Validate active admin, organization, draft, guardrails, and Clerk org id.
2. Normalize email.
3. Compute intended capabilities.
4. Compute Clerk role.
5. Create and commit access-operation with stable idempotency key and draft payload.
6. Call Clerk synchronously to create organization invitation.
7. On Clerk failure:
   - update operation as `failed`;
   - return safe modal error;
   - do not create visible member row.
8. On Clerk success:
   - create or reuse account;
   - create membership;
   - create teacher profile when applicable;
   - store invitation id/status;
   - attach operation ids;
   - commit.
9. If local commit fails after Clerk success:
   - attempt invitation revocation compensation;
   - if compensation succeeds, mark `compensated`;
   - if compensation fails, mark `support_required`;
   - return safe modal error.

Acceptance:

1. No visible row claims pending or active access unless Clerk side effect succeeded.
2. Compensation failures are trackable and block duplicate access changes.

### 7.3 Edit With Access Or Role Changes

Implementation steps:

1. Validate editable draft and guardrails.
2. Check unresolved operations.
3. Check sync-error blockers.
4. Persist access-operation with previous and intended state.
5. Call Clerk synchronously for:
   - create invitation;
   - revoke invitation;
   - revoke membership;
   - role change;
   - restore access.
6. Commit local state only after required Clerk operation succeeds.
7. Attempt compensation on local commit failure.
8. Refresh or invalidate frontend member/session state after success.

Acceptance:

1. Access revocation is enforced by backend on next request.
2. Role downgrade from mixed/admin to teacher-only maps Clerk role to `org:member` when platform access remains.
3. Failed Clerk operation does not partially apply local draft changes.

### 7.4 Support-Required Recovery Surface

Implementation steps:

1. Add a support-only CLI command or protected admin-only maintenance endpoint.
2. Prefer the CLI surface for launch. If a maintenance endpoint is used, it must be disabled by default and enabled only in the internal operations environment.
3. Define `support-only` as product-owner/operator access, not school-admin access.
4. The support surface must require one of these operator authentication boundaries:
   - local server/console access for CLI execution; or
   - internal service authentication for a maintenance endpoint; or
   - an explicitly configured operator account type that is not available to school organizations.
5. A school admin with `Equipa` admin capability must never be authorized to run support recovery only because they are an organization admin.
6. A maintenance endpoint, if implemented, must not be exposed in the public school-admin router or normal frontend bundle.
7. A maintenance endpoint, if implemented, must require an internal deployment guard such as environment allow-list plus service/operator credential.
8. Every support recovery command must require:
   - target type: `member_access_operation` or `clerk_webhook_event`;
   - target id: `member_access_operation.id`, `clerk_webhook_event.id`, or `clerk_webhook_event.svix_id`;
   - explicit action name;
   - dry-run flag or explicit `--apply`;
   - operator identifier;
   - non-sensitive note or ticket reference.
9. For `member_access_operation`, it must inspect one access operation by id and show safe fields:
   - previous state;
   - intended state;
   - Clerk ids;
   - compensation status;
   - non-sensitive error category/reference.
10. For `clerk_webhook_event`, it must inspect one event by id or `svix_id` and show safe fields:
   - `svix_id`;
   - event type;
   - Clerk object ids;
   - processing status;
   - attempt count;
   - next retry timestamp;
   - safe sanitized payload summary;
   - safe error category.
11. Add dry-run reconciliation against current Clerk state before mutation.
12. Add safe retry for failed compensation or local commit when idempotency keys prove it is safe.
13. Add support actions for access operations:
   - `confirm_already_compensated`;
   - `retry_compensation`;
   - `commit_confirmed_clerk_state`;
   - `force_sync_error`.
14. Add support actions for dead-letter webhook events:
   - `inspect_dead_letter`;
   - `replay_dead_letter`;
   - `mark_dead_letter_ignored`;
   - `mark_dead_letter_sync_error`;
   - `leave_dead_letter_blocked`.
15. `replay_dead_letter` must:
   - use the stored sanitized payload only;
   - re-run the same reconciliation service with normal uniqueness and tenant checks;
   - refuse to run if required payload fields were purged;
   - fail closed when the local target is ambiguous;
   - never create product capabilities from unmatched Clerk state.
16. `mark_dead_letter_ignored` is allowed only when the event is valid but intentionally has no product target.
17. `mark_dead_letter_sync_error` is allowed only when the event maps to a local member/access problem that must remain denied or support-visible.
18. Store for access-operation support actions:
   - `support_resolution_action`;
   - `support_resolved_by_user_id`;
   - `support_resolved_at`;
   - non-sensitive note or ticket reference.
19. For webhook support actions, store equivalent audit data in structured logs or a support audit table:
   - `clerk_webhook_event.id`;
   - `svix_id`;
   - operator id;
   - action;
   - dry-run/apply mode;
   - outcome category;
   - non-sensitive note or ticket reference.
20. Emit a structured audit log for every dry run and every applied support action.
21. The audit log must include operation/event id, operator id, action, dry-run/apply mode, organization id when known, membership id when known, and non-sensitive outcome category.

Acceptance:

1. Support recovery never creates product capabilities from unmatched Clerk state.
2. Support recovery enforces last-active-admin guardrail unless explicit emergency bootstrap is documented in migration runbook.
3. After resolution, new duplicate create/resend/retry operations are allowed only when no unresolved operation remains.
4. School admins cannot invoke support recovery through the `Equipa` UI, normal API token, or organization admin capability.
5. Applied support actions are auditable without exposing passwords, raw tokens, secrets, raw provider responses, or cross-organization account existence.
6. `dead_letter` webhook events can be inspected, replayed, marked ignored, marked sync-error, or intentionally left blocked through support-only tooling.
7. Webhook dead-letter replay uses the same conservative matching rules as normal webhook processing.

## 8. WBS 6 - Clerk Webhooks And Reconciliation

### 8.0 Webhook Operational Setup

Implementation steps:

1. Register the public Clerk webhook endpoint as `/api/v1/webhooks/clerk`.
2. Ensure the route is reachable by Clerk without a user session.
3. Exempt the route from normal Clerk user-auth dependencies while still requiring Svix signature verification.
4. Do not exempt the route from request size limits, JSON parsing safety, structured logging, or rate/abuse protections that do not break Clerk delivery.
5. Configure per-environment webhook secret storage:
   - local development secret;
   - staging secret;
   - production secret.
6. Define runtime configuration keys:
   - `CLERK_WEBHOOK_ENABLED`;
   - `CLERK_WEBHOOK_SIGNING_SECRET`;
   - `WEBHOOK_PROCESSING_TIMEOUT_SECONDS`;
   - `WEBHOOK_MAX_ATTEMPTS`.
7. Store webhook secrets only in environment/secret management, never in source code or docs with real values.
8. Configure the Clerk dashboard webhook endpoint for each deployed environment that should receive real events.
9. Subscribe the endpoint to these event families:
   - organization membership events;
   - organization invitation events;
   - user events;
   - organization events.
10. Add a startup/configuration check that fails webhook handling closed when `CLERK_WEBHOOK_ENABLED = true` and `CLERK_WEBHOOK_SIGNING_SECRET` is missing.
11. Add a secret rotation procedure:
   - configure new secret in runtime;
   - deploy/restart with new secret;
   - update Clerk dashboard endpoint secret;
   - send a test event;
   - remove old secret only after test success.
12. Add a safe test-event procedure for local/staging that verifies signature, idempotency row creation, and terminal processing.
13. Document the environment names and endpoint URLs in deployment notes without including real secrets.

Acceptance:

1. `/api/v1/webhooks/clerk` is public to Clerk delivery but not usable without a valid Svix signature.
2. The route does not require an authenticated school user.
3. Missing webhook secret prevents unsafe processing and does not grant access.
4. Staging and production Clerk dashboard endpoint configuration is explicitly tracked before launch.

### 8.1 Webhook Verification And Idempotency

Implementation steps:

1. Verify Svix headers and signature.
2. Reject invalid signatures.
3. Start a database transaction before applying side effects.
4. Use this insert-or-lock pattern for `svix_id`:
   - attempt to insert a new `clerk_webhook_event` row with status `processing`, `attempt_count = 1`, and sanitized payload;
   - if insert succeeds, the handler owns processing for that event;
   - if insert conflicts on `svix_id`, select the existing row `FOR UPDATE`;
   - if the locked row is terminal, commit and return the terminal-safe response;
   - if the locked row is `received`, `retryable_failed`, or stale `processing`, update it to `processing`, increment `attempt_count`, store `last_attempt_at`, and process it;
   - if the locked row is fresh `processing`, do not apply side effects twice; return a retryable non-`2xx` response so Clerk/Svix can redeliver later.
5. Apply webhook side effects only while the event row is owned by the current transaction.
6. Commit event and local side effects together as `processed`, `ignored`, or `sync_error`.
7. Return `2xx` for terminal safe states.
8. Return non-`2xx` for transient dependency/database failures after recording `retryable_failed` when possible.
9. Reprocess duplicate delivery when existing row is `received`, stale `processing`, or `retryable_failed`.
10. Skip duplicate delivery only when existing row is terminal.

Acceptance:

1. Duplicate `svix-id` terminal rows are idempotent.
2. Duplicate retryable rows are reprocessed safely.
3. Repeated webhooks do not create duplicates.

### 8.1A Webhook Retry And Dead-Letter State Machine

Implementation steps:

1. Configure `WEBHOOK_PROCESSING_TIMEOUT_SECONDS = 300` for launch.
2. Configure `WEBHOOK_MAX_ATTEMPTS = 5` for launch.
3. Configure retry backoff by attempt:
   - after attempt 1 failure: `next_retry_at = now + 60 seconds`;
   - after attempt 2 failure: `next_retry_at = now + 300 seconds`;
   - after attempt 3 failure: `next_retry_at = now + 900 seconds`;
   - after attempt 4 failure: `next_retry_at = now + 3600 seconds`.
4. Define stale `processing` as `processing_status = processing` and `last_attempt_at` older than `WEBHOOK_PROCESSING_TIMEOUT_SECONDS`.
5. On transient provider, database, or lock failure:
   - set status `retryable_failed` when `attempt_count < WEBHOOK_MAX_ATTEMPTS`;
   - set `next_retry_at` from the backoff schedule;
   - return non-`2xx` so Clerk/Svix can retry.
6. When a retryable event reaches `attempt_count >= WEBHOOK_MAX_ATTEMPTS`:
   - set status `dead_letter`;
   - set `processed_at`;
   - store safe error category;
   - emit structured log and metric;
   - return `2xx` for that delivery because automatic processing is exhausted.
7. Scheduled reconciliation may reprocess `retryable_failed` rows whose `next_retry_at <= now`.
8. Scheduled reconciliation may identify stale `processing` rows and move them to retry processing.
9. Scheduled reconciliation must not mutate `dead_letter` rows except through explicit support recovery.
10. `sync_error` is terminal for that exact event delivery, but the affected member may later be repaired through retry-sync or support recovery.

Acceptance:

1. Processing timeout, max attempts, retry backoff, and dead-letter transition are configured and tested.
2. `dead_letter` rows are visible in logs/metrics and require support inspection.
3. Retry processing never applies side effects twice for the same terminal event.

### 8.2 Handle Required Clerk Events

Implementation steps:

1. Handle `organizationMembership.created`.
2. Handle `organizationMembership.updated`.
3. Handle `organizationMembership.deleted`.
4. Handle `organizationInvitation.created`.
5. Handle `organizationInvitation.accepted`.
6. Handle `organizationInvitation.revoked`.
7. Handle `user.created`.
8. Handle `user.updated`.
9. Handle `user.deleted`.
10. Handle `organization.created`.
11. Handle `organization.updated`.
12. Handle `organization.deleted`.

Acceptance:

1. Invitation events update invitation state and derived access state.
2. Membership events link or update exactly one valid local membership.
3. User events update linked account identity/profile state.
4. Organization deactivation does not hard delete member, teacher, or scheduler history.

### 8.3 Implement Reconciliation Matching Order

Implementation steps for invitation events:

1. Match by stored `clerk_invitation_id`.
2. Validate Clerk organization id against local organization.
3. Update invitation status and derived access status.
4. If accepted, wait for or fetch membership/user identifiers before marking access `active`.

Implementation steps for membership events:

1. Match by stored `clerk_membership_id` when available.
2. Match by `clerk_invitation_id` through invitation/access operation when available.
3. Match by Clerk org id, Clerk user id, verified email, and pending local membership/access-operation record.
4. Validate expected Clerk role against local capabilities.
5. Link account `clerk_user_id` and membership only when target is unique.
6. Mark `active`, `blocked`, or `sync_error` as appropriate.

Implementation steps for user events:

1. Update existing linked account by `clerk_user_id`.
2. If no linked account exists, match only through verified email plus valid pending membership/access-operation context.
3. If Clerk primary verified email collides with another account, do not merge.
4. Mark affected memberships `sync_error` with `identity_conflict`.
5. Do not create orphan product users from `user.created` alone.

Acceptance:

1. Metadata is helpful but not required.
2. No unmatched Clerk membership creates product capabilities.
3. Ambiguous matches fail closed.

### 8.4 Handle External Clerk Drift Conservatively

Implementation steps:

1. Do not create product capabilities from unmatched Clerk memberships.
2. Mark role mismatch as `sync_error`.
3. Mark direct membership removal as `blocked` or `sync_error`.
4. Deny backend authorization for removed/mismatched access.
5. Do not grant admin capability from direct Clerk role upgrade.
6. Do not remove Cronos capability from direct Clerk role downgrade, but block access until reconciled.
7. Do not count blocked, mismatched, pending, archived, sync-error, or no-Clerk-id admin-capable members as active admins.

Acceptance:

1. External Clerk changes do not silently grant Cronos product permissions.
2. Drift states are visible through safe access statuses and logs.

### 8.5 Invitation Expiry Detection

Implementation steps:

1. Store `invitation_expires_at` when Clerk returns expiration timestamp.
2. On `GET /members`, convert pending invitations with `invitation_expires_at <= now()` to `invite_expired` before rendering.
3. When timestamp is missing or pending invite is older than threshold, perform Clerk Backend API lookup before rendering `Convite pendente`.
4. Perform current-state check before `Reenviar convite`.
5. Add scheduled reconciliation at least hourly in production-like environments.
6. Own scheduled reconciliation in the backend runtime, not the frontend.
7. Implement the scheduled task through Celery because the backend already has `backend/app/celery_worker.py` and `beat_schedule`:
   - add a Celery task named `members.reconcile_access_state`;
   - register the task import in the Celery worker configuration;
   - add a Celery Beat entry that runs the task every hour in production-like environments.
8. Add a manual fallback command under `backend/scripts/` named `reconcile_members.py` that runs the same service method once for operations/debugging.
9. The scheduled task and manual fallback must acquire a database lock before work starts:
   - use a named advisory lock such as `member_reconciliation`; or
   - use a single-row job lock table with `SELECT ... FOR UPDATE`.
10. If the lock is already held, the task must exit successfully with a structured `skipped_already_running` log.
11. The scheduled task must check pending invitations older than threshold.
12. The scheduled task must update revoked, expired, or accepted state using Clerk current invitation or membership state.
13. The scheduled task must reprocess eligible `retryable_failed` webhook rows whose `next_retry_at <= now`.
14. The scheduled task must detect stale `processing` webhook rows older than `WEBHOOK_PROCESSING_TIMEOUT_SECONDS`.
15. The scheduled task must emit a summary log and metric counters for:
   - checked pending invitations;
   - invitations marked expired;
   - invitations confirmed pending;
   - invitations accepted;
   - provider-state-unconfirmed cases;
   - retryable webhook rows reprocessed;
   - stale processing rows recovered;
   - dead-letter rows observed.
16. If Clerk is unavailable for scheduled reconciliation:
   - do not convert pending invites to `sync_error` solely because of provider outage;
   - record provider-state-unconfirmed counters and logs;
   - leave rows for next scheduled run or on-read lookup.
17. Ambiguous provider responses become `sync_error` only when local state cannot be safely classified as pending or expired.
18. Provider outage during `GET /members` returns local row with `provider_state = unconfirmed` and disabled resend.

Acceptance:

1. Stale pending invites are not rendered as confirmed pending without a current-state check.
2. Provider outage does not create `sync_error` solely because Clerk is temporarily unavailable.
3. Resend always checks current state before mutating Clerk state.
4. Only one reconciliation task mutates member/webhook state at a time.
5. Reconciliation failures are observable without requiring a support dashboard.

## 9. WBS 7 - First Login And Session Routing

### 9.1 First-Login Synchronous Reconciliation

Implementation steps:

1. Trigger on first authenticated request when local membership is:
   - `pending_invite`;
   - missing `clerk_user_id`;
   - missing `clerk_membership_id`;
   - stale or incomplete.
2. Use session claims to get:
   - Clerk user id `sub`;
   - Clerk organization id;
   - session organization role.
3. Resolve local organization by Clerk organization id.
4. Call Clerk Backend API for current user's organization membership.
5. Match Clerk user to pending local membership by:
   - stored invitation id;
   - access-operation id;
   - verified email;
   - organization id;
   - expected role.
6. Link account `clerk_user_id`.
7. Link membership `clerk_membership_id`.
8. Update invitation status.
9. Set access status `active` only after confirmed Clerk membership.
10. Commit link/update in one local transaction.
11. Return member context for routing.

Required Clerk reads:

1. `GET /v1/organizations/{organization_id}/memberships?user_id[]={clerk_user_id}&limit=2`.
2. Fallback `GET /v1/users/{user_id}` when verified email or primary email id is needed.
3. Fallback `GET /v1/organizations/{organization_id}/memberships?email_address[]={normalized_email}&limit=2` only after the email has been verified on the Clerk user.
4. `GET /v1/organizations/{organization_id}/invitations/{invitation_id}` when a local pending membership stores `clerk_invitation_id`.
5. Optional `GET /v1/users/{user_id}/organization_invitations?status=accepted|pending|revoked|expired` when invitation state is missing locally and the endpoint is available in the installed Clerk SDK/API client.

Required fields to consume:

1. Session claims:
   - Clerk user id `sub`;
   - Clerk organization id;
   - session organization role.
2. Organization membership response:
   - `id`;
   - `role`;
   - `organization.id`;
   - `public_user_data.user_id`;
   - `public_user_data.identifier`;
   - `public_metadata`;
   - `private_metadata`;
   - `created_at`;
   - `updated_at`.
3. Invitation response:
   - `id`;
   - `email_address`;
   - `role`;
   - `organization_id`;
   - `status`;
   - `expires_at`;
   - `inviter_id`;
   - `public_metadata`;
   - `private_metadata`.
4. User response:
   - `id`;
   - `primary_email_address_id`;
   - `email_addresses[].id`;
   - `email_addresses[].email_address`;
   - `email_addresses[].verification.status`.

Matching precedence:

1. `organization_membership.private_metadata.access_operation_id` or `public_metadata.access_operation_id` equals the stored local access-operation id.
2. `organization_membership.private_metadata.membership_id` or `public_metadata.membership_id` equals the local membership id.
3. Stored local `clerk_invitation_id` resolves to an accepted invitation whose metadata, email, role, and organization match the local pending membership.
4. Verified Clerk primary email, Clerk organization id, expected role, and exactly one pending local membership/access operation match.

Acceptance:

1. First login does not depend on webhook delivery.
2. If multiple local targets match, reconciliation fails closed.
3. If Clerk membership exists but no unique local pending membership/operation matches, deny access and mark or log `sync_error`.
4. If Clerk Backend API is unavailable, return `503` with retryable `member_access_provider_failed`.

### 9.2 Role-Based Landing

Implementation steps:

1. After successful session/member resolution, route teacher-only members to teacher experience.
2. Route admin-only members to admin experience.
3. Route mixed members to admin experience by default.
4. Make sidebar mode switcher available for mixed members.
5. Do not add custom `/accept-invite`, welcome, or profile-confirmation flow for launch.
6. Accept Clerk-controlled session setup or organization selection before Cronos routing.

Acceptance:

1. Invited teacher lands in teacher experience once Clerk returns to Cronos.
2. Invited admin lands in admin experience once Clerk returns to Cronos.
3. Invited mixed member lands in admin experience and can switch to teacher mode.

## 10. WBS 8 - Frontend `Equipa`

### 10.1 Routes And Navigation

Implementation steps:

1. Add admin staff-management route `/members`.
2. Label route as `Equipa`.
3. Add primary action `Adicionar Membro`.
4. Remove old visible `/teachers` admin page from launch navigation.
5. Redirect old visible `/teachers` admin page away from launch navigation if the route cannot be deleted immediately.
6. Keep teacher self-service routes:
   - `/my-availability`;
   - `/my-schedules`;
   - `/my-progress`.

Acceptance:

1. Admins navigate to `Equipa` for member management.
2. There is no visible `Novo Professor` launch staff-management action.
3. Teacher self-service navigation remains role-appropriate.

### 10.2 Member Data Hooks

Implementation steps:

1. Add `useMembers(filters)`.
2. Add `useMember(memberId)`.
3. Add `useCurrentMember()`.
4. Add `useCreateMember()`.
5. Add `useUpdateMember()`.
6. Add `useRemoveMember()`.
7. Add `useRestoreMember()`.
8. Add `useResendMemberInvitation()`.
9. Add `useRetryMemberSync()`.
10. Deprecate staff-management use of:
   - `useCreateEntity('teachers')`;
   - `useUpdateEntity('teachers')`;
   - `useDeleteEntity('teachers')`.

Acceptance:

1. `Equipa` sends only `/members` admin mutations.
2. No staff-management mutation calls `/teachers`.

### 10.3 Unified Member Table

Implementation steps:

1. Render one row per member from `GET /members`.
2. Render search by name and email.
3. Render filters by capability.
4. Render filters by access status.
5. Render `Mostrar arquivados`.
6. Hide archived members by default.
7. Render archived rows distinctly when shown.
8. Render capability chips:
   - `Professor`;
   - `Administrador`;
   - both for mixed.
9. Render lifecycle chips:
   - `Ativo`;
   - `Arquivado`.
10. Render access chips:
   - `Sem acesso`;
   - `Convite pendente`;
   - `Convite expirado`;
   - `Com acesso`;
   - `Acesso bloqueado`;
   - `Erro de sincronização`.
11. Render competency summary for teacher-capable members.
12. Render `Sem competências` warning when teacher has no competencies.
13. Render safe status messages for provider-state or sync issues.
14. When only current admin exists, render practical empty state with `Adicionar Membro`.

Acceptance:

1. Mixed member appears once.
2. Table does not derive access labels from local `User.is_active`.
3. Table does not show raw Clerk status labels.
4. Table uses backend action flags.

### 10.4 Transactional Member Modal

Implementation steps:

1. Use one modal for create, edit/details, resend, retry, remove, and restore actions where applicable.
2. Opening the modal creates a draft.
3. Closing, cancelling, or dismissing discards draft.
4. `Guardar` is the only confirmation step.
5. Do not add a second review dialog after `Guardar`.
6. Include organization display name.
7. Include email.
8. Include capability selector:
   - `Professor`;
   - `Administrador`;
   - `Professor + Administrador`.
9. Show teacher access mode when `Professor` selected:
   - `Com acesso a plataforma`;
   - `Apenas recurso de horário`.
10. Add `?` help for scheduler-only teacher mode.
11. The scheduler-only help explains the member is a teacher resource for scheduling, subjects, classes, availability planning, and operational records, but is not invited to sign in or use teacher self-service screens.
12. Show teacher competencies only when `Professor` selected.
13. Show admin-specific access confirmation when `Administrador` selected.
14. Hide teacher fields for admin-only.
15. Remove all password fields.
16. Remove all local account switch/copy tied to `create_user_account`.
17. Use backend field errors for inline validation.
18. Keep modal open on validation errors.
19. Keep modal open on failed Clerk operations.
20. Close modal on successful create/edit/remove/restore.
21. Show short success toast after successful actions.

Acceptance:

1. The modal never asks the admin for another user's password.
2. Draft changes do not leak into the table before save.
3. Failed saves leave table unchanged.

### 10.5 Modal Action Rules

Implementation steps:

1. Show `Reenviar convite` only for `Convite pendente` and `Convite expirado`.
2. Disable resend when `provider_state = unconfirmed`.
3. Show `Tentar novamente` for `Erro de sincronização`.
4. Block risky edits while unresolved sync error remains.
5. Use `remove_effect` to explain whether remove will hard delete or archive.
6. Expose one remove action, not separate delete/archive actions.
7. Show restore action only for archived members where backend allows it.
8. For blocked actions, show a safe product message from backend.

Acceptance:

1. Row actions do not bypass the saved modal flow.
2. Remove modal copy matches backend `remove_effect`.
3. Sync-error state guides retry or support without exposing Clerk internals.

### 10.6 Mixed-Role Mode Switcher

Implementation steps:

1. Use `GET /members/me` for current member capabilities.
2. Show mode switcher only when member has both `teacher` and `admin`.
3. Default mixed members to admin mode.
4. Admin mode shows admin navigation.
5. Teacher mode shows teacher navigation.
6. Switching mode does not sign out.
7. Switching mode does not change Clerk account.
8. Switching mode does not change Clerk organization.
9. Teacher mode must work when Clerk role is `org:admin` and local capability includes `teacher`.

Acceptance:

1. Single-role members do not see the switcher.
2. Mixed member can access both admin and teacher product areas through local capabilities.

### 10.7 Frontend State Refresh

Implementation steps:

1. Invalidate members list after successful member mutations.
2. Invalidate current member state after access or capability changes.
3. Refresh Clerk organization/session/member state where the Clerk client supports it.
4. Handle backend `member_session_refresh_required`.
5. Ensure stale UI cannot keep access because backend authorization is authoritative.

Acceptance:

1. Access/capability changes are reflected immediately after save.
2. Revoked access fails on next API request even if UI was stale.

## 11. WBS 9 - Legacy Cleanup

### 11.1 Remove Or Rewrite Legacy Frontend Staff Management

Implementation steps:

1. Remove `frontend/src/pages/Teachers.jsx` as launch navigation surface.
2. Rewrite or remove `TeacherForm` password state.
3. Rewrite or remove `TeacherForm` `create_user_account` behavior.
4. Remove frontend tests that assert password creation or admin-created account behavior.
5. Remove visible `Professores` admin CRUD navigation.
6. Remove visible `Novo Professor` staff-management action.
7. Remove table labels `Conta Ativa` and `Inativo` for platform access.
8. Replace staff-management create/update/delete calls to teachers endpoints with `/members`.

Acceptance:

1. No visible launch admin staff-management screen depends on old teacher CRUD.
2. No staff-management UI displays access from local `User.is_active`.

### 11.2 Remove Or Rewrite Legacy Backend Staff Management

Implementation steps:

1. Remove admin create/update/delete from `/api/v1/teachers`.
2. Keep `/teachers/me/...` self-service endpoints.
3. Keep teacher-domain read endpoints needed by scheduler/resource workflows.
4. Remove `TeacherCreate.create_user_account` and `TeacherUpdate.create_user_account` from canonical member APIs.
5. Remove teacher creation calls that create local login stubs with `clerk_user_id = null`.
6. Remove best-effort Clerk invitation behavior that logs failure but still commits misleading access.
7. Rewrite auth code that mutates local product role from Clerk token role as source of product permissions.

Acceptance:

1. `/api/v1/teachers` is not the canonical admin staff-management CRUD.
2. Teacher self-service and scheduler-domain operations remain functional.

### 11.3 Documentation Cleanup

Implementation steps:

1. Update docs touched by this implementation to use `Equipa` for visible staff-management area.
2. Update docs touched by this implementation to use `/members` for admin member API.
3. Use `teachers` only for:
   - teacher self-service;
   - teacher profile;
   - scheduler/domain behavior;
   - historical context.
4. Mark historical documents explicitly when they describe old `/teachers` admin CRUD, password setup, or local active teacher users and are intentionally retained as history.

Acceptance:

1. New or updated launch docs do not present `/teachers` admin CRUD as current launch behavior.
2. New or updated launch docs do not present password setup by admins as current launch behavior.

## 12. WBS 10 - Observability

### 12.1 Structured Logs

Implementation steps:

Add structured log events for:

1. Member create requested.
2. Member created.
3. Teacher profile created.
4. Member invite requested.
5. Access-operation created.
6. Clerk invitation created.
7. Clerk invitation failed.
8. Clerk side-effect compensation succeeded.
9. Clerk side-effect compensation failed.
10. Support-required operation resolved.
11. Support-required operation still blocked.
12. Webhook linked account/membership/teacher profile.
13. Webhook ignored due to invalid or missing reconciliation context.
14. Webhook retryable failure.
15. Stale webhook processing recovery.
16. Webhook dead-letter transition.
17. Access blocked or deactivated.
18. Sync error created.
19. Identity conflict detected.
20. Provider state unconfirmed during invitation expiry lookup.
21. Sync retry attempted.
22. Sync retry resolved.
23. Sync retry unresolved.
24. Last-active-admin guardrail blocked an action.

Safe identifiers to include when available:

1. Organization id.
2. Account id.
3. Membership id.
4. Teacher profile id.
5. Access-operation id.
6. Clerk user id.
7. Clerk organization id.
8. Clerk invitation id.
9. Clerk membership id.
10. Event type.
11. Non-sensitive error category.

Acceptance:

1. Logs do not include passwords, tokens, secrets, stack traces in user-facing data, or cross-organization account information.
2. Every failed Clerk side effect can be correlated to an access-operation id.

### 12.2 Counter-Ready Metrics

Implementation steps:

Expose or record counter-ready signals for:

1. Invite success count.
2. Invite failure count.
3. Pending invites older than threshold.
4. Webhook link success count.
5. Webhook retryable failure count.
6. Webhook dead-letter count.
7. Webhook sync-error count.
8. Identity-conflict count.
9. Provider-state-unconfirmed count.
10. Support-required access-operation count.
11. Login failures caused by missing teacher profile for local `teacher` capability.

Acceptance:

1. Metrics can be queried or derived in production-like environments.
2. No dedicated support dashboard is required for launch.

## 13. WBS 11 - Backend Tests

### 13.1 Service Tests

Required tests:

1. Create teacher-only scheduler resource.
2. Create teacher-only platform member.
3. Create admin-only member.
4. Create mixed member.
5. Migrate/bootstrap existing active admin into account plus membership without relying on legacy `user.role`.
6. Migration dry-run reports organizations, admin candidates, zero-admin blockers, duplicate emails, duplicate Clerk ids, teacher link plan, local stubs, pending invite verification needs, and support-required rows without writing data.
7. Migration aborts before writes when legacy admin teacher writes are still enabled.
8. Migration aborts before writes when auth/RLS replacement tests fail.
9. Migration aborts before writes when an organization would have zero verified active admins.
10. Migration aborts before writes when Clerk Organizations are not enabled or `org:admin`/`org:member` cannot be verified.
11. Cutover test proves old and new app versions cannot serve concurrently during auth/RLS migration.
12. Cutover test proves staff-management writes remain disabled until post-cutover verification passes.
13. Replace auth/RLS helper behavior for account, membership, capability, and tenant context resolution.
14. Edit name.
15. Edit email before active access.
16. Edit capabilities.
17. Edit access mode.
18. Edit competencies.
19. Remove `teacher` capability with no blockers.
20. Block removing `teacher` capability with blockers.
21. Cover every operational-history blocker listed in WBS 5.3.
22. Remove `admin` capability with last-active-admin guardrail.
23. Block unsafe self-edit actions.
24. Hard delete when eligible.
25. Archive when `remove_effect = archive`.
26. Remove active accepted member revokes Clerk organization membership before archive.
27. Remove pending member revokes Clerk invitation with current admin as `requesting_user_id`.
28. Restore scheduler-only archived member.
29. Restore teacher-only platform archived member.
30. Restore admin-only archived member.
31. Restore mixed archived member.
32. Resend pending invitation.
33. Resend expired invitation.
34. Resend revoke-success/create-failure stores `invite_expired`.
35. Resend revoke calls include current admin as `requesting_user_id`.
36. Clerk `429` on invite create returns retryable safe error and creates no visible pending row.
37. Clerk `429` on resend after old invite remains pending leaves local invitation unchanged.
38. Clerk `429` on resend after old invite was revoked records honest expired/retry state without showing stale pending access.
39. Support retry respects stored rate-limit retry timing unless operator uses explicit override.
40. Invitation expiry by timestamp.
41. Invitation expiry by on-read Clerk lookup.
42. Invitation expiry by scheduled reconciliation.
43. Scheduled reconciliation lock prevents two concurrent mutators.
44. Scheduled reconciliation provider outage leaves pending rows for retry and emits provider-state-unconfirmed logs/counters.
45. Provider outage during expiry lookup returns `member_provider_state_unconfirmed`, disables resend, and does not mark `sync_error`.
46. Duplicate normalized email conflict.
47. Conflicting `clerk_user_id` identity conflict.
48. Clerk primary email collision identity conflict.
49. Support-required operation recovery through launch CLI or maintenance endpoint.
50. Support-required recovery denies school-admin organization tokens.
51. Support-required recovery audit log records operator id, dry-run/apply mode, operation id, action, and outcome category.
52. Webhook dead-letter support inspection by `clerk_webhook_event.id` or `svix_id`.
53. Webhook dead-letter replay refuses to run after required sanitized payload fields are purged.
54. Webhook dead-letter replay fails closed on ambiguous local target.
55. Retry sync errors.
56. No active access without `clerk_user_id`.
57. No duplicate account, membership, or teacher profile on retry.

Acceptance:

1. All required service tests pass.
2. Tests do not depend on legacy `user.role` or `User.is_active` for launch authorization.

### 13.2 API Contract Tests

Required tests:

1. `/members` list view model contains every field needed by `Equipa`.
2. `/members` list response has top-level `total` outside `items`.
3. `/members` item shape does not contain per-row `total`.
4. `POST /members` rejects `password`.
5. `POST /members` rejects `create_user_account`.
6. `POST /members` validates teacher access mode.
7. `POST /members` does not leak external account existence.
8. `/members` errors follow stable envelope.
9. `/members` errors follow status-code policy.
10. `/members` validation errors populate `fields`.
11. Clerk failure keeps modal-save response failed and visible table unchanged.
12. Resend failure after old invite revocation returns `invite_expired`.
13. Invitation expiry lookup outage returns `provider_state = unconfirmed` and disables resend.
14. `GET /members` exposes one removal action via `can_remove` plus `remove_effect`.
15. `GET /members` does not expose separate `can_archive`.
16. Action flags reflect backend guardrails.
17. Teacher-only members cannot access `Equipa`.
18. Admin-capable members can access `Equipa`.
19. Mixed-role members can access admin and teacher product areas through local capabilities.
20. Legacy admin `POST/PATCH/DELETE /api/v1/teachers` staff-management routes are removed and fail closed with `404/405`.
21. Clerk `429` create/invite response returns stable error envelope with `retryable = true`, safe message, and no raw provider body.
22. Clerk `429` resend response returns stable error envelope and does not expose external account state.

Acceptance:

1. API tests prove frontend can be built without guessing member state.
2. API tests prove no password or local credential semantics remain in `/members`.

### 13.3 Webhook Tests

Required tests:

1. Svix signature rejection.
2. Missing webhook secret fails closed in webhook-enabled environment.
3. Webhook route does not require user auth but does require valid Svix signature.
4. Insert-or-lock pattern inserts a new `processing` row for first delivery.
5. Insert-or-lock pattern locks existing row on duplicate `svix_id`.
6. Duplicate `svix-id` terminal row idempotency.
7. Duplicate `svix-id` reprocessing for `received`.
8. Duplicate `svix-id` reprocessing for stale `processing`.
9. Duplicate `svix-id` reprocessing for `retryable_failed`.
10. Fresh `processing` duplicate does not apply side effects twice and returns retryable non-`2xx`.
11. Retryable webhook failure returns non-`2xx` and later duplicate delivery reprocesses.
12. Retry backoff sets `next_retry_at` according to configured attempt schedule.
13. Attempt count reaching `WEBHOOK_MAX_ATTEMPTS` transitions to `dead_letter`.
14. `dead_letter` is observable and not automatically mutated without support recovery.
15. Sanitized payload retains only the allow-listed fields needed for retry/reconciliation.
16. Sanitized payload redacts or drops images, phone numbers, session data, IP addresses, user agents, unrecognized metadata, tokens, and raw provider bodies.
17. Sanitized payload retention reduces or purges old processed payloads according to the WBS retention rule.
18. `dead_letter` support action `inspect_dead_letter`.
19. `dead_letter` support action `replay_dead_letter`.
20. `dead_letter` support action `mark_dead_letter_ignored`.
21. `dead_letter` support action `mark_dead_letter_sync_error`.
22. `organizationInvitation.created`.
23. `organizationInvitation.accepted`.
24. `organizationInvitation.revoked`.
25. `organizationMembership.created`.
26. `organizationMembership.updated`.
27. `organizationMembership.deleted`.
28. `user.created`.
29. `user.updated`.
30. `user.deleted`.
31. Membership event without invitation metadata reconciles safely when local records uniquely match.
32. First-login reconciliation uses the exact Clerk Backend API paths, fields, and matching precedence listed in WBS 9.1.
33. Unmatched membership does not create product capabilities.
34. Role mismatch becomes `sync_error`.
35. Primary email collision becomes identity-conflict `sync_error`.
36. Stale session role mismatch does not become `sync_error` until Backend API confirms real drift.
37. Direct membership removal becomes blocked or sync-error.
38. Repeated webhooks do not create duplicates.

Acceptance:

1. Webhook handling is verified, idempotent, retry-aware, and conservative.
2. Webhooks cannot grant access without unique local reconciliation target.

### 13.4 Auth And Tenant Isolation Tests

Required tests:

1. Active admin can access `/members`.
2. Teacher-only member cannot access `/members`.
3. Admin-capable pending invite does not count as active admin.
4. Admin-capable expired invite does not count as active admin.
5. Admin-capable blocked member does not count as active admin.
6. Admin-capable archived member does not count as active admin.
7. Admin-capable sync-error member does not count as active admin.
8. Admin-capable no-Clerk-id member does not count as active admin.
9. Mixed-role member can access teacher features with Clerk `org:admin`.
10. Revoked access denied on next request.
11. Signed-in user with no active Clerk organization context is denied product access.
12. Membership optional mode, if configured, still cannot enter product routes without active organization context.
13. Cross-tenant account read denied.
14. Cross-tenant membership read denied.
15. Cross-tenant teacher profile read denied.
16. Cross-tenant schedule read denied.
17. Cross-tenant audit read denied.

Acceptance:

1. Replacing auth helpers does not weaken tenant isolation.
2. Backend remains authoritative over stale frontend state.

## 14. WBS 12 - Frontend Tests

Required tests:

1. `Equipa` route appears for active admin.
2. Old visible `Professores` admin CRUD route is absent from launch navigation.
3. `Equipa` table renders lifecycle chips.
4. `Equipa` table renders access chips.
5. Member modal has no password field.
6. Teacher-only scheduler creation sends no access operation intent.
7. Teacher platform creation sends access intent.
8. Admin-only creation requires platform access.
9. Mixed creation requires platform access.
10. Teacher fields hide for admin-only members.
11. Admin-specific confirmation appears for admin capability.
12. Scheduler-only `?` help appears and explains no sign-in access in product terms.
13. Modal draft discards on cancel.
14. Modal draft discards on close.
15. Failed validation keeps modal open.
16. Failed Clerk save keeps modal open.
17. Successful save closes modal and shows toast.
18. `Reenviar convite` visible only for pending/expired invites.
19. Resend disabled when provider state is unconfirmed.
20. Remove modal uses one action and explains hard delete vs archive from `remove_effect`.
21. `Erro de sincronização` shows retry.
22. `Erro de sincronização` blocks risky edits.
23. Mixed-role mode switcher appears only for mixed members.
24. Mixed-role mode switcher changes visible navigation without signing out.
25. Frontend uses `/members/me` for mode availability.

Acceptance:

1. Frontend tests do not assert admin-created passwords.
2. Frontend tests do not assert local `User.is_active` access labels.

## 15. WBS 13 - End-To-End Validation

Required flows:

1. Admin creates scheduler-only teacher and sees `Sem acesso`.
2. Scheduler-only teacher appears as scheduling resource.
3. Scheduler-only teacher cannot sign in through Cronos as active platform member.
4. Admin creates teacher with platform access and sees `Convite pendente`.
5. Invited teacher accepts through Clerk default flow.
6. Invited teacher lands in teacher experience after Clerk returns to Cronos.
7. Invited teacher first login succeeds when Clerk webhooks are delayed but Backend API lookup succeeds.
8. Invited teacher can access `/my-availability`.
9. Invited teacher can access `/my-schedules`.
10. Invited teacher can access `/my-progress`.
11. Teacher-only member cannot access `Equipa`.
12. Admin creates admin-only member.
13. Invited admin accepts through Clerk default flow.
14. Invited admin can access `Equipa`.
15. Admin creates mixed member.
16. Invited mixed member accepts through Clerk default flow.
17. Invited mixed member lands in admin experience.
18. Invited mixed member switches to teacher mode.
19. Mixed member can access teacher features while Clerk role is `org:admin`.
20. Admin revokes teacher access and backend denies next teacher API request.
21. Admin attempts last-active-admin destructive action and receives blocked explanation.
22. Admin removes unused setup member and hard delete occurs only when eligible.
23. Admin removes historical member and archive occurs.
24. Admin restores scheduler-only archived teacher.
25. Admin restores admin-capable archived member only with access operation or admin capability removal.

Acceptance:

1. E2E coverage proves all launch member types:
   - `Professor`;
   - `Administrador`;
   - `Professor + Administrador`.
2. E2E coverage proves Clerk default invitation acceptance is enough for launch.
3. E2E coverage proves backend access revocation is immediate.

## 16. WBS 14 - Final Legacy Deletion Gate

Run this gate after backend, frontend, tests, and E2E validation pass.

### 16.1 Required Repo Search Gate

Search for these legacy strings and resolve every launch-scope hit:

1. `Novo Professor`.
2. `create_user_account`.
3. `Password de Acesso`.
4. `Conta Ativa`.
5. `User.is_active`.
6. `clerk_user_id = null`.
7. `clerk_user_id=None`.
8. Admin `POST /api/v1/teachers`.
9. Admin `PATCH /api/v1/teachers`.
10. Admin `DELETE /api/v1/teachers`.
11. `useCreateEntity('teachers')` in staff management.
12. `useUpdateEntity('teachers')` in staff management.
13. `useDeleteEntity('teachers')` in staff management.
14. Role guards that assume `org:member` is the only teacher product role.
15. Role guards that block teacher features solely because Clerk role is `org:admin`.

Acceptance:

1. Every remaining hit is either removed, rewritten, or documented as valid teacher self-service/scheduler/domain/historical context.
2. No launch staff-management behavior uses the legacy hits.

### 16.2 Documentation Index Gate

Implementation steps:

1. Ensure product strategy index links this WBS.
2. Ensure root documentation index identifies PRD, tech spec, and this WBS as the implementation baseline.
3. Ensure candidate-delete documentation lists legacy cleanup targets if they still exist.

Acceptance:

1. A junior implementer can find PRD, tech spec, and WBS from the documentation index.
2. Documentation does not point implementers to the older professor/access WBS as the Clerk member-management implementation plan.

## 17. Launch Definition Of Done

Launch is blocked unless all items below are true:

1. `Equipa` replaces visible `Professores` admin CRUD.
2. `/members` is the canonical admin staff-management API.
3. No member create/edit UI asks for a password.
4. No canonical member create/update schema accepts `create_user_account`.
5. Clerk Organizations are enabled in every launch Clerk instance.
6. Clerk membership mode and active organization behavior are verified against the organization-scoped product baseline.
7. Clerk roles `org:admin` and `org:member` exist and are usable for launch invitations.
8. Legacy admin `/api/v1/teachers` create/update/delete staff-management writes are quarantined before or in the same cutover as the global-account migration.
9. Migration dry-run report passes before real migration writes.
10. Database backup/snapshot id is recorded before cutover.
11. Persistent shared environments use maintenance/single-version cutover; old and new auth/RLS app versions do not serve concurrently.
12. Staff-management writes are disabled during cutover until post-cutover verification passes.
13. Membership schema, account semantics migration, admin bootstrap, legacy write quarantine, and auth/RLS replacement ship as one atomic cutover unit.
14. Existing active admins are migrated into verified account plus organization membership records before teacher/member cutover completes.
15. RLS/auth helpers are replaced so `user.organization_id`, `role`, `teacher_id`, and `is_active` no longer drive launch authorization.
16. Scheduler-only teachers can be created with access `none`.
17. Platform-access teachers are invited through Clerk as `org:member`.
18. Admin-only and mixed members are invited through Clerk as `org:admin`.
19. Normal invitations use the current authenticated admin's Clerk user id as inviter.
20. Normal invitation revokes use the current authenticated admin's Clerk user id as `requesting_user_id`.
21. Clerk `429` responses are handled as retryable transient failures without persisting misleading access.
22. `GET /members` returns top-level `total`, not per-row `total`.
23. First login after Clerk invitation acceptance works when webhooks are delayed.
24. First-login reconciliation uses the exact Clerk Backend API paths, response fields, and matching precedence listed in WBS 9.1.
25. Webhook endpoint is public to Clerk delivery, exempt from user auth, protected by Svix signature verification, and configured per environment.
26. Webhook payload storage is sanitized by allow-list, redacts unsupported fields, and has retention/purge behavior.
27. Webhook retry processing has configured processing timeout, max attempts, backoff, and dead-letter transition.
28. Webhook insert-or-lock handling prevents duplicate side effects for new and duplicate `svix_id` deliveries.
29. Dead-letter webhook events have support-only inspect, replay, ignore, sync-error, and leave-blocked actions.
30. Scheduled reconciliation has a backend owner/runtime, single-run lock, logs/metrics, and safe provider-outage behavior.
31. Invitation expiry is detected before rendering stale pending states.
32. Invitation expiry is detected before resending.
33. Provider outages use `member_provider_state_unconfirmed`.
34. Resend invitation cannot leave a revoked old invitation displayed as `Convite pendente`.
35. Remove/archive flows revoke applicable pending invitation or active Clerk organization membership before preserving local history.
36. Restore covers scheduler-only, teacher-only platform, admin-only, and mixed archived members.
37. Invitation/access failures are visible.
38. Invitation/access failures do not persist misleading access.
39. Clerk side effects have durable access-operation records.
40. Clerk side effects have compensation/support-required handling.
41. Support-required operations have documented CLI or protected maintenance recovery.
42. Support recovery is not invokable by school admins through organization admin capability.
43. Support recovery actions are audited with operator id, dry-run/apply mode, operation or webhook event id, action, and non-sensitive outcome.
44. Webhook reconciliation is verified, idempotent, retry-aware, and conservative.
45. Identity conflicts are detected.
46. Identity conflicts do not silently merge different Clerk users.
47. Backend authorization uses local membership capabilities and access state.
48. Session role mismatch handles stale tokens before persisting `sync_error`.
49. Mixed-role members can access teacher features even when Clerk role is `org:admin`.
50. Last-active-admin guardrail is enforced.
51. Old visible `/teachers` admin CRUD is removed from launch navigation and canonical API use.
52. Required backend service tests pass.
53. Required API contract tests pass.
54. Required webhook tests pass.
55. Required frontend tests pass.
56. Required E2E tests for teacher-only, admin-only, and mixed-role members pass.

## 18. Junior Implementation Checklist

Follow this order exactly:

1. Inventory legacy staff-management code.
2. Confirm Clerk Backend API support for inviter, revoker, invitations, membership revoke, role change, and reconciliation reads.
3. Verify Clerk Organizations are enabled, membership mode is correct, active organization behavior works, and `org:admin`/`org:member` exist.
4. Quarantine legacy admin teacher write paths so they fail closed.
5. Build migration dry-run report and cutover failure checks.
6. Prepare maintenance/single-version cutover steps for persistent shared environments.
7. Add schema migrations.
8. Add migration/bootstrap logic for active admins and existing teacher resources.
9. Replace auth/RLS helpers in the same cutover unit as the membership migration.
10. Add service classes.
11. Add `/members` API routes and response schemas.
12. Add Clerk access operations with access-operation ledger, including Clerk `429` handling.
13. Add webhook operational setup: public route, Svix secret configuration, Clerk dashboard registration, and secret rotation notes.
14. Add webhook payload sanitization and retention/purge behavior.
15. Add webhook insert-or-lock handling, retry/backoff/dead-letter state machine, and reconciliation event handlers.
16. Add scheduled reconciliation with backend runtime ownership, single-run lock, and logs/metrics.
17. Add first-login reconciliation with exact Clerk Backend API reads, fields, and matching precedence.
18. Add support recovery CLI or protected maintenance surface with operator auth, dry-run, audit, school-admin denial, and webhook dead-letter actions.
19. Add backend tests for services, API, webhooks, auth, migration dry-run, support recovery, rate limits, and tenant isolation.
20. Build frontend hooks.
21. Build `/members` `Equipa` route.
22. Build member table.
23. Build transactional member modal.
24. Build mixed-role mode switcher.
25. Replace old visible teacher admin navigation.
26. Delete or rewrite legacy staff-management frontend code.
27. Delete or rewrite legacy staff-management backend code.
28. Update docs touched by the implementation.
29. Run frontend tests.
30. Run backend tests.
31. Run E2E tests.
32. Run final legacy search gate.
33. Compare the result against the launch definition of done.

Do not mark the feature complete if any item in the launch definition of done is false.
