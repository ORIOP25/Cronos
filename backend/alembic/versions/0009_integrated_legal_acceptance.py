"""Integrate privacy version into append-only legal acceptance evidence."""

import sqlalchemy as sa

from alembic import op

revision = "0009_integrated_legal_acceptance"
down_revision = "0008_remove_tutorial_telemetry"
branch_labels = None
depends_on = None


_HISTORICAL_LEGAL_COLUMNS = {
    "controller_legal_name": sa.String(length=200),
    "controller_registration_number": sa.String(length=50),
    "controller_registered_address": sa.String(length=500),
    "controller_contact_email": sa.String(length=254),
    "representative_name": sa.String(length=150),
    "representative_role": sa.String(length=100),
}


def upgrade() -> None:
    op.add_column(
        "organization_legal_acceptance",
        sa.Column("privacy_version", sa.String(length=40), nullable=True),
        schema="public",
    )
    for column, column_type in _HISTORICAL_LEGAL_COLUMNS.items():
        op.alter_column(
            "organization_legal_acceptance",
            column,
            existing_type=column_type,
            nullable=True,
            schema="public",
        )
    op.drop_constraint(
        "uq_organization_legal_acceptance_versions",
        "organization_legal_acceptance",
        schema="public",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_organization_legal_acceptance_versions",
        "organization_legal_acceptance",
        ["organization_id", "terms_version", "dpa_version", "privacy_version"],
        schema="public",
    )


def downgrade() -> None:
    connection = op.get_bind()
    incompatible_records = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM public.organization_legal_acceptance
            WHERE privacy_version IS NOT NULL
               OR controller_legal_name IS NULL
               OR controller_registration_number IS NULL
               OR controller_registered_address IS NULL
               OR controller_contact_email IS NULL
               OR representative_name IS NULL
               OR representative_role IS NULL
            """
        )
    ).scalar_one()
    if incompatible_records:
        raise RuntimeError(
            "Downgrade 0009_integrated_legal_acceptance aborted: "
            f"{incompatible_records} legal acceptance record(s) are incompatible "
            "with the previous schema; no evidence was changed."
        )

    op.drop_constraint(
        "uq_organization_legal_acceptance_versions",
        "organization_legal_acceptance",
        schema="public",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_organization_legal_acceptance_versions",
        "organization_legal_acceptance",
        ["organization_id", "terms_version", "dpa_version"],
        schema="public",
    )
    for column, column_type in _HISTORICAL_LEGAL_COLUMNS.items():
        op.alter_column(
            "organization_legal_acceptance",
            column,
            existing_type=column_type,
            nullable=False,
            schema="public",
        )
    op.drop_column("organization_legal_acceptance", "privacy_version", schema="public")
