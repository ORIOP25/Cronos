"""Sprint 2 — LessonOccurrence & Substitution refactor

Changes:
  1. lesson_occurrence — new table (immutable historical record, ON DELETE SET NULL)
  2. substitutions.substitute_subject_id — tracks which subject was actually taught

Revision ID: a2b3c4d5e6f7
Revises: c1d2e3f4a5b6
Create Date: 2026-03-03
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = 'a2b3c4d5e6f7'
down_revision: str | None = 'c1d2e3f4a5b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 1. Enum type — criar apenas se não existir (idempotente para dev/CI)
    type_exists = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'lessonoccurrencestatus'")
    ).fetchone()
    if type_exists is None:
        bind.execute(
            sa.text(
                "CREATE TYPE lessonoccurrencestatus "
                "AS ENUM ('GIVEN', 'GAP', 'SUBSTITUTED')"
            )
        )

    # 2. Create lesson_occurrence table (só se ainda não existir).
    #    Usamos SQL raw para evitar que o sistema de eventos do SQLAlchemy
    #    tente recriar o tipo enum via _on_table_create.
    if 'lesson_occurrence' not in existing_tables:
        bind.execute(sa.text("""
            CREATE TABLE lesson_occurrence (
                id          SERIAL PRIMARY KEY,
                org_id      INTEGER NOT NULL
                                REFERENCES organization(id) ON DELETE CASCADE,
                schedule_output_id INTEGER
                                REFERENCES schedule_output(id) ON DELETE SET NULL,
                date        DATE NOT NULL,
                status      lessonoccurrencestatus NOT NULL,
                substitute_teacher_id INTEGER
                                REFERENCES teacher(id) ON DELETE SET NULL,
                substitute_subject_id INTEGER
                                REFERENCES subject(id) ON DELETE SET NULL,
                hours_given FLOAT NOT NULL DEFAULT 0.0,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_lesson_occurrence_output_date
                    UNIQUE (schedule_output_id, date)
            )
        """))
        bind.execute(sa.text(
            "CREATE INDEX ix_lesson_occurrence_org_id "
            "ON lesson_occurrence (org_id)"
        ))
        bind.execute(sa.text(
            "CREATE INDEX ix_lesson_occurrence_date "
            "ON lesson_occurrence (date)"
        ))
        bind.execute(sa.text(
            "CREATE INDEX ix_lesson_occurrence_schedule_output_id "
            "ON lesson_occurrence (schedule_output_id)"
        ))

    # 3. Add substitute_subject_id to substitutions (só se ainda não existir)
    existing_sub_cols = {c['name'] for c in inspector.get_columns('substitutions')}
    if 'substitute_subject_id' not in existing_sub_cols:
        op.add_column(
            'substitutions',
            sa.Column(
                'substitute_subject_id',
                sa.Integer(),
                sa.ForeignKey('subject.id', ondelete='SET NULL'),
                nullable=True,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TABLE substitutions DROP COLUMN IF EXISTS substitute_subject_id"))
    bind.execute(sa.text("DROP TABLE IF EXISTS lesson_occurrence"))
    bind.execute(sa.text("DROP TYPE IF EXISTS lessonoccurrencestatus"))
