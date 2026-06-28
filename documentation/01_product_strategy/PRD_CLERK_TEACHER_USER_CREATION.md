# PRD - Clerk Teacher User Creation

## 1. Metadata

- Status: draft for implementation planning.
- Feature: integrate Clerk-backed user creation into the staff management flow, replacing the visible `/teachers` product concept with `Equipa`.
- Product area: teacher access, organization membership, authentication.
- Primary user: school admin.
- Secondary user: teacher invited to the platform.
- Owner context: solo developer, pre-launch product in final launch stage.

## 2. Problem

Clerk already owns sign-in, sign-out, organization creation, organization membership, role-based navigation, request authentication, and webhook sync. The teacher creation flow in `/teachers` still creates a local `User` row directly and only attempts a best-effort Clerk organization invitation afterwards.

This leaves the product in an unsafe pre-production state:

- the admin can create a teacher in the UI, but the login/access identity is not guaranteed to exist in Clerk;
- the frontend asks for a password even though the backend ignores it;
- local users can be created with `clerk_user_id = null`;
- Clerk webhooks later create or sync users by real `clerk_user_id`, which can conflict with or bypass the local stub;
- the UI reports account activity from local state, not from a guaranteed Clerk source of truth.

The target behavior is that the admin creates teachers normally, while Clerk owns identity creation/invitation/membership and the local database stores only the required application mirror and teacher-domain link.

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

1. Admins can create teachers from `/teachers` with no mental model change.
2. Clerk is the source of truth for teacher login identity and organization membership.
3. The local database stores the teacher domain profile and a synced app-user mirror, not independent credentials.
4. A teacher invite acceptance results in exactly one local active app user linked to exactly one local teacher in the correct organization.
5. Invitation failures are visible to the admin and do not silently create misleading active accounts.
6. The implementation is small enough to land safely before first launch.

## 5. Non-Goals

- Building a custom teacher sign-up form.
- Letting admins set teacher passwords directly.
- Supporting student users.
- Building a full user-management console beyond teacher creation/access status.
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

`Equipa` shows one unified member table. Each member appears once, even if they have both teacher and admin capabilities. Capabilities and access states are shown as compact chips, and teacher-specific details such as competencies are summarized in the row and managed through edit/details UI.

Teacher competencies are optional at creation but visibly flagged when missing.

The launch access statuses shown in `Equipa` are:

- `Sem acesso`;
- `Convite pendente`;
- `Ativo`;
- `Acesso bloqueado`;
- `Erro no convite`.

When `Erro no convite` appears, the UI must include a clear, non-technical explanation and a contextual next action. The message must not expose sensitive Clerk details, account existence outside the organization, secrets, raw provider responses, or stack traces. Recovery depends on the cause:

- transient/network issue: ask the admin to try again;
- invalid or unreachable email issue: ask the admin to check/edit the email;
- permission/configuration issue: ask the admin to contact support;
- unknown issue: provide a safe retry/support path.

Member type is modeled as capabilities, not as one mutually exclusive role. The launch capabilities are:

- `Professor`;
- `Administrador`;
- `Professor + Administrador`.

Teacher-specific fields appear only when `Professor` is selected. Admin-specific access confirmation appears when `Administrador` is selected.

Every member requires an email address at creation time, including teacher-only members without platform access. Email remains editable after creation.

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

Email identifies a global person/account, not a per-organization duplicate identity. Organization access and permissions are represented as memberships scoped to each organization.

When an admin adds or invites an email that already belongs to an existing global account, the UI must not disclose whether the account exists elsewhere. The admin sees only the result for the current organization, using the normal product access statuses.

When `Administrador` is selected, platform access is mandatory. There is no scheduler-only or no-access admin member state.

Admins can manage other admins from `Equipa`, but the organization must always retain at least one active admin.

Removing a member is safe by default. Members with operational history are deactivated/archived, while members with no meaningful history can be hard deleted.

Archived members are hidden from the default `Equipa` table and can be shown with a `Mostrar arquivados` filter.

Archived members can be restored from the archived view. Restoring returns the member to the active `Equipa` list but does not silently restore platform access; access must follow the normal access-mode rules.

Members with both `Professor` and `Administrador` capabilities land in the admin experience by default. They can switch between admin and teacher experiences through an in-app sidebar mode switcher. This switch is not a Clerk account switch and does not require signing out; it only changes the visible navigation and default work area for the same authenticated member.

The old `/teachers` concept may remain as an internal route or compatibility implementation detail only if it does not leak into the launch UX. Any visible copy, navigation, page title, empty state, and documentation should use `Equipa` for the broader staff-management area.

