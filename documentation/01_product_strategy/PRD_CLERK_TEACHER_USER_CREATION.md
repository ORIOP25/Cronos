# PRD - Clerk-Backed Equipa Member Management

## 1. Metadata

- Status: closed product baseline after audit corrections; ready for technical specification.
- Feature: integrate Clerk-backed identity, invitations, and organization membership into the `Equipa` staff-management flow, replacing the visible `/teachers` admin CRUD concept.
- Product area: staff management, teacher access, organization membership, authentication.
- Primary user: school admin.
- Secondary users: teachers and admins invited to the platform.
- Owner context: solo developer, pre-launch product in final launch stage.

## 2. Problem

Clerk already owns sign-in, sign-out, organization creation, organization membership, role-based navigation, request authentication, and webhook sync. The teacher creation flow in `/teachers` still creates a local `User` row directly and only attempts a best-effort Clerk organization invitation afterwards.

This leaves the product in an unsafe pre-production state:

- the admin can create a teacher in the UI, but the login/access identity is not guaranteed to exist in Clerk;
- the frontend asks for a password even though the backend ignores it;
- local users can be created with `clerk_user_id = null`;
- Clerk webhooks later create or sync users by real `clerk_user_id`, which can conflict with or bypass the local stub;
- the UI reports account activity from local state, not from a guaranteed Clerk source of truth.

The target behavior is that the admin manages organization members normally from `Equipa`, while Clerk owns identity creation, invitation acceptance, and organization membership. The local database stores only the required application mirror, organization membership state, capabilities, and teacher-domain links.

## 3. Current Behavior Baseline

### 3.1 Admin UX

1. Admin signs in through Clerk.
2. Admin must have the current Clerk organization role `org:admin` to access `/teachers`.
3. Admin clicks `Novo Professor`.
4. Admin fills:
   - `Nome Completo`;
   - `Email de Login`;
   - `Criar conta de acesso?`;
   - `Password de Acesso`, only when account creation is enabled;
   - subject competencies.
5. Frontend sends the form to `POST /api/v1/teachers/`.
6. The table reloads teacher data from `GET /api/v1/import/teachers`.
7. The table shows email plus local status:
   - `Conta Ativa` when local `User.is_active = true`;
   - `Inativo` when no local user exists or `is_active = false`.

### 3.2 Frontend DX

The frontend already uses Clerk for app auth:

- `ClerkProvider` wraps the React app.
- axios receives a Clerk token through `setClerkTokenGetter(getToken)`.
- route guards use `useAuth()` and `useOrganization()`.
- admin-only routes check Clerk membership role `org:admin`.
- teacher-only routes check Clerk membership role `org:member`.

The teacher form is not Clerk-native yet:

- `TeacherForm` keeps `password` in local component state.
- `password` is required in the browser when `create_user_account` is true.
- the backend `TeacherCreate` schema does not define `password`, so Pydantic ignores it.
- no frontend code calls Clerk user creation, Clerk invitations, or Clerk organization membership APIs directly.

### 3.3 Backend DX

`POST /teachers/` currently:

1. authenticates the admin via Clerk token;
2. resolves a local active admin user;
3. creates a local `Teacher`;
4. links selected subjects through `teacher_subject_link`;
5. creates a local `User` whenever an email is present:
   - role `teacher`;
   - `teacher_id` linked to the new teacher;
   - `organization_id` from the current admin;
   - `clerk_user_id = null`;
   - `is_active = create_user_account`;
6. records scheduler state change;
7. if `create_user_account = true` and the organization has a `clerk_org_id`, attempts a Clerk organization invitation with:
   - role `org:member`;
   - email address from the form;
   - public metadata containing `teacher_id`;
8. logs but does not fail the teacher creation if Clerk invitation fails.

Separately, Clerk webhooks already handle:

- organization create/update/delete;
- user create/update/delete;
- organization membership create/update/delete;
- mapping Clerk membership role `member`/`org:member` to app role `teacher`;
- attaching `teacher_id` from Clerk public metadata when present.

The current split means `/teachers` uses local SQL user creation, while auth sync uses Clerk/webhook-driven user creation.

## 4. Goals

1. `Equipa` replaces the visible `Professores`/`/teachers` admin CRUD surface for launch.
2. Admins can create and manage teacher-only, admin-only, and mixed `Professor + Administrador` members from one flow.
3. Clerk is the source of truth for platform login identity, invitation acceptance, and organization membership.
4. The local database stores global account mirrors, organization membership state, local capabilities, and teacher profiles, not independent credentials.
5. Platform-access invitation failures are visible to the admin and do not silently create misleading active access.
6. Scheduler-only teachers remain usable as teaching/scheduling resources without platform sign-in.
7. The implementation is small enough to land safely before first launch.

## 5. Non-Goals

- Building a custom teacher sign-up form.
- Letting admins set teacher passwords directly.
- Supporting student users.
- Bulk member import.
- Billing, checkout, plan gating, or seat-limit enforcement.
- Internal support dashboard, webhook replay UI, or full audit-log UI.
- Replacing the existing Clerk sign-in, sign-up, org creation, route guard, and webhook foundations.

## 6. Target User Experience

### 6.0 Navigation Baseline

The product launch baseline renames the visible `Professores` management area to `Equipa`.

`Equipa` is the source-of-truth admin workspace for managing people in the organization:

- teachers as scheduling and teaching resources;
- teachers with platform access;
- admins with organization management access;
- future staff roles if needed.

The primary creation action is `Adicionar Membro`.

This action opens one unified creation flow for staff members. The flow starts by identifying what kind of member is being added and then reveals the fields required for that member type.

Launch scope is manual member management only. Bulk import is out of scope for this PRD baseline.

`Equipa` shows one unified member table. Each member appears once, even if they have both teacher and admin capabilities. Capabilities and access states are shown as compact chips, and teacher-specific details such as competencies are summarized in the row and managed through edit/details UI.

Teacher competencies are optional at creation but visibly flagged when missing.

`Equipa` separates member lifecycle from platform access.

Lifecycle labels:

- `Ativo`;
- `Arquivado`.

Access labels:

- `Sem acesso`;
- `Convite pendente`;
- `Convite expirado`;
- `Com acesso`;
- `Acesso bloqueado`;
- `Erro de sincronização`.

Failed create/edit saves are not persisted as table states. When a Clerk invitation/access operation fails during `Guardar`, the modal remains open, the table remains unchanged, and the UI shows a clear, non-technical error. The message must not expose sensitive Clerk details, account existence outside the organization, secrets, raw provider responses, or stack traces. Recovery depends on the cause:

- transient/network issue: ask the admin to try again;
- invalid or unreachable email issue: ask the admin to check/edit the email;
- permission/configuration issue: ask the admin to contact support;
- unknown issue: provide a safe retry/support path.

When a member is in `Convite pendente`, admins can resend the invitation from the edit/member details modal.

Member type is modeled as capabilities, not as one mutually exclusive role. The launch capabilities are:

- `Professor`;
- `Administrador`;
- `Professor + Administrador`.

Teacher-specific fields appear only when `Professor` is selected. Admin-specific access confirmation appears when `Administrador` is selected.

Every member requires an email address at creation time, including teacher-only members without platform access. Email remains editable after creation.

Email remains admin-editable before the member has access status `Com acesso`. After a member has accepted access and reached `Com acesso`, email is treated as the user's global identity and is managed by the user through Clerk account management or by support for exceptional cases.

Cronos uses an organization-scoped display name for each member in `Equipa`, schedules, teacher pages, and admin lists. Clerk/account profile names remain identity/account data and do not overwrite the organization-scoped Cronos display name.

When `Professor` is selected, the admin must explicitly choose the teacher access mode:

- `Com acesso a plataforma`;
- `Apenas recurso de horario`.

The `Apenas recurso de horario` option includes a small contextual help control labeled with `?`. When opened, it explains that this member will exist as a teacher resource for scheduling, subjects, classes, availability planning, and operational records, but will not be invited to sign in or use teacher self-service screens.

Teacher access is managed through the create/edit member modal, not through a separate table invite action:

- creating a teacher with `Com acesso a plataforma` sends the Clerk-backed invitation/access flow immediately;
- creating a teacher with `Apenas recurso de horario` does not send an invitation;
- editing a scheduler-only teacher and changing them to `Com acesso a plataforma` sends the Clerk-backed invitation/access flow;
- editing an accessible teacher and changing them to `Apenas recurso de horario` revokes platform access immediately;
- turning access back on later restores access through the Clerk-backed invitation/access flow appropriate to the member's current Clerk state.

Revoking teacher access removes that member's ability to sign in to the organization but preserves the teacher profile and all operational history.

After creation, admins can edit core member fields from `Equipa`: name, email, capabilities, teacher access mode, and teacher competencies. Edits must enforce guardrails for global identity uniqueness, membership uniqueness, last active admin, and Clerk-backed access consistency.

Member editing is transactional. Opening a member modal creates a draft. Changes are applied only when the admin clicks `Guardar`. Closing the modal, clicking `Cancelar`, or dismissing it discards all unsaved changes.

`Guardar` is the confirmation action. The launch baseline does not add a second confirmation/review dialog after `Guardar`. Risky or invalid changes must be blocked or explained before save, and validation errors keep the modal open without applying partial changes.

For launch, Clerk invitation/access operations run synchronously during `Guardar`. This favors implementation speed and immediate admin feedback while the app is small and member changes are manual.

Member saves are all-or-nothing for launch. If a required Clerk access operation fails, the entire save fails and local changes from that draft are not applied.

After a successful create/edit/remove/restore action, the modal closes, the `Equipa` table updates, and the admin sees a short toast confirming the outcome.

When `Equipa` has no members beyond the current admin, the page shows a practical setup empty state with `Adicionar Membro` as the primary action.

Email identifies a global person/account, not a per-organization duplicate identity. Organization access and permissions are represented as memberships scoped to each organization.

When an admin adds or invites an email that already belongs to an existing global account, the UI must not disclose whether the account exists elsewhere. The admin sees only the result for the current organization, using the normal product access statuses.

When `Administrador` is selected, platform access is mandatory. There is no scheduler-only or no-access admin member state.

Creating an admin member whose email does not yet have a Clerk account sends a Clerk organization invitation with role `org:admin`. The invited user defines and manages their own password through Clerk; admins in Cronos never set passwords for other users.

For launch, invited users accept invitations through Clerk's default invitation acceptance/account flow. Cronos does not need a custom `/accept-invite` flow in this PRD baseline.

After accepting a Clerk invitation and signing in for the first time, Cronos must route members to the correct app experience as soon as Clerk returns them to the application:

- teacher-only members land in the teacher experience;
- admin-only members land in the admin experience;
- mixed `Professor + Administrador` members land in the admin experience, with the sidebar mode switcher available for teacher mode.

Under Clerk's default acceptance flow, required Clerk session or organization-selection steps are acceptable before the member reaches Cronos. The launch baseline does not add a separate Cronos welcome screen, profile-confirmation step, or custom invitation acceptance page after invitation acceptance.

For future billing and subscription limits, only members with access status `Com acesso` count as seats. Scheduler-only teachers, pending invites, expired invites, blocked access, sync-error states, and archived members do not count as active seats. Failed create/edit saves do not create seats because they do not persist table changes.

This PRD defines seat-counting policy only. It does not implement billing, checkout, plan gating, or seat-limit enforcement.

Admins can manage other admins from `Equipa`, but the organization must always retain at least one active admin.

Admins can edit their own safe profile fields, but cannot perform self-actions that reduce their current ability to manage the organization.

Removing a member is safe by default. Members with operational-history blockers are deactivated/archived, while unused setup records with no blockers can be hard deleted.

Archived members are hidden from the default `Equipa` table and can be shown with a `Mostrar arquivados` filter.

Archived members can be restored from the archived view through a saved modal action. Restoring a scheduler-only teacher returns the member to the active `Equipa` list with `Sem acesso`. Restoring an admin-capable member must either start/restore the Clerk-backed invite/access flow in the same save or remove `Administrador` during restore when guardrails allow.

Members with both `Professor` and `Administrador` capabilities land in the admin experience by default. They can switch between admin and teacher experiences through an in-app sidebar mode switcher. This switch is not a Clerk account switch and does not require signing out; it only changes the visible navigation and default work area for the same authenticated member.

Access and capability changes take effect immediately at the backend authorization layer. The frontend must invalidate or reload its local session/member state after successful access or capability changes. Stale UI must not grant access because backend authorization remains authoritative.

The old visible `/teachers` admin CRUD is not part of the launch baseline. Any visible copy, navigation, page title, empty state, and documentation must use `Equipa` for the broader staff-management area.

Implementation must introduce a dedicated `Equipa`/members admin surface and API for staff management. Teacher-specific endpoints remain for teacher self-service and scheduler/domain operations.

The user-facing UI label is `Equipa`; the backend/API resource name is `members`.

### 6.1 Create Teacher Without Platform Access

The admin can create a teacher as a scheduling/resource profile without sending an invitation.

Expected UX:

- admin fills name, email, and competencies;
- admin leaves platform access disabled;
- system creates the local global account record, organization membership, and teacher profile;
- the organization membership has `teacher` capability, lifecycle `active`, and access `none`;
- the global account record stores the required email/name but is not an active login identity until linked to Clerk;
- the teacher appears in scheduling workflows;
- the table shows access state `Sem acesso`, not `Inativo` as if a disabled login existed.

### 6.2 Create Teacher With Platform Access

The admin can create a teacher and invite them to the current Clerk organization.

Expected UX:

