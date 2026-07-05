"""clerk backed equipa members

Revision ID: e7b8c9d0a1f2
Revises: d3a7e5b9c2f1
Create Date: 2026-06-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7b8c9d0a1f2"
down_revision: Union[str, None] = "d3a7e5b9c2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    for column in (
        sa.Column("clerk_primary_email_id", sa.String(length=255), nullable=True),
        sa.Column("clerk_profile_name", sa.String(length=255), nullable=True),
        sa.Column("last_clerk_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("user", column)

    op.execute('UPDATE "user" SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL')
    op.execute('UPDATE "user" SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL')
    if dialect != "sqlite":
        op.alter_column("user", "created_at", nullable=False)
        op.alter_column("user", "updated_at", nullable=False)
        op.alter_column("user", "organization_id", existing_type=sa.Integer(), nullable=True)
        op.alter_column("user", "role", existing_type=sa.String(), nullable=True)
        op.alter_column("user", "is_active", existing_type=sa.Boolean(), nullable=True)

    op.create_table(
        "organization_membership",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("organization_display_name", sa.String(length=150), nullable=False),
        sa.Column("lifecycle_status", _enum("membershiplifecyclestatus", "active", "archived"), nullable=False, server_default="active"),
        sa.Column("access_status", _enum("membershipaccessstatus", "none", "pending_invite", "invite_expired", "active", "blocked", "sync_error"), nullable=False, server_default="none"),
        sa.Column("teacher_access_mode", _enum("teacheraccessmode", "platform", "scheduler_only"), nullable=True),
        sa.Column("expected_clerk_role", _enum("clerkorganizationrole", "org:member", "org:admin"), nullable=True),
        sa.Column("clerk_membership_id", sa.String(length=255), nullable=True),
        sa.Column("clerk_invitation_id", sa.String(length=255), nullable=True),
        sa.Column("clerk_invitation_status", _enum("clerkinvitationstatus", "pending", "accepted", "revoked", "expired"), nullable=True),
        sa.Column("invitation_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_error_category", sa.String(length=80), nullable=True),
        sa.Column("access_error_safe_message", sa.String(length=240), nullable=True),
        sa.Column("access_block_reason", sa.String(length=120), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["account_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "account_id", name="uq_org_membership_account"),
    )
    op.create_index("ix_organization_membership_organization_id", "organization_membership", ["organization_id"])
    op.create_index("ix_organization_membership_account_id", "organization_membership", ["account_id"])
    op.create_index("ix_organization_membership_access_status", "organization_membership", ["access_status"])
    op.create_index("ix_organization_membership_lifecycle_status", "organization_membership", ["lifecycle_status"])
    op.create_index("ix_organization_membership_clerk_membership_id", "organization_membership", ["clerk_membership_id"])
    op.create_index("ix_organization_membership_clerk_invitation_id", "organization_membership", ["clerk_invitation_id"])

    op.create_table(
        "organization_membership_capability",
        sa.Column("organization_membership_id", sa.Integer(), nullable=False),
        sa.Column("capability", _enum("membershipcapability", "teacher", "admin"), nullable=False),
        sa.ForeignKeyConstraint(["organization_membership_id"], ["organization_membership.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_membership_id", "capability"),
        sa.UniqueConstraint("organization_membership_id", "capability", name="uq_org_membership_capability"),
    )

    op.add_column("teacher", sa.Column("organization_membership_id", sa.Integer(), nullable=True))
    op.add_column("teacher", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_teacher_organization_membership_id", "teacher", ["organization_membership_id"], unique=True)
    op.create_foreign_key(
        "fk_teacher_organization_membership",
        "teacher",
        "organization_membership",
        ["organization_membership_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "member_access_operation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("target_email", sa.String(length=255), nullable=False),
        sa.Column("operation_type", _enum("memberaccessoperationtype", "create_invitation", "revoke_invitation", "revoke_membership", "change_role", "resend_invitation", "restore_access", "block_access"), nullable=False),
        sa.Column("operation_status", _enum("memberaccessoperationstatus", "pending", "clerk_succeeded", "local_committed", "failed", "compensated", "compensation_failed", "support_required"), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("intended_capabilities_json", sa.JSON(), nullable=False),
        sa.Column("intended_clerk_role", sa.String(length=40), nullable=True),
        sa.Column("previous_access_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("draft_payload_json", sa.JSON(), nullable=True),
        sa.Column("clerk_org_id", sa.String(length=255), nullable=True),
        sa.Column("clerk_user_id", sa.String(length=255), nullable=True),
        sa.Column("clerk_membership_id", sa.String(length=255), nullable=True),
        sa.Column("clerk_invitation_id", sa.String(length=255), nullable=True),
        sa.Column("provider_error_category", sa.String(length=80), nullable=True),
        sa.Column("provider_error_safe_message", sa.String(length=240), nullable=True),
        sa.Column("provider_error_reference", sa.String(length=120), nullable=True),
        sa.Column("compensation_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("support_required_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("support_resolution_action", sa.String(length=80), nullable=True),
        sa.Column("support_resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("support_resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("support_resolution_note", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["account_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["membership_id"], ["organization_membership.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["support_resolved_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_member_access_operation_organization_id", "member_access_operation", ["organization_id"])
    op.create_index("ix_member_access_operation_membership_id", "member_access_operation", ["membership_id"])
    op.create_index("ix_member_access_operation_account_id", "member_access_operation", ["account_id"])
    op.create_index("ix_member_access_operation_target_email", "member_access_operation", ["target_email"])
    op.create_index("ix_member_access_operation_operation_status", "member_access_operation", ["operation_status"])

    op.create_table(
        "clerk_webhook_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("svix_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("clerk_object_id", sa.String(length=255), nullable=True),
        sa.Column("clerk_org_id", sa.String(length=255), nullable=True),
        sa.Column("clerk_user_id", sa.String(length=255), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("processing_status", _enum("clerkwebhookprocessingstatus", "received", "processing", "processed", "ignored", "retryable_failed", "sync_error", "dead_letter"), nullable=False, server_default="received"),
        sa.Column("error_category", sa.String(length=80), nullable=True),
        sa.Column("support_resolution_action", sa.String(length=80), nullable=True),
        sa.Column("support_resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("support_resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("support_resolution_note", sa.String(length=500), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["support_resolved_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("svix_id"),
    )
    op.create_index("ix_clerk_webhook_event_svix_id", "clerk_webhook_event", ["svix_id"])
    op.create_index("ix_clerk_webhook_event_event_type", "clerk_webhook_event", ["event_type"])
    op.create_index("ix_clerk_webhook_event_clerk_object_id", "clerk_webhook_event", ["clerk_object_id"])
    op.create_index("ix_clerk_webhook_event_clerk_org_id", "clerk_webhook_event", ["clerk_org_id"])
    op.create_index("ix_clerk_webhook_event_clerk_user_id", "clerk_webhook_event", ["clerk_user_id"])
    op.create_index("ix_clerk_webhook_event_processing_status", "clerk_webhook_event", ["processing_status"])

    op.execute(
        """
        INSERT INTO organization_membership (
            organization_id, account_id, organization_display_name, lifecycle_status,
            access_status, teacher_access_mode, expected_clerk_role, clerk_membership_id,
            created_by_user_id, updated_by_user_id, created_at, updated_at
        )
        SELECT
            u.organization_id,
            u.id,
            COALESCE(NULLIF(u.name, ''), split_part(u.email, '@', 1)),
            'active',
            CASE
                WHEN u.role IN ('admin', 'teacher') AND u.clerk_user_id IS NOT NULL THEN 'active'
                ELSE 'none'
            END,
            CASE WHEN u.teacher_id IS NOT NULL THEN 'platform' ELSE NULL END,
            CASE WHEN u.role = 'admin' THEN 'org:admin' WHEN u.role = 'teacher' THEN 'org:member' ELSE NULL END,
            NULL,
            u.id,
            u.id,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM "user" u
        WHERE u.organization_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO organization_membership_capability (organization_membership_id, capability)
        SELECT om.id, 'admin'
        FROM organization_membership om
        JOIN "user" u ON u.id = om.account_id
        WHERE u.role = 'admin'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO organization_membership_capability (organization_membership_id, capability)
        SELECT om.id, 'teacher'
        FROM organization_membership om
        JOIN "user" u ON u.id = om.account_id
        WHERE u.role = 'teacher' OR u.teacher_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE teacher
        SET organization_membership_id = om.id
        FROM organization_membership om
        JOIN "user" u ON u.id = om.account_id
        WHERE u.teacher_id = teacher.id
          AND teacher.organization_id = om.organization_id
          AND teacher.organization_membership_id IS NULL
        """
    )
    if dialect != "sqlite":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION app_security.resolve_auth_context(
                clerk_user_id text,
                clerk_org_id text
            )
            RETURNS TABLE(user_id integer, organization_id integer, role text, is_active boolean)
            LANGUAGE sql
            SECURITY DEFINER
            STABLE
            SET search_path = pg_catalog, public
            AS $$
                SELECT
                    u.id,
                    om.organization_id,
                    CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM public.organization_membership_capability omc
                            WHERE omc.organization_membership_id = om.id
                              AND omc.capability = 'admin'
                        ) THEN 'admin'
                        WHEN EXISTS (
                            SELECT 1
                            FROM public.organization_membership_capability omc
                            WHERE omc.organization_membership_id = om.id
                              AND omc.capability = 'teacher'
                        ) THEN 'teacher'
                        ELSE NULL
                    END,
                    true
                FROM public.organization_membership om
                JOIN public."user" u ON u.id = om.account_id
                JOIN public.organization o ON o.id = om.organization_id
                WHERE resolve_auth_context.clerk_user_id IS NOT NULL
                  AND resolve_auth_context.clerk_org_id IS NOT NULL
                  AND length(resolve_auth_context.clerk_user_id) BETWEEN 1 AND 255
                  AND length(resolve_auth_context.clerk_org_id) BETWEEN 1 AND 255
                  AND u.clerk_user_id = resolve_auth_context.clerk_user_id
                  AND o.clerk_org_id = resolve_auth_context.clerk_org_id
                  AND om.lifecycle_status = 'active'
                  AND om.access_status = 'active'
                LIMIT 1;
            $$;
            REVOKE ALL ON FUNCTION app_security.resolve_auth_context(text, text) FROM PUBLIC;
            ALTER FUNCTION app_security.resolve_auth_context(text, text) OWNER TO cronos_auth_definer;
            GRANT EXECUTE ON FUNCTION app_security.resolve_auth_context(text, text) TO cronos_app;
            """
        )