### 6.1 Create Teacher Without Platform Access

The admin can create a teacher as a scheduling/resource profile without sending an invitation.

Expected UX:

- admin fills name, email, and competencies;
- admin leaves platform access disabled;
- system creates the local teacher profile only;
- the teacher appears in scheduling workflows;
- the table shows an access state equivalent to `Sem acesso` or `Nao convidado`, not `Inativo` as if a disabled login existed.

### 6.2 Create Teacher With Platform Access

The admin can create a teacher and invite them to the current Clerk organization.

Expected UX:

- admin fills name, email, and competencies;
- admin enables platform access;
- no password field is shown;
- backend creates the teacher profile and sends/creates the Clerk invitation;
- table shows `Convite pendente`;
- when the teacher accepts the invitation, Clerk creates membership and webhook sync links the local user to the teacher;
- teacher can sign in through Clerk and lands in teacher-only routes.

### 6.3 Failure UX

If Clerk invitation creation fails:

- the admin receives a clear error;
- no local record should claim the teacher has active login access;
- the admin can retry invitation after fixing config/network/email issues.

If teacher profile creation succeeds but invitation fails after the local transaction:

- the teacher profile may remain as a scheduling resource;
- access state must be explicit: `Convite falhou` or `Sem acesso`;
- retry must be possible without creating duplicate teachers or users.

## 7. Product Requirements

### PR-1 Source of Truth

Clerk must be the source of truth for authentication identity and organization membership.

Acceptance:

- local `User.clerk_user_id` is non-null for every teacher who can sign in;
- local `User` rows for teacher access are created or completed from Clerk membership/webhook/BAPI sync;
- local-only `User` rows are not created as active login identities.

### PR-2 Admin Teacher Creation

The admin must still create teachers from `/teachers` using the existing modal pattern.

Acceptance:

- the admin can create a teacher with name, email, and competencies;
- existing scheduling resource behavior remains intact;
- existing teacher subject link behavior remains intact;
- existing tenant isolation remains intact.

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

### PR-2A.1 Teacher Competencies

Teacher competencies are optional at member creation but must remain visible as scheduler readiness data.

Acceptance:

- a professor can be created without competencies;
- competencies can be added or edited later;
- professor rows without competencies show a visible warning/status such as `Sem competencias`;
- scheduler/preflight readiness can identify teachers without competencies;
- admin-only members do not show competencies.

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
- the local teacher profile remains available for schedules, subjects, classes, timesheets, absences, and history;
- historical records are not deleted;
- the underlying Clerk identity is not deleted as part of normal revocation;
- re-enabling access later can reuse or restore the member's access without duplicate teacher records.

### PR-2D Admin Access Mode

For members with `Administrador` capability, platform access is mandatory.

Acceptance:

- selecting `Administrador` automatically requires Clerk-backed platform access;
- no UI state allows creating an admin-only member without access;
- if a member is `Professor + Administrador`, admin access requirement wins and the member must be invited to the platform;
- admin-only members do not show teacher-specific scheduling fields.

### PR-2D.1 Admin Access Revocation Guardrail

Admin access can be revoked only when at least one other active admin remains in the organization.

Acceptance:

- admins can revoke another admin's access from `Equipa`;
- the system blocks revoking the last active admin;
- the UI explains why the action is blocked;
- the same last-admin guardrail applies to deleting, deactivating, or changing capabilities for admin members;
- support intervention through Clerk remains possible for exceptional cases, but is not the normal product path.

### PR-2F Member Removal

Removing a member must preserve operational history.

Acceptance:

- members with no meaningful operational history can be hard deleted;
- members linked to schedules, classes, subjects, timesheets, absences, audit logs, or other operational records are deactivated/archived instead of hard deleted;
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
- restoring a member returns them to the default active `Equipa` list;
- restoring a member preserves historical links;
- restoring does not automatically restore platform access unless required by current capabilities and explicitly confirmed through the normal access flow;
- restoring an admin-capable member still respects admin access and last-active-admin rules;
- if email or access state conflicts exist, the UI gives a clear non-technical message.

### PR-2E Mixed-Role Experience Switching

Members with both `Professor` and `Administrador` capabilities must be able to switch between focused app experiences.

Acceptance:

- mixed-role members land in admin mode by default after sign-in;
- mixed-role members see a sidebar mode switcher with admin and teacher modes;
- admin mode shows admin navigation;
- teacher mode shows teacher navigation;
- switching modes does not sign out, change Clerk organization, or require a second account;
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