- admin fills name, email, and competencies;
- admin enables platform access;
- no password field is shown;
- backend creates the teacher profile and sends/creates the Clerk invitation;
- table shows `Convite pendente`;
- when the teacher accepts the invitation, Clerk creates membership and webhook sync links the global account and organization membership to the teacher profile;
- teacher can sign in through Clerk and lands in teacher-only routes.

### 6.3 Failure UX

If Clerk invitation creation fails:

- the admin receives a clear error;
- no local record should claim the teacher has active login access;
- local draft changes from that save are not applied;
- the table remains unchanged;
- the admin can retry invitation after fixing config/network/email issues.

If a Clerk operation succeeds but a later local commit fails, the system must attempt compensating cleanup, such as revoking the just-created Clerk invitation or membership change. The admin still sees the save as failed, the modal remains open, and `Equipa` must not show a member/profile change that was not fully committed.

No Clerk invitation, membership, or role change can be created without a durable local access-operation record that can be used to revoke, retry, or reconcile the Clerk side effect. If compensation also fails, the product must not lose track of the live Clerk side effect: the operation is marked as support-required reconciliation, further access changes for the same organization/email/member are blocked until resolved, and structured logs retain the safe Clerk and local identifiers needed for cleanup.

## 7. Product Requirements

### PR-1 Source Of Truth

Clerk must be the source of truth for authentication identity and current Clerk organization membership. Cronos must be the source of truth for product capabilities, teacher profiles, lifecycle/archive state, scheduler history, and the admin-facing `Equipa` member record.

Acceptance:

- every member who can sign in is linked to a global account with a real Clerk user id;
- local organization membership rows for access are created or completed from Clerk membership/webhook/BAPI sync;
- local-only active login identities are not created.
- Cronos local capabilities do not automatically change when a Clerk role is changed outside Cronos;
- Cronos must not show access status `active` (`Com acesso`) unless the current Clerk organization membership exists and the local membership is valid;
- Clerk/local drift is handled through blocked access or `sync_error`, not by silently importing new product permissions.

### PR-2 Admin Member Creation

The admin must create organization members from `Equipa` through the `Adicionar Membro` flow.

Acceptance:

- the admin can create teacher-only, admin-only, and mixed-role members;
- the admin can create a teacher with name, email, and optional competencies;
- existing scheduling resource behavior remains intact;
- existing teacher subject link behavior remains intact;
- existing tenant isolation remains intact.

### PR-2.1 Manual Member Management Only

Launch scope must use manual `Adicionar Membro` creation and editing only.

Acceptance:

- no CSV/XLSX bulk member import is required for this launch baseline;
- no mass invitation flow is required;
- each member invitation/access change is initiated intentionally by the admin for one member at a time;
- future bulk import must be defined in a separate PRD or extension.

### PR-2A Member Capability Model

`Equipa` must let admins manage members by capability.

Acceptance:

- a member can be created as teacher-only;
- a member can be created as admin-only;
- a member can be created as both teacher and admin;
- teacher-only members can exist with or without platform access;
- admin-capable members always require platform access;
- every member requires an email address;
- teacher-specific fields are hidden unless `Professor` is selected.

Removing `Professor` capability is allowed only when doing so will not break operational history.

### PR-2A.1 Teacher Competencies

Teacher competencies are optional at member creation but must remain visible as scheduler readiness data.

Acceptance:

- a professor can be created without competencies;
- competencies can be added or edited later;
- professor rows without competencies show a visible warning/status such as `Sem competencias`;
- scheduler/preflight readiness can identify teachers without competencies;
- admin-only members do not show competencies.

### PR-2A.2 Removing Professor Capability

Removing `Professor` capability must protect scheduler and historical data.

Acceptance:

- if the teacher profile has no operational-history blockers, removing `Professor` can remove the teacher profile;
- if the teacher profile is linked to schedules, lessons/classes, class assignments, timesheets, absences, audit logs, or other operational records, removing `Professor` is blocked;
- teacher-subject competency links alone do not block removing `Professor` if they have not been used by scheduler/class/lesson/history records;
- when blocked, the UI explains that the member can be archived or access can be disabled instead;
- removing `Professor` from a mixed-role member does not affect their admin capability unless explicitly changed.

### PR-2C Teacher Access Mode

For members with `Professor` capability, platform access must be an explicit required choice.

Acceptance:

- create-member flow requires choosing either `Com acesso a plataforma` or `Apenas recurso de horario`;
- `Com acesso a plataforma` starts the Clerk invitation/access lifecycle;
- `Apenas recurso de horario` creates a teacher scheduling resource without sign-in access;
- the `Apenas recurso de horario` option has a `?` contextual help control;
- the help text explains the practical meaning without requiring knowledge of Clerk or backend concepts.

### PR-2C.1 Teacher Access Changes Happen Through Edit Member

Teacher platform access must be controlled by creating or editing the member, not by a separate row-level invite action.

Acceptance:

- creating a teacher with access sends the Clerk-backed invite/access flow;
- creating a teacher without access sends no invite;
- editing a teacher from no-access to access sends the invite/access flow;
- editing a teacher from access to no-access revokes platform access immediately;
- re-enabling access later works without creating a duplicate teacher or duplicate member;
- the table reflects the resulting access state after each edit.

### PR-2C.2 Teacher Access Revocation

Revoking teacher platform access must preserve the teacher as an operational resource.

Acceptance:

- the teacher can no longer sign in to the organization immediately after revocation;
- if the member has accepted platform access, Cronos removes the member's current Clerk organization membership for that organization;
- if the member only has a pending invitation, Cronos revokes the pending Clerk invitation;
- the local teacher profile remains available for schedules, subjects, classes, timesheets, absences, and history;
- historical records are not deleted;
- the underlying Clerk identity is not deleted as part of normal revocation;
- re-enabling access later creates a fresh Clerk-backed invitation/access flow without duplicate teacher records;
- blocked access means local product access is denied and no current Clerk organization membership or usable pending invitation grants access for that organization.

### PR-2D Admin Access Mode

For members with `Administrador` capability, platform access is mandatory.

Acceptance:

- selecting `Administrador` automatically requires Clerk-backed platform access;
- no UI state allows creating an admin-only member without access;
- if a member is `Professor + Administrador`, admin access requirement wins and the member must be invited to the platform;
- admin-only members do not show teacher-specific scheduling fields.

### PR-2D.0 Admin Invitation Flow

Creating an admin member must use the Clerk organization invitation flow.

Acceptance:

- admin-only members are invited with Clerk role `org:admin`;
- mixed `Professor + Administrador` members are invited with Clerk role `org:admin`;
- Cronos admins never set another user's password;
- invited admins define/sign in with their own Clerk credentials;
- accepted admin invitations create/link the global account and organization membership through Clerk webhook/sync;
- until accepted, the member appears as `Convite pendente`.

### PR-2D.0A Invitation Acceptance Flow

Invitation acceptance must use Clerk's default flow for launch.

Acceptance:

- Cronos creates Clerk organization invitations with the appropriate role;
- Clerk handles account creation/sign-in/password setup during invitation acceptance;
- Cronos does not implement a custom invitation ticket acceptance page for launch;
- after acceptance, Clerk webhook/sync updates Cronos membership state;
- accepted members are routed by Cronos according to their capabilities and default experience rules once Clerk returns them to the app;
- Clerk-required session or organization-selection steps are acceptable before Cronos routing.

### PR-2D.0B Clerk Invitation Policy

Platform-access invitations must follow one explicit Clerk invitation policy for launch.

Acceptance:

- invitations are created for the current Clerk organization only;
- the current authenticated admin is the inviter for human-initiated invitations;
- `inviterUserId` must come from the current authenticated admin's Clerk user id;
- system/null inviter behavior is out of scope for normal `Equipa` member creation;
- invitation role is derived from selected capabilities:
  - teacher-only with platform access uses `org:member`;
  - admin-only uses `org:admin`;
  - mixed `Professor + Administrador` uses `org:admin`;
- Cronos stores the Clerk invitation id and current invitation status on the organization membership;
- recognized invitation statuses are `pending`, `accepted`, `revoked`, and `expired`;
- the product maps those statuses to the separate `access_status` axis;
- invitation metadata contains only safe linking context required for reconciliation, such as local organization id, membership id, and teacher profile id when applicable;
- metadata must not contain secrets, passwords, raw tokens, or sensitive cross-organization information;
- launch uses Clerk's default acceptance behavior; if a safe app redirect URL is already configured, it may be used, but a custom Cronos acceptance page is not required by this PRD.

### PR-2D.1 Admin Access Revocation Guardrail

Admin access can be revoked only when at least one other active admin remains in the organization.

For this guardrail, an active admin means a current-organization membership that:

- has lifecycle `active`;
- has capability `admin`;
- has access status `active` (`Com acesso`);
- is not archived;
- is not blocked;
- is linked to a real Clerk user id.

Acceptance:

- admins can revoke another admin's access from `Equipa`;
- the system blocks revoking the last active admin;
- the UI explains why the action is blocked;
- the same last-admin guardrail applies to deleting, deactivating, or changing capabilities for admin members;
- pending, expired, blocked, archived, scheduler-only, or sync-error members do not count as active admins;
- support intervention through Clerk remains possible for exceptional cases, but is not the normal product path.

### PR-2D.1A Removing Admin Capability

Removing `Administrador` capability must preserve valid remaining capabilities and enforce the last-active-admin guardrail.

Acceptance:

- removing `Administrador` is allowed only if at least one other active admin remains;
- removing `Administrador` from a mixed-role member keeps their `Professor` capability unless explicitly changed;
- if the member remains teacher-only with platform access, Clerk role is downgraded to `org:member`;
- if the member no longer needs platform access, access follows the normal revocation rules;
- session freshness behavior follows the immediate-backend-authorization rule.

### PR-2D.2 Admin Self-Editing Guardrail

Admins can edit safe parts of their own member record but cannot self-lock out.

Acceptance:

- an admin can edit their own safe profile fields such as name;
- email self-editing is allowed only if it can be completed safely through the Clerk-backed identity flow;
- an admin cannot remove their own admin capability;
- an admin cannot block/revoke their own access;
- an admin cannot archive/remove themselves;
- disabled self-actions explain why they are blocked.

### PR-2F Member Removal

Removing a member must preserve operational history.

Acceptance:

- members with no operational-history blockers can be hard deleted;
- members with any operational-history blocker are archived instead of hard deleted;
- operational-history blockers include schedules, lessons/classes, class assignments, timesheets, absences, audit logs, accepted or past Clerk organization membership, historical access events, or any other persisted operational record linked to the member, membership, account, or teacher profile;
- teacher-subject competency links alone do not block hard delete when they have not been used by schedules, classes, lessons, or other operational records;
- pending invitations with no operational-history blockers can be revoked and hard deleted;
- hard delete must revoke/clean up any pending Clerk invitation before deleting local records;
- active, accepted, past-access, sync-error, or blocked-access members are archived instead of hard deleted;
- soft-removed members cannot sign in;
- soft-removed teachers remain available in historical records;
- removing or deactivating admins still respects the last-active-admin guardrail;
- the UI explains when a member is archived instead of permanently deleted.

### PR-2F.1 Archived Member Visibility

Archived members must not clutter the normal team-management view.

Acceptance:

- archived members are hidden from the default `Equipa` table;
- admins can enable `Mostrar arquivados`;
- archived rows are visually distinct when shown;
- archived members cannot sign in;
- archived members can be inspected for history and support context.

### PR-2F.2 Restore Archived Member

Admins must be able to restore archived members when appropriate.

Acceptance:

- archived members expose `Restaurar membro`;
- restore is a saved modal action, not an automatic one-click permission change;
- restoring a member returns them to the default active `Equipa` list only after the required validation and access operations succeed;
- restoring a member preserves historical links;
- restoring a teacher-only member that should remain scheduler-only restores lifecycle only and leaves access as `Sem acesso`;
- restoring a member with `Administrador` capability requires platform access and must start or restore the Clerk-backed invite/access flow in the same save;
- an archived admin-capable member cannot be restored as active admin-capable with `Sem acesso` or `Acesso bloqueado`;
- the admin can remove `Administrador` during restore when guardrails allow, in which case the restored member follows the remaining capabilities;
- restoring an admin-capable member still respects admin access, Clerk role mapping, and last-active-admin rules;
- if email or access state conflicts exist, the UI gives a clear non-technical message.

### PR-2E Mixed-Role Experience Switching

Members with both `Professor` and `Administrador` capabilities must be able to switch between focused app experiences.

Acceptance:

- mixed-role members land in admin mode by default after sign-in;
- mixed-role members see a sidebar mode switcher with admin and teacher modes;
- admin mode shows admin navigation;
- teacher mode shows teacher navigation;
- switching modes does not sign out, change Clerk organization, or require a second account;
- product route access is based on local Cronos capabilities, not Clerk role exclusivity;
- mixed-role members with Clerk `org:admin` and local `teacher` capability can access teacher features while in teacher mode;
- single-role members do not see the mode switcher.

### PR-2B Mandatory Member Email

Every member in `Equipa` must have an email address.

Acceptance:

- the create-member form requires email for teacher-only, admin-only, and teacher-admin members;
- the email can be edited later;
- no fake placeholder email is generated by the system;
- Clerk-backed access flows use this same email for invitations and identity matching.

### PR-2B.3 Editable Member Fields

Admins must be able to correct and manage core member information after creation.

Acceptance:

- admins can edit the organization-scoped member display name;
- admins can edit member email;
- admins can edit member capabilities;
- admins can edit teacher access mode for members with `Professor` capability;
- admins can edit competencies/subjects for members with `Professor` capability;
- admin-only members do not show teacher competency fields;
- email edits enforce global identity uniqueness, organization membership uniqueness, and Clerk sync requirements;
- capability edits enforce the last-active-admin guardrail;
- access edits enforce the teacher access lifecycle rules.

