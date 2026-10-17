"""School-owned room types and the nullable room_type reference.

Additive part of the class home room work (S1): creates ``room_type``, seeds the
four initial types of every existing school, and adds ``room.room_type_id`` and
``subject.room_type_id`` backfilled from the legacy ``RoomType`` enum. The
columns stay nullable and the enum remains in place until the final pass (S4).

Revision ID: 0006_room_types
Revises: 0005_teacher_presence
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_room_types"
down_revision = "0005_teacher_presence"
branch_labels = None
depends_on = None

TABLE = "room_type"
INITIAL_TYPES = (
    ("Normal", True),
    ("Laboratório", False),
    ("Ginásio", False),
    ("Artes", False),
)
ENUM_TO_NAME = {
    "normal": "Normal",
    "lab": "Laboratório",
    "gym": "Ginásio",
    "art": "Artes",
}


def _create_table() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("is_normal", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name="room_type_organization_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="room_type_pkey"),
        sa.UniqueConstraint("organization_id", "id", name="uq_room_type_org_id"),
    )
    op.create_index("ix_room_type_organization_id", TABLE, ["organization_id"])
    op.execute(
        f"CREATE UNIQUE INDEX uq_room_type_org_name ON public.{TABLE} "
        "USING btree (organization_id, lower(name))"
    )
    op.execute(
        f"CREATE UNIQUE INDEX uq_room_type_org_normal ON public.{TABLE} "
        "USING btree (organization_id) WHERE (is_normal IS TRUE)"
    )


def _harden_table() -> None:
    op.execute(f"ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{TABLE} TO cronos_app "
        "USING ((organization_id = app_security.current_organization_id())) "
        "WITH CHECK ((organization_id = app_security.current_organization_id()))"
    )
    op.execute(f"GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.{TABLE} TO cronos_app")
    op.execute(f"GRANT SELECT,USAGE ON SEQUENCE public.{TABLE}_id_seq TO cronos_app")


def _seed_initial_types() -> None:
    values = ", ".join(f"('{name}', {str(is_normal).lower()})" for name, is_normal in INITIAL_TYPES)
    op.execute(
        f"INSERT INTO public.{TABLE} (organization_id, name, is_normal, is_archived) "
        f"SELECT o.id, seed.name, seed.is_normal, false "
        f"FROM public.organization o CROSS JOIN (VALUES {values}) AS seed(name, is_normal)"
    )


def _backfill(table: str, enum_column: str) -> None:
    cases = " ".join(f"WHEN '{code}' THEN '{name}'" for code, name in ENUM_TO_NAME.items())
    op.execute(
        f"UPDATE public.{table} AS target SET room_type_id = rt.id "
        f"FROM public.{TABLE} AS rt "
        "WHERE rt.organization_id = target.organization_id "
        f"AND rt.name = CASE target.{enum_column}::text {cases} END"
    )


def upgrade() -> None:
    _create_table()
    _harden_table()
    _seed_initial_types()

    op.add_column("room", sa.Column("room_type_id", sa.Integer(), nullable=True))
    op.add_column("subject", sa.Column("room_type_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_room_room_type_org",
        "room",
        TABLE,
        ["organization_id", "room_type_id"],
        ["organization_id", "id"],
    )
    op.create_foreign_key(
        "fk_subject_room_type_org",
        "subject",
        TABLE,
        ["organization_id", "room_type_id"],
        ["organization_id", "id"],
    )

    _backfill("room", "type")
    _backfill("subject", "required_room_type")


def downgrade() -> None:
    op.drop_constraint("fk_subject_room_type_org", "subject", type_="foreignkey")
    op.drop_constraint("fk_room_room_type_org", "room", type_="foreignkey")
    op.drop_column("subject", "room_type_id")
    op.drop_column("room", "room_type_id")
    op.drop_table(TABLE)
