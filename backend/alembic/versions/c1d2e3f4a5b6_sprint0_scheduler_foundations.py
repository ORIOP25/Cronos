"""Sprint 0 — Scheduler Foundations

Adds the database structures required before the CP-SAT solver can run:
  1. organization_settings  — per (org, academic_year) configuration
  2. school_calendar_event  — holidays & school breaks (hard constraints)
  3. schedule_output.date   — absolute date per scheduled slot
  4. schedule_output.is_draft — pending director approval
  5. class.projected_end_date — solver output: projected finish date
  6. class.is_archived       — true when all modules complete & end_year past

Revision ID: c1d2e3f4a5b6
Revises: 9b20286aaa27
Create Date: 2026-03-03
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = 'c1d2e3f4a5b6'
down_revision: str | None = '9b20286aaa27'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. organization_settings
    op.create_table(
        'organization_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=10), nullable=False),
        sa.Column('school_start_date', sa.Date(), nullable=True),
        sa.Column('school_target_end_date', sa.Date(), nullable=True),
        sa.Column('region_code', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organization.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', 'academic_year', name='uq_org_academic_year'),
    )
    op.create_index('ix_organization_settings_org_id', 'organization_settings', ['org_id'])

    # 2. school_calendar_event
    op.create_table(
        'school_calendar_event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.String(length=10), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column(
            'event_type',
            sa.Enum('national_holiday', 'school_break', 'exam_period', 'other',
                    name='calendareventtype'),
            nullable=False,
        ),
        sa.Column(
            'source',
            sa.Enum('auto', 'manual', name='calendareventsource'),
            nullable=False,
            server_default='manual',
        ),
        sa.ForeignKeyConstraint(['org_id'], ['organization.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_school_calendar_event_org_id', 'school_calendar_event', ['org_id'])

    # 3 & 4. schedule_output: add date and is_draft
    op.add_column('schedule_output', sa.Column('date', sa.Date(), nullable=True))
    op.add_column('schedule_output', sa.Column('is_draft', sa.Boolean(), nullable=False, server_default='false'))
    op.create_index('ix_schedule_output_date', 'schedule_output', ['date'])

    # 5 & 6. class: add projected_end_date and is_archived
    op.add_column('class', sa.Column('projected_end_date', sa.Date(), nullable=True))
    op.add_column('class', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('class', 'is_archived')
    op.drop_column('class', 'projected_end_date')

    op.drop_index('ix_schedule_output_date', table_name='schedule_output')
    op.drop_column('schedule_output', 'is_draft')
    op.drop_column('schedule_output', 'date')

    op.drop_index('ix_school_calendar_event_org_id', table_name='school_calendar_event')
    op.drop_table('school_calendar_event')
    op.execute("DROP TYPE IF EXISTS calendareventtype")
    op.execute("DROP TYPE IF EXISTS calendareventsource")

    op.drop_index('ix_organization_settings_org_id', table_name='organization_settings')
    op.drop_table('organization_settings')