Name behavior:

- Cronos owns an organization-scoped display name used in `Equipa`, schedules, teacher pages, and admin lists;
- admins can edit this organization display name from `Equipa`;
- Clerk/user profile names are account identity data and do not overwrite the Cronos organization display name;
- no separate teacher preferred name is required beyond the organization display name for launch.

Email behavior:

- admins can edit email for members without access status `Com acesso`;
- admins can edit email for pending invitations to correct mistakes before acceptance;
- admins cannot directly edit the email of a member with access status `Com acesso` from `Equipa`;
- active users manage their own email through Clerk account management where supported;
- exceptional active-user email changes are handled through support.

### PR-2B.3A Transactional Member Editing

Member edit modals must apply changes only after explicit save.

Acceptance:

- opening a member modal creates an editable draft;
- changes are not persisted while the admin is editing fields;
- clicking `Guardar` validates and applies the draft;
- clicking `Cancelar` discards the draft;
- closing/dismissing the modal discards the draft;
- after a discarded edit, the member table remains unchanged;
- validation errors keep the modal open and do not partially apply changes.

### PR-2B.3B Save Is The Confirmation

The explicit `Guardar` action is the launch confirmation mechanism for member edits.

Acceptance:

- no second review/confirmation dialog appears after clicking `Guardar`;
- safe edits apply after successful validation;
- risky edits apply after successful validation and guardrail checks;
- blocked actions are disabled or explained before save;
- validation errors keep the modal open;
- partial changes are not applied when validation or Clerk-backed access operations fail.

### PR-2B.3D Synchronous Clerk Access Operations

Launch implementation must perform Clerk invitation/access operations synchronously during member save.

Acceptance:

- when a save requires creating, revoking, restoring, or resending access, the request waits for the Clerk operation result;
- the admin receives immediate success/failure feedback;
- if the Clerk operation fails, the UI shows a safe non-technical message;
- partial local state must not misleadingly show active access after a failed Clerk operation;
- background jobs are not required for the launch baseline.

### PR-2B.3E All-Or-Nothing Save Semantics

Member saves that include Clerk-backed access changes must succeed or fail as one operation.

Acceptance:

- if all validation and Clerk operations succeed, local changes are committed;
- if a required Clerk operation fails, local draft changes are rolled back;
- if a Clerk operation succeeds but the local commit fails, the system attempts compensating cleanup for the Clerk side effect before returning failure;
- the table remains unchanged after failed save;
- the modal remains open and shows a safe non-technical error;
- no member appears access `Com acesso` or `Convite pendente` unless the corresponding Clerk operation succeeded;
- if compensation fails, a durable local support-required reconciliation record remains available and blocks further access changes for the same organization/email/member until resolved.

### PR-2B.3F Durable Clerk Operation Tracking

Cronos must durably track each Clerk access side effect before calling Clerk.

Acceptance:

- before creating, revoking, restoring, resending, removing, or role-changing Clerk organization access, Cronos persists a local access-operation record with organization id, target email/account id when known, membership id when known, intended capabilities, intended Clerk role, and operation type;
- when Clerk returns an invitation id, membership id, user id, or role result, Cronos records those identifiers on the local operation and/or organization membership;
- a Clerk invitation, organization membership, or role change must never exist without enough local recorded context to retry, revoke, or reconcile it;
- if the normal member save fails after the Clerk side effect and compensation also fails, the operation is marked `support_required` or equivalent and is included in structured logs;
- retrying the same organization/email/member must first resolve or safely reuse the existing operation record, not create a second untracked Clerk side effect;
- the normal `Equipa` table remains unchanged after a failed modal save unless a previously committed member exists, but support/retry paths must be able to identify the orphan-risk operation.

### PR-2B.3C Post-Save Feedback

Successful member actions must return the admin to the updated `Equipa` list.

Acceptance:

- successful create/edit/remove/restore closes the modal;
- the table updates to reflect the new member state;
- a short toast confirms the result;
- access status chips reflect the latest state after the action;
- failed saves keep the modal open and show a non-technical error.

### PR-2B.4 Existing Global Account Privacy

Adding or inviting a member must not reveal whether the email already belongs to another Cronos/Clerk account outside the current organization.

Acceptance:

- the admin sees the same neutral invitation-style flow for new and existing global accounts;
- enabling platform access shows `Convite pendente` for the current organization regardless of whether the email already has a global account;
- `Com acesso` appears only after access for the current organization is accepted/synced/confirmed;
- error messages do not reveal membership in another organization;
- launch access enablement uses the Clerk organization invitation flow for both new and existing global accounts;
- Cronos must not directly attach an existing Clerk user to the organization during admin create/edit in a way that grants immediate `Com acesso`;
- if Clerk reports that the email already belongs to the current organization, Cronos handles it as a current-organization duplicate or reconciliation case without revealing cross-organization account existence;
- duplicate membership in the same organization is still prevented.

### PR-2B.1 Unified Member List

`Equipa` must be a single source-of-truth list for organization members.

Acceptance:

- all members appear in one unified table;
- a mixed-role member appears once, not separately as a teacher and admin;
- capability chips show whether the member is `Professor`, `Administrador`, or both;
- access status chips show whether the member has no access, pending invite, expired invite, active access, blocked access, or sync error;
- table search covers at least name and email;
- filters can narrow by capability and access state without changing the underlying source of truth.

### PR-2B.1A Empty State

`Equipa` must guide first setup when the organization has no added members yet.

Acceptance:

- when only the current admin exists, the page shows a practical empty state;
- the empty state focuses on adding the school team, not explaining implementation details;
- `Adicionar Membro` is the primary action;
- empty state copy mentions configuring members, teachers, access, or permissions in product language.

### PR-2B.2 Lifecycle And Access Status Axes

`Equipa` must model member lifecycle separately from platform access.

Lifecycle states:

- `active`: member is part of the current organization view and can be used according to capabilities/access;
- `archived`: member is hidden by default, preserved for history/support, and cannot sign in.

Access states:

- `none`: member has no platform sign-in access;
- `pending_invite`: Clerk-backed invitation/access flow exists but has not been accepted;
- `invite_expired`: the previous invitation is no longer usable and must be resent/recreated;
- `active`: member can sign in to the organization;
- `blocked`: member previously had access but access is currently revoked/disabled;
- `sync_error`: local/Clerk state requires retry or support reconciliation and must not be presented as usable access.

Product labels:

- lifecycle `active` displays as `Ativo`;
- lifecycle `archived` displays as `Arquivado`;
- access `none` displays as `Sem acesso`;
- access `pending_invite` displays as `Convite pendente`;
- access `invite_expired` displays as `Convite expirado`;
- access `active` displays as `Com acesso`;
- access `blocked` displays as `Acesso bloqueado`;
- access `sync_error` displays as `Erro de sincronização`.

Acceptance:

- archive state is not encoded inside `access_status`;
- failed create/edit saves are modal errors, not persisted row states;
- no row appears as access `pending_invite` unless a Clerk invitation/access side effect is known to exist;
- no row appears as access `active` unless the member can sign in to the organization;
- no Clerk-specific status label is required for launch unless it is translated into one of these product states.

### PR-2B.2C Seat Counting Policy

Seat counting must be based on access status `Com acesso`.

Acceptance:

- members with access status `Com acesso` count as seats;
- scheduler-only teachers with `Sem acesso` do not count as seats;
- `Convite pendente` and `Convite expirado` members do not count as active seats until access is accepted/active;
- `Erro de sincronização` members do not count as active seats;
- `Acesso bloqueado` members do not count as active seats;
- archived members do not count as active seats;
- failed create/edit saves do not count as seats because they are not persisted as rows;
- billing implementation is not required by this PRD unless a separate billing PRD extends it.

### PR-2B.2D Billing Enforcement Out Of Scope

This PRD must not implement subscription or seat-limit enforcement.

Acceptance:

- no checkout/pricing UI is required;
- no plan gating is required;
- no automatic blocking based on seat limits is required;
- no Clerk Billing integration is required;
- the active-seat counting rule is documented for future billing work.

### PR-2B.2B Resend Invitation

Admins must be able to send a fresh invitation for pending or expired invitations without leaving `Equipa`.

Acceptance:

- `Reenviar convite` is available from the edit/member details modal when status is `Convite pendente` or `Convite expirado`;
- `Reenviar convite` is not shown for statuses where it is irrelevant;
- resending uses the current member email, current organization context, current capabilities, and current inviter admin;
- for a pending invitation, the system revokes the current pending Clerk invitation when possible, then creates a new invitation;
- for an expired invitation, the system creates a new Clerk invitation;
- the new Clerk invitation id/status replaces the stored invitation id/status on the same organization membership;
- the UI confirms the resend result with a non-technical success or failure message;
- resending does not create duplicate members or duplicate memberships.

### PR-2B.2A Invite Error UX

Invite/access setup failures and sync problems must be understandable and safe for school admins.

Acceptance:

- modal save failures are always paired with a non-technical message;
- persisted `Erro de sincronização` states are paired with a non-technical message and a safe `Tentar novamente` action;
- if retry succeeds, the member returns to the correct lifecycle/access state;
- if retry fails or the mismatch remains unclear, the UI asks the admin to contact support;
- while `Erro de sincronização` remains unresolved, risky edits such as email changes, capability changes, access toggles, removal, archive, or restore are blocked;
- the message explains what the admin can do next;
- transient failures can show a retry action;
- email-related failures guide the admin to correct the email;
- support-required failures ask the admin to contact support;
- messages do not reveal sensitive provider details, raw Clerk errors, stack traces, secrets, or cross-organization account existence.

### PR-3 No Admin-Set Password

The `Equipa` member creation UI must not ask the admin to set another user's password.

Acceptance:

- `Equipa` member create/edit removes the password field;
- backend create/update schemas do not accept or rely on password;
- tests assert no password field appears in member create/edit flows.

### PR-4 Invitation Lifecycle

The system must model member lifecycle, platform access, and teacher resource existence separately.

Minimum lifecycle states:

- active;
- archived.

Minimum access states:

- no access requested;
- invitation pending;
- invitation expired;
- active;
- blocked;
- sync error.

Acceptance:

- `Equipa` displays lifecycle and access state derived from local/Clerk sync data;
- access status `active` (`Com acesso`) means the member has a local account mirror linked to a real Clerk user and current organization access;
- pending means invitation/access setup exists but no accepted organization membership has synced yet;
- expired means the previous invitation is no longer usable and must be resent/recreated;
- blocked means access was revoked, disabled, or externally removed while preserving local history, and Cronos must not leave a current usable Clerk organization membership or pending invitation for that organization;
- sync error means safe retry or support reconciliation is required before the product can honestly show a normal access state.

### PR-5 Idempotency

Create/invite/retry operations must be idempotent for the same organization, teacher, and email.

Acceptance:

- retrying after a failed modal save or resending an expired/pending invite does not create duplicate teachers;
- repeated Clerk webhooks do not create duplicate users;
- accepting an invitation links to the intended `teacher_id`;
- the same email cannot create duplicate local account identities or leave one local stub plus one Clerk-backed user.

### PR-6 Teacher Platform Access

After accepting the invite, a member with `Professor` capability can sign in through Clerk and use teacher routes.

Acceptance:

- local `teacher` capability, access status `Com acesso`, and a linked teacher profile allow teacher routes;
- Clerk role is not treated as the product teacher role because mixed members may have Clerk `org:admin`;
- authenticated teachers and mixed-role members in teacher mode have a current teacher profile id;
- `/teachers/me/availability`, `/my-availability`, `/my-schedules`, and `/my-progress` work for the invited teacher;
- teacher-only members cannot access `Equipa`.

## 8. Technical Requirements

### TR-1 Backend Create Flow

The staff/member creation flow must stop creating active local login identities with `clerk_user_id = null`.

Target behavior:

- create or reuse the local global account record for the required email;
- create the organization membership with the selected capabilities for all member types;
- create the organization-scoped teacher profile and subject links when `Professor` capability is selected;
- when access is requested, create a Clerk organization invitation or equivalent Clerk-backed invite operation;
- store enough local access metadata to show pending/retry status;
- rely on membership webhook or synchronous Clerk fallback to create/link the global account and organization membership with a real Clerk user id.

Scheduler-only teacher behavior:

- a scheduler-only teacher still has a local global account record, organization membership, and teacher profile;
- the account may have `clerk_user_id = null` only while the membership does not have access status `Com acesso`;
- no platform route authorization can treat an account without `clerk_user_id` as signed-in or active;
- enabling access later uses the same account/membership/profile records and starts the Clerk-backed invitation/access lifecycle.

### TR-2 Clerk Invitation Metadata And Reconciliation Fallback

Clerk invitation creation must carry safe local linking context when Clerk supports it, but webhook reconciliation must not depend on metadata being present on every Clerk event.

Required metadata:

- local membership id;
- local `organization_id` or enough context to validate it;
- local `teacher_id` when the invited member has `Professor` capability;
- intended capability/role context when needed for reconciliation.

Acceptance:

- invitation webhooks first reconcile by stored Clerk invitation id when available;
- membership webhooks reconcile by verified Clerk organization id, Clerk user id, local account email, and pending local membership/access-operation records;
- webhook handlers must not assume `organizationMembership.*` events include invitation metadata;
- metadata is used as a validation/linking accelerator, not as the only source of truth;
- if no unique local membership can be identified, the event is rejected into `sync_error`/support reconciliation and must not grant product access;
- mismatched org/member/teacher metadata is rejected or ignored safely;
- metadata is safe to expose according to Clerk metadata visibility and must never include secrets or raw auth tokens.

