import enum
from datetime import datetime, time, timezone, date as date_type
from typing import List, Optional
from sqlalchemy import (
    Column, Integer, String, Boolean,
    ForeignKey, Date, DateTime, Time,
    Text, Enum as SAEnum, UniqueConstraint, CheckConstraint, ForeignKeyConstraint,
    Table, Float, Index, event,
)
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship
from app.db.database import Base

# --- FK Reference Constants (SonarQube S1192) ---
FK_ORG_ID = "organization.id"
FK_TEACHER_ID = "teacher.id"
FK_SUBJECT_ID = "subject.id"
FK_CLASS_ID = "class.id"
FK_TIMESLOT_ID = "timeslot.id"
FK_SCHEDULE_OUTPUT_ID = "schedule_output.id"
CASCADE_ALL_DELETE = "all, delete-orphan"
ON_DELETE_SET_NULL = "SET NULL"

class RoomType(str, enum.Enum):
    normal = "normal"
    lab = "lab"
    gym = "gym"
    art = "art"

class CalendarEventType(str, enum.Enum):
    national_holiday = "national_holiday"
    school_break = "school_break"
    exam_period = "exam_period"
    other = "other"

class CalendarEventSource(str, enum.Enum):
    auto = "auto"
    manual = "manual"

class LessonOccurrenceStatus(str, enum.Enum):
    GIVEN = "GIVEN"
    GAP = "GAP"
    SUBSTITUTED = "SUBSTITUTED"
    REVOKED = "REVOKED"

class LessonLogStatus(str, enum.Enum):
    """Estado de execução de um bloco de aula gerado pelo Solver."""
    PENDING = "PENDING"        # Aula ainda não registada (padrão)
    COMPLETED = "COMPLETED"    # Professor confirmou que a aula foi dada
    OCCURRENCE = "OCCURRENCE"  # Falta/Ocorrência registada para este bloco

class OperationalBlockStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"

class OperationalBlockExecutionStatus(str, enum.Enum):
    PENDING_LOG = "PENDING_LOG"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class SchoolYearPublicationState(str, enum.Enum):
    UNPUBLISHED = "UNPUBLISHED"
    PUBLISHED = "PUBLISHED"


class ScheduleGenerationStrategy(str, enum.Enum):
    COMPLETE_GENERATION = "COMPLETE_GENERATION"
    ADAPTIVE_REPAIR = "ADAPTIVE_REPAIR"


class ScheduleGenerationTrigger(str, enum.Enum):
    FIRST_GENERATION = "FIRST_GENERATION"
    EXPLICIT_DEBT = "EXPLICIT_DEBT"
    SCHEDULER_CHANGE = "SCHEDULER_CHANGE"
    MIXED = "MIXED"


class ScheduleGenerationJobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELED = "CANCELED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    NO_VALID_OUTPUT = "NO_VALID_OUTPUT"


class ScheduleGenerationResultCategory(str, enum.Enum):
    COMPLETE_SUCCESS = "COMPLETE_SUCCESS"
    PARTIAL_RECOVERY = "PARTIAL_RECOVERY"
    NO_VALID_OUTPUT = "NO_VALID_OUTPUT"


class ScheduleDraftState(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REPLACED = "REPLACED"
    STALE = "STALE"
    INVALIDATED = "INVALIDATED"


class ScheduleDraftBlockChangeType(str, enum.Enum):
    UNCHANGED = "UNCHANGED"
    ADDED = "ADDED"
    MOVED = "MOVED"
    ROOM_ONLY = "ROOM_ONLY"
    REPLACED = "REPLACED"


class ScheduleDiffChangeType(str, enum.Enum):
    ADDED = "ADDED"
    MOVED = "MOVED"
    CHANGED = "CHANGED"
    REMOVED = "REMOVED"
    UNCHANGED_IMPACTED = "UNCHANGED_IMPACTED"


class ScheduleDiffScope(str, enum.Enum):
    AFFECTED = "AFFECTED"
    RELATED = "RELATED"
    UNRELATED = "UNRELATED"


class ActiveScheduleBlockStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REMOVED = "REMOVED"
    CANCELED = "CANCELED"


class PlannedRecoveryLinkStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    DELIVERED = "DELIVERED"
    CANCELED = "CANCELED"
    REPLACED = "REPLACED"


class SchedulerStateChangeOperation(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    BULK_IMPORT = "BULK_IMPORT"


class SchedulerStateChangeScope(str, enum.Enum):
    FUTURE_IMPACTING = "FUTURE_IMPACTING"
    PAST_ONLY = "PAST_ONLY"
    NO_OP = "NO_OP"
    INACTIVE_RESOURCE = "INACTIVE_RESOURCE"

class TimesheetStatus(str, enum.Enum):
    """Estado do ciclo de vida do fecho semanal de um professor."""
    OPEN = "OPEN"            # Semana aberta — professor pode editar
    SUBMITTED = "SUBMITTED"  # Professor submeteu — aguarda aprovação do admin
    APPROVED = "APPROVED"    # Admin aprovou — semana congelada

class UserRole(str, enum.Enum):
    admin = "admin"
    teacher = "teacher"
    student = "student"


class MembershipLifecycleStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class MembershipAccessStatus(str, enum.Enum):
    none = "none"
    pending_invite = "pending_invite"
    invite_expired = "invite_expired"
    active = "active"
    blocked = "blocked"
    sync_error = "sync_error"


class TeacherAccessMode(str, enum.Enum):
    platform = "platform"
    scheduler_only = "scheduler_only"


class MembershipCapability(str, enum.Enum):
    teacher = "teacher"
    admin = "admin"


class ClerkOrganizationRole(str, enum.Enum):
    member = "org:member"
    admin = "org:admin"


class ClerkInvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"
    expired = "expired"


class MemberAccessOperationType(str, enum.Enum):
    create_invitation = "create_invitation"
    revoke_invitation = "revoke_invitation"
    revoke_membership = "revoke_membership"
    change_role = "change_role"
    resend_invitation = "resend_invitation"
    restore_access = "restore_access"
    block_access = "block_access"


class MemberAccessOperationStatus(str, enum.Enum):
    pending = "pending"
    clerk_succeeded = "clerk_succeeded"
    local_committed = "local_committed"
    failed = "failed"
    compensated = "compensated"
    compensation_failed = "compensation_failed"
    support_required = "support_required"


class ClerkWebhookProcessingStatus(str, enum.Enum):
    received = "received"
    processing = "processing"
    processed = "processed"
    ignored = "ignored"
    retryable_failed = "retryable_failed"
    sync_error = "sync_error"
    dead_letter = "dead_letter"

class OrganizationPlanStatus(str, enum.Enum):
    inactive = "inactive"
    active = "active"
    suspended = "suspended"

class SubstitutionStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"

class ConstraintType(str, enum.Enum):
    # Regras de Sala/Tempo
    specific_room = "specific_room"
    lock_time = "lock_time"
    
    # Regras de Professor
    teacher_unavailable = "teacher_unavailable"
    teacher_preferred = "teacher_preferred"
    
    # Outras genéricas
    min_gap = "min_gap"
    max_days = "max_days"

class PreferenceLevel(int, enum.Enum):
    PREFERRED = 2    # Verde: "Quero muito" (Bónus no score)
    NEUTRAL = 1      # Amarelo: "Tanto faz" (Padrão)
    AVOID = 0        # Laranja: "Evitar" (Penalização no score)
    IMPOSSIBLE = -1  # Vermelho: "Proibido" (Hard Constraint)

# Tabela Relacional entre Cursos e Disciplinas
course_subject_link = Table(
    "course_subject_link",
    Base.metadata,
    Column("organization_id", ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, primary_key=True),
    Column("course_id", ForeignKey("course.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", ForeignKey(FK_SUBJECT_ID, ondelete="CASCADE"), primary_key=True),
    Index("ix_course_subject_link_organization_id", "organization_id"),
)

# Tabela Relacional entre Professores e Disciplinas
teacher_subject_link = Table(
    "teacher_subject_link",
    Base.metadata,
    Column("organization_id", ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, primary_key=True),
    Column("teacher_id", ForeignKey(FK_TEACHER_ID, ondelete="CASCADE"), primary_key=True),
    Column("subject_id", ForeignKey(FK_SUBJECT_ID, ondelete="CASCADE"), primary_key=True),
    Index("ix_teacher_subject_link_organization_id", "organization_id"),
)

# Tabela Relacional: Disciplinas de uma Turma (com professor opcional)
# Esta tabela define que disciplinas uma turma tem num determinado grade_level
# e quem é o professor atribuído a cada uma.
class ClassSubjectLink(Base):
    __tablename__ = "class_subject_link"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True)
    class_id: Mapped[int] = mapped_column(ForeignKey(FK_CLASS_ID, ondelete="CASCADE"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey(FK_SUBJECT_ID, ondelete="CASCADE"), index=True)
    grade_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 10, 11, 12
    teacher_id: Mapped[Optional[int]] = mapped_column(ForeignKey(FK_TEACHER_ID, ondelete=ON_DELETE_SET_NULL), nullable=True, index=True)

    # Relacionamentos
    class_: Mapped["Class"] = relationship()
    subject: Mapped["Subject"] = relationship()
    teacher: Mapped[Optional["Teacher"]] = relationship()

    __table_args__ = (
        UniqueConstraint("organization_id", "class_id", "subject_id", "grade_level", name="uq_class_subject_grade"),
    )

class Availability(Base):
    __tablename__ = "availability"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey(FK_TEACHER_ID), index=True)
    timeslot_id: Mapped[int] = mapped_column(ForeignKey(FK_TIMESLOT_ID), index=True)
    
    # O Score (-1 a 2)
    score: Mapped[int] = mapped_column(Integer, default=PreferenceLevel.NEUTRAL.value, nullable=False)

    # Relacionamentos (Ajusta os nomes se as tuas classes Teacher/Timeslot forem diferentes)
    teacher: Mapped["Teacher"] = relationship(back_populates="availabilities")
    timeslot: Mapped["Timeslot"] = relationship()

    __table_args__ = (
        UniqueConstraint('organization_id', 'teacher_id', 'timeslot_id', name='uq_teacher_timeslot_availability'),
    )

# Modelo "Organization" (O Colégio)
# Esta é a tabela "mãe" de quase todas as outras.
class Organization(Base):
    __tablename__ = "organization"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    clerk_org_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)

    courses: Mapped[List["Course"]] = relationship(back_populates="organization", cascade=CASCADE_ALL_DELETE)
    
    # Campo para o plano de subscrição (do Ponto 3.6 do Charter)
    plan_status: Mapped[OrganizationPlanStatus] = mapped_column(
        SAEnum(OrganizationPlanStatus), default=OrganizationPlanStatus.inactive, nullable=False
    )

    # --- Relacionamentos ---
    # Isto cria "atalhos" em Python para aceder aos dados ligados.
    # Ex: my_organization.users, my_organization.teachers, etc.
    users: Mapped[List["User"]] = relationship(back_populates="organization")
    teachers: Mapped[List["Teacher"]] = relationship(back_populates="organization")
    classes: Mapped[List["Class"]] = relationship(back_populates="organization")
    rooms: Mapped[List["Room"]] = relationship(back_populates="organization")
    subjects: Mapped[List["Subject"]] = relationship(back_populates="organization")
    timeslots: Mapped[List["Timeslot"]] = relationship(back_populates="organization")

    settings: Mapped[Optional["OrganizationSettings"]] = relationship(back_populates="organization", cascade=CASCADE_ALL_DELETE, uselist=False)
    grid_settings: Mapped[Optional["OrganizationGridSettings"]] = relationship(back_populates="organization", cascade=CASCADE_ALL_DELETE, uselist=False)
    calendar_events: Mapped[List["SchoolCalendarEvent"]] = relationship(back_populates="organization", cascade=CASCADE_ALL_DELETE)

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name='{self.name}')>"


