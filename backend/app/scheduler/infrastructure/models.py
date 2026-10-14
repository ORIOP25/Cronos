"""Relational scheduler v1 curricular records."""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

JOB_STATUSES = (
    "QUEUED",
    "RUNNING",
    "VALIDATING",
    "SUCCEEDED",
    "CANCELLED",
    "STALE",
    "FAILED",
    "INFEASIBLE",
    "INCONCLUSIVE",
)
JOB_ACTIVE_STATUSES = ("QUEUED", "RUNNING", "VALIDATING")
JOB_TERMINAL_STATUSES = (
    "SUCCEEDED",
    "CANCELLED",
    "STALE",
    "FAILED",
    "INFEASIBLE",
    "INCONCLUSIVE",
)
JOB_STRATEGIES = ("COMPLETE_GENERATION", "ADAPTIVE_RECOVERY")
PROPOSAL_STATUSES = ("PENDING", "APPROVED", "REJECTED", "STALE", "SUPERSEDED")


class CurricularAssignment(Base):
    __tablename__ = "curricular_assignment"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    school_year_id: Mapped[int] = mapped_column(Integer, nullable=False)
    class_id: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    teacher_id: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "school_year_id"],
            ["scheduler_school_year.organization_id", "scheduler_school_year.id"],
            name="fk_curricular_assignment_year_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "class_id"],
            ["class.organization_id", "class.id"],
            name="fk_curricular_assignment_class_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "subject_id"],
            ["subject.organization_id", "subject.id"],
            name="fk_curricular_assignment_subject_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "teacher_id"],
            ["teacher.organization_id", "teacher.id"],
            name="fk_curricular_assignment_teacher_org",
        ),
        UniqueConstraint("organization_id", "id", name="uq_curricular_assignment_org_id"),
        UniqueConstraint(
            "organization_id",
            "school_year_id",
            "id",
            name="uq_curricular_assignment_year_id",
        ),
        UniqueConstraint(
            "organization_id",
            "school_year_id",
            "class_id",
            "subject_id",
            name="uq_curricular_assignment_class_subject",
        ),
    )


class CurricularRequirement(Base):
    __tablename__ = "curricular_requirement"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    assignment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    module_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    required_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    # False marks a retired module that keeps executed history.
    planned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "assignment_id"],
            ["curricular_assignment.organization_id", "curricular_assignment.id"],
            name="fk_curricular_requirement_assignment_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "module_id"],
            ["module.organization_id", "module.id"],
            name="fk_curricular_requirement_module_org",
        ),
        UniqueConstraint("organization_id", "id", name="uq_curricular_requirement_org_id"),
        UniqueConstraint("assignment_id", "module_id", name="uq_curricular_requirement_module"),
        UniqueConstraint("assignment_id", "sequence", name="uq_curricular_requirement_sequence"),
        CheckConstraint("sequence > 0", name="ck_curricular_requirement_sequence_positive"),
        CheckConstraint("required_minutes > 0", name="ck_curricular_requirement_minutes_positive"),
    )


class CurricularExecution(Base):
    __tablename__ = "curricular_execution"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    assignment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(String(160), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    author_membership_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planning_relevant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reversal_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "assignment_id"],
            ["curricular_assignment.organization_id", "curricular_assignment.id"],
            name="fk_curricular_execution_assignment_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "author_membership_id"],
            ["organization_membership.organization_id", "organization_membership.id"],
            name="fk_curricular_execution_author_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reversal_of_id"],
            ["curricular_execution.organization_id", "curricular_execution.id"],
            name="fk_curricular_execution_reversal_org",
        ),
        UniqueConstraint("organization_id", "id", name="uq_curricular_execution_org_id"),
        UniqueConstraint(
            "organization_id", "origin", "revision", name="uq_curricular_execution_origin_revision"
        ),
        CheckConstraint("revision > 0", name="ck_curricular_execution_revision_positive"),
        CheckConstraint("length(trim(reason)) > 0", name="ck_curricular_execution_reason_nonempty"),
        CheckConstraint("length(trim(origin)) > 0", name="ck_curricular_execution_origin_nonempty"),
        CheckConstraint(
            "reversal_of_id IS NULL OR reversal_of_id <> id",
            name="ck_curricular_execution_not_self_reversal",
        ),
        Index(
            "ix_curricular_execution_assignment_date",
            "organization_id",
            "assignment_id",
            "recorded_at",
        ),
    )