def downgrade() -> None:
    op.drop_table("clerk_webhook_event")
    op.drop_index("ix_member_access_operation_operation_status", table_name="member_access_operation")
    op.drop_index("ix_member_access_operation_target_email", table_name="member_access_operation")
    op.drop_index("ix_member_access_operation_account_id", table_name="member_access_operation")
    op.drop_index("ix_member_access_operation_membership_id", table_name="member_access_operation")
    op.drop_index("ix_member_access_operation_organization_id", table_name="member_access_operation")
    op.drop_table("member_access_operation")
    op.drop_constraint("fk_teacher_organization_membership", "teacher", type_="foreignkey")
    op.drop_index("ix_teacher_organization_membership_id", table_name="teacher")
    op.drop_column("teacher", "archived_at")
    op.drop_column("teacher", "organization_membership_id")
    op.drop_table("organization_membership_capability")
    op.drop_index("ix_organization_membership_clerk_invitation_id", table_name="organization_membership")
    op.drop_index("ix_organization_membership_clerk_membership_id", table_name="organization_membership")
    op.drop_index("ix_organization_membership_lifecycle_status", table_name="organization_membership")
    op.drop_index("ix_organization_membership_access_status", table_name="organization_membership")
    op.drop_index("ix_organization_membership_account_id", table_name="organization_membership")
    op.drop_index("ix_organization_membership_organization_id", table_name="organization_membership")
    op.drop_table("organization_membership")
    for column in (
        "updated_at",
        "created_at",
        "last_clerk_sync_at",
        "clerk_profile_name",
        "clerk_primary_email_id",
    ):
        op.drop_column("user", column)
