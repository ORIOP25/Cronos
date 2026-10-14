"""Class weekly availability and persisted scheduler job diagnostics.

Adds ``class_availability`` with a composed tenant primary key, forced RLS and
least-privilege grants, and adds ``scheduler_job_v1.diagnostics_json``.

Revision ID: 0003_class_availability
Revises: 0002_class_subject_modules
"""

from alembic import op

revision = "0003_class_availability"
down_revision = "0002_class_subject_modules"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE public.class_availability (
    organization_id integer NOT NULL,
    class_id integer NOT NULL,
    timeslot_id integer NOT NULL,
    score integer NOT NULL,
    CONSTRAINT class_availability_pkey PRIMARY KEY (organization_id, class_id, timeslot_id),
    CONSTRAINT ck_class_availability_score CHECK (score IN (-1, 0, 2)),
    CONSTRAINT class_availability_organization_id_fkey FOREIGN KEY (organization_id)
        REFERENCES public.organization(id) ON DELETE CASCADE,
    CONSTRAINT fk_class_availability_class_tenant_scoped FOREIGN KEY (organization_id, class_id)
        REFERENCES public.class(organization_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_class_availability_timeslot_tenant_scoped FOREIGN KEY (organization_id, timeslot_id)
        REFERENCES public.timeslot(organization_id, id) ON DELETE CASCADE
);

ALTER TABLE public.class_availability OWNER TO cronos_migrator;

CREATE INDEX ix_class_availability_org_timeslot ON public.class_availability USING btree (organization_id, timeslot_id);

ALTER TABLE public.class_availability ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.class_availability FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON public.class_availability TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));

GRANT SELECT,INSERT,DELETE ON TABLE public.class_availability TO cronos_app;

ALTER TABLE public.scheduler_job_v1 ADD COLUMN diagnostics_json jsonb;
"""

DOWNGRADE_SQL = r"""
ALTER TABLE public.scheduler_job_v1 DROP COLUMN IF EXISTS diagnostics_json;
DROP TABLE IF EXISTS public.class_availability;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
