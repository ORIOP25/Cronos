"""Create date-effective grid versions and attach existing timeslots.

The initial version per organization preserves every existing timeslot id. A
regular legacy grid rebuilds its full configuration; an irregular legacy grid
keeps its blocks with a null configuration until an explicit proposal.
"""

import json
from datetime import date, time

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011_grid_versions"
down_revision = "0001_scheduler_v1_baseline"
branch_labels = None
depends_on = None

FALLBACK_EFFECTIVE_DATE = date(2000, 1, 1)
GRID_VERSION_SEQUENCE = "grid_version_id_seq"


def _minutes(start: time, end: time) -> int:
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


def _whole_minute(value: time) -> bool:
    return value.second == 0 and value.microsecond == 0


def derive_grid_configuration(rows: list[tuple[int, time, time]]) -> dict | None:
    """Rebuild the full configuration when the legacy grid is regular."""
    if not rows:
        return None
    by_day: dict[int, list[tuple[time, time]]] = {}
    for day, start, end in rows:
        if not _whole_minute(start) or not _whole_minute(end) or end <= start:
            return None
        by_day.setdefault(day, []).append((start, end))

    days = sorted(by_day)
    reference: list[tuple[time, time]] | None = None
    usual_break: int | None = None
    for day in days:
        sequence = sorted(by_day[day])
        if not sequence:
            return None
        durations = {_minutes(start, end) for start, end in sequence}
        if len(durations) != 1 or not 15 <= durations.pop() <= 120:
            return None
        if any(
            current[0] < previous[1]
            for previous, current in zip(sequence, sequence[1:], strict=False)
        ):
            return None
        if reference is None:
            reference = sequence
        elif sequence != reference:
            return None
        gaps = [
            _minutes(sequence[index][1], sequence[index + 1][0])
            for index in range(len(sequence) - 1)
        ]
        for gap in gaps:
            if not 0 <= gap <= 60:
                return None
            if usual_break is None:
                usual_break = gap
            elif gap != usual_break:
                return None

    return {
        "opening_time": reference[0][0].strftime("%H:%M"),
        "closing_time": reference[-1][1].strftime("%H:%M"),
        "slot_duration_minutes": _minutes(*reference[0]),
        "break_duration_minutes": usual_break or 0,
        "break_overrides": [],
        "days_of_week": days,
    }


def _backfill_versions() -> None:
    bind = op.get_bind()
    organizations = bind.execute(
        sa.text(
            """
            SELECT o.id, s.school_start_date
            FROM public.organization o
            LEFT JOIN public.organization_settings s ON s.organization_id = o.id
            WHERE EXISTS (
                SELECT 1 FROM public.timeslot t WHERE t.organization_id = o.id
            )
            """
        )
    ).fetchall()
    for organization_id, school_start_date in organizations:
        rows = bind.execute(
            sa.text(
                """
                SELECT day_of_week, start_time, end_time
                FROM public.timeslot
                WHERE organization_id = :organization_id
                ORDER BY day_of_week, start_time
                """
            ),
            {"organization_id": organization_id},
        ).fetchall()
        configuration = derive_grid_configuration([(row[0], row[1], row[2]) for row in rows])
        version_id = bind.execute(
            sa.text(
                """
                INSERT INTO public.grid_version
                    (organization_id, effective_date, state, configuration_json)
                VALUES
                    (:organization_id, :effective_date, 'ACTIVE', :configuration)
                RETURNING id
                """
            ),
            {
                "organization_id": organization_id,
                "effective_date": school_start_date or FALLBACK_EFFECTIVE_DATE,
                "configuration": (None if configuration is None else json.dumps(configuration)),
            },
        ).scalar_one()
        bind.execute(
            sa.text(
                """
                UPDATE public.timeslot
                SET grid_version_id = :version_id
                WHERE organization_id = :organization_id
                """
            ),
            {"version_id": version_id, "organization_id": organization_id},
        )