class CurricularExecutionCredit(Base):
    __tablename__ = "curricular_execution_credit"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    execution_id: Mapped[int] = mapped_column(Integer, nullable=False)
    module_id: Mapped[int] = mapped_column(Integer, nullable=False)
    offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    delta_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "execution_id"],
            ["curricular_execution.organization_id", "curricular_execution.id"],
            name="fk_curricular_execution_credit_execution_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "module_id"],
            ["module.organization_id", "module.id"],
            name="fk_curricular_execution_credit_module_org",
        ),
        UniqueConstraint("execution_id", "module_id", name="uq_curricular_execution_credit_module"),
        CheckConstraint("offset_minutes >= 0", name="ck_curricular_execution_credit_offset"),
        CheckConstraint("delta_minutes <> 0", name="ck_curricular_execution_credit_nonzero"),
    )


class CurricularDebt(Base):
    __tablename__ = "curricular_debt"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    assignment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(String(160), nullable=False)
    origin_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    origin_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    created_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    author_membership_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "assignment_id"],
            ["curricular_assignment.organization_id", "curricular_assignment.id"],
            name="fk_curricular_debt_assignment_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "author_membership_id"],
            ["organization_membership.organization_id", "organization_membership.id"],
            name="fk_curricular_debt_author_org",
        ),
        UniqueConstraint("organization_id", "id", name="uq_curricular_debt_org_id"),
        UniqueConstraint(
            "organization_id", "assignment_id", "id", name="uq_curricular_debt_assignment_id"
        ),
        UniqueConstraint(
            "assignment_id", "origin", "origin_revision", name="uq_curricular_debt_origin"
        ),
        CheckConstraint("origin_revision > 0", name="ck_curricular_debt_revision_positive"),
        CheckConstraint("created_minutes > 0", name="ck_curricular_debt_minutes_positive"),
        CheckConstraint("length(trim(reason)) > 0", name="ck_curricular_debt_reason_nonempty"),
        Index(
            "ix_curricular_debt_assignment_origin",
            "organization_id",
            "assignment_id",
            "origin_date",
        ),
    )


class CurricularDebtRevision(Base):
    __tablename__ = "curricular_debt_revision"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    debt_id: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(String(160), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    delta_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    author_membership_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "debt_id"],
            ["curricular_debt.organization_id", "curricular_debt.id"],
            name="fk_curricular_debt_revision_debt_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "author_membership_id"],
            ["organization_membership.organization_id", "organization_membership.id"],
            name="fk_curricular_debt_revision_author_org",
        ),
        UniqueConstraint("organization_id", "id", name="uq_curricular_debt_revision_org_id"),
        UniqueConstraint(
            "debt_id", "origin", "revision", name="uq_curricular_debt_revision_origin"
        ),
        CheckConstraint("revision > 0", name="ck_curricular_debt_revision_number_positive"),
        CheckConstraint("delta_minutes <> 0", name="ck_curricular_debt_revision_nonzero"),
        CheckConstraint(
            "length(trim(reason)) > 0", name="ck_curricular_debt_revision_reason_nonempty"
        ),
    )


class CurricularDebtSettlement(Base):
    __tablename__ = "curricular_debt_settlement"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    debt_id: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_id: Mapped[int] = mapped_column(Integer, nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    reversal_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "debt_id"],
            ["curricular_debt.organization_id", "curricular_debt.id"],
            name="fk_curricular_debt_settlement_debt_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "execution_id"],
            ["curricular_execution.organization_id", "curricular_execution.id"],
            name="fk_curricular_debt_settlement_execution_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reversal_of_id"],
            ["curricular_debt_settlement.organization_id", "curricular_debt_settlement.id"],
            name="fk_curricular_debt_settlement_reversal_org",
        ),
        UniqueConstraint("organization_id", "id", name="uq_curricular_debt_settlement_org_id"),
        UniqueConstraint("debt_id", "execution_id", name="uq_curricular_debt_settlement_execution"),
        CheckConstraint("minutes <> 0", name="ck_curricular_debt_settlement_nonzero"),
        CheckConstraint(
            "reversal_of_id IS NULL OR reversal_of_id <> id",
            name="ck_curricular_debt_settlement_not_self_reversal",
        ),
    )