- admins can edit member name;
- admins can edit member email;
- admins can edit member capabilities;
- admins can edit teacher access mode for members with `Professor` capability;
- admins can edit competencies/subjects for members with `Professor` capability;
- admin-only members do not show teacher competency fields;
- email edits enforce global identity uniqueness, organization membership uniqueness, and Clerk sync requirements;
- capability edits enforce the last-active-admin guardrail;
- access edits enforce the teacher access lifecycle rules.

### PR-2B.4 Existing Global Account Privacy

Adding or inviting a member must not reveal whether the email already belongs to another Cronos/Clerk account outside the current organization.

Acceptance:

- the admin sees the same neutral create/invite flow for new and existing global accounts;
- success states are expressed only for the current organization, such as `Convite pendente` or `Ativo`;
- error messages do not reveal membership in another organization;
- behind the scenes, existing global identities are attached/invited to the current organization through the membership model;
- duplicate membership in the same organization is still prevented.

### PR-2B.1 Unified Member List

`Equipa` must be a single source-of-truth list for organization members.

Acceptance:

- all members appear in one unified table;
- a mixed-role member appears once, not separately as a teacher and admin;
- capability chips show whether the member is `Professor`, `Administrador`, or both;
- access status chips show whether the member has no access, pending invite, active access, inactive access, or failed invite;
- table search covers at least name and email;
- filters can narrow by capability and access state without changing the underlying source of truth.

### PR-2B.2 Access Status Vocabulary

`Equipa` must use product-level access statuses rather than Clerk implementation details.

Acceptance:

- `Sem acesso` means the member exists in Cronos but cannot sign in;
- `Convite pendente` means a Clerk-backed invitation/access flow has started but the member has not completed access;
- `Ativo` means the member can sign in to the organization;
- `Acesso bloqueado` means the member previously had access but it is currently revoked/disabled;
- `Erro no convite` means access setup failed and requires admin action or support;
- no Clerk-specific status label is required for launch unless it is translated into one of these product statuses.

### PR-2B.2A Invite Error UX

Invite/access setup failures must be understandable and safe for school admins.

Acceptance:

- `Erro no convite` is always paired with a non-technical message;
- the message explains what the admin can do next;
- transient failures can show a retry action;
- email-related failures guide the admin to correct the email;
- support-required failures ask the admin to contact support;
- messages do not reveal sensitive provider details, raw Clerk errors, stack traces, secrets, or cross-organization account existence.

### PR-3 No Admin-Set Password

The teacher creation UI must not ask the admin to set a teacher password.

Acceptance:

- `TeacherForm` removes the password field;
- backend create/update schemas do not accept or rely on password;
- tests assert no password field appears in create-teacher flow.

### PR-4 Invitation Lifecycle

The system must model teacher access lifecycle separately from teacher resource existence.

Minimum states:

- no access requested;
- invitation pending;
- active;
- inactive/deactivated;
- invitation failed or needs retry.

Acceptance:

- `/teachers` table displays a state derived from Clerk/local sync data;
- active means the teacher has a local user mirror linked to a real Clerk user and the current organization;
- pending means invitation was created but no accepted membership has synced yet.

### PR-5 Idempotency

Create/invite/retry operations must be idempotent for the same organization, teacher, and email.

Acceptance:

- retrying a failed invite does not create duplicate teachers;
- repeated Clerk webhooks do not create duplicate users;
- accepting an invitation links to the intended `teacher_id`;
- the same email cannot create duplicate local account identities or leave one local stub plus one Clerk-backed user.

### PR-6 Teacher Login

After accepting the invite, the teacher can sign in through Clerk and use teacher routes.

Acceptance:

- Clerk membership role maps to local app role `teacher`;
- authenticated teacher has `current_user.teacher_id`;
- `/teachers/me/availability`, `/my-availability`, `/my-schedules`, and `/my-progress` work for the invited teacher;
- teacher cannot access admin `/teachers`.

## 8. Technical Requirements

### TR-1 Backend Create Flow

`teacher_service.create_teacher()` must stop creating active local users with `clerk_user_id = null`.

Target behavior:

- create the `Teacher` row and subject links in the local transaction;
- when access is requested, create a Clerk organization invitation or equivalent Clerk-backed invite operation;
- store enough local access metadata to show pending/retry status;
- rely on membership webhook or synchronous Clerk fallback to create/link the local `User` with real `clerk_user_id`.

### TR-2 Clerk Invitation Metadata

Clerk invitation or membership creation must carry the local teacher link.

Required metadata:

- local `teacher_id`;
- local `organization_id` or enough context to validate it;
- intended app role `teacher` if needed.

Acceptance:

- webhook handler receives `teacher_id` and links the local `User.teacher_id`;
- mismatched org/teacher metadata is rejected or ignored safely.