# Modelo "User" (O Diretor/Admin)
class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    clerk_user_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    # O Papel do utilizador (Admin por defeito)
    role: Mapped[Optional[UserRole]] = mapped_column(SAEnum(UserRole), default=None, nullable=True)
    # Se for admin, isto fica NULL. Se for professor, aponta para o ID dele.
    teacher_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(FK_TEACHER_ID, name="fk_user_teacher", use_alter=True),
        nullable=True,
    )
    organization_id: Mapped[Optional[int]] = mapped_column(ForeignKey(FK_ORG_ID), nullable=True, index=True)
    organization: Mapped["Organization"] = relationship(back_populates="users")
    # Atalho para aceder aos dados do professor (se existirem)
    teacher_profile: Mapped[Optional["Teacher"]] = relationship()
    # Permite bloquear utilizadores sem apagar o histórico (Soft Delete)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, default=None, nullable=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    clerk_primary_email_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    clerk_profile_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_clerk_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    memberships: Mapped[List["OrganizationMembership"]] = relationship(
        back_populates="account",
        foreign_keys="OrganizationMembership.account_id",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


# 5. Modelo "Teacher"
class Teacher(Base):
    __tablename__ = "teacher"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Chave Estrangeira: Liga o Professor à sua Organization
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID))
    organization_membership_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "organization_membership.id",
            ondelete=ON_DELETE_SET_NULL,
            name="fk_teacher_organization_membership",
            use_alter=True,
        ),
        nullable=True,
        unique=True,
        index=True,
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relacionamento: Permite-nos fazer my_teacher.organization
    organization: Mapped["Organization"] = relationship(back_populates="teachers")
    organization_membership: Mapped[Optional["OrganizationMembership"]] = relationship(back_populates="teacher_profile")

    subjects: Mapped[List["Subject"]] = relationship(
        secondary=teacher_subject_link,
        back_populates="teachers"
    )

    @property
    def subject_ids(self) -> List[int]:
        """
        Permite ao Pydantic ler 'teacher.subject_ids' e receber [1, 2]
        em vez de crashar a tentar ler objetos complexos.
        """
        return [s.id for s in self.subjects]

    availabilities: Mapped[List["Availability"]] = relationship(back_populates="teacher", cascade=CASCADE_ALL_DELETE)
    timesheets: Mapped[List["TeacherWeeklyTimesheet"]] = relationship(back_populates="teacher", cascade=CASCADE_ALL_DELETE)

    def __repr__(self) -> str:
        return f"<Teacher(id={self.id}, name='{self.name}')>"


class OrganizationMembership(Base):
    __tablename__ = "organization_membership"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    lifecycle_status: Mapped[MembershipLifecycleStatus] = mapped_column(
        SAEnum(MembershipLifecycleStatus), default=MembershipLifecycleStatus.active, nullable=False, index=True
    )
    access_status: Mapped[MembershipAccessStatus] = mapped_column(
        SAEnum(MembershipAccessStatus), default=MembershipAccessStatus.none, nullable=False, index=True
    )
    teacher_access_mode: Mapped[Optional[TeacherAccessMode]] = mapped_column(SAEnum(TeacherAccessMode), nullable=True)
    expected_clerk_role: Mapped[Optional[ClerkOrganizationRole]] = mapped_column(
        SAEnum(ClerkOrganizationRole, values_callable=lambda enum_cls: [item.value for item in enum_cls]),
        nullable=True,
    )
    clerk_membership_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    clerk_invitation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    clerk_invitation_status: Mapped[Optional[ClerkInvitationStatus]] = mapped_column(SAEnum(ClerkInvitationStatus), nullable=True)
    invitation_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    access_error_category: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    access_error_safe_message: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    access_block_reason: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True)
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    organization: Mapped["Organization"] = relationship()
    account: Mapped["User"] = relationship(back_populates="memberships", foreign_keys=[account_id])
    capabilities: Mapped[List["OrganizationMembershipCapability"]] = relationship(
        back_populates="membership", cascade=CASCADE_ALL_DELETE
    )
    teacher_profile: Mapped[Optional["Teacher"]] = relationship(back_populates="organization_membership", uselist=False)
    created_by_user: Mapped[Optional["User"]] = relationship(foreign_keys=[created_by_user_id])
    updated_by_user: Mapped[Optional["User"]] = relationship(foreign_keys=[updated_by_user_id])

    __table_args__ = (
        UniqueConstraint("organization_id", "account_id", name="uq_org_membership_account"),
        CheckConstraint(
            "access_status != 'active' OR account_id IS NOT NULL",
            name="ck_membership_active_has_account",
        ),
    )


class OrganizationMembershipCapability(Base):
    __tablename__ = "organization_membership_capability"

    organization_membership_id: Mapped[int] = mapped_column(
        ForeignKey("organization_membership.id", ondelete="CASCADE"), primary_key=True
    )
    capability: Mapped[MembershipCapability] = mapped_column(SAEnum(MembershipCapability), primary_key=True)

    membership: Mapped["OrganizationMembership"] = relationship(back_populates="capabilities")