class SchedulerVersionV1(Base):
    __tablename__ = "scheduler_version_v1"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    school_year_id: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "school_year_id"],
            ["scheduler_school_year.organization_id", "scheduler_school_year.id"],
            name="fk_scheduler_version_v1_year_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "school_year_id", "previous_version_id"],
            [
                "scheduler_version_v1.organization_id",
                "scheduler_version_v1.school_year_id",
                "scheduler_version_v1.id",
            ],
            name="fk_scheduler_version_v1_previous",
        ),
        UniqueConstraint(
            "organization_id", "school_year_id", "id", name="uq_scheduler_version_v1_year_id"
        ),
        CheckConstraint(
            "status IN ('CANDIDATE', 'ACTIVE', 'SUPERSEDED')",
            name="ck_scheduler_version_v1_status",
        ),
        CheckConstraint(
            "status <> 'ACTIVE' OR approved_at IS NOT NULL",
            name="ck_scheduler_version_v1_active_approved",
        ),
        CheckConstraint("length(trim(origin)) > 0", name="ck_scheduler_version_v1_origin"),
        CheckConstraint(
            "length(snapshot_digest) = 64", name="ck_scheduler_version_v1_digest_length"
        ),
        Index(
            "uq_scheduler_version_v1_active_year",
            "organization_id",
            "school_year_id",
            unique=True,
            postgresql_where=(status == "ACTIVE"),
        ),
    )


class SchedulerLessonV1(Base):
    __tablename__ = "scheduler_lesson_v1"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    school_year_id: Mapped[int] = mapped_column(Integer, nullable=False)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    assignment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    stable_key: Mapped[str] = mapped_column(String(64), nullable=False)
    school_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    room_id: Mapped[int] = mapped_column(Integer, nullable=False)
    physical_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    credit_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    source_lesson_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "school_year_id", "version_id"],
            [
                "scheduler_version_v1.organization_id",
                "scheduler_version_v1.school_year_id",
                "scheduler_version_v1.id",
            ],
            name="fk_scheduler_lesson_v1_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "school_year_id", "assignment_id"],
            [
                "curricular_assignment.organization_id",
                "curricular_assignment.school_year_id",
                "curricular_assignment.id",
            ],
            name="fk_scheduler_lesson_v1_assignment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "room_id"],
            ["room.organization_id", "room.id"],
            name="fk_scheduler_lesson_v1_room",
        ),
        ForeignKeyConstraint(
            ["organization_id", "school_year_id", "source_lesson_id"],
            [
                "scheduler_lesson_v1.organization_id",
                "scheduler_lesson_v1.school_year_id",
                "scheduler_lesson_v1.id",
            ],
            name="fk_scheduler_lesson_v1_source",
        ),
        UniqueConstraint(
            "organization_id", "school_year_id", "id", name="uq_scheduler_lesson_v1_year_id"
        ),
        UniqueConstraint(
            "organization_id",
            "school_year_id",
            "version_id",
            "id",
            name="uq_scheduler_lesson_v1_version_id",
        ),
        UniqueConstraint(
            "organization_id",
            "school_year_id",
            "assignment_id",
            "id",
            name="uq_scheduler_lesson_v1_assignment_id",
        ),
        UniqueConstraint("version_id", "stable_key", name="uq_scheduler_lesson_v1_stable_key"),
        CheckConstraint("ends_at > starts_at", name="ck_scheduler_lesson_v1_interval"),
        CheckConstraint("physical_minutes > 0", name="ck_scheduler_lesson_v1_physical"),
        CheckConstraint(
            "physical_minutes * 60 = EXTRACT(EPOCH FROM (ends_at - starts_at))",
            name="ck_scheduler_lesson_v1_physical_matches_interval",
        ),
        CheckConstraint(
            "credit_minutes > 0 AND credit_minutes <= physical_minutes",
            name="ck_scheduler_lesson_v1_credit",
        ),
        CheckConstraint("length(trim(stable_key)) > 0", name="ck_scheduler_lesson_v1_key"),
        Index(
            "ix_scheduler_lesson_v1_assignment_date",
            "organization_id",
            "school_year_id",
            "assignment_id",
            "school_date",
        ),
    )


class SchedulerLessonSliceV1(Base):
    __tablename__ = "scheduler_lesson_slice_v1"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    school_year_id: Mapped[int] = mapped_column(Integer, nullable=False)
    lesson_id: Mapped[int] = mapped_column(Integer, nullable=False)
    module_id: Mapped[int] = mapped_column(Integer, nullable=False)
    offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "school_year_id", "lesson_id"],
            [
                "scheduler_lesson_v1.organization_id",
                "scheduler_lesson_v1.school_year_id",
                "scheduler_lesson_v1.id",
            ],
            name="fk_scheduler_lesson_slice_v1_lesson",
        ),
        ForeignKeyConstraint(
            ["organization_id", "module_id"],
            ["module.organization_id", "module.id"],
            name="fk_scheduler_lesson_slice_v1_module",
        ),
        UniqueConstraint("lesson_id", "module_id", name="uq_scheduler_lesson_slice_v1_module"),
        CheckConstraint("offset_minutes >= 0", name="ck_scheduler_lesson_slice_v1_offset"),
        CheckConstraint("minutes > 0", name="ck_scheduler_lesson_slice_v1_minutes"),
    )