### TR-3 Local Data Model

The local model must distinguish:

- `Teacher`: scheduling/domain resource;
- `User`: authenticated app mirror of a Clerk user;
- teacher access invitation/status: pending/error/retry metadata.

Implementation may use one of these approaches:

- add explicit invitation/access fields to `Teacher`;
- add a dedicated `teacher_access_invitation` table;
- use a small user-access table if aligned with future user management.

Acceptance:

- no production UI depends on a fake local user to show pending access;
- invitation status can be queried with the teacher list.

### TR-4 Webhook Compatibility

Existing Clerk webhook behavior must remain the sync authority.

Acceptance:

- `organizationMembership.created` with teacher metadata creates or updates exactly one local user;
- `user.created` without membership does not create orphan users;
- `organizationMembership.deleted` or `user.deleted` deactivates access without deleting teacher scheduling history.

### TR-5 API Contract

Teacher create/update API must expose access intent and status clearly.

Recommended request fields:

- `name`;
- `email`;
- `subject_ids`;
- `invite_to_platform` or replacement for `create_user_account`.

Recommended response fields:

- `id`;
- `name`;
- `email`;
- `subject_ids`;
- `access_status`;
- `clerk_user_id` only if useful for admin/debug display, not required in normal UI;
- `invitation_status` or `invitation_error` when applicable.

Acceptance:

- `create_user_account` is either migrated to a clearer name or preserved as a compatibility alias with no password semantics;
- frontend uses the response instead of guessing from `User.is_active` alone.

### TR-6 Error Handling

Clerk failures must not be swallowed silently.

Acceptance:

- backend logs structured Clerk invitation errors;
- API returns clear failure status or stores retryable failure state;
- frontend shows actionable message to admin;
- no account is displayed as active when Clerk invitation failed.

## 9. Security Requirements

1. Only active admins in the current Clerk organization can invite teachers.
2. A teacher invitation must only target the admin's current organization.
3. A teacher cannot self-link to another teacher profile.
4. Webhook teacher metadata must be validated against the local organization.
5. The system must not persist or transmit admin-entered teacher passwords.
6. Deactivation must preserve scheduling and audit history.
7. Tenant isolation tests must cover invited teacher access.

## 10. Observability Requirements

Minimum events/logs:

- teacher profile created;
- teacher invite requested;
- Clerk invitation created;
- Clerk invitation failed;
- membership webhook linked user to teacher;
- webhook ignored due to invalid/missing teacher metadata;
- teacher access deactivated.

Minimum metrics or dashboard-ready counters:

- invite success count;
- invite failure count;
- pending invites older than threshold;
- webhook link success count;
- login failures caused by missing `teacher_id`.

## 11. Migration And Cleanup

Because the app has not launched, implementation can favor a clean cutover over backwards compatibility.

Required cleanup:

1. Find local teacher users with `clerk_user_id IS NULL`.
2. Decide whether each should become:
   - a teacher-only domain profile with no access;
   - a pending Clerk invite;
   - a deleted local stub if duplicate/invalid.
3. Remove password UI and tests that imply local credential creation.
4. Remove or quarantine local `user_service.create_user()` usage from teacher creation.
5. Add a regression that proves no active teacher login user exists without `clerk_user_id`.

## 12. Acceptance Matrix

| Area | Acceptance criteria |
| --- | --- |
| Admin create no access | Teacher profile is created, competencies saved, no active local user with null Clerk ID exists. |
| Admin create with access | Clerk invitation is created for current organization and local status becomes pending. |
| Invite acceptance | Clerk webhook creates/updates one local user with real `clerk_user_id`, role teacher, correct `teacher_id`, correct org. |
| Teacher login | Invited teacher can sign in and access teacher-only pages. |
| Admin route protection | Teacher cannot access `/teachers`; admin can. |
| Password removal | No teacher password field exists in UI, API contract, or tests. |
| Failure handling | Clerk failure is visible and retryable; UI never claims active account after failed invite. |
| Idempotency | Repeated create/retry/webhook events do not create duplicate teachers or duplicate users. |
| Tenant isolation | Teacher invite/link cannot cross organizations. |
| Existing scheduling | Teacher resource still works in subjects, availability, lessons, schedules, and timesheets. |

## 13. Test Plan

### Frontend

- Teacher form renders no password field.
- Creating a teacher without access sends no invite flag.
- Creating a teacher with access sends the invite/access flag.
- Teacher table renders no-access, pending, active, inactive, and failed states.
- Role guards still route admin and teacher correctly.

### Backend