class MemberAccessOperation(Base):
    __tablename__ = "member_access_operation"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True)
    membership_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organization_membership.id", ondelete=ON_DELETE_SET_NULL), nullable=True, index=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True, index=True)
    target_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    operation_type: Mapped[MemberAccessOperationType] = mapped_column(SAEnum(MemberAccessOperationType), nullable=False)
    operation_status: Mapped[MemberAccessOperationStatus] = mapped_column(
        SAEnum(MemberAccessOperationStatus), default=MemberAccessOperationStatus.pending, nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    intended_capabilities_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    intended_clerk_role: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    previous_access_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    draft_payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    clerk_org_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    clerk_user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    clerk_membership_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    clerk_invitation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_error_category: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    provider_error_safe_message: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    provider_error_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    compensation_attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    support_required_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    support_resolution_action: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    support_resolved_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True)
    support_resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    support_resolution_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ClerkWebhookEvent(Base):
    __tablename__ = "clerk_webhook_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    svix_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    clerk_object_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    clerk_org_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    clerk_user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    processing_status: Mapped[ClerkWebhookProcessingStatus] = mapped_column(
        SAEnum(ClerkWebhookProcessingStatus), default=ClerkWebhookProcessingStatus.received, nullable=False, index=True
    )
    error_category: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    support_resolution_action: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    support_resolved_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True)
    support_resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    support_resolution_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# 6. Modelo "Class" (Turma)
class Class(Base):
    __tablename__ = "class"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)  # Sem default - admin define

    # Ciclo do curso (ex: 2025-2028 para 10º, 2024-2027 para 11º, 2023-2026 para 12º)
    start_year: Mapped[int] = mapped_column(Integer, nullable=False)  # Ex: 2025
    end_year: Mapped[int] = mapped_column(Integer, nullable=False)  # Ex: 2028
    grade_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 10, 11, 12

    # Sprint 0: Dados de progresso do solver
    projected_end_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Associação a um Curso
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id"), nullable=False)
    course: Mapped["Course"] = relationship(back_populates="classes")

    # Histórico de progresso
    progress_records: Mapped[List["ClassProgress"]] = relationship(back_populates="class_", cascade=CASCADE_ALL_DELETE)

    # Chave Estrangeira: Liga a Turma à sua Organization
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID))
    
    # Relacionamento: Permite-nos fazer my_class.organization
    organization: Mapped["Organization"] = relationship(back_populates="classes")

    def __repr__(self) -> str:
        return f"<Class(id={self.id}, name='{self.name}')>"


# 7. Modelo "Room" (Sala)
class Room(Base):
    __tablename__ = "room"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Adicionamos a capacidade (Lotação)
    capacity: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    
    # Usamos o Enum que definimos em cima
    type: Mapped[RoomType] = mapped_column(SAEnum(RoomType), nullable=False, default=RoomType.normal)

    # Chave Estrangeira: Liga a Sala à sua Organization
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID))
    
    # Relacionamento: Permite-nos fazer my_room.organization
    organization: Mapped["Organization"] = relationship(back_populates="rooms")

    def __repr__(self) -> str:
        return f"<Room(id={self.id}, name='{self.name}', type='{self.type.value}')>"


# 8. Modelo "Subject" (Disciplina)
class Subject(Base):
    __tablename__ = "subject"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Define qual o tipo de sala ideal para esta disciplina.
    # Default: Sala Normal.
    required_room_type: Mapped[RoomType] = mapped_column(
        SAEnum(RoomType), 
        default=RoomType.normal, 
        nullable=False
    )

    modules: Mapped[List["Module"]] = relationship(back_populates="subject", cascade=CASCADE_ALL_DELETE)

    # Chave Estrangeira: Liga a Disciplina à sua Organization
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID))
    
    # Relacionamento: Permite-nos fazer my_subject.organization
    organization: Mapped["Organization"] = relationship(back_populates="subjects")
    
    # Relação N:M com Course - Define a Matriz Curricular
    courses: Mapped[List["Course"]] = relationship(
        secondary=course_subject_link,
        back_populates="subjects"
    )

    teachers: Mapped[List[Teacher]] = relationship(
        secondary=teacher_subject_link,
        back_populates="subjects"
    )

    def __repr__(self) -> str:
        return f"<Subject(id={self.id}, name='{self.name}')>"


# 9. Modelo "Timeslot" (Bloco Horário)
class Timeslot(Base):
    __tablename__ = "timeslot"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # 0=Segunda, 1=Terça, ..., 6=Domingo
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False) 
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    # Chave Estrangeira: Liga o Bloco Horário à sua Organization
    # Isto confirma a nossa decisão: cada escola define os seus próprios blocos
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID))
    
    # Relacionamento: Permite-nos fazer my_timeslot.organization
    organization: Mapped["Organization"] = relationship(back_populates="timeslots")

    # Garante que não há blocos duplicados para a mesma organização
    __table_args__ = (
        UniqueConstraint("day_of_week", "start_time", "organization_id", name="uq_timeslot"),
    )

    def __repr__(self) -> str:
        return f"<Timeslot(id={self.id}, day={self.day_of_week}, start='{self.start_time}')>"
    
# 10. Modelo "Lesson" (A "Necessidade de Aula")
# (Como definido no Ponto 3.5 do Charter)
class Lesson(Base):
    __tablename__ = "lesson"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID), index=True)

    class_id: Mapped[int] = mapped_column(ForeignKey(FK_CLASS_ID), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey(FK_SUBJECT_ID), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey(FK_TEACHER_ID), index=True)
    
    # --- Relacionamentos ---
    # (Para podermos aceder a lesson.class, lesson.teacher, etc.)
    organization: Mapped["Organization"] = relationship()
    class_model: Mapped["Class"] = relationship()
    subject: Mapped["Subject"] = relationship()
    teacher: Mapped["Teacher"] = relationship()

    # Garante que não definimos a mesma aula duas vezes
    __table_args__ = (
        UniqueConstraint(
            "organization_id", 
            "class_id", 
            "subject_id", 
            "teacher_id", 
            name="uq_lesson_definition"
        ),
    )

    def __repr__(self) -> str:
        return f"<Lesson(id={self.id}, class_id={self.class_id}, subject_id={self.subject_id})>"
    


# 11. Modelo "Constraint" (A "Regra")
class Constraint(Base):
    __tablename__ = "constraint"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), index=True)
    rule_type: Mapped[ConstraintType] = mapped_column(SAEnum(ConstraintType), nullable=False)
    rule_payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    organization: Mapped["Organization"] = relationship()

    def __repr__(self) -> str:
        return f"<Constraint(id={self.id}, type='{self.rule_type}')>"
    
# 12. Modelo "ScheduleOutput" (O Horário Final)
# (Como definido no Ponto 3.5 do Charter)
class ScheduleOutput(Base):
    __tablename__ = "schedule_output"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID), index=True)

    # A "aula" que foi agendada (ex: Matemática do 10A)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id"), index=True)
    
    # O "bloco" onde ela foi agendada (ex: Segunda 09:00)
    timeslot_id: Mapped[int] = mapped_column(ForeignKey(FK_TIMESLOT_ID), index=True)
    
    # A "sala" que foi usada (ex: Sala 1.1)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), index=True)
    
    # ID para versionar (ex: "Geração de Verão 2025")
    generation_id: Mapped[str] = mapped_column(String(100), index=True)

    # Sprint 0: Data absoluta e flag de rascunho
    date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True, index=True)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relacionamentos
    organization: Mapped["Organization"] = relationship()
    lesson: Mapped["Lesson"] = relationship()
    timeslot: Mapped["Timeslot"] = relationship()
    room: Mapped["Room"] = relationship()
    lesson_logs: Mapped[List["LessonLog"]] = relationship(viewonly=True)

    def __repr__(self) -> str:
        return f"<ScheduleOutput(lesson_id={self.lesson_id}, timeslot_id={self.timeslot_id})>"
    
# --- CONFIGURAÇÕES DA ESCOLA (Sprint 0) ---

class OrganizationSettings(Base):
    """Configurações da escola (única por organização)."""
    __tablename__ = "organization_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), unique=True, index=True)
    school_start_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    school_hard_end_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    repair_stability_window_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    auto_confirm_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_confirm_cutoff_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="settings")

    def __repr__(self) -> str:
        return f"<OrganizationSettings(organization_id={self.organization_id})>"


class SchedulerSchoolYear(Base):
    """Stable tenant-scoped identity for one scheduler school year."""
    __tablename__ = "scheduler_school_year"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(FK_ORG_ID, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    hard_end_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Lisbon")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "id", "organization_id", name="uq_scheduler_school_year_id_org"
        ),
        UniqueConstraint("organization_id", "label", name="uq_scheduler_school_year_org_label"),
        CheckConstraint("hard_end_date >= start_date", name="ck_scheduler_school_year_date_order"),
        Index(
            "uq_scheduler_school_year_active_org",
            "organization_id",
            unique=True,
            postgresql_where=(is_active.is_(True)),
        ),
    )