class SchedulerRecoveryReservationV1(Base):
    __tablename__ = "scheduler_recovery_reservation_v1"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    school_year_id: Mapped[int] = mapped_column(Integer, nullable=False)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    assignment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    lesson_id: Mapped[int] = mapped_column(Integer, nullable=False)
    debt_id: Mapped[int] = mapped_column(Integer, nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "school_year_id", "version_id", "lesson_id"],
            [
                "scheduler_lesson_v1.organization_id",
                "scheduler_lesson_v1.school_year_id",
                "scheduler_lesson_v1.version_id",
                "scheduler_lesson_v1.id",
            ],
            name="fk_scheduler_recovery_reservation_v1_lesson",
        ),
        ForeignKeyConstraint(
            ["organization_id", "school_year_id", "assignment_id", "lesson_id"],
            [
                "scheduler_lesson_v1.organization_id",
                "scheduler_lesson_v1.school_year_id",
                "scheduler_lesson_v1.assignment_id",
                "scheduler_lesson_v1.id",
            ],
            name="fk_scheduler_recovery_reservation_v1_lesson_assignment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assignment_id", "debt_id"],
            [
                "curricular_debt.organization_id",
                "curricular_debt.assignment_id",
                "curricular_debt.id",
            ],
            name="fk_scheduler_recovery_reservation_v1_debt_assignment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "debt_id"],
            ["curricular_debt.organization_id", "curricular_debt.id"],
            name="fk_scheduler_recovery_reservation_v1_debt",
        ),
        UniqueConstraint(
            "version_id",
            "lesson_id",
            "debt_id",
            name="uq_scheduler_recovery_reservation_v1_debt",
        ),
        CheckConstraint("minutes > 0", name="ck_scheduler_recovery_reservation_v1_minutes"),
    )


class SchedulerLessonLogV1(Base):
    __tablename__ = "scheduler_lesson_log_v1"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    school_year_id: Mapped[int] = mapped_column(Integer, nullable=False)
    lesson_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_membership_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_membership_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(250), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    logged_by_membership_id: Mapped[int] = mapped_column(Integer, nullable=False)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "school_year_id", "lesson_id"],
            [
                "scheduler_lesson_v1.organization_id",
                "scheduler_lesson_v1.school_year_id",
                "scheduler_lesson_v1.id",
            ],
            name="fk_scheduler_lesson_log_v1_lesson",
        ),
        ForeignKeyConstraint(
            ["organization_id", "logged_by_membership_id"],
            ["organization_membership.organization_id", "organization_membership.id"],
            name="fk_scheduler_lesson_log_v1_author_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "decided_by_membership_id"],
            ["organization_membership.organization_id", "organization_membership.id"],
            name="fk_scheduler_lesson_log_v1_decider_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "revoked_by_membership_id"],
            ["organization_membership.organization_id", "organization_membership.id"],
            name="fk_scheduler_lesson_log_v1_revoker_org",
        ),
        UniqueConstraint("lesson_id", name="uq_scheduler_lesson_log_v1_lesson"),
        UniqueConstraint("organization_id", "id", name="uq_scheduler_lesson_log_v1_org_id"),
        CheckConstraint("revision > 0", name="ck_scheduler_lesson_log_v1_revision"),
        CheckConstraint(
            "status IN ('COMPLETED', 'OCCURRENCE', 'REVOKED')",
            name="ck_scheduler_lesson_log_v1_status",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('GIVEN', 'GAP', 'SUBSTITUTED')",
            name="ck_scheduler_lesson_log_v1_decision",
        ),
        CheckConstraint(
            "(decision IS NULL) = (decided_at IS NULL)",
            name="ck_scheduler_lesson_log_v1_decision_metadata",
        ),
    )


