"""Move the foundation wizard to ten steps with the optional internship flows step."""

from alembic import op

revision = "0014_foundation_internship_step"
down_revision = "0013_internship_flows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "chk_organization_foundation_draft_current_step",
        "organization_foundation_draft",
        schema="public",
        type_="check",
    )
    op.create_check_constraint(
        "chk_organization_foundation_draft_current_step",
        "organization_foundation_draft",
        "current_step BETWEEN 1 AND 10",
        schema="public",
    )
    op.execute(
        """
        UPDATE public.organization_foundation_draft
        SET current_step = 10,
            payload_json = payload_json || '{"internship_flows": []}'::jsonb
        WHERE current_step = 9
          AND NOT (payload_json ? 'internship_flows')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE public.organization_foundation_draft
        SET current_step = 9,
            payload_json = payload_json - 'internship_flows'
        WHERE current_step = 10
        """
    )
    op.drop_constraint(
        "chk_organization_foundation_draft_current_step",
        "organization_foundation_draft",
        schema="public",
        type_="check",
    )
    op.create_check_constraint(
        "chk_organization_foundation_draft_current_step",
        "organization_foundation_draft",
        "current_step BETWEEN 1 AND 9",
        schema="public",
    )