class SchedulerSchoolYearState(Base):
    """Publication lifecycle state for one tenant and school year."""
    __tablename__ = "scheduler_school_year_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(FK_ORG_ID, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    school_year_id: Mapped[int] = mapped_column(
        nullable=False,
        index=True,
    )
    school_year_publication_state: Mapped[SchoolYearPublicationState] = mapped_column(
        SAEnum(SchoolYearPublicationState),
        nullable=False,
        default=SchoolYearPublicationState.UNPUBLISHED,
    )
    active_schedule_version_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pending_draft_id: Mapped[Optional[int]] = mapped_column(
        nullable=True,
    )
    scheduler_state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_scheduler_state_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL),
        nullable=True,
    )
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["school_year_id", "organization_id"],
            ["scheduler_school_year.id", "scheduler_school_year.organization_id"],
            name="fk_scheduler_school_year_state_year_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id",
            "school_year_id",
            name="uq_scheduler_school_year_state_org_year",
        ),
        CheckConstraint(
            "scheduler_state_version >= 0",
            name="ck_scheduler_school_year_state_version_nonnegative",
        ),
        CheckConstraint(
            "lock_version >= 0",
            name="ck_scheduler_school_year_state_lock_version_nonnegative",
        ),
        CheckConstraint(
            "school_year_publication_state <> 'PUBLISHED' OR active_schedule_version_id IS NOT NULL",
            name="ck_scheduler_school_year_state_published_has_version",
        ),
        ForeignKeyConstraint(
            ["pending_draft_id", "organization_id", "school_year_id"],
            [
                "schedule_drafts.id",
                "schedule_drafts.organization_id",
                "schedule_drafts.school_year_id",
            ],
            name="fk_scheduler_school_year_state_pending_draft_scope",
        ),
    )


class ScheduleGenerationJob(Base):
    """Auditable execution record for one bounded generation attempt."""
    __tablename__ = "schedule_generation_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(FK_ORG_ID, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    school_year_id: Mapped[int] = mapped_column(
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL),
        nullable=True,
    )
    strategy: Mapped[ScheduleGenerationStrategy] = mapped_column(
        SAEnum(ScheduleGenerationStrategy),
        nullable=False,
    )
    trigger_type: Mapped[Optional[ScheduleGenerationTrigger]] = mapped_column(
        SAEnum(ScheduleGenerationTrigger),
        nullable=True,
    )
    job_status: Mapped[ScheduleGenerationJobStatus] = mapped_column(
        SAEnum(ScheduleGenerationJobStatus),
        nullable=False,
        default=ScheduleGenerationJobStatus.QUEUED,
    )
    result_category: Mapped[Optional[ScheduleGenerationResultCategory]] = mapped_column(
        SAEnum(ScheduleGenerationResultCategory),
        nullable=True,
    )
    generation_input_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    debt_basis_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scheduler_state_version_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    repair_policy_snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    input_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cancellation_requested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failure_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["school_year_id", "organization_id"],
            ["scheduler_school_year.id", "scheduler_school_year.organization_id"],
            name="fk_schedule_generation_job_year_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "school_year_id",
            name="uq_schedule_generation_job_id_scope",
        ),
        UniqueConstraint(
            "organization_id",
            "school_year_id",
            "idempotency_key",
            name="uq_schedule_generation_job_idempotency",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_schedule_generation_job_duration_nonnegative",
        ),
        CheckConstraint(
            "(job_status = 'SUCCEEDED' AND result_category IN "
            "('COMPLETE_SUCCESS', 'PARTIAL_RECOVERY')) OR "
            "(job_status = 'NO_VALID_OUTPUT' AND result_category = 'NO_VALID_OUTPUT') OR "
            "(job_status NOT IN ('SUCCEEDED', 'NO_VALID_OUTPUT') AND result_category IS NULL)",
            name="ck_schedule_generation_job_result_consistency",
        ),
        CheckConstraint(
            "(job_status IN ('CANCELED', 'SUCCEEDED', 'FAILED', 'NO_VALID_OUTPUT') "
            "AND finished_at IS NOT NULL) OR "
            "(job_status NOT IN ('CANCELED', 'SUCCEEDED', 'FAILED', 'NO_VALID_OUTPUT') "
            "AND finished_at IS NULL)",
            name="ck_schedule_generation_job_terminal_finished",
        ),
        CheckConstraint(
            "started_at IS NULL OR started_at >= queued_at",
            name="ck_schedule_generation_job_started_after_queued",
        ),
        CheckConstraint(
            "finished_at IS NULL OR (started_at IS NOT NULL AND finished_at >= started_at)",
            name="ck_schedule_generation_job_finished_after_started",
        ),
        Index(
            "uq_schedule_generation_job_active_year",
            "organization_id",
            "school_year_id",
            unique=True,
            postgresql_where=job_status.in_((
                ScheduleGenerationJobStatus.QUEUED,
                ScheduleGenerationJobStatus.RUNNING,
                ScheduleGenerationJobStatus.CANCEL_REQUESTED,
            )),
        ),
    )


class ScheduleDraft(Base):
    """Auditable proposed schedule state produced by a successful generation job."""
    __tablename__ = "schedule_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(FK_ORG_ID, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("scheduler_school_year.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    generation_job_id: Mapped[int] = mapped_column(
        nullable=False,
    )
    strategy: Mapped[ScheduleGenerationStrategy] = mapped_column(
        SAEnum(ScheduleGenerationStrategy),
        nullable=False,
    )
    draft_state: Mapped[ScheduleDraftState] = mapped_column(
        SAEnum(ScheduleDraftState),
        nullable=False,
        default=ScheduleDraftState.PENDING,
    )
    result_category: Mapped[ScheduleGenerationResultCategory] = mapped_column(
        SAEnum(ScheduleGenerationResultCategory),
        nullable=False,
    )
    trigger_type: Mapped[ScheduleGenerationTrigger] = mapped_column(
        SAEnum(ScheduleGenerationTrigger),
        nullable=False,
    )
    generation_input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduler_state_version_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    debt_basis_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    repair_policy_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    repair_policy_snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    editable_start_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    recovery_escalation_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    adaptation_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    projected_completion_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    hard_end_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    partial_recovery_blocker_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    main_blocker_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_actions_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    warnings_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    stale_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invalidated_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    decided_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL),
        nullable=True,
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["generation_job_id", "organization_id", "school_year_id"],
            [
                "schedule_generation_job.id",
                "schedule_generation_job.organization_id",
                "schedule_generation_job.school_year_id",
            ],
            name="fk_schedule_drafts_generation_job_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "generation_job_id",
            name="uq_schedule_drafts_generation_job",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "school_year_id",
            name="uq_schedule_drafts_id_scope",
        ),
        UniqueConstraint(
            "id",
            "generation_job_id",
            "organization_id",
            "school_year_id",
            name="uq_schedule_drafts_id_job_scope",
        ),
        CheckConstraint(
            "projected_completion_date <= hard_end_date",
            name="ck_schedule_drafts_completion_by_hard_end",
        ),
        CheckConstraint(
            "result_category <> 'NO_VALID_OUTPUT'",
            name="ck_schedule_drafts_has_valid_output",
        ),
        CheckConstraint(
            "scheduler_state_version_used IS NULL OR scheduler_state_version_used >= 0",
            name="ck_schedule_drafts_state_version_nonnegative",
        ),
        CheckConstraint(
            "strategy = 'COMPLETE_GENERATION' OR editable_start_date IS NOT NULL",
            name="ck_schedule_drafts_adaptive_editable_start",
        ),
        CheckConstraint(
            "(draft_state = 'PENDING' AND decided_at IS NULL AND decided_by_user_id IS NULL) "
            "OR (draft_state <> 'PENDING' AND decided_at IS NOT NULL)",
            name="ck_schedule_drafts_decision_consistency",
        ),
        CheckConstraint(
            "(draft_state = 'STALE' AND stale_reason IS NOT NULL) OR "
            "(draft_state <> 'STALE' AND stale_reason IS NULL)",
            name="ck_schedule_drafts_stale_reason",
        ),
        CheckConstraint(
            "(draft_state = 'INVALIDATED' AND invalidated_reason IS NOT NULL) OR "
            "(draft_state <> 'INVALIDATED' AND invalidated_reason IS NULL)",
            name="ck_schedule_drafts_invalidated_reason",
        ),
        Index(
            "uq_schedule_drafts_pending_year",
            "organization_id",
            "school_year_id",
            unique=True,
            postgresql_where=(draft_state == ScheduleDraftState.PENDING),
        ),
    )


