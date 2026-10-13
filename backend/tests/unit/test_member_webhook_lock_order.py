"""The membership webhook locks the membership row first.

A restore updates the membership, then calls Clerk; Clerk's
organizationMembership.created webhook arrives during that call. Production
(2026-10-13) deadlocked when the webhook touched the account before waiting on
the membership. Locking the membership first keeps one lock order.
"""

import asyncio

from sqlalchemy.dialects import postgresql

from app.services import member_webhook_service


class _CapturingSession:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)

        class _Result:
            def scalars(self):
                class _Scalars:
                    def all(self):
                        return []

                return _Scalars()

        return _Result()


def test_matching_membership_is_loaded_for_update_of_the_membership_row():
    db = _CapturingSession()
    asyncio.run(
        member_webhook_service._load_matching_membership(
            db, clerk_org_id="org_1", email=None, membership_id=7
        )
    )
    sql = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE OF organization_membership" in sql