### TR-3 Local Data Model

The local model must use a global account plus organization membership pattern.

Required concepts:

- global `Account` or `User`: one identity per person, email unique globally, linked to Clerk user id when access exists;
- `OrganizationMembership`: organization-scoped access, capability set, access state, invitation state, and last-active-admin guardrails;
- `TeacherProfile`: organization-scoped scheduling/teaching resource, linked to an organization membership when the member has `Professor` capability;
- `AccessOperation` or equivalent durable ledger: one record per Clerk access side effect, used for retry, compensation, and support reconciliation;
- invitation/access status metadata: enough state to show no-access, pending, expired, active, blocked, and sync-error access states in `Equipa`.

For launch, current invitation/access state is stored on `OrganizationMembership`, including Clerk invitation id/status when relevant. A separate invitation-history table is not required.

Archived members are represented through organization membership lifecycle state, not by archiving the global account.

Clerk organization roles are coarse identity/membership roles. Cronos local membership capabilities are the precise product permissions.

The current table names may differ during implementation, but the domain boundaries must match these concepts.

Acceptance:

- no production UI depends on a fake local user to show pending access;
- invitation and access status can be queried with the unified `Equipa` list;
- current invitation/access state can be read from the organization membership record;
- archived/current visibility is controlled by organization membership lifecycle state;
- the same global account can belong to multiple organizations through memberships;
- the same global account cannot be added twice to the same organization;
- each membership stores a capability set that can include `teacher`, `admin`, or both;
- teacher profiles remain organization-scoped and preserve scheduler/history behavior.
- access-operation records preserve enough safe context to reconcile Clerk side effects even when the visible member save fails.

### TR-4 Webhook Compatibility

Existing Clerk webhook behavior must remain the asynchronous sync path for Clerk state, with direct Clerk API checks used when synchronous save/retry flows need immediate confirmation.

Acceptance:

- `organizationMembership.created` creates or updates exactly one local account/membership only after the event is matched to a valid local membership, invitation, or access-operation record;
- membership events without invitation metadata still reconcile safely through Clerk organization id, Clerk user id, verified email, and stored local operation state;
- `user.created` without membership does not create orphan users;
- `organizationMembership.deleted` or `user.deleted` deactivates access without deleting teacher scheduling history.

Required webhook events for this feature:

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

Acceptance:

- membership events sync active/revoked organization access;
- invitation events sync pending/accepted/revoked invitation state;
- user events sync global account identity/profile state;
- organization events sync organization lifecycle state;
- missing or malformed events fail safely and do not grant access.

Webhook handling must be idempotent by storing processed Clerk event IDs or an equivalent deduplication record.

### TR-4A Clerk Role Mapping

Cronos must map local capabilities to Clerk organization roles for access operations.

Acceptance:

- teacher-only members with platform access use Clerk `org:member`;
- admin-capable members use Clerk `org:admin`;
- mixed `Professor + Administrador` members use Clerk `org:admin` plus local capabilities `admin` and `teacher`;
- scheduler-only teachers have no active Clerk access requirement;
- app authorization uses local capabilities for product-specific behavior;
- frontend and backend guards must not block teacher features solely because a mixed-role member's Clerk role is `org:admin`;
- current role-exclusive guard behavior must be replaced where it conflicts with local capabilities;
- Clerk roles remain the source for broad organization membership/admin authority.

### TR-4A.1 External Clerk Change Handling

Changes made directly in Clerk outside Cronos must be reconciled conservatively.

Acceptance:

- Cronos local capabilities remain the source of truth for product permissions and are not silently imported from Clerk role changes;
- if Clerk organization membership is removed outside a matching Cronos operation, Cronos marks the local access as `blocked` or `sync_error` and backend authorization denies access;
- if Clerk role no longer matches the role expected from local capabilities, Cronos marks the membership `sync_error` and blocks risky edits until retry/support reconciliation succeeds;
- if Clerk grants a user organization membership with no matching Cronos membership, account, invitation, or access-operation record, Cronos does not auto-create product capabilities or teacher access;
- external Clerk changes that match a recorded support/retry operation may reconcile the local state only after organization, user/email, and membership identity are validated;
- last-active-admin risk caused by an external Clerk change is logged as support-required reconciliation and must not be hidden by counting a blocked, mismatched, or no-Clerk-id member as active admin.

### TR-4B Session Freshness After Access Changes

Access and capability changes must be enforced immediately by the backend.

Acceptance:

- backend authorization uses current local membership/access state;
- revoked access is denied on subsequent API requests even if the frontend UI is stale;
- frontend reloads or refreshes relevant session/member state after save when possible;
- stale UI cannot bypass backend authorization;
- applying changes only on next login is not acceptable.

### TR-5 API Contract

The `/members` create/update API must expose capability, access intent, and status clearly.

Required request fields:

- `name`;
- `email`;
- `capabilities`;
- `teacher_access_mode` when the member has the `Professor` capability;
- `subject_ids` when the member has the `Professor` capability.

Required action response fields:

- `id`;
- `name`;
- `email`;
- `subject_ids`;
- `access_status`;
- `invitation_status` or `invitation_error` when applicable.

`clerk_user_id` is not required in the normal admin UI response. If exposed for support/debug contexts, it must not become a visible school-admin affordance or decision signal.

Acceptance:

- no password field or local credential field exists in the request;
- old `create_user_account` semantics are removed from the canonical launch API;
- frontend uses the response instead of guessing from local user flags alone.

The `/members` API must return a complete member view model for the `Equipa` table and edit modal.

Required response fields include:

- member/membership id;
- organization display name;
- email;
- capabilities;
- access status;
- invitation status and safe error category/message when relevant;
- lifecycle status such as active/archived;
- teacher profile id when applicable;
- competency subject ids and names/summary when applicable;
- allowed action flags such as can edit, can archive, can restore, can remove admin, can resend invite, can retry sync.

Acceptance:

- the frontend can render the `Equipa` table from one list response;
- the frontend can open the edit modal without assembling account/membership/teacher state from multiple unrelated resources for common fields;
- action availability is driven by backend-calculated guardrails;
- response does not expose sensitive Clerk internals.

### TR-5A Members API And Route Boundary

Admin staff management must move to a member/staff API and frontend route boundary.

Acceptance:

- launch frontend navigation uses `Equipa`;
- admin member CRUD is implemented under a members/staff API boundary rather than expanding `/teachers` as the canonical admin surface;
- teacher self-service endpoints remain teacher-specific;
- scheduler/domain operations can continue using teacher profile ids where appropriate;
- old `/teachers` admin CRUD is removed completely after `Equipa` replaces it.

Naming:

- frontend navigation/page label: `Equipa`;
- API resource: `/members`;
- code/domain language: member, account, organization membership, teacher profile.

### TR-6 Error Handling

Clerk failures must not be swallowed silently.

Acceptance:

- backend logs structured Clerk invitation errors;
- API returns clear failure status or stores retryable failure state;
- frontend shows actionable message to admin;
- no account is displayed as active when Clerk invitation failed.

## 9. Security Requirements

1. Only active admins, as formally defined by this PRD, can create or invite members from `Equipa`.
2. Member invitations must only target the admin's current organization.
3. A member cannot self-link to another member or teacher profile.
4. Webhook metadata and fallback reconciliation inputs must be validated against the local organization, membership, account, access-operation record, and teacher profile when applicable.
5. The system must not persist or transmit admin-entered passwords.
6. Deactivation/archive must preserve scheduling, membership, and audit history.
7. Tenant isolation tests must cover invited teacher, admin, and mixed-role access.

## 10. Observability Requirements

Minimum events/logs:

- member created;
- teacher profile created when applicable;
- member invite requested;
- Clerk invitation created;
- Clerk invitation failed;
- membership webhook linked account to organization membership and teacher profile when applicable;
- webhook ignored due to invalid/missing member metadata;
- member access deactivated or blocked;
- last-active-admin guardrail blocked an action.

Launch scope requires structured logs plus admin-visible status/error states. A dedicated internal support dashboard is not required for this PRD baseline.

Minimum metrics or dashboard-ready counters:

- invite success count;
- invite failure count;
- pending invites older than threshold;
- webhook link success count;
- login failures caused by missing `teacher_id`.

Structured logs must include the relevant safe identifiers and categories available for the event, such as organization id, account id, membership id, teacher profile id, Clerk user id, Clerk organization id, invitation id, access status, event type, and non-sensitive error category.

## 11. Migration And Cleanup

Because the app has not launched, implementation can favor a clean cutover over backwards compatibility.

Migration must target the new account/membership/profile baseline directly. Existing local development stubs that conflict with the new model can be transformed, archived, discarded, or reset as appropriate.

Required cleanup:

1. Find local teacher users with `clerk_user_id IS NULL`.
2. Decide whether each should become:
   - a teacher-only domain profile with no access;
   - a pending Clerk invite;
   - a deleted local stub if duplicate/invalid.
3. Remove password UI and tests that imply local credential creation.
4. Remove or quarantine local `user_service.create_user()` usage from teacher creation.
5. Add a regression that proves no member with access status `Com acesso` exists without `clerk_user_id`.

## 12. Acceptance Matrix

| Area | Acceptance criteria |
| --- | --- |
| Teacher-only no access | Global account, organization membership, and teacher profile are created; access is `none`; the member cannot sign in without Clerk ID. |
| Teacher-only with access | Clerk invitation is created for current organization with `org:member`; local access becomes `pending_invite`. |
| Admin-only with access | Clerk invitation is created for current organization with `org:admin`; admin capability and last-active-admin rules apply. |
| Mixed-role with access | Clerk invitation is created with `org:admin`; local capabilities include both `admin` and `teacher`; teacher profile links correctly. |
| Invite acceptance | Clerk webhook creates/updates the global account and organization membership with real `clerk_user_id`; teacher profile is linked when `Professor` capability exists; admin/mixed capabilities remain scoped to the current organization. |
| Teacher login | Invited teacher-only member can sign in and access teacher-only pages. |
| Admin login | Invited admin-only member can sign in and access admin pages, including `Equipa`. |
| Admin route protection | Teacher-only members cannot access `Equipa`; admin-capable members can. |
| Mixed-role authorization | Mixed-role members can access admin features and teacher features through local capabilities even when Clerk role is `org:admin`. |
| Last active admin | Pending, expired, blocked, archived, sync-error, or no-Clerk-id admin-capable members do not count as active admins. |
| Password removal | No member password field exists in UI, API contract, or tests. |
| Failure handling | Clerk save failure is visible in the modal and retryable; UI never claims active access after failed invite/access setup. |
| Sync error recovery | `Erro de sincronização` shows `Tentar novamente`; unresolved sync errors block risky edits and escalate to support. |
| Idempotency | Repeated create/retry/webhook events do not create duplicate members, accounts, memberships, teacher profiles, or Clerk invitations. |
| Durable Clerk operation tracking | A Clerk side effect cannot be created without a local operation record; failed local commit plus failed compensation leaves a support-required record and blocks duplicate access changes. |
| External Clerk drift | Direct Clerk role/membership changes do not silently grant capabilities; removed/mismatched access becomes blocked or `sync_error`. |
| Tenant isolation | Member invite/link cannot cross organizations. |
| Existing scheduling | Teacher resource still works in subjects, availability, lessons, schedules, and timesheets. |
| Removal/archive | Unused setup records can be hard deleted; members with operational-history blockers are archived and access is revoked/blocked. |

## 13. Test Plan

### Frontend

- `Equipa` member form renders no password field.
- Creating a teacher-only member without access sends no invite/access request.
- Creating a teacher-only member with access sends the invite/access request.
- Creating an admin-only member requires access and sends an admin invite.
- Creating a mixed-role member requires access, sends an admin invite, and shows teacher fields.
- `Equipa` table renders lifecycle `Ativo`/`Arquivado` plus access `Sem acesso`, `Convite pendente`, `Convite expirado`, `Com acesso`, `Acesso bloqueado`, and `Erro de sincronização`.
- Route guards use local capabilities for product features while still requiring Clerk organization membership.
- `Equipa` modal changes are transactional and discard on cancel/close.
- Mixed-role members can switch between admin and teacher modes.
- Mixed-role members with Clerk `org:admin` can access teacher mode/features when local `teacher` capability exists.
- `Erro de sincronização` shows safe retry and blocks risky edits while unresolved.

### Backend

- `POST /members` without access creates only the membership/teacher profile data required for the selected capabilities.
- `POST /members` with access calls the Clerk invitation service synchronously.
- create/edit/revoke/archive/restore service and API tests cover teacher-only, admin-only, and mixed-role members where the action applies.
- Clerk invitation failure is captured and returned or stored.
- Webhook reconciliation links account/membership/teacher profile through stored invitation id, Clerk org/user ids, verified email, metadata when available, and access-operation records.
- Webhook membership missing invitation metadata does not accidentally grant teacher self-service or admin product access.
- Webhook acceptance tests cover teacher-only, admin-only, and mixed-role invitations.
- Duplicate webhook events are idempotent.
- Access status `Com acesso` with `clerk_user_id = null` is rejected or impossible.
- Account, membership, and teacher profile creation are tested at service level.
- sync retry reconciles recoverable local/Clerk drift or returns a support-required error without enabling risky edits.
- `Reenviar convite` revokes current pending invitations when possible, recreates expired/pending invitations, and updates the same membership.
- failed local commit after a successful Clerk side effect records a support-required operation and does not create a duplicate side effect on retry.
- external Clerk membership/role drift is reconciled conservatively and does not silently grant local capabilities.
- `Adicionar Membro`, edit, revoke, restore, and last-active-admin guardrails are tested at API level.
- last-active-admin tests cover pending, expired, blocked, archived, sync-error, and no-Clerk-id admin-capable members.
- removal tests cover hard delete with no blockers, pending-invite revoke plus hard delete, archive when operational-history blockers exist, and archive for accepted/past-access members.