class ScheduleDraftBlock(Base):
    """One concrete target block in a draft's complete editable-future state."""
    __tablename__ = "schedule_draft_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True
    )
    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("scheduler_school_year.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    draft_id: Mapped[int] = mapped_column(
        nullable=False, index=True
    )
    source_active_block_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "active_schedule_blocks.id",
            name="fk_schedule_draft_blocks_source_active",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        nullable=True,
    )
    stable_block_key: Mapped[str] = mapped_column(String(64), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey(FK_CLASS_ID), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey(FK_SUBJECT_ID), nullable=False)
    teacher_id: Mapped[int] = mapped_column(ForeignKey(FK_TEACHER_ID), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=False)
    room_type_id: Mapped[Optional[RoomType]] = mapped_column(SAEnum(RoomType), nullable=True)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    timeslot_id: Mapped[int] = mapped_column(ForeignKey(FK_TIMESLOT_ID), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    module_sequence_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_recovery_block: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recovery_source_occurrence_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("lesson_occurrence.id", ondelete="RESTRICT"), nullable=True
    )
    recovery_source_occurrence_revision: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    change_type: Mapped[ScheduleDraftBlockChangeType] = mapped_column(
        SAEnum(ScheduleDraftBlockChangeType), nullable=False
    )
    reason_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_id", "organization_id", "school_year_id"],
            [
                "schedule_drafts.id",
                "schedule_drafts.organization_id",
                "schedule_drafts.school_year_id",
            ],
            name="fk_schedule_draft_blocks_draft_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "draft_id", "stable_block_key", name="uq_schedule_draft_blocks_stable_key"
        ),
        UniqueConstraint(
            "id", "organization_id", "school_year_id",
            name="uq_schedule_draft_blocks_id_scope",
        ),
        UniqueConstraint(
            "draft_id", "class_id", "date", "timeslot_id",
            name="uq_schedule_draft_blocks_class_slot",
        ),
        UniqueConstraint(
            "draft_id", "teacher_id", "date", "timeslot_id",
            name="uq_schedule_draft_blocks_teacher_slot",
        ),
        UniqueConstraint(
            "draft_id", "room_id", "date", "timeslot_id",
            name="uq_schedule_draft_blocks_room_slot",
        ),
        CheckConstraint(
            "duration_minutes > 0", name="ck_schedule_draft_blocks_duration_positive"
        ),
        CheckConstraint(
            "module_sequence_index IS NULL OR module_sequence_index >= 0",
            name="ck_schedule_draft_blocks_module_sequence_nonnegative",
        ),
        CheckConstraint(
            "(is_recovery_block AND recovery_source_occurrence_id IS NOT NULL AND "
            "recovery_source_occurrence_revision IS NOT NULL) OR "
            "(NOT is_recovery_block AND recovery_source_occurrence_id IS NULL AND "
            "recovery_source_occurrence_revision IS NULL)",
            name="ck_schedule_draft_blocks_recovery_source",
        ),
        CheckConstraint(
            "recovery_source_occurrence_revision IS NULL "
            "OR recovery_source_occurrence_revision > 0",
            name="ck_schedule_draft_blocks_recovery_revision_positive",
        ),
        CheckConstraint(
            "(change_type = 'ADDED' AND source_active_block_id IS NULL) OR "
            "(change_type <> 'ADDED' AND source_active_block_id IS NOT NULL)",
            name="ck_schedule_draft_blocks_change_source",
        ),
        CheckConstraint(
            "length(trim(stable_block_key)) > 0",
            name="ck_schedule_draft_blocks_stable_key_nonempty",
        ),
    )


