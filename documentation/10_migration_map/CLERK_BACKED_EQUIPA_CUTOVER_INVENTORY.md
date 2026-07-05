# Clerk-Backed Equipa Cutover Inventory

Source of truth: `documentation/01_product_strategy/PRD_CLERK_TEACHER_USER_CREATION.md`,
`documentation/01_product_strategy/TECH_SPEC_CLERK_BACKED_EQUIPA_MEMBER_MANAGEMENT.md`, and
`documentation/01_product_strategy/WBS_CLERK_BACKED_EQUIPA_MEMBER_MANAGEMENT.md`.

## WBS 0 Inventory

- `frontend/src/pages/Teachers.jsx`: legacy visible admin staff-management CRUD. Rewrite/delete during WBS 13 after `/members` covers launch staff management.
- `frontend/src/components/Forms/TeacherForm.jsx`: legacy password and `create_user_account` UI. Rewrite/delete during WBS 13; no launch member modal may ask for passwords.
- `frontend/src/components/DefaultLayout.jsx`: visible `Professores` admin navigation. Rewrite during frontend implementation to `Equipa` at `/members`.
- `frontend/src/App.jsx`: admin `/teachers` route. Replace with `/members`; keep teacher self-service routes.
- `frontend/src/hooks/useSchoolData.js`: legacy `teachers` CRUD hooks are valid only for domain reads until removed from staff-management UI.
- `backend/app/api/v1/endpoints/teachers.py`: keep `/teachers/me/...`, observability, and teacher availability/domain operations; quarantine admin create/update/delete staff-management writes.
- `backend/app/services/teacher_service.py`: legacy local login stub creation and best-effort Clerk invite path. Stop using it for canonical staff management; `/members` owns launch member writes.
- `backend/app/schemas.py`: `TeacherCreate.create_user_account` and `TeacherUpdate.create_user_account` are legacy teacher CRUD fields, not valid in `/members`.
- `backend/app/api/deps.py`: legacy authorization currently resolves through `user.role`, `user.teacher_id`, and `is_active`. Rewrite to membership-aware auth during WBS 1.
- RLS migration `f4a9b2c8d1e7_tenant_hardening_rls.py`: contains old role mapping from Clerk roles. Replace in the membership cutover migration.
- Tests referencing `TeacherForm`, `create_user_account`, local active teacher users, or admin `/api/v1/teachers` writes: rewrite under WBS 11/12 to assert `/members`.
- Documentation outside the three source-of-truth docs that presents visible admin `Professores` CRUD or password setup as launch behavior: update, mark historical, or delete during WBS 14.

Teacher self-service and scheduler/domain use remain valid when they operate on local `teacher` capability/profile semantics:

- `/api/v1/teachers/me/availability`
- `/api/v1/teachers/me/progress`
- `/api/v1/teachers/{teacher_id}/availability`
- teacher profile reads for scheduler, lessons, classes, substitutions, progress, and operational history

## Clerk Backend API Capability Notes

The Clerk organization API supports the launch operations needed by this baseline:

- create organization invitations for a specific organization with `role` and inviter (`inviterUserId` in SDK, `inviter_user_id`/equivalent Backend API field);
- revoke organization invitations with `requesting_user_id`;
- create/update/remove organization memberships using `org:member` and `org:admin`;
- read users, organization memberships, and organization invitations for webhook and first-login reconciliation.

The implementation wraps these operations in `ClerkAccessService`; if SDK support is missing for inviter or revoker attribution in this project version, the service must use Clerk REST Backend API directly.

## Clerk Instance Configuration Gate

Before launch cutover in any persistent environment, record the Clerk instance/environment, organization id, membership mode, role names, current admin test account, and invitation setting verification in the cutover report. Launch remains blocked if organizations are disabled, active organization context is unavailable after sign-in, or `org:admin`/`org:member` cannot be used for organization invitations.