- `POST /teachers/` without access creates only the teacher domain profile.
- `POST /teachers/` with access calls Clerk invitation service.
- Clerk invitation failure is captured and returned or stored.
- Webhook membership with `teacher_id` links user to teacher.
- Webhook membership missing `teacher_id` does not accidentally grant teacher self-service access.
- Duplicate webhook events are idempotent.
- Local active teacher user with `clerk_user_id = null` is rejected or impossible.

### End-to-End

- Admin creates teacher and invites them.
- Teacher accepts Clerk invitation.
- Teacher signs in and lands in teacher UX.
- Teacher updates availability.
- Admin sees teacher remain available as scheduling resource.

## 14. Open Decisions

1. Should teacher access invitations be tracked on `Teacher` or in a dedicated table?
2. Should invite retry be an explicit row action in `Equipa` at launch, or can it be handled by re-saving the staff member?
3. Should the create flow fail the entire teacher creation if Clerk invitation fails, or preserve the teacher as a no-access resource with failed invite status?
4. Should `create_user_account` be renamed now to `invite_to_platform`, or kept as a compatibility alias for one release?

## 15. Recommended Launch Decision

For first launch, prefer this policy:

1. Keep teacher profile creation independent from platform access.
2. Remove admin-entered password entirely.
3. Rename the switch to a clear invitation action in the UI.
4. When access is enabled, create the teacher, create a Clerk invitation, and show pending.
5. Let Clerk webhook/BAPI sync create the local user mirror with real `clerk_user_id`.
6. Add a retry invite action before launch if invitation can fail after teacher creation.

This keeps the admin workflow simple while making Clerk the identity authority.

## 16. Decision Record

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
- implementation may keep internal `/teachers` routes temporarily only if launch UX and documentation use the new baseline.

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

### DR-4A.1 Existing Account Disclosure Is Neutral

Decision: the admin UI must not disclose whether an email already belongs to a global account outside the current organization.

Rationale:

- avoids leaking platform membership or another school's relationship with that email;
- supports the global account plus organization-membership model;
- keeps the admin focused on the current organization outcome;
- reduces account-enumeration risk.

Rejected alternatives:

- show `Existing Cronos account found`: transparent but leaks cross-organization account existence;
- block and require support: safe but contradicts self-service membership management.

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

### DR-6A Admin Access Management Requires One Active Admin

Decision: admins can manage other admins in `Equipa`, but the organization must always keep at least one active admin.

Rationale:

- schools can self-manage their team;
- the product avoids the lockout case where an organization has no administrator;
- support through Clerk remains available for exceptional recovery rather than routine admin management.

Rejected alternatives:

- support-only admin revocation: safest but creates unnecessary support burden;
- unrestricted admin revocation: too risky because it can lock the organization out.

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

### DR-9 Equipa Uses Simple Product Access Statuses

Decision: the launch statuses are `Sem acesso`, `Convite pendente`, `Ativo`, `Acesso bloqueado`, and `Erro no convite`.

Rationale:

- statuses are understandable to school admins;
- they cover no-access, pending, active, revoked, and failed flows;
- they avoid exposing Clerk lifecycle internals in the product UI;
- they provide enough visibility for solo-developer support.

Rejected alternatives:

- detailed lifecycle statuses: precise but too noisy for launch;
- binary `Com acesso` / `Sem acesso`: too simple and hides pending/failure states.

### DR-9A Invite Error Recovery Is Contextual

Decision: `Erro no convite` does not have one universal recovery workflow. The UI shows a safe, non-technical explanation and a next action based on the error category.

Rationale:

- different failures require different recovery paths;
- edit-and-save is not always the right baseline action;
- admins need clarity without Clerk internals;
- the product should avoid leaking sensitive identity or provider information.

Recovery examples:

- network/transient failure: show a retry action;
- invalid email: direct the admin to edit the email;
- provider/configuration/permission failure: ask the admin to contact support;
- unknown failure: offer safe retry or support escalation.

### DR-10 Member Removal Preserves History

Decision: `Remover` hard deletes only members with no meaningful operational history; otherwise it deactivates/archives them.

Rationale:

- schedules, timesheets, absences, and audit trails must remain trustworthy;
- accidental/test members can still be cleaned up when they have no history;
- access is revoked when a member is archived;
- the product avoids destructive deletion for records already used operationally.

Rejected alternatives:

- never delete, only archive: safest but creates clutter for mistakes and test records;
- always hard delete: simple but dangerous after operational links exist.

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

- restoration brings the member back to the active list but does not silently restore sign-in access. Access follows the member's capabilities and the normal access-mode workflow.

Rejected alternatives:

- archived members are read-only forever: safe but poor for returning staff or mistakes;
- support-only restore: controlled but unnecessary support burden.