class ScheduleDiffEntry(Base):
    """Optional immutable explanation of one before/after draft difference."""
    __tablename__ = "schedule_diff_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True
    )
    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("scheduler_school_year.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    generation_job_id: Mapped[int] = mapped_column(nullable=False)
    draft_id: Mapped[int] = mapped_column(nullable=False, index=True)
    class_id: Mapped[int] = mapped_column(ForeignKey(FK_CLASS_ID), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey(FK_SUBJECT_ID), nullable=False)
    teacher_id: Mapped[int] = mapped_column(ForeignKey(FK_TEACHER_ID), nullable=False)
    before_active_block_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "active_schedule_blocks.id",
            name="fk_schedule_diff_entries_before_active",
            ondelete=ON_DELETE_SET_NULL,
            use_alter=True,
        ),
        nullable=True,
    )
    after_draft_block_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("schedule_draft_blocks.id", ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    before_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    before_timeslot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(FK_TIMESLOT_ID, ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    before_room_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("room.id", ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    after_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    after_timeslot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(FK_TIMESLOT_ID, ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    after_room_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("room.id", ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    before_snapshot_json: Mapped[Optional[dict]] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    after_snapshot_json: Mapped[Optional[dict]] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    change_type: Mapped[ScheduleDiffChangeType] = mapped_column(
        SAEnum(ScheduleDiffChangeType), nullable=False
    )
    impact_scope: Mapped[ScheduleDiffScope] = mapped_column(
        SAEnum(ScheduleDiffScope), nullable=False, default=ScheduleDiffScope.AFFECTED
    )
    reason_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reason_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recovery_link_impact_json: Mapped[Optional[dict]] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_id", "generation_job_id", "organization_id", "school_year_id"],
            [
                "schedule_drafts.id",
                "schedule_drafts.generation_job_id",
                "schedule_drafts.organization_id",
                "schedule_drafts.school_year_id",
            ],
            name="fk_schedule_diff_entries_draft_job_scope",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(change_type = 'ADDED' AND before_snapshot_json IS NULL "
            "AND after_snapshot_json IS NOT NULL) OR "
            "(change_type = 'REMOVED' AND before_snapshot_json IS NOT NULL "
            "AND after_snapshot_json IS NULL) OR "
            "(change_type NOT IN ('ADDED', 'REMOVED') "
            "AND before_snapshot_json IS NOT NULL AND after_snapshot_json IS NOT NULL)",
            name="ck_schedule_diff_entries_sides",
        ),
    )


class ActiveScheduleBlock(Base):
    """Versioned published schedule block created from an approved draft target."""
    __tablename__ = "active_schedule_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True
    )
    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("scheduler_school_year.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schedule_version_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    stable_block_key: Mapped[str] = mapped_column(String(64), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey(FK_CLASS_ID), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey(FK_SUBJECT_ID), nullable=False)
    teacher_id: Mapped[int] = mapped_column(ForeignKey(FK_TEACHER_ID), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    timeslot_id: Mapped[int] = mapped_column(ForeignKey(FK_TIMESLOT_ID), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    source_draft_block_id: Mapped[int] = mapped_column(nullable=False)
    is_recovery_block: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[ActiveScheduleBlockStatus] = mapped_column(
        SAEnum(ActiveScheduleBlockStatus),
        nullable=False,
        default=ActiveScheduleBlockStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["source_draft_block_id", "organization_id", "school_year_id"],
            [
                "schedule_draft_blocks.id",
                "schedule_draft_blocks.organization_id",
                "schedule_draft_blocks.school_year_id",
            ],
            name="fk_active_schedule_blocks_draft_block_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "id", "organization_id", "school_year_id",
            name="uq_active_schedule_blocks_id_scope",
        ),
        UniqueConstraint(
            "id", "organization_id",
            name="uq_active_schedule_blocks_id_org",
        ),
        UniqueConstraint(
            "source_draft_block_id",
            name="uq_active_schedule_blocks_source_draft_block",
        ),
        UniqueConstraint(
            "organization_id", "school_year_id", "schedule_version_id", "stable_block_key",
            name="uq_active_schedule_blocks_version_stable_key",
        ),
        CheckConstraint(
            "duration_minutes > 0", name="ck_active_schedule_blocks_duration_positive"
        ),
        CheckConstraint(
            "length(trim(stable_block_key)) > 0",
            name="ck_active_schedule_blocks_stable_key_nonempty",
        ),
        Index(
            "uq_active_schedule_blocks_class_slot",
            "organization_id", "school_year_id", "class_id", "date", "timeslot_id",
            unique=True,
            postgresql_where=(status == ActiveScheduleBlockStatus.ACTIVE),
        ),
        Index(
            "uq_active_schedule_blocks_teacher_slot",
            "organization_id", "school_year_id", "teacher_id", "date", "timeslot_id",
            unique=True,
            postgresql_where=(status == ActiveScheduleBlockStatus.ACTIVE),
        ),
        Index(
            "uq_active_schedule_blocks_room_slot",
            "organization_id", "school_year_id", "room_id", "date", "timeslot_id",
            unique=True,
            postgresql_where=(status == ActiveScheduleBlockStatus.ACTIVE),
        ),
    )


class PlannedRecoveryLink(Base):
    """Idempotent accounting link from debt evidence to planned and delivered recovery."""
    __tablename__ = "planned_recovery_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True
    )
    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("scheduler_school_year.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    debt_occurrence_id: Mapped[int] = mapped_column(nullable=False)
    debt_occurrence_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_active_block_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    planned_draft_block_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    planned_recovery_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    delivered_recovery_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered_lesson_log_id: Mapped[Optional[int]] = mapped_column(
        nullable=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    class_id: Mapped[int] = mapped_column(ForeignKey(FK_CLASS_ID), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey(FK_SUBJECT_ID), nullable=False)
    teacher_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(FK_TEACHER_ID, ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    status: Mapped[PlannedRecoveryLinkStatus] = mapped_column(
        SAEnum(PlannedRecoveryLinkStatus),
        nullable=False,
        default=PlannedRecoveryLinkStatus.PLANNED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["debt_occurrence_id", "organization_id", "debt_occurrence_revision"],
            [
                "lesson_occurrence.id",
                "lesson_occurrence.organization_id",
                "lesson_occurrence.revision",
            ],
            name="fk_planned_recovery_links_debt_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["planned_active_block_id", "organization_id", "school_year_id"],
            [
                "active_schedule_blocks.id",
                "active_schedule_blocks.organization_id",
                "active_schedule_blocks.school_year_id",
            ],
            name="fk_planned_recovery_links_active_block_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["planned_draft_block_id", "organization_id", "school_year_id"],
            [
                "schedule_draft_blocks.id",
                "schedule_draft_blocks.organization_id",
                "schedule_draft_blocks.school_year_id",
            ],
            name="fk_planned_recovery_links_draft_block_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["delivered_lesson_log_id", "organization_id", "planned_active_block_id"],
            [
                "lesson_log.id",
                "lesson_log.organization_id",
                "lesson_log.active_schedule_block_id",
            ],
            name="fk_planned_recovery_links_delivery_evidence",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "planned_active_block_id", name="uq_planned_recovery_links_active_block"
        ),
        UniqueConstraint(
            "planned_draft_block_id", name="uq_planned_recovery_links_draft_block"
        ),
        UniqueConstraint(
            "delivered_lesson_log_id", name="uq_planned_recovery_links_delivery_log"
        ),
        CheckConstraint(
            "planned_recovery_minutes > 0",
            name="ck_planned_recovery_links_planned_minutes_positive",
        ),
        CheckConstraint(
            "delivered_recovery_minutes >= 0 AND "
            "delivered_recovery_minutes <= planned_recovery_minutes",
            name="ck_planned_recovery_links_delivered_minutes_range",
        ),
        CheckConstraint(
            "planned_active_block_id IS NOT NULL OR planned_draft_block_id IS NOT NULL",
            name="ck_planned_recovery_links_has_target",
        ),
        CheckConstraint(
            "(status = 'DELIVERED' AND planned_active_block_id IS NOT NULL "
            "AND delivered_recovery_minutes > 0 "
            "AND delivered_lesson_log_id IS NOT NULL AND delivered_at IS NOT NULL) OR "
            "(status <> 'DELIVERED' AND delivered_recovery_minutes = 0 "
            "AND delivered_lesson_log_id IS NULL AND delivered_at IS NULL)",
            name="ck_planned_recovery_links_delivery_evidence",
        ),
        CheckConstraint(
            "debt_occurrence_revision > 0",
            name="ck_planned_recovery_links_debt_revision_positive",
        ),
    )


class SchedulerStateVersionEvent(Base):
    """Append-only audit event explaining a scheduler state version decision."""
    __tablename__ = "scheduler_state_version_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(nullable=False, index=True)
    school_year_id: Mapped[int] = mapped_column(nullable=False, index=True)
    version_before: Mapped[int] = mapped_column(Integer, nullable=False)
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    operation: Mapped[SchedulerStateChangeOperation] = mapped_column(
        SAEnum(SchedulerStateChangeOperation), nullable=False
    )
    change_scope: Mapped[SchedulerStateChangeScope] = mapped_column(
        SAEnum(SchedulerStateChangeScope), nullable=False
    )
    changed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    before_metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after_metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "school_year_id"],
            [
                "scheduler_school_year_state.organization_id",
                "scheduler_school_year_state.school_year_id",
            ],
            name="fk_scheduler_state_version_events_state_scope",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "version_before >= 0 AND version_after >= 0",
            name="ck_scheduler_state_version_events_versions_nonnegative",
        ),
        CheckConstraint(
            "(change_scope = 'FUTURE_IMPACTING' AND version_after = version_before + 1) OR "
            "(change_scope <> 'FUTURE_IMPACTING' AND version_after = version_before)",
            name="ck_scheduler_state_version_events_increment",
        ),
        CheckConstraint(
            "length(trim(entity_type)) > 0",
            name="ck_scheduler_state_version_events_entity_type_nonempty",
        ),
        Index(
            "uq_scheduler_state_version_events_increment",
            "organization_id", "school_year_id", "version_after",
            unique=True,
            postgresql_where=(
                change_scope == SchedulerStateChangeScope.FUTURE_IMPACTING
            ),
        ),
    )

class OrganizationGridSettings(Base):
    """Configurações da grelha horária da organização."""
    __tablename__ = "organization_grid_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), unique=True, index=True)
    lunch_window_start: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    lunch_window_end: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    lunch_min_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="grid_settings")

    def __repr__(self) -> str:
        return f"<OrganizationGridSettings(organization_id={self.organization_id})>"


class SchoolCalendarEvent(Base):
    """Pausas letivas e feriados (hard constraint para o solver).
    source=AUTO: importado via package holidays Python.
    source=MANUAL: adicionado pelo diretor.
    """
    __tablename__ = "school_calendar_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    start_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    end_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    event_type: Mapped[CalendarEventType] = mapped_column(SAEnum(CalendarEventType), nullable=False)
    source: Mapped[CalendarEventSource] = mapped_column(
        SAEnum(CalendarEventSource), nullable=False, default=CalendarEventSource.manual
    )

    organization: Mapped["Organization"] = relationship(back_populates="calendar_events")

    def __repr__(self) -> str:
        return f"<SchoolCalendarEvent(id={self.id}, name='{self.name}', date='{self.start_date}')>"


# -- SUBSTITUIÇÕES --
class Substitution(Base):
    __tablename__ = "substitutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id"), nullable=False)
    timeslot_id: Mapped[int] = mapped_column(ForeignKey(FK_TIMESLOT_ID), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    original_teacher_id: Mapped[int] = mapped_column(ForeignKey(FK_TEACHER_ID), nullable=False)
    substitute_teacher_id: Mapped[int] = mapped_column(ForeignKey(FK_TEACHER_ID), nullable=False)
    substitute_subject_id: Mapped[Optional[int]] = mapped_column(ForeignKey(FK_SUBJECT_ID), nullable=True)

    status: Mapped[SubstitutionStatus] = mapped_column(
        SAEnum(SubstitutionStatus), default=SubstitutionStatus.PENDING, nullable=False
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    organization: Mapped["Organization"] = relationship()
    lesson: Mapped["Lesson"] = relationship()
    timeslot: Mapped["Timeslot"] = relationship()
    original_teacher: Mapped["Teacher"] = relationship(foreign_keys=[original_teacher_id])
    substitute_teacher: Mapped["Teacher"] = relationship(foreign_keys=[substitute_teacher_id])
    substitute_subject: Mapped[Optional["Subject"]] = relationship(foreign_keys=[substitute_subject_id])


# --- OCORRÊNCIAS DE AULAS (Sprint 2) ---

class LessonOccurrence(Base):
    """Registo imutável do que aconteceu numa data específica.
    NEVER delete — é histórico permanente (D24).
    schedule_output_id usa ON DELETE SET NULL para preservar o registo
    mesmo que o horário seja regenerado.
    """
    __tablename__ = "lesson_occurrence"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), index=True)

    # Liga ao slot planeado (pode ficar NULL se o horário for removido)
    schedule_output_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("schedule_output.id", ondelete=ON_DELETE_SET_NULL),
        nullable=True,
        index=True,
    )
    active_schedule_block_id: Mapped[Optional[int]] = mapped_column(
        nullable=True,
        index=True,
    )

    # Data em que deveria ter ocorrido
    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)

    # Contexto imutável de turma/disciplina (preservado mesmo se schedule_output for NULL)
    class_id: Mapped[Optional[int]] = mapped_column(ForeignKey(FK_CLASS_ID, ondelete=ON_DELETE_SET_NULL), nullable=True)
    subject_id: Mapped[Optional[int]] = mapped_column(ForeignKey(FK_SUBJECT_ID, ondelete=ON_DELETE_SET_NULL), nullable=True)

    # Decisao final. NULL significa ocorrencia aberta/pendente.
    status: Mapped[Optional[LessonOccurrenceStatus]] = mapped_column(
        SAEnum(LessonOccurrenceStatus), nullable=True
    )

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    creation_source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)

    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    revoked_reason: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)

    planned_timeslot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(FK_TIMESLOT_ID, ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    planned_room_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("room.id", ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    planned_generation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Horas planeadas do bloco (preservadas mesmo se o slot for removido)
    planned_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Substituição (preenchido quando status=SUBSTITUTED)
    substitute_teacher_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(FK_TEACHER_ID, ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    substitute_subject_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(FK_SUBJECT_ID, ondelete=ON_DELETE_SET_NULL), nullable=True
    )

    # Docente previsto e docente que efetivamente executou
    planned_teacher_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(FK_TEACHER_ID, ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    executed_teacher_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(FK_TEACHER_ID, ondelete=ON_DELETE_SET_NULL), nullable=True
    )

    # Módulo planeado e módulo efetivamente executado
    planned_module_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("module.id", ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    executed_module_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("module.id", ondelete=ON_DELETE_SET_NULL), nullable=True
    )

    # Horas efetivamente dadas na execução (0.0 quando GAP)
    hours_given: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Quem decidiu e quando decidiu o estado final
    decided_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Auditoria
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=True,
    )

    # Relacionamentos
    organization: Mapped["Organization"] = relationship()
    schedule_output: Mapped[Optional["ScheduleOutput"]] = relationship()
    active_schedule_block: Mapped[Optional["ActiveScheduleBlock"]] = relationship(
        viewonly=True
    )
    class_: Mapped[Optional["Class"]] = relationship(foreign_keys=[class_id])
    subject: Mapped[Optional["Subject"]] = relationship(foreign_keys=[subject_id])
    substitute_teacher: Mapped[Optional["Teacher"]] = relationship(
        foreign_keys=[substitute_teacher_id]
    )
    substitute_subject: Mapped[Optional["Subject"]] = relationship(
        foreign_keys=[substitute_subject_id]
    )
    planned_teacher: Mapped[Optional["Teacher"]] = relationship(
        foreign_keys=[planned_teacher_id]
    )
    executed_teacher: Mapped[Optional["Teacher"]] = relationship(
        foreign_keys=[executed_teacher_id]
    )
    planned_module: Mapped[Optional["Module"]] = relationship(
        foreign_keys=[planned_module_id]
    )
    executed_module: Mapped[Optional["Module"]] = relationship(
        foreign_keys=[executed_module_id]
    )
    decided_by_user: Mapped[Optional["User"]] = relationship(
        foreign_keys=[decided_by_user_id]
    )
    created_by_user: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by_user_id]
    )
    revoked_by_user: Mapped[Optional["User"]] = relationship(
        foreign_keys=[revoked_by_user_id]
    )
    planned_timeslot: Mapped[Optional["Timeslot"]] = relationship(
        foreign_keys=[planned_timeslot_id]
    )
    planned_room: Mapped[Optional["Room"]] = relationship(
        foreign_keys=[planned_room_id]
    )

    # Uma ocorrência por slot planeado (evita duplicados do cron)
    __table_args__ = (
        UniqueConstraint(
            "id", "organization_id", "revision",
            name="uq_lesson_occurrence_id_org_revision",
        ),
        UniqueConstraint(
            "organization_id", "schedule_output_id", "date", "revision",
            name="uq_lesson_occurrence_output_date_revision",
        ),
        UniqueConstraint(
            "organization_id", "active_schedule_block_id", "date", "revision",
            name="uq_lesson_occurrence_active_block_date_revision",
        ),
        ForeignKeyConstraint(
            ["active_schedule_block_id", "organization_id"],
            ["active_schedule_blocks.id", "active_schedule_blocks.organization_id"],
            name="fk_lesson_occurrence_active_block_scope",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index("ix_lesson_occurrence_org_active_date", "organization_id", "is_active", "date"),
    )

    def __repr__(self) -> str:
        return f"<LessonOccurrence(id={self.id}, date='{self.date}', status='{self.status}')>"


class OccurrenceOperationalEvent(Base):
    """Evento operacional de ocorrências para observabilidade interna (pilot baseline)."""
    __tablename__ = "occurrence_operational_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), index=True)

    occurrence_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("lesson_occurrence.id", ondelete=ON_DELETE_SET_NULL),
        nullable=True,
        index=True,
    )
    schedule_output_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("schedule_output.id", ondelete=ON_DELETE_SET_NULL),
        nullable=True,
        index=True,
    )
    actor_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL),
        nullable=True,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    result: Mapped[str] = mapped_column(String(50), nullable=False)
    decision_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=True,
        index=True,
    )

    organization: Mapped["Organization"] = relationship()
    occurrence: Mapped[Optional["LessonOccurrence"]] = relationship()
    schedule_output: Mapped[Optional["ScheduleOutput"]] = relationship()
    actor_user: Mapped[Optional["User"]] = relationship()

    __table_args__ = (
        Index("ix_occ_event_org_created", "organization_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<OccurrenceOperationalEvent(id={self.id}, organization_id={self.organization_id}, "
            f"event_type='{self.event_type}', result='{self.result}')>"
        )


class OperationalScheduleBlock(Base):
    """Bloco operacional derivado de uma ocorrencia, separado do horario curricular."""
    __tablename__ = "operational_schedule_block"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True)
    source_occurrence_id: Mapped[int] = mapped_column(ForeignKey("lesson_occurrence.id", ondelete="CASCADE"), nullable=False, index=True)
    source_occurrence_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    planned_schedule_output_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(FK_SCHEDULE_OUTPUT_ID, ondelete=ON_DELETE_SET_NULL),
        nullable=True,
        index=True,
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    timeslot_id: Mapped[int] = mapped_column(ForeignKey(FK_TIMESLOT_ID), nullable=False, index=True)
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("room.id", ondelete=ON_DELETE_SET_NULL), nullable=True)
    class_id: Mapped[int] = mapped_column(ForeignKey(FK_CLASS_ID), nullable=False, index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey(FK_TEACHER_ID), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey(FK_SUBJECT_ID), nullable=False, index=True)
    module_id: Mapped[Optional[int]] = mapped_column(ForeignKey("module.id", ondelete=ON_DELETE_SET_NULL), nullable=True)
    status: Mapped[OperationalBlockStatus] = mapped_column(
        SAEnum(OperationalBlockStatus), nullable=False, default=OperationalBlockStatus.ACTIVE
    )
    execution_status: Mapped[OperationalBlockExecutionStatus] = mapped_column(
        SAEnum(OperationalBlockExecutionStatus), nullable=False, default=OperationalBlockExecutionStatus.PENDING_LOG
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship()
    source_occurrence: Mapped["LessonOccurrence"] = relationship()
    planned_schedule_output: Mapped[Optional["ScheduleOutput"]] = relationship()
    timeslot: Mapped["Timeslot"] = relationship()
    room: Mapped[Optional["Room"]] = relationship()
    class_: Mapped["Class"] = relationship()
    teacher: Mapped["Teacher"] = relationship()
    subject: Mapped["Subject"] = relationship()
    module: Mapped[Optional["Module"]] = relationship()
    created_by_user: Mapped[Optional["User"]] = relationship()

    __table_args__ = (
        Index("ix_operational_block_org_teacher_date_slot", "organization_id", "teacher_id", "date", "timeslot_id"),
        Index("ix_operational_block_org_class_date", "organization_id", "class_id", "date"),
    )


class TeacherEndpointOperationalEvent(Base):
    """Evento operacional por endpoint crítico de professor (Passo 9)."""

    __tablename__ = "teacher_endpoint_operational_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL),
        nullable=True,
        index=True,
    )
    actor_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    endpoint_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    active_generation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    organization: Mapped["Organization"] = relationship()
    actor_user: Mapped[Optional["User"]] = relationship()

    __table_args__ = (
        Index("ix_teacher_endpoint_event_org_created", "organization_id", "created_at"),
        Index(
            "ix_teacher_endpoint_event_org_endpoint_created",
            "organization_id",
            "endpoint_key",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TeacherEndpointOperationalEvent(id={self.id}, organization_id={self.organization_id}, "
            f"endpoint_key='{self.endpoint_key}', http_status={self.http_status})>"
        )


@event.listens_for(LessonOccurrence, "before_delete")
def _prevent_lesson_occurrence_delete(mapper, connection, target) -> None:  # noqa: ARG001
    raise ValueError("LessonOccurrence é histórico imutável e não pode ser removida")


@event.listens_for(Session, "before_flush")
def _populate_direct_tenant_ownership(session, flush_context, instances) -> None:  # noqa: ARG001
    """Populate direct tenant ownership from already tenant-owned parents."""
    parent_rules = (
        (Availability, "teacher_id", Teacher),
        (ClassSubjectLink, "class_id", Class),
        (Module, "subject_id", Subject),
        (ClassProgress, "class_id", Class),
    )
    for obj in session.new:
        if getattr(obj, "organization_id", None) is not None:
            continue
        for model, parent_attr, parent_model in parent_rules:
            if not isinstance(obj, model):
                continue
            parent_id = getattr(obj, parent_attr, None)
            if parent_id is None:
                break
            parent = session.get(parent_model, parent_id)
            if parent is not None:
                obj.organization_id = parent.organization_id
            break


# --- REGISTO DE EXECUÇÃO DE AULAS (WBS Fase 1) ---

class LessonLog(Base):
    """Registo de execução de um bloco de aula gerado pelo Solver.

    Relação 1-para-1 com ScheduleOutput. Criado automaticamente quando
    o professor ou admin interage com um bloco pela primeira vez.
    É a nova fonte de verdade para o progresso da disciplina
    (substituindo o acoplamento a LessonOccurrence para aulas normais).
    """
    __tablename__ = "lesson_log"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Tenant isolation — obrigatório em todas as tabelas
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True
    )

    # Ligação 1-para-1 ao bloco gerado pelo Solver
    schedule_output_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(FK_SCHEDULE_OUTPUT_ID, ondelete="CASCADE"),
        nullable=True,
        unique=True,  # Garante relação 1-para-1
        index=True,
    )

    # Estado de execução da aula
    operational_block_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("operational_schedule_block.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
        index=True,
    )
    active_schedule_block_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("active_schedule_blocks.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    status: Mapped[LessonLogStatus] = mapped_column(
        SAEnum(LessonLogStatus), nullable=False, default=LessonLogStatus.PENDING
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Conteúdo pedagógico (ambos opcionais)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # Sumário da aula
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # Notas livres

    # Auditoria — quem registou e quando
    logged_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True
    )
    logged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relacionamentos
    organization: Mapped["Organization"] = relationship()
    schedule_output: Mapped[Optional["ScheduleOutput"]] = relationship()
    operational_block: Mapped[Optional["OperationalScheduleBlock"]] = relationship()
    active_schedule_block: Mapped[Optional["ActiveScheduleBlock"]] = relationship()
    logged_by_user: Mapped[Optional["User"]] = relationship(foreign_keys=[logged_by_user_id])

    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN schedule_output_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN operational_block_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN active_schedule_block_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_lesson_log_exactly_one_target",
        ),
        UniqueConstraint(
            "id", "organization_id", "active_schedule_block_id",
            name="uq_lesson_log_id_org_active_block",
        ),
        UniqueConstraint(
            "active_schedule_block_id",
            name="uq_lesson_log_active_schedule_block",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<LessonLog(id={self.id}, schedule_output_id={self.schedule_output_id}, "
            f"operational_block_id={self.operational_block_id}, status='{self.status}')>"
        )


class TeacherWeeklyTimesheet(Base):
    """Fecho semanal de um professor (workflow tipo Atlassian Tempo).

    Ciclo de vida:
      OPEN → (professor preenche todos os blocos) → SUBMITTED
      SUBMITTED → (admin aprova) → APPROVED
      APPROVED → (admin reabre) → OPEN

    Regra: só pode ser submetida quando todos os LessonLog da semana
    tiverem status != PENDING E nenhum bloco da semana for futuro.
    """
    __tablename__ = "teacher_weekly_timesheet"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Tenant isolation
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True
    )

    teacher_id: Mapped[int] = mapped_column(
        ForeignKey(FK_TEACHER_ID, ondelete="CASCADE"), nullable=False, index=True
    )

    # Identificação da semana (segunda-feira a domingo)
    week_start_date: Mapped[date_type] = mapped_column(Date, nullable=False)

    status: Mapped[TimesheetStatus] = mapped_column(
        SAEnum(TimesheetStatus), nullable=False, default=TimesheetStatus.OPEN
    )

    # Datas de transição de estado (auditoria)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relacionamentos
    organization: Mapped["Organization"] = relationship()
    teacher: Mapped["Teacher"] = relationship(back_populates="timesheets")
    approved_by_user: Mapped[Optional["User"]] = relationship(foreign_keys=[approved_by_user_id])

    # Uma única timesheet por professor por semana
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "teacher_id", "week_start_date",
            name="uq_teacher_weekly_timesheet",
        ),
        Index("ix_timesheet_org_week", "organization_id", "week_start_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<TeacherWeeklyTimesheet(id={self.id}, teacher_id={self.teacher_id}, "
            f"week='{self.week_start_date}', status='{self.status}')>"
        )