class SchedulerJobV1(Base):
    __tablename__ = "scheduler_job_v1"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    school_year_id: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    origin: Mapped[str] = mapped_column(String(160), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_token: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requested_by_membership_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grid_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_revision_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planning_revision_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "school_year_id"],
            ["scheduler_school_year.organization_id", "scheduler_school_year.id"],
            name="fk_scheduler_job_v1_year_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requested_by_membership_id"],
            ["organization_membership.organization_id", "organization_membership.id"],
            name="fk_scheduler_job_v1_requester_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "school_year_id", "base_version_id"],
            [
                "scheduler_version_v1.organization_id",
                "scheduler_version_v1.school_year_id",
                "scheduler_version_v1.id",
            ],
            name="fk_scheduler_job_v1_base_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "grid_version_id"],
            ["grid_version.organization_id", "grid_version.id"],
            name="fk_scheduler_job_v1_grid_version_tenant_scoped",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_scheduler_job_v1_org_id"),
        UniqueConstraint(
            "organization_id", "school_year_id", "id", name="uq_scheduler_job_v1_year_id"
        ),
        UniqueConstraint(
            "organization_id", "origin", "revision", name="uq_scheduler_job_v1_origin_revision"
        ),
        CheckConstraint("revision > 0", name="ck_scheduler_job_v1_revision_positive"),
        CheckConstraint("attempt_token > 0", name="ck_scheduler_job_v1_attempt_positive"),
        CheckConstraint(
            "strategy IN (" + ", ".join(f"'{value}'" for value in JOB_STRATEGIES) + ")",
            name="ck_scheduler_job_v1_strategy",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{value}'" for value in JOB_STATUSES) + ")",
            name="ck_scheduler_job_v1_status",
        ),
        CheckConstraint(
            "(status IN ("
            + ", ".join(f"'{value}'" for value in JOB_TERMINAL_STATUSES)
            + ") AND finished_at IS NOT NULL) OR "
            "(status NOT IN ("
            + ", ".join(f"'{value}'" for value in JOB_TERMINAL_STATUSES)
            + ") AND finished_at IS NULL)",
            name="ck_scheduler_job_v1_terminal_finished",
        ),
        Index(
            "uq_scheduler_job_v1_active_year",
            "organization_id",
            "school_year_id",
            unique=True,
            postgresql_where=(status.in_(JOB_ACTIVE_STATUSES)),
        ),
        Index("ix_scheduler_job_v1_grid_version_id", "grid_version_id"),
        Index(
            "uq_scheduler_job_v1_running_global",
            true(),
            unique=True,
            postgresql_where=(status.in_(("RUNNING", "VALIDATING"))),
        ),
    )


class SchedulerProposalV1(Base):
    __tablename__ = "scheduler_proposal_v1"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False)
    school_year_id: Mapped[int] = mapped_column(Integer, nullable=False)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_revision_used: Mapped[int] = mapped_column(Integer, nullable=False)
    planning_revision_used: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    diff_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_membership_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "school_year_id"],
            ["scheduler_school_year.organization_id", "scheduler_school_year.id"],
            name="fk_scheduler_proposal_v1_year_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "school_year_id", "job_id"],
            [
                "scheduler_job_v1.organization_id",
                "scheduler_job_v1.school_year_id",
                "scheduler_job_v1.id",
            ],
            name="fk_scheduler_proposal_v1_job",
        ),
        ForeignKeyConstraint(
            ["organization_id", "school_year_id", "version_id"],
            [
                "scheduler_version_v1.organization_id",
                "scheduler_version_v1.school_year_id",
                "scheduler_version_v1.id",
            ],
            name="fk_scheduler_proposal_v1_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "school_year_id", "base_version_id"],
            [
                "scheduler_version_v1.organization_id",
                "scheduler_version_v1.school_year_id",
                "scheduler_version_v1.id",
            ],
            name="fk_scheduler_proposal_v1_base_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "decided_by_membership_id"],
            ["organization_membership.organization_id", "organization_membership.id"],
            name="fk_scheduler_proposal_v1_decider_org",
        ),
        UniqueConstraint("organization_id", "id", name="uq_scheduler_proposal_v1_org_id"),
        UniqueConstraint("job_id", name="uq_scheduler_proposal_v1_job"),
        CheckConstraint("input_revision_used >= 0", name="ck_scheduler_proposal_v1_input_revision"),
        CheckConstraint(
            "planning_revision_used >= 0", name="ck_scheduler_proposal_v1_planning_revision"
        ),
        CheckConstraint(
            "length(snapshot_digest) = 64", name="ck_scheduler_proposal_v1_digest_length"
        ),
        CheckConstraint("length(trim(policy_version)) > 0", name="ck_scheduler_proposal_v1_policy"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{value}'" for value in PROPOSAL_STATUSES) + ")",
            name="ck_scheduler_proposal_v1_status",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND decided_at IS NULL AND decided_by_membership_id IS NULL) OR "
            "(status <> 'PENDING' AND decided_at IS NOT NULL)",
            name="ck_scheduler_proposal_v1_decision",
        ),
        Index(
            "uq_scheduler_proposal_v1_current_year",
            "organization_id",
            "school_year_id",
            unique=True,
            postgresql_where=(status == "PENDING"),
        ),
    )
