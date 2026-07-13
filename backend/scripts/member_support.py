from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select

from app import models
from app.db.database import SessionLocal
from app.services import member_reconciliation_service
from app.services.clerk_access_service import ClerkAccessService
from app.services.member_access_operation_service import MemberAccessOperationService


def _operation_to_dict(operation: models.MemberAccessOperation | None) -> dict:
    if operation is None:
        return {"found": False}
    return {
        "found": True,
        "id": operation.id,
        "organization_id": operation.organization_id,
        "membership_id": operation.membership_id,
        "operation_type": operation.operation_type.value,
        "operation_status": operation.operation_status.value,
        "target_email": operation.target_email,
        "provider_error_category": operation.provider_error_category,
        "provider_error_safe_message": operation.provider_error_safe_message,
        "support_required_at": operation.support_required_at,
        "support_resolution_action": operation.support_resolution_action,
    }


def _webhook_to_dict(event: models.ClerkWebhookEvent | None) -> dict:
    if event is None:
        return {"found": False}
    return {
        "found": True,
        "id": event.id,
        "svix_id": event.svix_id,
        "event_type": event.event_type,
        "processing_status": event.processing_status.value,
        "attempt_count": event.attempt_count,
        "error_category": event.error_category,
        "next_retry_at": event.next_retry_at,
    }


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Support-only Clerk-backed Equipa recovery")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_op = subparsers.add_parser("inspect-operation")
    inspect_op.add_argument("--id", type=int, required=True)

    resolve_op = subparsers.add_parser("resolve-operation")
    resolve_op.add_argument("--id", type=int, required=True)
    resolve_op.add_argument("--action", choices=["mark_resolved", "mark_support_required", "retry_compensation", "commit_confirmed_clerk_state"], required=True)
    resolve_op.add_argument("--operator-id", type=int, required=True)
    resolve_op.add_argument("--note", default="")
    resolve_op.add_argument("--apply", action="store_true")

    inspect_hook = subparsers.add_parser("inspect-webhook")
    inspect_hook.add_argument("--id", type=int)
    inspect_hook.add_argument("--svix-id")

    hook_action = subparsers.add_parser("webhook-action")
    hook_action.add_argument("--id", type=int, required=True)
    hook_action.add_argument("--action", choices=["replay", "ignore", "mark-sync-error", "replay_dead_letter", "leave_dead_letter_blocked"], required=True)
    hook_action.add_argument("--operator-id", type=int, required=True)
    hook_action.add_argument("--note", required=True)
    hook_action.add_argument("--apply", action="store_true")

    revoke_orphan = subparsers.add_parser("revoke-orphan-invitation")
    revoke_orphan.add_argument("--organization-id", type=int, required=True)
    revoke_orphan.add_argument("--invitation-id", required=True)
    revoke_orphan.add_argument("--email", required=True)
    revoke_orphan.add_argument("--operator-id", type=int, required=True)
    revoke_orphan.add_argument("--apply", action="store_true")

    args = parser.parse_args()
    async with SessionLocal() as db:
        if args.command == "revoke-orphan-invitation":
            organization = await db.get(models.Organization, args.organization_id)
            operator = await db.get(models.User, args.operator_id)
            if organization is None or not organization.clerk_org_id:
                raise RuntimeError("The Clerk-backed organization was not found.")
            if operator is None or not operator.clerk_user_id:
                raise RuntimeError("The Clerk-backed operator was not found.")
            preview = {
                "organization_id": organization.id,
                "clerk_org_id": organization.clerk_org_id,
                "invitation_id": args.invitation_id,
                "email": args.email.lower(),
                "apply": args.apply,
            }
            if not args.apply:
                print(json.dumps(preview, indent=2))
                return
            operations = MemberAccessOperationService()
            operation = await operations.create_pending(
                organization_id=organization.id,
                target_email=args.email,
                operation_type=models.MemberAccessOperationType.revoke_invitation,
                created_by_user_id=operator.id,
                intended_capabilities=set(),
                intended_role=None,
                intent={"orphan_invitation_id": args.invitation_id},
                clerk_org_id=organization.clerk_org_id,
                clerk_invitation_id=args.invitation_id,
            )
            result = await ClerkAccessService().revoke_organization_invitation(
                clerk_org_id=organization.clerk_org_id,
                invitation_id=args.invitation_id,
                requesting_user_id=operator.clerk_user_id,
            )
            if not result.ok:
                await operations.transition(
                    operation.id,
                    models.MemberAccessOperationStatus.failed,
                    error_category=result.error_category,
                    safe_message=result.safe_message,
                )
                raise RuntimeError(result.safe_message or "Clerk revocation failed.")
            await operations.transition(
                operation.id,
                models.MemberAccessOperationStatus.local_committed,
                clerk_invitation_id=args.invitation_id,
            )
            preview["operation_id"] = operation.id
            preview["status"] = "revoked"
            print(json.dumps(preview, indent=2))
            return

        if args.command == "inspect-operation":
            operation = await db.get(models.MemberAccessOperation, args.id)
            print(json.dumps(_operation_to_dict(operation), indent=2, default=str))
            return

        if args.command == "resolve-operation":
            operation = await db.get(models.MemberAccessOperation, args.id)
            if operation is None:
                print(json.dumps({"found": False}, indent=2))
                return
            if args.apply:
                if args.action in {"mark_resolved", "commit_confirmed_clerk_state"}:
                    operation.operation_status = models.MemberAccessOperationStatus.local_committed
                    operation.support_resolved_at = datetime.now(timezone.utc)
                    operation.support_resolved_by_user_id = args.operator_id
                    operation.support_resolution_action = args.action
                    operation.support_resolution_note = args.note
                elif args.action == "mark_support_required":
                    operation.operation_status = models.MemberAccessOperationStatus.support_required
                    operation.support_required_at = datetime.now(timezone.utc)
                elif args.action == "retry_compensation":
                    operation.operation_status = models.MemberAccessOperationStatus.pending
                    operation.compensation_attempted_at = datetime.now(timezone.utc)
                await db.commit()
            print(json.dumps(_operation_to_dict(operation), indent=2, default=str))
            return

        if args.command == "inspect-webhook":
            stmt = select(models.ClerkWebhookEvent)
            if args.id:
                stmt = stmt.where(models.ClerkWebhookEvent.id == args.id)
            elif args.svix_id:
                stmt = stmt.where(models.ClerkWebhookEvent.svix_id == args.svix_id)
            else:
                parser.error("--id or --svix-id is required")
            event = await db.scalar(stmt)
            print(json.dumps(_webhook_to_dict(event), indent=2, default=str))
            return

        if args.command == "webhook-action":
            event = await db.get(models.ClerkWebhookEvent, args.id)
            if event is None:
                print(json.dumps({"found": False}, indent=2))
                return
            preview = {
                "found": True,
                "applied": bool(args.apply),
                "operator_id": args.operator_id,
                "note": args.note,
                "before": _webhook_to_dict(event),
                "requested_action": args.action,
            }
            if args.apply:
                event.support_resolution_action = args.action
                event.support_resolved_at = datetime.now(timezone.utc)
                event.support_resolved_by_user_id = args.operator_id
                event.support_resolution_note = args.note
                if args.action in {"replay", "replay_dead_letter"}:
                    event.processing_status = models.ClerkWebhookProcessingStatus.retryable_failed
                    event.next_retry_at = datetime.now(timezone.utc)
                    await member_reconciliation_service.run_scheduled_reconciliation(db, limit=1)
                elif args.action == "ignore":
                    event.processing_status = models.ClerkWebhookProcessingStatus.ignored
                    event.processed_at = datetime.now(timezone.utc)
                elif args.action == "mark-sync-error":
                    event.processing_status = models.ClerkWebhookProcessingStatus.sync_error
                    event.error_category = event.error_category or "support_marked_sync_error"
                elif args.action == "leave_dead_letter_blocked":
                    event.processing_status = models.ClerkWebhookProcessingStatus.dead_letter
                await db.commit()
            preview["after"] = _webhook_to_dict(event)
            print(json.dumps(preview, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_main())