# --- ENSINO PROFISSIONAL / MODULAR ---

class Course(Base):
    """Ex: Técnico de Gestão e Programação de Sistemas Informáticos"""
    __tablename__ = "course"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    abbreviation: Mapped[str] = mapped_column(String(10), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID))
    
    organization: Mapped["Organization"] = relationship(back_populates="courses")
    classes: Mapped[List["Class"]] = relationship(back_populates="course")
    
    subjects: Mapped[List["Subject"]] = relationship(
        secondary=course_subject_link,
        back_populates="courses"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "abbreviation", name="uq_course_org_abbreviation"),
    )

    @property
    def subject_ids(self) -> List[int]:
        """
        Propriedade virtual que o Pydantic lê automaticamente
        devido ao 'from_attributes=True' no schema.
        """
        return [s.id for s in self.subjects]

    def __repr__(self) -> str:
        return f"<Course(id={self.id}, name='{self.name}')>"

class Module(Base):
    """Ex: UFCD 0789 - Fundamentos de Programação (50h)"""
    __tablename__ = "module"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # Ex: "0789"
    hours_total: Mapped[int] = mapped_column(Integer, nullable=False)  # Sem default - admin define
    order: Mapped[int] = mapped_column(Integer, nullable=False)  # Sequência no currículo (1, 2, 3...)
    
    # Um módulo pertence a uma disciplina macro (ex: pertence a "Programação")
    subject_id: Mapped[int] = mapped_column(ForeignKey(FK_SUBJECT_ID))
    subject: Mapped["Subject"] = relationship(back_populates="modules")

    # Garante ordem única por disciplina
    __table_args__ = (
        UniqueConstraint("organization_id", "subject_id", "order", name="uq_module_order_per_subject"),
    )

    def __repr__(self) -> str:
        return f"<Module(id={self.id}, code='{self.code}', hours={self.hours_total})>"