def upgrade() -> None:
    op.execute("CREATE TYPE gridversionstate AS ENUM ('PENDING', 'ACTIVE', 'REJECTED')")
    op.create_table(
        "grid_version",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column(
            "state",
            postgresql.ENUM(
                "PENDING", "ACTIVE", "REJECTED", name="gridversionstate", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "configuration_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["public.organization.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_grid_version_organization_id"),
        schema="public",
    )
    op.create_index(
        "ix_grid_version_organization_id",
        "grid_version",
        ["organization_id"],
        schema="public",
    )
    op.create_index(
        "ix_grid_version_org_effective",
        "grid_version",
        ["organization_id", "effective_date"],
        schema="public",
    )
    op.execute("ALTER TABLE public.grid_version ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.grid_version FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY grid_version_tenant_isolation
        ON public.grid_version FOR ALL
        USING (organization_id = app_security.current_organization_id())
        WITH CHECK (organization_id = app_security.current_organization_id())
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.grid_version TO cronos_app")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE public.{GRID_VERSION_SEQUENCE} TO cronos_app")

    op.add_column(
        "timeslot",
        sa.Column("grid_version_id", sa.Integer(), nullable=True),
        schema="public",
    )
    op.add_column(
        "schedule_generation_job",
        sa.Column("grid_version_id", sa.Integer(), nullable=True),
        schema="public",
    )
    op.add_column(
        "schedule_drafts",
        sa.Column("grid_version_id", sa.Integer(), nullable=True),
        schema="public",
    )
    op.create_index(
        "ix_timeslot_grid_version_id",
        "timeslot",
        ["grid_version_id"],
        schema="public",
    )
    op.create_foreign_key(
        "fk_timeslot_grid_version_tenant_scoped",
        "timeslot",
        "grid_version",
        ["organization_id", "grid_version_id"],
        ["organization_id", "id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_schedule_generation_job_grid_version_tenant_scoped",
        "schedule_generation_job",
        "grid_version",
        ["organization_id", "grid_version_id"],
        ["organization_id", "id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_schedule_drafts_grid_version_tenant_scoped",
        "schedule_drafts",
        "grid_version",
        ["organization_id", "grid_version_id"],
        ["organization_id", "id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )

    _backfill_versions()

    op.drop_constraint("uq_timeslot", "timeslot", schema="public", type_="unique")
    op.create_unique_constraint(
        "uq_timeslot_grid_version",
        "timeslot",
        ["organization_id", "grid_version_id", "day_of_week", "start_time"],
        schema="public",
    )


def downgrade() -> None:
    bind = op.get_bind()
    duplicate_slots = bind.execute(
        sa.text(
            """
            SELECT count(*) FROM (
                SELECT day_of_week, start_time, organization_id
                FROM public.timeslot
                GROUP BY day_of_week, start_time, organization_id
                HAVING count(*) > 1
            ) AS duplicates
            """
        )
    ).scalar_one()
    if duplicate_slots:
        raise RuntimeError(
            "Cannot downgrade grid versions while multiple versions share the same "
            "weekly slot. Remove the extra versions before downgrading."
        )
    op.drop_constraint("uq_timeslot_grid_version", "timeslot", schema="public", type_="unique")
    op.create_unique_constraint(
        "uq_timeslot",
        "timeslot",
        ["day_of_week", "start_time", "organization_id"],
        schema="public",
    )
    op.drop_constraint(
        "fk_schedule_drafts_grid_version_tenant_scoped",
        "schedule_drafts",
        schema="public",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_schedule_generation_job_grid_version_tenant_scoped",
        "schedule_generation_job",
        schema="public",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_timeslot_grid_version_tenant_scoped",
        "timeslot",
        schema="public",
        type_="foreignkey",
    )
    op.drop_index("ix_timeslot_grid_version_id", table_name="timeslot", schema="public")
    op.drop_column("schedule_drafts", "grid_version_id", schema="public")
    op.drop_column("schedule_generation_job", "grid_version_id", schema="public")
    op.drop_column("timeslot", "grid_version_id", schema="public")
    op.drop_index("ix_grid_version_org_effective", table_name="grid_version", schema="public")
    op.drop_index("ix_grid_version_organization_id", table_name="grid_version", schema="public")
    op.drop_table("grid_version", schema="public")
    op.execute("DROP TYPE IF EXISTS gridversionstate")