### End-to-End

- Admin creates a teacher-only member and invites them; teacher accepts Clerk invitation, signs in, lands in teacher UX, and updates availability.
- Admin creates an admin-only member; invited admin accepts and can access `Equipa`.
- Admin creates a mixed-role member; invited mixed member accepts, lands in admin UX, and can switch to teacher mode.
- Admin sees teacher and mixed-role teacher profiles remain available as scheduling resources where applicable.

Test strategy is layered: unit/service, API, webhook, frontend component, and Clerk-supported or equivalent controlled invite-acceptance coverage for teacher-only, admin-only, and mixed-role members.

## 14. Launch Definition Of Done

This feature is launch-ready when the lean production-ready gate is met.

Required before launch:

1. `Equipa` replaces the visible `Professores` admin CRUD for staff management.
2. Admins can create scheduler-only teachers without sending Clerk invites.
3. Admins can create teachers with platform access and send Clerk invitations.
4. Admins can create admin-capable members and send Clerk admin invitations.
5. Invited users can accept Clerk invitations, define/manage their own password through Clerk, and join the correct organization.
6. Access revocation takes effect immediately at the backend authorization layer.
7. The last active admin guardrail is enforced.
8. No member creation/edit flow asks an admin to set another user's password.
9. `/members` returns the complete view model needed by the `Equipa` table and edit modal.
10. Required Clerk webhooks are idempotent and safe to retry.
11. Core service/API tests cover create, invite, revoke, restore, role/capability changes, and last-admin protection.
12. Happy-path invite acceptance coverage proves teacher-only, admin-only, and mixed-role first access.
13. First login after invite acceptance routes the member to the correct role-based experience once Clerk returns them to Cronos.
14. Mixed-role authorization uses local capabilities so Clerk `org:admin` does not block teacher features.
15. Acceptance and tests cover all launch member types: `Professor`, `Administrador`, and `Professor + Administrador`.

Not required for first launch:

- support dashboard;
- advanced webhook replay tooling;
- full audit-log UI;
- bulk import;
- billing or seat-limit enforcement;
- custom Clerk invitation acceptance UI.

## 15. Launch Risks And Mitigations

Known risks should be named in this PRD with clear mitigations, but they only block launch when they violate the launch definition of done.

| Risk | Mitigation | Launch blocker? |
| --- | --- | --- |
| Clerk invitation creation fails during member save. | Save fails clearly, leaves the table unchanged, shows a non-technical error, and does not claim access is pending or active. | Yes, if failure is silent or leaves inconsistent state. |
| Clerk operation succeeds but local commit fails. | A durable local access-operation record already exists; the system attempts compensating cleanup, logs the recovery outcome, and blocks same org/email/member access changes if support reconciliation is required. | Yes, if the product can leave active or untracked Clerk access without a durable local reconciliation record. |
| Clerk webhook delivery is delayed. | Local pending status remains visible; webhook handlers are idempotent and safe to retry. | No, if the pending state is honest and retry-safe. |
| Clerk webhook delivery never arrives. | Product owner can inspect Clerk directly; future replay/support tooling can be added after launch. | No, unless common invite acceptance cannot complete. |
| Clerk role or membership is changed directly outside Cronos. | Cronos reconciles conservatively: no silent capability import, removed membership blocks/sync-errors access, role mismatch becomes `sync_error`, and support can resolve using safe identifiers. | Yes, if external changes can silently grant product access or leave misleading active access. |
| Existing local development users have no Clerk identity. | Pre-launch migration/cleanup removes or converts incompatible local stubs. | Yes, if active login users can exist without Clerk ids. |
| Admin revokes another member but the frontend still shows stale UI. | Backend authorization denies access immediately; frontend refresh is best effort. | No, if backend enforcement is correct. |
| Organization loses its only admin. | Last-active-admin guardrail blocks destructive admin changes. | Yes. |
| Mixed-role behavior confuses users. | Default to admin experience and provide an in-app mode switcher for teacher mode. | No, if routing and permissions remain clear. |
| Support needs arise before support tooling exists. | Product owner uses Clerk directly for exceptional recovery during early launch. | No, unless routine flows require manual support. |

Post-launch hardening candidates:

- support dashboard;
- webhook replay tooling;
- audit-log UI;
- broader E2E suite;
- billing seat-limit enforcement;
- custom invite acceptance page.

## 16. Remaining Implementation Decisions

The core UX baseline is closed. Remaining decisions are implementation-level details that must not weaken the product decisions above.

Those details belong in the technical specification, not in this PRD.

## 17. Post-PRD Handoff

After this PRD is finalized, the next artifacts should be created in this order:

1. technical specification documentation;
2. work breakdown structure;
3. implementation.

The PRD remains the product source of truth. The technical specification should translate these product decisions into architecture, schema, API, Clerk, migration, and testing details. The WBS should translate the technical specification into ordered implementation tasks.

## 18. Launch Decision

For first launch, prefer this policy:

1. Keep teacher profile creation independent from platform access.
2. Remove admin-entered password entirely.
3. Replace the visible `Professores` admin CRUD with `Equipa` and `Adicionar Membro`.
4. Use `/members` as the admin API boundary.
5. When access is enabled, create the member, create a Clerk invitation synchronously, and show pending.
6. Let Clerk webhook/BAPI sync create or update the global account and organization membership with a real Clerk user id.
7. Keep retry/recovery contextual inside member details or error handling, not as a universal table action.
8. Implement the backend contract first, then build the `Equipa` frontend against the stable `/members` view model.
9. After invitation acceptance, route members to the correct role-based app experience once Clerk returns them to Cronos.

This keeps the admin workflow simple while making Clerk the identity authority.

## 19. Decision Record

### DR-1 Visible Staff Area Name

Decision: replace the visible `Professores` management concept with `Equipa`.

Rationale:

- admin creation makes the area broader than teachers;
- school admins need one place to manage people in the organization;
- teachers can remain a staff subtype with pedagogical competencies;
- admins can be managed in the same product area without forcing access management into Clerk's dashboard.

Implications:

- navigation label becomes `Equipa`;
- page title and empty states use `Equipa`;
- teacher-specific controls remain visible only when the person is a teacher;
- old visible/admin `/teachers` CRUD is removed from the launch baseline, while genuinely teacher-specific self-service/domain routes may remain.

### DR-2 Staff Creation Entry Point

Decision: use one primary creation action named `Adicionar Membro`.

Rationale:

- the admin is managing organization members, not only teacher resources;
- one entry point avoids duplicated teacher/admin creation flows;
- it supports members who may be both teachers and admins;
- it keeps Clerk-backed organization membership aligned with the product language.

Rejected alternatives:

- separate `Novo Professor` and `Novo Administrador` buttons: clearer at first glance, but duplicates flows and makes combined teacher/admin members awkward;
- separate tabs with separate creation flows: explicit per role, but makes duplicate people and shared access state harder to reason about.

### DR-2A Bulk Import Is Out Of Scope For Launch

Decision: `Equipa` launch scope is manual member management only.

Rationale:

- Clerk-backed access and invitation flows should be reliable before mass operations exist;
- manual flows reduce accidental mass-invite risk;
- one-member-at-a-time workflows are easier to validate and support as the first production baseline.

Rejected alternatives:

- teacher-resource CSV/XLSX import for launch: useful but adds a second creation path;
- full bulk import with invitations: powerful but too risky before the single-member lifecycle is proven.

### DR-3 Member Type Is Capability-Based

Decision: `Adicionar Membro` supports `Professor`, `Administrador`, and `Professor + Administrador`.

Rationale:

- people can have both teaching responsibilities and admin permissions;
- one person should not need duplicate local records or duplicate Clerk identities;
- form fields can be conditionally displayed by capability;
- launch UX remains simple while avoiding an artificial role limitation.

Rejected alternatives:

- single required role only: simpler, but blocks legitimate mixed-role users;
- separate job type plus separate platform permission model: precise, but too abstract for the launch form.

### DR-3A Teacher Competencies Are Optional But Flagged

Decision: teacher competencies are optional at creation, with visible warnings when missing.

Rationale:

- schools may add the team before finishing subject setup;
- member creation should not be blocked by incomplete curriculum data;
- missing competencies still matter for scheduling readiness and must be visible.

Rejected alternatives:

- require competencies at creation: cleaner data but blocks onboarding when subjects are not ready;
- defer competencies to a separate setup flow only: keeps creation simple but splits a natural teacher setup task.

### DR-3B Removing Professor Capability Requires Dependency Checks

Decision: `Professor` capability can be removed only if the teacher profile has no operational-history blockers.

Rationale:

- teacher profiles are scheduler/domain resources;
- schedules, class assignments, timesheets, absences, and audit history must remain intact;
- mistaken unused teacher setup can still be cleaned up;
- historical teachers should be archived or have access disabled instead of having teacher identity removed.

Rejected alternatives:

- always allow removing `Professor`: risks orphaned or confusing historical teacher data;
- never allow removing `Professor`: too restrictive for unused setup mistakes.

### DR-4 Email Is Mandatory For Every Member

Decision: every member requires an email address at creation time.

Rationale:

- email is common and easy to edit later;
- the create-member flow stays simpler;
- Clerk invitations, local matching, and support workflows all have a stable identifier from the beginning;
- the product avoids ambiguous people records before launch.

Rejected alternatives:

- conditional email only for members with platform access: semantically precise, but adds branching to the form and table behavior;
- optional email for all members until invitation: flexible, but too loose for a launch baseline and awkward for admin/support workflows.

### DR-4.1 Cronos Owns Organization-Scoped Display Name

Decision: use a Cronos organization-scoped display name for product records, while Clerk/user profile names remain account identity data.

Rationale:

- school-facing names in schedules, classes, teacher pages, and `Equipa` must stay stable;
- admins need to correct school display names without changing global identity data;
- Clerk profile changes should not unexpectedly rewrite historical or operational school records;
- users can still manage their Clerk identity profile separately from the school display name.

Ownership:

- Cronos/admin owns the organization-scoped display name;
- Clerk/user owns account profile name;
- Cronos display name is used for `Equipa`, schedules, classes, teacher pages, and admin lists;
- Clerk profile name is used only where account identity/profile data is intentionally shown.

Rejected alternatives:

- one shared display name for member/account/teacher profile: simpler but lets identity sync unexpectedly alter school records;
- Clerk/user-owned display name after activation: aligns with identity ownership but removes useful admin control from school records.

### DR-4A Email Identity Is Globally Unique

Decision: email is globally unique as an account identity. Organization access is scoped through memberships, not duplicate per-organization user identities.

Rationale:

- one person should have one identity across Cronos;
- cross-organization work should use one login account and multiple organization memberships;
- SSO/social login/account recovery are cleaner with one global email identity;
- permissions remain organization-scoped through membership records;
- the same global user must not be added twice to the same organization.

Guardrails:

- enforce global email uniqueness for accounts;
- enforce membership uniqueness per organization;
- avoid leaking whether an email belongs to another organization;
- support soft deletion/anonymization later so historical audit logs can remain while emails can be reused when appropriate.

Rejected alternatives:

- organization-scoped email identity: technically possible, but creates duplicate login accounts for the same person;
- launch-only global block without memberships: simpler short-term, but does not support modern B2B multi-organization identity.

### DR-4A.0 Active User Email Is User-Owned

Decision: admins can edit member email before platform access is active. After invitation acceptance/activation, the user owns their global email identity through Clerk, with support handling exceptional changes.

Rationale:

- active email is a global login identity, not just an organization field;
- avoids account takeover risks from admin-side global email edits;
- still lets admins fix typos before invite acceptance;
- aligns with users managing their own credentials in Clerk.

Rejected alternatives:

- block all email edits after creation: too strict for pending invite mistakes;
- allow admins to update active Clerk user email directly: convenient but too risky for global identity.

### DR-4A.1 Existing Account Disclosure Is Neutral

Decision: the admin UI must not disclose whether an email already belongs to a global account outside the current organization. Enabling platform access uses the same invitation-style UX and shows `Convite pendente` whether the email is new or already has a global account.

Rationale:

- avoids leaking platform membership or another school's relationship with that email;
- supports the global account plus organization-membership model;
- keeps the admin focused on the current organization outcome;
- reduces account-enumeration risk.

Product rule:

- `Convite pendente` is the neutral visible result after access is enabled;
- launch uses the Clerk organization invitation flow for both new and existing global accounts;
- direct Clerk membership attachment during admin create/edit is not used when it would grant immediate access and leak that the account already existed;
- `Com acesso` appears only after access for the current organization is accepted/synced/confirmed;
- immediate `Com acesso` must not be used as a visible signal that the email already existed globally;
- same-organization duplicate membership can still be blocked with a current-organization message.

Rejected alternatives:

- show `Existing Cronos account found`: transparent but leaks cross-organization account existence;
- immediately show `Com acesso` for existing global accounts and `Convite pendente` for new accounts: convenient but leaks account existence;
- block and require support: safe but contradicts self-service membership management.

### DR-4A.2 Local Data Model Uses Account, Membership, And Teacher Profile

Decision: implement `Equipa` with a global account identity, organization-scoped membership, and organization-scoped teacher profile model.

Rationale:

- matches global email uniqueness;
- supports one person in multiple organizations without duplicate login accounts;
- keeps permissions and capabilities scoped to the organization;
- preserves teacher scheduling/history as an organization-specific domain profile;
- makes mixed-role members (`Professor + Administrador`) a single organization membership with multiple capabilities.

Conceptual model:

- global account/user: email, Clerk user id when platform access exists, global identity fields;
- organization membership: organization id, account id, capability set, lifecycle state, access status, invitation state;
- teacher profile: organization id, membership id, teacher name/profile data, subject competencies, scheduling links.

Scheduler-only teacher rule:

- scheduler-only teachers use the same three-record model: global account, organization membership, and teacher profile;
- the membership has capability `teacher`, lifecycle `active`, and access `none`;
- the account may exist without a Clerk user id only when it is not an active login identity;
- platform login/access always requires a real Clerk user id and valid organization access.

Rejected alternatives:

- keep current local `User` with direct `organization_id`, `role`, and `teacher_id`: faster but conflicts with global identity and multi-organization membership;
- rely only on Clerk memberships at runtime: keeps less local data but weakens `Equipa` querying, teacher profile linking, and operational history.

### DR-4A.2A Membership Stores Current Invitation State

Decision: store current invitation/access state on `OrganizationMembership`, including Clerk invitation id/status when relevant.

Rationale:

- `Equipa` can query one current member state efficiently;
- launch needs current status more than full invitation history;
- structured logs and webhook event records cover support/debug detail;
- avoids a separate invitation-history data model before it is needed.

Rejected alternatives:

- separate `MemberInvitation` table: better history but more implementation complexity;
- query Clerk for invitation state on demand: less local data but slower and less reliable for the team list.

### DR-4A.2B Archived Is A Membership Lifecycle State

Decision: represent archive/remove state on the organization membership, for example with lifecycle values such as `active` and `archived`.

Rationale:

- archiving is organization-specific;
- one global account can remain active in another organization;
- admin-only and teacher members use the same lifecycle model;
- teacher profiles remain linked for scheduling/history when the membership is archived.

Rejected alternatives:

- archive only the teacher profile: fails for admin-only members and puts lifecycle state at the wrong layer;
- soft-delete the global account: unsafe for multi-organization identity and historical audit.

### DR-4A.3 Membership Stores A Capability Set

Decision: organization membership stores capabilities as a set, such as `teacher`, `admin`, or both.

Rationale:

- directly represents `Professor`, `Administrador`, and `Professor + Administrador`;
- avoids special-case roles like `admin_teacher`;
- supports future staff capabilities if needed;
- keeps permissions scoped to the organization membership.

Rejected alternatives:

- single role enum: simple but awkward for mixed-role members and future growth;
- boolean columns such as `is_teacher` and `is_admin`: easy for two capabilities, but spreads permission logic as the model grows.

### DR-4A.4 Clerk Uses Default Roles, Cronos Uses Local Capabilities

Decision: use Clerk default roles for coarse organization membership and local Cronos capability sets for product permissions.

Mapping:

- teacher-only with sign-in: Clerk `org:member`, Cronos capability `teacher`;
- admin-only: Clerk `org:admin`, Cronos capability `admin`;
- teacher plus admin: Clerk `org:admin`, Cronos capabilities `admin` and `teacher`;
- scheduler-only teacher: no active Clerk access, Cronos teacher profile exists.

Authorization rule:

- Clerk proves authenticated organization membership and broad organization/admin authority;
- Cronos local capabilities decide access to product experiences and feature areas;
- `Professor` capability grants teacher product features;
- `Administrador` capability grants admin product features;
- mixed members with Clerk `org:admin` and Cronos `teacher` capability must be allowed into teacher mode and teacher feature routes.

Rationale:

- Clerk remains responsible for identity, organization membership, and broad admin authority;
- Cronos remains responsible for school-specific product permissions, teacher profiles, competencies, schedules, and mixed-role UX;
- avoids extra Clerk custom-role configuration before launch;
- avoids duplicating product semantics into Clerk when local capabilities are still required.

Rejected alternatives:

- custom Clerk roles for `teacher`, `school_admin`, and `teacher_admin`: more product-like labels in Clerk, but adds configuration and still requires local capabilities;
- all users as `org:member` with local-only permissions: gives local control but weakens Clerk's organization admin semantics;
- current Clerk-role-exclusive route guards: simplest but prevents mixed-role members from using teacher mode.

### DR-4B Core Member Fields Are Editable

Decision: admins can edit name, email, capabilities, teacher access mode, and teacher competencies from `Equipa`.

Rationale:

- schools can self-correct common mistakes;
- email was made mandatory, so it must also be correctable;
- capability and access changes are central to the staff-management workflow;
- teacher competencies remain part of the same member record.

Guardrails:

- enforce global identity uniqueness and membership uniqueness;
- prevent removing the last active admin;
- hide teacher-specific fields for admin-only members;
- keep Clerk-backed access state consistent after email/access/capability edits.

Rejected alternatives:

- only teacher-domain fields editable: too restrictive for self-management;
- everything editable except email: avoids sync complexity but creates poor UX for common typo fixes.

### DR-4C Member Editing Is Transactional

Decision: member edits are draft-based and apply only when the admin clicks `Guardar`.

Rationale:

- admins can explore changes safely before committing;
- cancel/close behavior is predictable;
- validation and Clerk sync can run as one explicit save operation;
- accidental modal dismissal does not mutate access, roles, or competencies.

Rejected alternatives:

- live-save while fields change: fast but dangerous for access and role edits;
- applying partial changes on close: unpredictable and risky.

### DR-4D Save Is The Confirmation

Decision: `Guardar` is the confirmation action for launch. There is no additional review dialog after save.

Rationale:

- transactional editing already protects accidental field changes;
- the modal has a clear commit/cancel model;
- extra confirmations would slow down common member-management work;
- risky actions should be prevented or explained through validation and disabled states rather than a second dialog.

Rejected alternatives:

- conditional confirmation summaries for risky changes: safer but adds modal complexity;
- confirmation for every edit: consistent but too slow for normal changes.

### DR-4D.1 Clerk Access Operations Are Synchronous For Launch

Decision: perform Clerk invitation/access operations synchronously during `Guardar`.

Rationale:

- the app is still small and pre-launch;
- member changes are manual and one-at-a-time;
- implementation is simpler and faster;
- admins get immediate feedback about invite/access success or failure.

Known tradeoff:

- background jobs would scale better and handle transient retries more elegantly, but they add complexity that is not required for the launch baseline.

Rejected alternatives:

- background job after saving local state: more resilient but more moving parts;
- hybrid synchronous plus background retry: best long-term UX, but too complex for the first production baseline.

### DR-4D.2 Member Saves Are All-Or-Nothing

Decision: if a member save requires a Clerk access operation, the save must succeed or fail as one logical operation. Local draft changes are not committed unless the required Clerk operation succeeds. Every Clerk side effect must have a durable local access-operation record before the Clerk call. If the Clerk operation succeeds but the local commit fails, the system must attempt compensating cleanup for the Clerk side effect.

Rationale:

- matches the transactional edit modal;
- avoids local/Clerk mismatch;
- keeps the admin mental model simple: `Guardar` either worked or did not;
- reduces partial-state support cases for launch.

Compensation examples:

- revoke a just-created Clerk invitation if the local member commit fails;
- revert or reapply the previous Clerk organization role when a capability change fails locally;
- restore the previous access state when a block/restore operation fails after a Clerk-side change.

Failure handling:

- if compensation succeeds, the admin sees the original save failure and the table remains unchanged;
- if compensation fails, the admin sees a safe support-required error and structured logs must identify the local/Clerk reconciliation issue;
- the durable access-operation record must retain enough local and Clerk identifiers to retry, revoke, or reconcile the side effect;
- further access changes for the same organization/email/member are blocked until the support-required operation is resolved;
- the product must never show access `Com acesso` or `Convite pendente` state unless the corresponding Clerk side effect is known to exist.

Rejected alternatives:

- save profile changes and mark only access as failed: preserves harmless edits but creates partial-success complexity;
- split profile and access saves internally: precise but harder to explain and implement.

### DR-4E Successful Saves Close The Modal

Decision: after successful create/edit/remove/restore, close the modal, update the `Equipa` table, and show a toast.

Rationale:

- keeps admins in the list-first workflow;
- confirms the result without adding another page or success screen;
- access status chips provide immediate visible state after save.

Example toasts:

- `Membro adicionado. Convite pendente.`
- `Alteracoes guardadas.`
- `Acesso bloqueado.`
- `Membro arquivado.`

Rejected alternatives:

- keep modal open on success: useful for details but slower for normal work;
- navigate to member details page: too heavy for launch.

### DR-5 Teacher Access Mode Is Explicit

Decision: when adding a professor, the admin must choose between `Com acesso a plataforma` and `Apenas recurso de horario`.

Rationale:

- scheduling-only teachers remain valid;
- platform invitations are intentional;
- the wording is clearer than the legacy `Criar conta de acesso?` switch;
- the choice maps cleanly to Clerk-backed invitation versus local teacher resource only.

UX requirement:

- `Apenas recurso de horario` has a `?` help control explaining that the teacher is usable in scheduler/class/subject workflows but cannot sign in.

Rejected alternatives:

- access enabled by default for all teachers: simpler but risks accidental invitations;
- access disabled by default with a checkbox: familiar but easier to miss and less explicit.

### DR-5A Teacher Access Is Changed Through Member Editing

Decision: teacher access is enabled or revoked through the create/edit member modal.

Rationale:

- it matches the admin's mental model: edit the member and change whether they can sign in;
- it avoids a separate `Convidar para a plataforma` row action;
- it supports the two launch workflows cleanly:
  - create with sign-in and send access immediately;
  - create without sign-in and send access only if the admin later enables it;
- revoking access is also an edit to the same member, not a separate support-only operation.

Rejected alternatives:

- row action `Convidar para a plataforma`: visible but creates an extra lifecycle action outside the edit flow;
- invite only at creation: too rigid for schools that roll out teacher access later;
- creating a new member to grant access later: creates duplicates and breaks the source-of-truth model.

### DR-5B Revoking Teacher Access Preserves Teacher History

Decision: revoking sign-in access removes organization access but keeps the teacher profile and operational history.

Rationale:

- the teacher may still be needed as a scheduling/resource record;
- schedules, timesheets, absences, and audit history must remain intact;
- deleting the underlying identity is too destructive for normal admin workflows;
- reactivation should not require recreating the teacher.

Rejected alternatives:

- disable only the local user mirror while leaving Clerk membership untouched: creates auth mismatch risk;
- delete the Clerk user/account: too destructive and risky for support, audit, and future reactivation.

### DR-6 Admin Capability Always Requires Platform Access

Decision: selecting `Administrador` always means the member must have platform access and receive a Clerk-backed invite/access flow.

Rationale:

- an admin who cannot sign in cannot administer the organization;
- the form avoids a nonsensical no-access admin state;
- support and permission behavior remain simpler before launch.

Implications:

- admin-only members do not need teacher scheduling fields;
- `Professor + Administrador` members must have platform access, even if the teacher side would otherwise allow scheduler-only mode;
- deactivating an admin later must be handled as an access/permission action, not by deleting their historical staff record.

Rejected alternatives:

- admin without access, invited later: symmetrical with teachers but confusing because the member cannot administer anything;
- separate staff profile from admin permission: flexible but too complex for the launch baseline.

### DR-6.0 Admin Creation Uses Clerk Invitation

Decision: creating an admin member whose email does not yet have a Clerk account sends a Clerk organization invitation with role `org:admin`.

Rationale:

- standard Clerk organization membership flow;
- consistent with teacher invitations;
- no admin-set password flow is needed;
- the invited admin owns their own credentials and account recovery.

Rejected alternatives:

- create the Clerk user directly through Backend API: gives immediate user existence but complicates password/setup/email verification;
- require the person to register before being added: clunky and not a normal B2B SaaS invitation flow.

### DR-6.0A Minimal Explicit Clerk Invitation Policy

Decision: define a minimal product-level Clerk invitation policy in the PRD and leave endpoint/config mechanics to the technical specification.

Policy:

- human-initiated `Equipa` invitations use the current authenticated admin as inviter;
- `inviterUserId` comes from the current admin's Clerk user id;
- invitations are always scoped to the current Clerk organization;
- invitation role is derived from member capabilities;
- Cronos stores the current Clerk invitation id and invitation status on the organization membership;
- recognized Clerk invitation statuses are `pending`, `accepted`, `revoked`, and `expired`;
- metadata contains only safe reconciliation context, such as local organization id, membership id, and teacher profile id when applicable;
- launch uses Clerk default invitation acceptance behavior unless a safe app redirect URL already exists.

Rationale:

- avoids leaving product policy for the tech spec to invent;
- tracks who sent each invitation;
- supports idempotent reconciliation between Clerk webhooks and local member records;
- keeps the PRD out of low-level endpoint/config details that may change during implementation.

Rejected alternatives:

- fully specify every Clerk endpoint/config detail in the PRD: precise but turns the product document into technical configuration;
- leave invitation details entirely to the tech spec: too ambiguous and was flagged by audit.

### DR-6.1 Users Manage Their Own Passwords In Clerk

Decision: every invited user manages their own authentication credentials through Clerk.

Rationale:

- admins do not know or set teacher/admin passwords;
- invited users set or authenticate with their own credentials during Clerk invite acceptance;
- signed-in users can use Clerk account management to update their own password when available for their sign-in method;
- this applies to teacher-only, admin-only, and mixed-role members with platform access.

### DR-6.2 Use Clerk Default Invitation Acceptance For Launch

Decision: rely on Clerk's default invitation acceptance/account flow for launch.

Rationale:

- fastest path with least custom auth code;
- Clerk owns account creation, sign-in, and password setup;
- aligns with the decision that users manage their own credentials;
- custom branded invite acceptance can be revisited later if needed.

Rejected alternatives:

- custom Cronos `/accept-invite` ticket flow: more control but more auth complexity;
- default now and custom later is acceptable as future scope, but not required for this PRD baseline.

### DR-13 Required Clerk Webhook Coverage

Decision: this feature requires Clerk webhook coverage for organization memberships, organization invitations, users, and organizations.

Rationale:

- `Equipa` access statuses depend on invitation and membership lifecycle;
- user profile/account changes must sync to the global account model;
- organization lifecycle changes must keep tenant state consistent;
- complete event coverage reduces auth drift and support ambiguity.

Required event families:

- `organizationMembership.*`;
- `organizationInvitation.*`;
- `user.*`;
- `organization.*`.

Rejected alternatives:

- memberships and users only: smaller but weak pending/revoked invitation status;
- membership events only: too little for profile, invite, and organization lifecycle consistency.

### DR-14 Webhook Processing Is Idempotent

Decision: store processed Clerk event IDs or equivalent deduplication state so webhook retries are safe.

Rationale:

- webhook retries are expected behavior;
- access, role, invite, and membership changes must not duplicate records or side effects;
- an event log improves support/debugging for membership sync issues.

Acceptance:

- duplicate webhook deliveries do not create duplicate accounts, memberships, invitations, or teacher links;
- out-of-order webhook handling remains safe where possible;
- processed event records retain enough metadata for support diagnosis.

Rejected alternatives:

- rely only on upserts: simpler but weaker once handlers grow side effects;
- ignore idempotency for launch: unsafe for access-management webhooks.

### DR-15 Backend Authorization Changes Immediately

Decision: access and capability changes take effect immediately in backend authorization. Frontend/session refresh is best-effort UX, not the security boundary.

Rationale:

- revoked access must stop working immediately at API level;
- forcing full session revocation/sign-out is more complex than required for launch;
- stale UI is acceptable only if backend requests are denied correctly.

Rejected alternatives:

- force sign-out/revoke active sessions on every access change: strongest consistency but more complex and potentially jarring;
- apply changes only on next login: too weak for access revocation.

### DR-16 Migration Is A Clean Pre-Launch Cutover

Decision: migrate directly to the new global account, organization membership, and teacher profile baseline. Do not preserve incompatible legacy local-user semantics.

Rationale:

- the app is pre-launch;
- the PRD is the new source of truth;
- legacy local user stubs with `clerk_user_id = null` conflict with Clerk-owned identity;
- clean migration reduces long-term complexity.

Migration policy:

- valid local data may be transformed into the new model;
- incompatible local development stubs may be archived, discarded, or reset;
- tests and seeds must be updated to the new baseline;
- backward compatibility with the old teacher-create local user flow is not required.

Rejected alternatives:

- preserve all existing local user rows: unnecessary pre-launch complexity;
- skip migration and rely on manual reset only: too fragile for launch discipline.

### DR-17 Test Strategy Is Layered

Decision: use layered coverage for the `Equipa` + Clerk access feature.

Rationale:

- identity/access bugs are launch-critical;
- backend sync, webhooks, UI state, and route guards each fail differently;
- layered tests reduce regressions as Clerk integration evolves.

Minimum coverage:

- service tests for account/membership/profile creation;
- API tests for member create/edit/revoke/restore and last-active-admin guardrails;
- webhook tests for invitations, memberships, users, organizations, and idempotency;
- frontend component tests for modal transaction behavior, status chips, and mode switching;
- invite-acceptance coverage for teacher-only, admin-only, and mixed-role members using Clerk-supported test tooling or an equivalent controlled test environment.

Rejected alternatives:

- backend-only coverage: misses important UX state and route behavior;
- manual QA only: too risky for auth/access management.

### DR-17A Tests Cover All Launch Member Types

Decision: acceptance and tests must cover all launch member types: `Professor`, `Administrador`, and `Professor + Administrador`.

Rationale:

- `Equipa` is the launch staff-management baseline, not a teacher-only feature;
- admin-only and mixed-role members carry important access, routing, and last-admin rules;
- the technical specification should not be able to narrow the implementation back to teacher-first coverage;
- route guard changes are especially risky for mixed-role members because Clerk role and Cronos capabilities intentionally differ.

Required coverage:

- create/edit/revoke/archive/restore where applicable for teacher-only, admin-only, and mixed-role members;
- invitation acceptance for teacher-only, admin-only, and mixed-role members;
- capability-based route authorization for single-role and mixed-role members;
- last-active-admin guardrails for admin-only and mixed-role members;
- teacher scheduling/profile behavior for teacher-only and mixed-role members.

Rejected alternatives:

- teacher-first coverage with admin/mixed smoke tests: faster but under-tests the new `Equipa` baseline;
- leave test depth to the technical specification: lighter PRD but risks reintroducing teacher-centric drift.

### DR-18 Launch Observability Is Logs Plus Product Statuses

Decision: for launch, use structured logs and admin-visible `Equipa` statuses/errors. Do not build a dedicated support dashboard yet.

Rationale:

- enough for solo-developer troubleshooting;
- keeps implementation lean;
- Clerk Dashboard remains available for identity-level support;
- Cronos UI shows school-safe status and recovery messages.

Required log coverage:

- invite requested/created/failed;
- access revoked/restored;
- webhook received/processed/ignored/failed;
- membership linked to teacher profile;
- last-admin guardrail blocks;
- idempotent duplicate webhook ignored.

Rejected alternatives:

- internal support/debug page: useful later but extra scope before launch;
- rely only on Clerk Dashboard: misses Cronos-specific membership, teacher profile, and scheduler context.

### DR-19 Introduce Equipa/Members API Boundary

Decision: create a dedicated `Equipa`/members admin route and API boundary for staff management.

Rationale:

- staff management now covers teachers, admins, and mixed-role members;
- `/teachers` is no longer the correct canonical admin CRUD concept;
- teacher-specific endpoints remain valid for teacher self-service, availability, progress, and scheduler domain behavior;
- clean route/API boundaries reduce future cleanup.

Rejected alternatives:

- keep `/teachers` as backend/admin API while renaming frontend: faster but misleading;
- keep everything under `/teachers` for launch: fastest but conflicts with the new definitive baseline.

### DR-20 Remove Old Teachers Admin CRUD

Decision: remove the old `/teachers` admin CRUD path completely once `Equipa` is implemented.

Rationale:

- avoids two admin creation/edit paths;
- prevents legacy local-user creation behavior from surviving;
- keeps the launch baseline clean and aligned with `Equipa`;
- reduces future ambiguity for tests and frontend data hooks.

Scope retained:

- teacher self-service/domain endpoints may remain where they are genuinely teacher-specific, such as availability, progress, schedules, and scheduler references.

Rejected alternatives:

- keep old `/teachers` admin CRUD as a wrapper around new member service: compatible but preserves confusing route semantics;
- keep old `/teachers` unchanged for scheduler-only teachers: conflicts with the new source of truth.

### DR-21 API Resource Is Members

Decision: use `/members` as the API resource for `Equipa`.

Rationale:

- aligns with organization membership vocabulary;
- fits the global account plus organization membership model;
- keeps user-facing Portuguese copy separate from backend/API naming;
- avoids overloading teacher-specific domain routes.

Rejected alternatives:

- `/staff`: good school-language fit but less aligned with Clerk membership concepts;
- `/team`: friendly but less precise for access and membership semantics.

### DR-22 Members API Returns A Complete View Model

Decision: `/members` returns a complete member view model for the `Equipa` table and edit modal.

Rationale:

- keeps frontend state simple;
- centralizes guardrail/action logic in the backend;
- avoids multiple common-case fetches for account, membership, teacher profile, and invitation state;
- keeps product-safe error/action display consistent.

View model includes:

- identity fields: id, organization display name, email;
- membership fields: capabilities, lifecycle, access status;
- invitation fields: status, safe error category/message;
- teacher fields: teacher profile id and competency summary when applicable;
- action flags: allowed/blocked actions with safe reasons where needed.

Rejected alternatives:

- minimal list plus detail fetch: lighter response but more UI loading and complexity;
- separate resource objects for frontend composition: cleaner resource boundaries but too much assembly for launch.

### DR-23 Backend Contract First Implementation Sequence

Decision: implement the backend contract first, then build the `Equipa` frontend against the stable `/members` API and view model.

Rationale:

- Clerk integration correctness depends on identity, membership, invite, revocation, webhook, and guardrail behavior;
- a stable `/members` contract keeps the frontend simpler and reduces rework;
- backend service tests can prove the dangerous cases before UI polish begins;
- the solo-developer launch context favors a clear implementation order over parallel speculative work.

Suggested order:

1. data model and migration cleanup;
2. Clerk service boundary for invites, revocation, role changes, and webhook sync;
3. `/members` API contract and service tests;
4. `Equipa` frontend table/modal built against the final view model;
5. end-to-end invite acceptance and access revocation verification.

Rejected alternatives:

- frontend first with mocked behavior: faster to see but risks building assumptions the Clerk/API layer cannot safely support;
- vertical slices first: useful, but likely causes repeated edits across the same data model, service, and UI surfaces.

### DR-24 Lean Production-Ready Definition Of Done

Decision: use a lean production-ready gate for launch.

Rationale:

- the product is still pre-release and developed by a solo developer;
- the critical risks are identity correctness, invite acceptance, access revocation, and admin lockout prevention;
- advanced support tooling can be postponed because support will be handled directly through Clerk by the product owner;
- the feature should be reliable without becoming a broad internal-ops project before first launch.

Launch gate:

- member creation works for scheduler-only teachers, platform teachers, admins, and mixed-role members;
- Clerk invitations, acceptance, password ownership, and organization membership work end-to-end;
- access revocation and last-admin protection are enforced by the backend;
- no local password creation remains;
- required webhooks are idempotent;
- API/service tests cover core lifecycle and guardrails;
- invite acceptance paths are verified for teacher-only, admin-only, and mixed-role members.

Rejected alternatives:

- full hardening gate: stronger for scale but delays launch with support dashboards, replay tooling, audit UI, and broad E2E coverage;
- private beta gate: useful for staged rollout but adds temporary flags/processes instead of declaring the new `Equipa` baseline.

### DR-25 Risks Are Named With Mitigations

Decision: known launch risks are documented with mitigations, but only block launch when they violate the launch definition of done.

Rationale:

- the PRD should stay honest about Clerk, webhook, migration, and support risks;
- not every edge case should become launch scope for a solo-developer pre-release product;
- accepted risks remain visible for post-launch hardening;
- launch blockers stay tied to concrete product safety rules instead of general anxiety.

Launch-blocking examples:

- silent Clerk invite failure;
- inconsistent local/Clerk active access state;
- active login user without Clerk identity;
- ability to remove the organization's last active admin;
- backend access not revoked immediately after access is blocked.

Accepted for launch with mitigation:

- rare support recovery handled directly in Clerk by the product owner;
- delayed webhook delivery when local pending state remains honest;
- no support dashboard;
- no advanced webhook replay UI;
- no billing seat enforcement.

Rejected alternatives:

- make every known risk a launch blocker: safest but likely over-scopes the first release;
- move risks into a separate backlog only: cleaner PRD but weakens this document as the source of truth.

### DR-26 Post-PRD Sequence

Decision: after this PRD, create a technical specification, then a work breakdown structure, then implement.

Rationale:

- keeps this document focused on product decisions and launch behavior;
- gives the technical specification room to define architecture, schema, API contracts, Clerk operations, migrations, and tests;
- gives the WBS room to turn the technical specification into ordered work;
- avoids mixing product source-of-truth decisions with implementation task management.

Rejected alternatives:

- append a full implementation checklist to the PRD: convenient but blurs product and execution concerns;
- start coding directly from the PRD: faster initially but risks missing sequencing, migration, and verification details.

### DR-27 Best-Effort Role-Based First Login

Decision: after invitation acceptance and first sign-in, Cronos routes members to the correct role-based app experience once Clerk returns them to the application.

Routing:

- teacher-only members land in the teacher experience;
- admin-only members land in the admin experience;
- mixed `Professor + Administrador` members land in the admin experience and can switch to teacher mode from the sidebar.

Clerk default-flow allowance:

- if Clerk requires session setup, authentication, or organization selection before returning to Cronos, that intermediate Clerk step is acceptable for launch;
- Cronos does not promise to bypass all Clerk-controlled invitation/session tasks without a custom accept-invite flow;
- Cronos must route correctly once the user reaches the app with a valid session and organization context.

Rationale:

- keeps first login smooth and low-friction;
- respects the role/capability configured by the admin during member creation;
- avoids duplicating Clerk account/profile management inside Cronos;
- matches the launch goal of using Clerk for identity setup and Cronos for product access.

Rejected alternatives:

- hard direct-landing guarantee with no Clerk intermediate steps: cleaner UX but likely requires custom invitation/session handling;
- short welcome screen: friendlier but adds extra state and friction before the user reaches the product;
- profile confirmation step: useful for correction but duplicates Clerk account management and slows first access.

### DR-28 Reclose PRD After Accepted Audit Corrections

Decision: re-close the PRD immediately after accepted audit corrections are added, rather than keeping it visually reopened until a separate final pass.

Rationale:

- accepted audit corrections are now part of the product baseline;
- the next planned artifact remains the technical specification;
- further changes should be treated as explicit baseline amendments, not as an open-ended draft state;
- the document should not remain indefinitely reopened while individual clarifications are folded in.

Rejected alternatives:

- keep reopened until a final consistency pass: safer but keeps the source-of-truth status ambiguous;
- split unresolved audit items into a separate appendix: unnecessary while corrections are being resolved in the PRD itself.

### DR-6A Admin Access Management Requires One Active Admin

Decision: admins can manage other admins in `Equipa`, but the organization must always keep at least one active admin.

Definition:

An active admin is a current-organization membership that:

- has lifecycle `active`;
- has capability `admin`;
- has access status `active` (`Com acesso`);
- is not archived;
- is not blocked;
- is linked to a real Clerk user id.

Members with pending invites, expired invites, blocked access, archived lifecycle, scheduler-only teacher access, or sync errors do not count as active admins for this guardrail.

Rationale:

- schools can self-manage their team;
- the product avoids the lockout case where an organization has no administrator;
- the guardrail must not count people who cannot actually administer the organization;
- support through Clerk remains available for exceptional recovery rather than routine admin management.

Rejected alternatives:

- capability-only definition: too weak because archived, blocked, or pending admins could count;
- live Clerk verification on every guardrail check: strongest but creates a Clerk dependency for normal local saves and can fail during transient provider issues;
- support-only admin revocation: safest but creates unnecessary support burden;
- unrestricted admin revocation: too risky because it can lock the organization out.

### DR-6A.1 Removing Admin Capability Downgrades Access When Appropriate

Decision: removing `Administrador` is allowed when the last-active-admin guardrail passes. Mixed-role members become teacher-only if `Professor` remains selected.

Rationale:

- supports normal team management;
- preserves teacher access/profile for mixed-role members;
- keeps Clerk role aligned with broad organization authority;
- avoids support-only admin changes.

Clerk mapping:

- mixed role before removal: Clerk `org:admin`, local capabilities `admin` and `teacher`;
- teacher-only after removal with platform access: Clerk `org:member`, local capability `teacher`.

Rejected alternatives:

- archive/remove the entire member when admin is removed: wrong for mixed-role teachers;
- support-only admin removal: too restrictive for normal administration.

### DR-6B Admin Self-Editing Is Limited

Decision: admins can edit safe parts of their own member record but cannot perform self-actions that reduce their organization management access.

Rationale:

- harmless corrections should remain self-service;
- the product must prevent accidental self-lockout;
- dangerous account/permission changes should require another admin or support.

Blocked self-actions:

- remove own admin capability;
- block/revoke own access;
- archive/remove own member record;
- any equivalent action that removes current organization management ability.

Rejected alternatives:

- disallow all self-editing: safe but frustrating for harmless profile corrections;
- allow full self-editing: too dangerous because admins can lock themselves out.

### DR-7 Mixed-Role Members Use A Sidebar Mode Switcher

Decision: members with both `Professor` and `Administrador` capabilities default to admin mode and can switch to teacher mode through the sidebar.

Rationale:

- admin work remains the default for higher-privilege users;
- teacher self-service remains available without mixing all links into one noisy sidebar;
- the switch is discoverable in daily navigation;
- no Clerk account switch or sign-out is required.

Rejected alternatives:

- one combined sidebar with admin and teacher sections: visible but cluttered and less focused;
- account/profile menu switch: clean, but too hidden for a recurring workflow.

### DR-8 Equipa Uses One Unified Member Table

Decision: `Equipa` shows one unified member table with capability and access-status chips.

Rationale:

- it is the clearest source of truth for people in the organization;
- it avoids duplicate rows for mixed-role members;
- search by name/email works across the whole team;
- teacher-specific data can be summarized without turning the page back into a teacher-only view.

Rejected alternatives:

- role tabs: easier scanning, but mixed-role members can appear in multiple places;
- separate teacher/admin sections: explicit, but weakens the unified team model and complicates mixed-role editing.

### DR-8A Equipa Uses A Practical Setup Empty State

Decision: when no members beyond the current admin exist, `Equipa` shows a practical setup empty state with `Adicionar Membro`.

Rationale:

- first-time admins know the next action;
- the UI feels intentional rather than blank;
- the empty state stays operational and avoids turning into documentation.

Rejected alternatives:

- detailed model explanation: educational but too verbose for in-app UI;
- empty table only: simple but feels unfinished during onboarding.

### DR-9 Equipa Uses Separate Lifecycle And Access Status Axes

Decision: `Equipa` models member lifecycle separately from platform access.

Lifecycle states:

- `active`, displayed as `Ativo`;
- `archived`, displayed as `Arquivado`.

Access states:

- `none`, displayed as `Sem acesso`;
- `pending_invite`, displayed as `Convite pendente`;
- `invite_expired`, displayed as `Convite expirado`;
- `active`, displayed as `Com acesso`;
- `blocked`, displayed as `Acesso bloqueado`;
- `sync_error`, displayed as `Erro de sincronização`.

Rationale:

- archive/restore is not the same concept as platform access;
- failed create/edit saves should remain modal errors because all-or-nothing saves leave the table unchanged;
- invitation expiry needs a real state that is not the same as no access or blocked access;
- sync errors are retry/reconciliation states, not ordinary invite failures.

Rejected alternatives:

- one simple status enum: easier UI but mixes lifecycle, access, invitation, and error concepts;
- one expanded mega-status enum: precise at first but grows messy as archive, restore, expiry, and sync states interact.

### DR-9A Save And Sync Error Recovery Is Contextual

Decision: modal save failures and persisted `Erro de sincronização` states show safe, non-technical explanations and next actions based on the error category. Persisted sync errors allow a safe retry first, then support escalation if retry fails.

Rationale:

- different failures require different recovery paths;
- edit-and-save is not always the right baseline action;
- admins need clarity without Clerk internals;
- the product should avoid leaking sensitive identity or provider information.

Recovery examples:

- network/transient save failure: show a retry action in the modal;
- invalid email: direct the admin to edit the email before saving again;
- provider/configuration/permission failure: ask the admin to contact support;
- persisted sync error: show `Tentar novamente`; if retry succeeds, return to the correct state;
- unresolved sync error after retry: ask the admin to contact support and prevent misleading access labels;
- unknown failure: offer safe retry or support escalation.

Blocked while unresolved:

- email changes;
- capability changes;
- access toggles;
- remove/archive/restore actions;
- any action that could worsen the local/Clerk mismatch.

### DR-9B Resend Creates A Fresh Invitation

Decision: `Reenviar convite` is available inside the edit/member details modal for `Convite pendente` and `Convite expirado` members, and it creates a fresh Clerk invitation.

Behavior:

- for `Convite pendente`, revoke the current pending Clerk invitation when possible, then create a new invitation;
- for `Convite expirado`, create a new invitation;
- store the new Clerk invitation id/status on the same organization membership;
- do not create duplicate members or memberships;
- use the current member email, current organization, current capabilities, and current inviter admin.

Rationale:

- keeps normal access lifecycle actions inside the member management flow;
- avoids cluttering the unified table with row actions;
- gives schools self-service recovery for pending or expired invitations;
- makes the admin meaning of resend clear: send a fresh invitation.

Rejected alternatives:

- keep pending invites and recreate only expired invites: fewer Clerk operations but does not match the admin expectation of a fresh invite;
- table row action: faster but adds access lifecycle controls to the table;
- support-only resend: safe but unnecessary support burden.

### DR-9C Seats Count Active Platform Access Only

Decision: only members with access status `Com acesso` count as seats for future billing/subscription limits.

Rationale:

- scheduler-only teachers do not consume login/self-service product access;
- pending, expired, sync-error, blocked, and archived states are not usable active access;
- blocked and archived members do not count as active paid seats;
- this policy remains compatible with future organization-level seat-limit plans.

Rejected alternatives:

- count every `Equipa` member: simpler, but unfair for scheduler-only teacher resources;
- count only admins for now: conservative, but not future-proof for teacher self-service.

### DR-9D Billing Enforcement Is Out Of Scope

Decision: define seat-counting policy only. Do not implement billing, checkout, plan gating, or seat-limit enforcement in this PRD.

Rationale:

- keeps scope focused on `Equipa`, Clerk identity, and access lifecycle;
- avoids pulling a separate billing project into launch-critical auth work;
- preserves a clear future billing rule without implementing it prematurely.

Rejected alternatives:

- manual seat-limit enforcement now: prepares monetization but adds plan/limit edge cases;
- full Clerk Billing integration now: production-grade but too much scope for this feature.

### DR-10 Member Removal Preserves History

Decision: `Remover` hard deletes only members with no operational-history blockers; otherwise it archives them.

Hard-delete eligibility:

- no schedules, lessons/classes, class assignments, timesheets, absences, audit logs, accepted/past Clerk membership, historical access events, or other persisted operational records are linked to the member, membership, account, or teacher profile;
- no active, accepted, past-access, blocked-access, or sync-error platform access exists;
- any pending Clerk invitation can be revoked before local deletion;
- teacher-subject competency links alone do not block hard delete if they have not been used by scheduler/class/lesson/history records.

Archive behavior:

- archive the organization membership;
- revoke/block platform access when applicable;
- preserve account, membership, teacher profile, and historical links required for audit and operational records;
- hide the member from the default `Equipa` view.

Rationale:

- schedules, timesheets, absences, and audit trails must remain trustworthy;
- accidental/test members can still be cleaned up when they have no history;
- access is revoked when a member is archived;
- the product avoids destructive deletion for records already used operationally.

Rejected alternatives:

- never delete, only archive: safest but creates clutter for mistakes and test records;
- always hard delete: simple but dangerous after operational links exist;
- admin chooses hard delete or archive manually: flexible but increases accidental data-loss risk.

### DR-11 Archived Members Are Hidden By Default

Decision: archived members are hidden from the default `Equipa` table and can be shown with `Mostrar arquivados`.

Rationale:

- daily team management stays focused on active/current members;
- archived records remain recoverable and auditable;
- the unified table model remains intact without a separate archive page.

Rejected alternatives:

- show archived members in the main table by default: transparent but cluttered over time;
- separate `Arquivo` tab: clean but adds navigation complexity and weakens the single-list model.

### DR-12 Archived Members Can Be Restored

Decision: archived members can be restored from `Mostrar arquivados`.

Rationale:

- staff can return in later terms;
- accidental archive actions can be corrected;
- historical continuity is preserved;
- recreation would risk duplicates and broken context.

Access rule:

- restoration is a saved modal action.
- restoration brings the member back to the active list only after validation and any required Clerk access operation succeeds.
- teacher-only scheduler resources can be restored with `Sem acesso`.
- admin-capable members cannot be restored as active admin-capable members with `Sem acesso` or `Acesso bloqueado`.
- restoring an admin-capable member must either start/restore the Clerk-backed invite/access flow or remove `Administrador` during the restore save when guardrails allow.
- access follows the member's final capabilities and the normal access-mode workflow.

Rejected alternatives:

- archived members are read-only forever: safe but poor for returning staff or mistakes;
- support-only restore: controlled but unnecessary support burden;
- restore lifecycle first and fix admin access later: simpler, but creates an active admin-capable member in an invalid no-access state.

### DR-30 Webhook Metadata Is Helpful But Not Required

Decision: Clerk invitation metadata is used when available, but Cronos must also reconcile webhook events through stored Clerk invitation ids, Clerk organization ids, Clerk user ids, verified email, and durable local access-operation records.

Rationale:

- Clerk membership webhook payloads may not contain the original invitation metadata;
- launch correctness cannot depend on one optional metadata path;
- webhook reconciliation must fail safely when the local target is ambiguous.

Rejected alternatives:

- depend only on invitation metadata: simpler, but brittle if membership events do not carry it;
- auto-create product members from unmatched Clerk memberships: convenient for support edits, but unsafe for tenant isolation and product permissions.

### DR-31 External Clerk Changes Reconcile Conservatively

Decision: changes made directly in Clerk outside Cronos do not silently change Cronos product capabilities. Clerk remains authoritative for whether organization access exists, while Cronos remains authoritative for product permissions and teacher/admin capabilities.

Rationale:

- the product owner may use Clerk for support, but schools manage members through `Equipa`;
- a direct Clerk role upgrade must not grant admin product access unless Cronos local capabilities say so;
- a direct Clerk membership removal means access cannot honestly remain active in Cronos.

Rules:

- unmatched Clerk memberships do not create product capabilities automatically;
- Clerk membership removal blocks or sync-errors local access and backend authorization denies access;
- Clerk role mismatch marks `sync_error` until retry/support reconciliation resolves it;
- last-active-admin checks do not count blocked, mismatched, or no-Clerk-id admin-capable members.

Rejected alternatives:

- import all Clerk role changes into Cronos capabilities: simple for support, but risks accidental permission grants;
- ignore external Clerk changes until the next admin edit: simpler, but leaves misleading access state;
- make Cronos overwrite Clerk automatically on every drift event: stronger consistency, but risky during support recovery and transient Clerk/webhook timing.

### DR-29 Baseline Language Is Normative

Decision: launch behavior in this PRD must use required language. The technical specification can choose implementation mechanics, but it must not soften the product baseline for `Equipa`, `/members`, Clerk invitation/access behavior, routing, logging, test coverage, or launch readiness.

Rationale:

- this PRD is the closed product source of truth for the launch baseline;
- ambiguous words such as "recommended" or "where feasible" can cause the implementation plan to underbuild critical auth and access behavior;
- a solo-developer launch benefits from clear must-have requirements before moving into technical specification and WBS.

Rejected alternatives:

- leave soft wording for the technical specification to interpret: flexible, but risks reintroducing ambiguity after the audit corrections;
- rewrite the full PRD into a shorter canonical version now: cleaner, but unnecessary before technical specification because the existing decision record already captures the baseline.