class ClassProgress(Base):
    """Rastreia quantas horas a turma já fez de um módulo"""
    __tablename__ = "class_progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True)
    
    class_id: Mapped[int] = mapped_column(ForeignKey(FK_CLASS_ID))
    module_id: Mapped[int] = mapped_column(ForeignKey("module.id"))
    
    hours_completed: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    hours_debt: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relacionamentos
    class_: Mapped["Class"] = relationship(back_populates="progress_records")
    module: Mapped["Module"] = relationship()
    
    # Garante uma entrada por turma/módulo
    __table_args__ = (
        UniqueConstraint("organization_id", "class_id", "module_id", name="uq_class_module"),
    )


class ProgressLedgerEntry(Base):
    """Ledger idempotente dos deltas aplicados a progresso/divida curricular."""
    __tablename__ = "progress_ledger_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_revision: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    class_id: Mapped[int] = mapped_column(ForeignKey(FK_CLASS_ID), nullable=False, index=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("module.id"), nullable=False, index=True)
    completed_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    debt_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id", ondelete=ON_DELETE_SET_NULL), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    reverses_ledger_entry_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("progress_ledger_entry.id", ondelete=ON_DELETE_SET_NULL),
        nullable=True,
    )

    organization: Mapped["Organization"] = relationship()
    class_: Mapped["Class"] = relationship()
    module: Mapped["Module"] = relationship()
    created_by_user: Mapped[Optional["User"]] = relationship()
    reverses_ledger_entry: Mapped[Optional["ProgressLedgerEntry"]] = relationship(remote_side=[id])

    __table_args__ = (
        Index("ix_progress_ledger_org_source", "organization_id", "source_type", "source_id"),
    )
