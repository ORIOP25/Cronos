# Members and Access

## Purpose

This document describes organization membership, capabilities, teacher profiles, and Clerk synchronization.

## Intended Reader

This document targets backend and frontend engineers implementing access control.

## Prerequisites

Read [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md).

## What the System Does

Clerk provides identity and organization membership.
Cronos stores local membership state, capabilities, access mode, and teacher linkage.

## Why the Behavior Exists

Local state supports tenant queries, route guards, operational permissions, and recovery after provider synchronization failures.

## Components and Ownership

| Area | Implementation |
| :--- | :--- |
| Access models | `backend/app/models.py` |
| Auth dependencies | `backend/app/api/deps.py` |
| Member API | `backend/app/api/v1/endpoints/members.py` |
| Clerk webhook | `backend/app/api/v1/endpoints/webhooks.py`, `backend/app/services/member_webhook_service.py` |
| Clerk sync | `backend/app/services/clerk_sync.py`, `backend/app/services/member_reconciliation_service.py` |
| Access operations | `backend/app/services/member_access_operation_service.py` |
| Frontend guards | `frontend/src/routeGuards.jsx`, `frontend/src/roleAccess.js` |

## Data or Request Flow

1. Clerk identifies the signed-in user and active organization.
2. Cronos resolves the local membership inside that organization.
3. The API checks active lifecycle and access status.
4. Capability checks allow `admin` or `teacher` operations.
5. Webhooks and member actions reconcile provider and local state.

## Contracts and Invariants

- Active access requires `lifecycle_status=active` and `access_status=active`.
- Capabilities are `admin` and `teacher`.
- Clerk organization roles are `org:member` and `org:admin`.
- A teacher route requires a linked `teacher_id`.
- A member can hold both capabilities.
- `scheduler_only` teacher access does not imply platform login access.
- Member operations record provider and local outcomes.

## States and Transitions

Lifecycle states are `active` and `archived`.
Access states are `none`, `pending_invite`, `invite_expired`, `active`, `blocked`, and `sync_error`.
Teacher access modes are `platform` and `scheduler_only`.
Access operation types are `create_invitation`, `revoke_invitation`, `revoke_membership`, `change_role`, `resend_invitation`, `restore_access`, and `block_access`.
Access operation statuses are `pending`, `clerk_succeeded`, `local_committed`, `failed`, `compensated`, `compensation_failed`, and `support_required`.
Access operations use compensating states when provider and local commits diverge.
Clerk webhook events use `received`, `processing`, `processed`, `ignored`, `retryable_failed`, `sync_error`, and `dead_letter`.

## Failure Modes

- Missing or invalid Clerk credentials return an authentication error.
- An inactive or blocked membership cannot access tenant routes.
- A teacher without a profile cannot access teacher routes.
- A provider operation failure remains visible for retry or support.

## Verification Procedure

1. Open `/members` as an administrator.
2. Create, resend, block, restore, or retry a member action.
3. Verify the local status and operation record.
4. Test a teacher-only account on `/my-schedules` and `/config`.

## Source Map

- Models: `backend/app/models.py`
- Dependencies: `backend/app/api/deps.py`
- API: `backend/app/api/v1/endpoints/members.py`
- Services: `backend/app/services/member_service.py`, `clerk_sync.py`, `member_webhook_service.py`, `member_reconciliation_service.py`, `member_access_operation_service.py`
- Tests: `backend/tests/integration/committed/test_members_api.py`, `backend/tests/integration/committed/test_webhooks.py`, `backend/tests/unit/test_clerk_sync.py`

## Related Documents

- [Professional Education](PROFESSIONAL_EDUCATION.md)
- [Routes and Permissions](../06_frontend_ux/ROUTES_AND_PERMISSIONS.md)
