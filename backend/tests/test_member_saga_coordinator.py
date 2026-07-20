from app import models
from app.services.clerk_access_service import ClerkAccessResult
from app.services.member_access_operation_service import MemberAccessSagaCoordinator


class FakeOperations:
    def __init__(self, clerk_access):
        self.clerk_access = clerk_access
        self.transitions = []

    async def transition(self, operation_id, status, **details):
        self.transitions.append((operation_id, status, details))


class FakeClerkAccess:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def revoke_organization_invitation(self, **details):
        self.calls.append(("revoke_invitation", details))
        return self.result

    async def revoke_organization_membership(self, **details):
        self.calls.append(("revoke_membership", details))
        return self.result

    async def change_membership_role(self, **details):
        self.calls.append(("restore_role", details))
        return self.result


async def test_saga_compensates_created_invitation_and_closes_operation():
    clerk = FakeClerkAccess(ClerkAccessResult())
    operations = FakeOperations(clerk)
    saga = MemberAccessSagaCoordinator(operations)

    outcome = await saga.compensate_created_invitation(
        operation_id=7,
        clerk_org_id="org_1",
        invitation_id="inv_1",
        requesting_user_id="user_1",
        error_category="local_commit_failed",
        safe_message="IntegrityError",
    )

    assert outcome.support_required is False
    assert clerk.calls == [
        (
            "revoke_invitation",
            {
                "clerk_org_id": "org_1",
                "invitation_id": "inv_1",
                "requesting_user_id": "user_1",
            },
        )
    ]
    assert operations.transitions == [
        (
            7,
            models.MemberAccessOperationStatus.compensated,
            {
                "clerk_invitation_id": "inv_1",
                "error_category": "local_commit_failed",
                "safe_message": "IntegrityError",
                "compensation_attempted": True,
                "support_required": False,
            },
        )
    ]


async def test_saga_persists_support_required_when_membership_compensation_fails():
    clerk = FakeClerkAccess(
        ClerkAccessResult(
            error_category="provider_unavailable",
            safe_message="Try again later.",
        )
    )
    operations = FakeOperations(clerk)
    saga = MemberAccessSagaCoordinator(operations)

    outcome = await saga.compensate_created_membership(
        operation_id=8,
        clerk_org_id="org_1",
        clerk_user_id="user_2",
        clerk_membership_id="mem_2",
        error_category="local_commit_failed",
        safe_message="IntegrityError",
    )

    assert outcome.support_required is True
    assert operations.transitions[0][1] == models.MemberAccessOperationStatus.support_required
    assert operations.transitions[0][2]["error_category"] == "provider_unavailable"
    assert operations.transitions[0][2]["safe_message"] == "Try again later."


async def test_saga_marks_missing_previous_role_for_support_without_provider_call():
    clerk = FakeClerkAccess(ClerkAccessResult())
    operations = FakeOperations(clerk)
    saga = MemberAccessSagaCoordinator(operations)

    outcome = await saga.compensate_role_change(
        operation_id=9,
        clerk_org_id="org_1",
        clerk_user_id="user_3",
        previous_role=None,
        clerk_membership_id="mem_3",
        error_category="local_commit_failed",
        safe_message="IntegrityError",
    )

    assert outcome.support_required is True
    assert clerk.calls == []
    assert operations.transitions[0][1] == models.MemberAccessOperationStatus.support_required
    assert operations.transitions[0][2]["compensation_attempted"] is False
