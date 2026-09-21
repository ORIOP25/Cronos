from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from .models import (
    CalendarEventSource,
    CalendarEventType,
    ConstraintType,
    LessonLogStatus,
    LessonOccurrenceStatus,
    OrganizationFoundationStatus,
    PreferenceLevel,
    RoomType,
    TimesheetStatus,
)


class OperationalOccurrenceState(StrEnum):
    OPEN_PENDING = "OPEN_PENDING"
    DECIDED_GIVEN = "DECIDED_GIVEN"
    DECIDED_GAP = "DECIDED_GAP"
    DECIDED_SUBSTITUTED = "DECIDED_SUBSTITUTED"
    REVOKED = "REVOKED"


# --- CONFIGURAÇÃO GLOBAL ---
# Esta é a "magia" que diz ao Pydantic para ler dados
# diretamente dos nossos modelos SQLAlchemy (ex: ler um objeto "Teacher" da BD
# e convertê-lo num schema "TeacherRead").
model_config = ConfigDict(from_attributes=True)


class ContactSubmission(BaseModel):
    """Validated public contact questionnaire payload."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    subject: str = Field(..., min_length=1, max_length=120)
    courses: str = Field(..., min_length=1, max_length=40)
    teachers: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    message: str | None = Field(default=None, max_length=3000)
    # Honeypot values must reach the application service so bots receive the
    # same successful response as legitimate visitors.
    website: str = Field(default="", max_length=200)
    turnstile_token: str = Field(min_length=1, max_length=2048)


class LegalAcceptanceCreate(BaseModel):
    """Organization legal acceptance command."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    acceptance_confirmed: Literal[True]
    terms_version: str = Field(min_length=1, max_length=40)
    dpa_version: str = Field(min_length=1, max_length=40)
    privacy_version: str = Field(min_length=1, max_length=40)


class LegalAcceptanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    organization_id: int
    accepted_by_membership_id_snapshot: int
    authority_confirmed: Literal[True]
    terms_version: str
    dpa_version: str
    privacy_version: str
    accepted_at: datetime


class LegalStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    requires_acceptance: bool
    terms_version: str
    dpa_version: str
    privacy_version: str
    accepted_at: datetime | None = None


# ==========================================
#  CONSTANTES DE DESCRIÇÃO (SonarQube: evitar duplicação de literals)
# ==========================================
DESC_SUBJECT_IDS = "IDs das disciplinas associadas"
DESC_CLASS_SIZE = "Número de alunos da turma"
DESC_GRADE_LEVEL = "Ano de escolaridade (10, 11, 12)"
DESC_START_YEAR = "Ano de início (ex: 2025)"
DESC_END_YEAR = "Ano de fim (ex: 2028)"
ERR_YEAR_RANGE = "Ano de fim deve ser maior que o ano de início"
DESC_HOURS_TOTAL = "Carga horária total do módulo"

# ==========================================
#  ESCOLA (Entidades Básicas)
# ==========================================


class OrganizationBase(BaseModel):
    name: str


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationRead(OrganizationBase):
    id: int
    plan_status: str
    model_config = model_config


# --- TEACHER ---
class TeacherBase(BaseModel):
    name: str
    email: EmailStr | None = None


class TeacherRead(TeacherBase):
    id: int
    organization_id: int
    user_id: int | None = None
    login_email: str | None = None
    # NOVO: Para o frontend saber se a conta está ativa ou inativa
    is_active: bool = False
    subject_ids: list[int] = Field(default_factory=list, description=DESC_SUBJECT_IDS)
    # Opcional: Incluir lista de disponibilidades quando pedes o professor
    # availabilities: List[AvailabilityRead] = []

    model_config = ConfigDict(from_attributes=True)


# --- EQuipa / Members ---

MemberCapabilityLiteral = Literal["teacher", "admin"]
TeacherAccessModeLiteral = Literal["platform", "scheduler_only"]
LifecycleStatusLiteral = Literal["active", "archived"]
AccessStatusLiteral = Literal[
    "none",
    "pending_invite",
    "invite_expired",
    "active",
    "blocked",
    "sync_error",
]


class MemberErrorEnvelope(BaseModel):
    code: str
    category: str | None = None
    message: str
    retryable: bool = False
    support_required: bool = False
    fields: dict[str, str] = Field(default_factory=dict)


class ClientErrorReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reference: str = Field(..., pattern=r"^[A-Z0-9]{12}$")
    category: Literal["render_error", "chunk_load_error"]
    revision: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")


class MemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_display_name: str = Field(..., min_length=1, max_length=150)
    email: EmailStr
    capabilities: list[MemberCapabilityLiteral] = Field(..., min_length=1)
    teacher_access_mode: TeacherAccessModeLiteral | None = None
    subject_ids: list[int] = Field(default_factory=list, description=DESC_SUBJECT_IDS)

    @model_validator(mode="after")
    def validate_member_shape(self):
        caps = set(self.capabilities)
        if not caps.issubset({"teacher", "admin"}):
            raise ValueError("Capacidade inválida")
        if "teacher" in caps and self.teacher_access_mode is None:
            raise ValueError("teacher_access_mode é obrigatório para professores")
        if "teacher" not in caps and self.teacher_access_mode is not None:
            raise ValueError("teacher_access_mode só pode ser usado para professores")
        if "admin" in caps and self.teacher_access_mode == "scheduler_only":
            raise ValueError("Administrador requer acesso à plataforma")
        return self


class MemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_display_name: str | None = Field(None, min_length=1, max_length=150)
    email: EmailStr | None = None
    capabilities: list[MemberCapabilityLiteral] | None = Field(None, min_length=1)
    teacher_access_mode: TeacherAccessModeLiteral | None = None
    subject_ids: list[int] | None = Field(None, description=DESC_SUBJECT_IDS)
    lock_version: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def validate_member_update_shape(self):
        if self.capabilities is not None:
            caps = set(self.capabilities)
            if not caps.issubset({"teacher", "admin"}):
                raise ValueError("Capacidade inválida")
            if "admin" in caps and self.teacher_access_mode == "scheduler_only":
                raise ValueError("Administrador requer acesso à plataforma")
        return self


class MemberRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    restore_access: bool = True
    capabilities: list[MemberCapabilityLiteral] | None = Field(None, min_length=1)
    teacher_access_mode: TeacherAccessModeLiteral | None = None
    subject_ids: list[int] | None = Field(None, description=DESC_SUBJECT_IDS)

    @model_validator(mode="after")
    def validate_member_restore_shape(self):
        if self.capabilities is not None:
            caps = set(self.capabilities)
            if not caps.issubset({"teacher", "admin"}):
                raise ValueError("Capacidade invalida")
            if "admin" in caps and self.teacher_access_mode == "scheduler_only":
                raise ValueError("Administrador requer acesso a plataforma")
        return self


class MemberActionFlags(BaseModel):
    can_edit: bool = True
    can_remove: bool = True
    remove_effect: Literal["hard_delete", "archive"] = "archive"
    can_restore: bool = False
    can_resend_invite: bool = False
    can_retry_sync: bool = False
    provider_state: Literal["confirmed", "unconfirmed", "not_required"] = "confirmed"


class MemberRead(BaseModel):
    id: int
    account_id: int
    organization_id: int
    organization_display_name: str
    email: EmailStr
    capabilities: list[MemberCapabilityLiteral]
    lifecycle_status: LifecycleStatusLiteral
    access_status: AccessStatusLiteral
    teacher_access_mode: TeacherAccessModeLiteral | None = None
    expected_clerk_role: Literal["org:member", "org:admin"] | None = None
    clerk_user_id: str | None = None
    clerk_membership_id: str | None = None
    clerk_invitation_id: str | None = None
    clerk_invitation_status: Literal["pending", "accepted", "revoked", "expired"] | None = None
    invitation_expires_at: datetime | None = None
    teacher_id: int | None = None
    subject_ids: list[int] = Field(default_factory=list)
    access_error_category: str | None = None
    access_error_safe_message: str | None = None
    support_reference: str | None = None
    provider_state: Literal["confirmed", "unconfirmed", "not_required"] = "confirmed"
    remove_effect: Literal["hard_delete", "archive"] = "archive"
    actions: MemberActionFlags = Field(default_factory=MemberActionFlags)
    lock_version: int


class MemberListRead(BaseModel):
    items: list[MemberRead]
    total: int
    limit: int
    offset: int


class CurrentMemberRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member_id: int
    account_id: int
    organization_id: int
    capabilities: list[MemberCapabilityLiteral]
    access_status: AccessStatusLiteral
    lifecycle_status: LifecycleStatusLiteral
    teacher_id: int | None = None
    default_mode: Literal["admin", "teacher"]
    available_modes: list[Literal["admin", "teacher"]]
    foundation_status: OrganizationFoundationStatus


class SessionBootstrapOrganization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    clerk_org_id: str
    name: str


class SessionBootstrapMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    access_status: Literal["active"]
    lifecycle_status: Literal["active"]
    capabilities: list[MemberCapabilityLiteral]
    default_mode: Literal["admin", "teacher"]
    teacher_id: int | None = None


class SessionBootstrapResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: SessionBootstrapOrganization
    member: SessionBootstrapMember
    foundation_status: OrganizationFoundationStatus


# --- Foundation & Readiness Schemas ---
class FoundationDraftData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    school_start_date: date | None = None
    school_hard_end_date: date | None = None
    repair_stability_window_days: int = Field(default=14, ge=0, le=60)
    days_of_week: list[int] | None = None
    opening_time: time | None = None
    closing_time: time | None = None
    slot_duration_minutes: int | None = Field(default=None, ge=15, le=120)
    break_duration_minutes: int | None = Field(default=None, ge=0, le=60)
    lunch_window_start: time | None = None
    lunch_window_end: time | None = None
    lunch_min_duration_minutes: int | None = Field(default=None, ge=1, le=180)
    automatic_holidays_enabled: bool = False

    @field_validator("repair_stability_window_days", mode="before")
    @classmethod
    def default_missing_repair_stability_window(cls, value: int | None) -> int:
        return 14 if value is None else value


class FoundationDraftWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(..., ge=0)
    current_step: int = Field(default=1, ge=1, le=9)
    data: FoundationDraftData


class FoundationDraftRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    current_step: int = Field(default=1, ge=1, le=9)
    data: FoundationDraftData
    updated_at: datetime | None = None


class FoundationCompleteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(..., ge=0)
    confirmed: Literal[True]


class FoundationStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    foundation_status: OrganizationFoundationStatus
    foundation_completed_at: datetime | None = None
    first_real_schedule_approved_at: datetime | None = None
    organization_name: str


class FoundationCompleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    foundation_status: OrganizationFoundationStatus
    foundation_completed_at: datetime
    generated_timeslot_count: int


class PreflightIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    severity: Literal["BLOCKER", "WARNING"]
    message: str
    route: str


class PreflightReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["BLOCKED", "READY_WITH_WARNINGS", "READY"]
    fingerprint: str | None = None
    issues: list[PreflightIssue] = Field(default_factory=list)


class ReadinessStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    status: Literal["COMPLETE", "PENDING"]
    route: str


class BasesReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    percentage: int
    depth: int
    complete: bool
    fingerprint: str | None = None
    issues: list[PreflightIssue] = Field(default_factory=list)
    steps: list[ReadinessStep] = Field(default_factory=list)


# --- Class (Turma) ---
class ClassBase(BaseModel):
    name: str
    size: int = Field(default=25, gt=0, description=DESC_CLASS_SIZE)


class ClassCreateInCourse(ClassBase):
    grade_level: int = Field(..., ge=10, le=12, description=DESC_GRADE_LEVEL)
    start_year: int = Field(..., description=DESC_START_YEAR)
    end_year: int = Field(..., description=DESC_END_YEAR)

    @model_validator(mode="after")
    def validate_year_window(self):
        if self.end_year <= self.start_year:
            raise ValueError(ERR_YEAR_RANGE)
        return self


class ClassUpdateInCourse(BaseModel):
    name: str | None = None
    size: int | None = Field(None, gt=0, description=DESC_CLASS_SIZE)
    grade_level: int | None = Field(None, ge=10, le=12, description=DESC_GRADE_LEVEL)
    start_year: int | None = Field(None, description=DESC_START_YEAR)
    end_year: int | None = Field(None, description=DESC_END_YEAR)

    @model_validator(mode="after")
    def validate_year_window_if_present(self):
        if (
            self.start_year is not None
            and self.end_year is not None
            and self.end_year <= self.start_year
        ):
            raise ValueError(ERR_YEAR_RANGE)
        return self


class ClassRead(ClassBase):
    id: int
    organization_id: int
    course_id: int | None = None
    grade_level: int
    start_year: int
    end_year: int
    model_config = model_config


# --- MÓDULOS ---
class ModuleBase(BaseModel):
    name: str
    code: str | None = None
    hours_total: int = Field(..., gt=0, description=DESC_HOURS_TOTAL)
    order: int = Field(..., ge=0, description="Ordem sequencial do módulo (0, 1, 2...)")


class ModuleCreate(ModuleBase):
    pass


class ModuleUpsert(BaseModel):
    """Módulo para upsert: se id presente = atualizar, se ausente = criar"""

    id: int | None = None
    name: str
    code: str | None = None
    hours_total: int = Field(..., gt=0, description=DESC_HOURS_TOTAL)
    order: int = Field(..., ge=0, description="Ordem sequencial do módulo")


class ModuleUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    hours_total: int | None = Field(None, gt=0, description=DESC_HOURS_TOTAL)
    subject_id: int | None = None


class ModuleRead(ModuleBase):
    id: int
    subject_id: int
    model_config = ConfigDict(from_attributes=True)


# --- SUBJECT ---
class SubjectBase(BaseModel):
    name: str
    required_room_type: RoomType = RoomType.normal


class SubjectCreate(SubjectBase):
    modules: list[ModuleCreate] = Field(
        default_factory=list, description="Lista de módulos iniciais"
    )

    @model_validator(mode="after")
    def validate_module_order(self):
        """
        Valida que os módulos têm ordem sequencial começando em 0: [0, 1, 2, ...]
        Garante integridade de dados - pré-requisitos funcionam corretamente.

        4º Pilar - Security: Evita injeção de dados inválidos via API
        """
        if not self.modules:
            # Permitir subject sem módulos (criar depois)
            return self

        # Extrai orders e ordena
        orders = sorted([m.order for m in self.modules])
        expected = list(range(0, len(self.modules)))

        # Valida sequência começando em 0
        if orders != expected:
            raise ValueError(
                f"Módulos devem ter ordem sequencial começando em 0 [0, 1, 2, ...]. "
                f"Recebido: {orders}, Esperado: {expected}"
            )
        return self


class SubjectUpdate(BaseModel):
    name: str | None = None
    required_room_type: RoomType | None = None
    modules: list[ModuleUpsert] | None = None

    @model_validator(mode="after")
    def validate_module_order(self):
        if self.modules is None:
            return self
        orders = sorted([m.order for m in self.modules])
        expected = list(range(0, len(self.modules)))
        if orders != expected:
            raise ValueError(
                f"Módulos devem ter ordem sequencial começando em 0 [0, 1, 2, ...]. "
                f"Recebido: {orders}, Esperado: {expected}"
            )
        return self


class SubjectRead(SubjectBase):
    id: int
    organization_id: int
    modules: list[ModuleRead] = []
    model_config = model_config


# --- ROOM (SALA) ---
class RoomBase(BaseModel):
    name: str
    type: RoomType
    capacity: int = Field(30, gt=0)


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: str | None = None
    type: RoomType | None = None
    capacity: int | None = Field(None, gt=0)


class RoomRead(RoomBase):
    id: int
    organization_id: int
    model_config = model_config


# ==========================================
#  HORÁRIOS (Complexo)
# ==========================================


# --- TIMESLOT (BLOCO DE TEMPO) ---
class TimeslotBase(BaseModel):
    # 0=Segunda, 6=Domingo.
    day_of_week: int = Field(..., ge=0, le=6, description="0=Segunda, 6=Domingo")
    start_time: time
    end_time: time

    # VALIDAÇÃO SÉNIOR: Garantir que o fim é depois do início
    @model_validator(mode="after")
    def check_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("A hora de fim deve ser posterior à hora de início")
        return self


class TimeslotCreate(TimeslotBase):
    pass


class TimeslotUpdate(BaseModel):
    day_of_week: int | None = Field(None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None

    @model_validator(mode="after")
    def check_times(self):
        if self.start_time is not None and self.end_time is not None:
            if self.end_time <= self.start_time:
                raise ValueError("A hora de fim deve ser posterior à hora de início")
        return self


class TimeslotRead(TimeslotBase):
    id: int
    organization_id: int

    model_config = ConfigDict(from_attributes=True)


# --- LESSON (ATRIBUIÇÃO DE PROFESSOR) ---
#
# Padrão (Service Distribution):
# Associação canónica entre turma, disciplina e professor.
# O Solver calcula dinamicamente quantas vezes por semana o professor dá aulas,
# baseado no currículo do curso, progresso modular e disponibilidade.
#
# - Turma: A que turma é? (ex: 10º TGEI)
# - Disciplina: Qual disciplina? (ex: Matemática)
# - Professor: Quem leciona? (ex: Prof. Silva) [VALIDADO: deve ter competência]


class LessonBase(BaseModel):
    class_id: int
    subject_id: int
    teacher_id: int


class LessonCreate(LessonBase):
    # NOVO: Permite criar uma atribuição sem especificar horas exatas.
    # O Solver dirá quantas horas por semana são necessárias.
    pass


class LessonRead(LessonBase):
    id: int
    organization_id: int
    model_config = model_config


# --- CONSTRAINT (REGRA) ---
class SupportedConstraintType(StrEnum):
    specific_room = "specific_room"
    lock_time = "lock_time"
    teacher_unavailable = "teacher_unavailable"
    teacher_preferred = "teacher_preferred"


StrictPositiveInt = Annotated[int, Field(strict=True, gt=0)]
ConstraintDate = date


class _ConstraintPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SpecificRoomPayload(_ConstraintPayload):
    class_id: StrictPositiveInt
    subject_id: StrictPositiveInt
    room_id: StrictPositiveInt


class LockTimePayload(_ConstraintPayload):
    class_id: StrictPositiveInt
    subject_id: StrictPositiveInt
    timeslot_id: StrictPositiveInt


class TeacherPreferredPayload(_ConstraintPayload):
    teacher_id: StrictPositiveInt
    timeslot_id: StrictPositiveInt


class TeacherUnavailablePayload(_ConstraintPayload):
    teacher_id: StrictPositiveInt
    timeslot_id: StrictPositiveInt | None = None
    day_of_week: Annotated[int, Field(strict=True, ge=0, le=6)] | None = None
    date: ConstraintDate | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_selector_shape(cls, value):
        if not isinstance(value, dict):
            return value
        selector_keys = set(value) - {"teacher_id"}
        if selector_keys not in (
            {"timeslot_id"},
            {"day_of_week"},
            {"date"},
            {"date", "timeslot_id"},
        ):
            raise ValueError("teacher_unavailable requires exactly one canonical selector form")
        date_value = value.get("date")
        if date_value is not None and (
            not isinstance(date_value, (str, date))
            or isinstance(date_value, datetime)
            or (isinstance(date_value, str) and "T" in date_value)
        ):
            raise ValueError("date must be an ISO date, not a datetime")
        return value


class _ConstraintWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SpecificRoomConstraintCreate(_ConstraintWrite):
    rule_type: Literal[SupportedConstraintType.specific_room]
    rule_payload: SpecificRoomPayload


class LockTimeConstraintCreate(_ConstraintWrite):
    rule_type: Literal[SupportedConstraintType.lock_time]
    rule_payload: LockTimePayload


class TeacherUnavailableConstraintCreate(_ConstraintWrite):
    rule_type: Literal[SupportedConstraintType.teacher_unavailable]
    rule_payload: TeacherUnavailablePayload


class TeacherPreferredConstraintCreate(_ConstraintWrite):
    rule_type: Literal[SupportedConstraintType.teacher_preferred]
    rule_payload: TeacherPreferredPayload


ConstraintCreate = Annotated[
    SpecificRoomConstraintCreate
    | LockTimeConstraintCreate
    | TeacherUnavailableConstraintCreate
    | TeacherPreferredConstraintCreate,
    Field(discriminator="rule_type"),
]


class ConstraintBase(BaseModel):
    rule_type: ConstraintType
    rule_payload: Any  # Flexível para aceitar JSON complexo


class ConstraintRead(ConstraintBase):
    id: int
    organization_id: int
    generation_compatible: bool = True
    validation_errors: list[str] = Field(default_factory=list)
    model_config = model_config

    @model_validator(mode="after")
    def derive_generation_compatibility(self):
        from app.scheduler.domain.constraints import SchedulerConstraintPolicy

        result = SchedulerConstraintPolicy.parse(
            [{"id": self.id, "rule_type": self.rule_type, "rule_payload": self.rule_payload}]
        )
        errors = [row.message for row in result.configuration_violations]
        self.generation_compatible = not errors
        self.validation_errors = errors
        return self


# --- Disponibilidade ---
MAX_WEEKLY_TIMETABLE_SLOTS = 7 * 24 * 60


class AvailabilityBase(BaseModel):
    teacher_id: int
    timeslot_id: int
    # O Pydantic valida se é um dos valores do Enum (-1, 0, 1, 2)
    score: PreferenceLevel = PreferenceLevel.NEUTRAL


class AvailabilityCreate(AvailabilityBase):
    pass


class AvailabilitySelfCreate(BaseModel):
    """Disponibilidade sem teacher_id (usa ID do path/autenticacao)."""

    timeslot_id: int
    score: PreferenceLevel = PreferenceLevel.NEUTRAL


TeacherAvailabilityPayload = Annotated[
    list[AvailabilitySelfCreate], Field(max_length=MAX_WEEKLY_TIMETABLE_SLOTS)
]


class AvailabilitySelfRead(BaseModel):
    """Leitura self-service de disponibilidade do professor autenticado."""

    timeslot_id: int
    score: PreferenceLevel = PreferenceLevel.NEUTRAL


class AvailabilityRead(AvailabilityBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# --- GERADOR DE HORÁRIOS (Sprint 1) ---
class ScheduleGenerateRequest(BaseModel):
    """Pedido publico de geração de horário.

    A estratégia é escolhida internamente pelo estado de publicação do ano letivo.
    """

    model_config = ConfigDict(extra="forbid")

    replace_pending_draft: bool = False
    idempotency_key: str | None = Field(None, min_length=1, max_length=100)


class SchedulerGenerateResponse(BaseModel):
    job_id: int
    strategy: Literal["COMPLETE_GENERATION", "ADAPTIVE_REPAIR"]
    trigger_type: Literal["FIRST_GENERATION", "EXPLICIT_DEBT", "SCHEDULER_CHANGE", "MIXED"]
    status: str


class SchedulerStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    school_year_id: int | None
    school_year_publication_state: Literal["UNPUBLISHED", "PUBLISHED"] | None
    pending_draft_id: int | None
    primary_action: Literal[
        "REVIEW_PENDING_DRAFT",
        "GENERATE_SCHEDULE",
        "GENERATION_UNAVAILABLE",
    ]
    can_generate_new_draft: bool
    can_regenerate_with_confirmation: bool
    blocked_reason: str | None
    trigger_type: (
        Literal[
            "FIRST_GENERATION",
            "EXPLICIT_DEBT",
            "SCHEDULER_CHANGE",
            "MIXED",
        ]
        | None
    )
    unresolved_debt_hours: float = Field(ge=0)
    scheduler_state_version: int | None = Field(default=None, ge=0)
    approved_scheduler_state_version: int | None = Field(default=None, ge=0)


class ScheduleGenerationJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy: Literal["COMPLETE_GENERATION", "ADAPTIVE_REPAIR"]
    trigger_type: Literal["FIRST_GENERATION", "EXPLICIT_DEBT", "SCHEDULER_CHANGE", "MIXED"] | None
    job_status: Literal[
        "QUEUED",
        "RUNNING",
        "CANCEL_REQUESTED",
        "CANCELED",
        "SUCCEEDED",
        "FAILED",
        "NO_VALID_OUTPUT",
    ]
    result_category: Literal["COMPLETE_SUCCESS", "PARTIAL_RECOVERY", "NO_VALID_OUTPUT"] | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    deadline_at: datetime | None
    duration_ms: int | None
    failure_code: str | None
    failure_message: str | None
    failure_reference: str | None


class ScheduleGenerationCancelResponse(BaseModel):
    job_id: int
    job_status: str


class ScheduleDraftSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    draft_id: int
    strategy: Literal["COMPLETE_GENERATION", "ADAPTIVE_REPAIR"]
    draft_state: Literal["PENDING", "APPROVED", "REJECTED", "REPLACED", "STALE", "INVALIDATED"]
    result_category: Literal["COMPLETE_SUCCESS", "PARTIAL_RECOVERY"]
    trigger_type: Literal["FIRST_GENERATION", "EXPLICIT_DEBT", "SCHEDULER_CHANGE", "MIXED"]
    recovery_escalation_level: str | None
    adaptation_level: str | None
    projected_completion_date: date
    hard_end_date: date
    debt_hours_before: float = Field(ge=0)
    debt_hours_recovered: float = Field(ge=0)
    debt_hours_remaining: float = Field(ge=0)
    partial_recovery_blocker_type: str | None
    main_blocker_message: str | None
    recommended_actions: list[str] | tuple[str, ...]
    changed_blocks: int = Field(ge=0)
    affected_classes: int = Field(ge=0)
    affected_teachers: int = Field(ge=0)
    affected_days: int = Field(ge=0)
    disruption_score: float = Field(ge=0)
    warnings: list[str] | tuple[str, ...]
    can_approve: bool
    quality_policy_version: str | None = None
    quality_optimization_complete: bool | None = None
    class_completion_spread_days: int = Field(default=0, ge=0)
    class_high_load_days: int = Field(default=0, ge=0)
    teacher_high_load_days: int = Field(default=0, ge=0)
    class_gap_minutes: int = Field(default=0, ge=0)
    teacher_gap_minutes: int = Field(default=0, ge=0)
    availability_disutility_minutes: int = Field(default=0, ge=0)
    consecutive_excess_minutes: int = Field(default=0, ge=0)
    recovery_stack_excess_minutes: int = Field(default=0, ge=0)
    workload_override_used: bool = False
    class_overload_count: int = Field(default=0, ge=0)
    class_overload_excess_minutes: int = Field(default=0, ge=0)
    teacher_overload_count: int = Field(default=0, ge=0)
    teacher_overload_excess_minutes: int = Field(default=0, ge=0)


class ScheduleDraftDiffEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    change_type: Literal["ADDED", "MOVED", "CHANGED", "REMOVED", "UNCHANGED_IMPACTED"]
    impact_scope: Literal["AFFECTED", "RELATED", "UNRELATED"]
    class_id: int
    subject_id: int
    teacher_id: int
    before_active_block_id: int | None
    after_draft_block_id: int | None
    before_snapshot: dict[str, Any] | None
    after_snapshot: dict[str, Any] | None
    reason_code: str | None
    reason_message: str | None
    recovery_link_impact: dict[str, Any] | None


class ScheduleDraftApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    draft_id: int
    draft_state: Literal["APPROVED"]
    school_year_publication_state: Literal["PUBLISHED"]
    active_schedule_version_id: str
    active_block_count: int = Field(ge=0)


class ScheduleDraftRejectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    draft_id: int
    draft_state: Literal["REJECTED"]


class SchedulerResetYearRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool


class SchedulerResetYearResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    school_year_id: int
    school_year_publication_state: Literal["UNPUBLISHED"]
    canceled_jobs: int = Field(ge=0)
    invalidated_drafts: int = Field(ge=0)
    canceled_active_blocks: int = Field(ge=0)
    canceled_recovery_links: int = Field(ge=0)


# --- CURSOS ---
# Classes Auxiliares
class ClassConfigCreate(BaseModel):
    """Define as regras para criar uma turma automática"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    grade_level: int = Field(..., ge=10, le=12, description=DESC_GRADE_LEVEL)
    size: int = Field(25, gt=0, description="Número de alunos")
    start_year: int = Field(..., description=DESC_START_YEAR)
    end_year: int = Field(..., description=DESC_END_YEAR)


class TeacherAssignmentCreate(BaseModel):
    """Define quem é o professor 'padrão' para uma disciplina neste curso"""

    subject_id: int
    teacher_id: int


class CourseBase(BaseModel):
    name: str
    abbreviation: str = Field(
        ..., min_length=2, max_length=10, description="Sigla do curso (ex: TGEI)"
    )


class CourseCreate(CourseBase):
    subject_ids: list[int] = Field(
        default_factory=list, description="IDs das disciplinas que compõem o curso"
    )
    teacher_assignments: list[TeacherAssignmentCreate] = Field(
        default_factory=list, description="Professores por disciplina"
    )
    classes_config: list[ClassConfigCreate] = Field(
        default_factory=list, description="Configuração das turmas a criar"
    )


class CourseUpdate(BaseModel):
    name: str | None = None
    abbreviation: str | None = Field(None, min_length=2, max_length=10)
    subject_ids: list[int] | None = None


class BulkImportFilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(..., min_length=1, max_length=255)
    content_base64: str = Field(..., min_length=1)


class BulkImportFiles(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rooms: BulkImportFilePayload | None = None
    subjects: BulkImportFilePayload | None = None
    courses: BulkImportFilePayload | None = None
    teachers: BulkImportFilePayload | None = None
    assignments: BulkImportFilePayload | None = None

    @model_validator(mode="after")
    def require_a_file(self):
        if not any(
            getattr(self, resource) is not None
            for resource in ("rooms", "subjects", "courses", "teachers", "assignments")
        ):
            raise ValueError("Selecione pelo menos um ficheiro de importação.")
        return self


class BulkImportFilesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: BulkImportFiles


class BulkImportIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Literal["error", "warning"]
    resource: str
    line: int | None = None
    field: str | None = None
    message: str


class BulkImportPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counts: dict[str, int] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)
    can_commit: bool


class BulkImportValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    can_commit: bool
    preview: BulkImportPreview
    issues: list[BulkImportIssue] = Field(default_factory=list)


class BulkImportCommitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[BulkImportIssue] = Field(default_factory=list)
    message: str = "Importação concluída."


class SubjectSimple(BaseModel):
    """Versão simplificada de Subject para não over-fetch"""

    id: int
    name: str
    required_room_type: RoomType
    model_config = ConfigDict(from_attributes=True)


class CourseRead(CourseBase):
    id: int
    organization_id: int
    model_config = ConfigDict(from_attributes=True)


# Este schema traz logo as turmas + disciplinas associadas para não termos de fazer múltiplos pedidos
class CourseDetailRead(CourseRead):
    subjects: list[SubjectSimple] = Field(
        default_factory=list, description="Disciplinas do curso (sem módulos)"
    )
    classes: list[ClassRead] = Field(default_factory=list, description="Turmas do curso")
    model_config = ConfigDict(from_attributes=True)


# --- COURSE BASIC (para relacionamentos) ---
class CourseBasic(CourseBase):
    """Versão simples de Course sem disciplinas/turmas (evita circular imports)"""

    id: int
    organization_id: int
    model_config = ConfigDict(from_attributes=True)


# --- CLASS DETAIL READ (Turma + Curso) ---
class ClassDetailRead(ClassRead):
    """
    Detalhes da turma incluindo o curso associado.
    Não inclui Lessons (horário) para manter payload leve - essas vêm de um endpoint separado.

    4º Pilar - Scalability: Endpoint é autossuficiente (tem course no browser navigation),
    sem sobrecarregar com centenas de lessons. O horário vem depois se necessário.
    """

    course: CourseBasic | None = None
    model_config = ConfigDict(from_attributes=True)


# --- PROGRESSO DE MÓDULOS (Dashboard da Turma) ---


class ModuleProgressRead(BaseModel):
    """Módulo com informação de progresso para uma turma específica"""

    id: int
    name: str
    code: str | None = None
    hours_total: float
    order: int
    hours_completed: float = 0.0
    hours_debt: float = 0.0
    is_completed: bool = False
    percentage: float = 0.0


class SubjectProgressRead(BaseModel):
    """Disciplina com módulos e progresso agregado por turma"""

    id: int
    name: str
    required_room_type: RoomType
    modules: list[ModuleProgressRead] = []
    total_hours: float = 0.0
    completed_hours: float = 0.0
    overall_percentage: float = 0.0


class ClassFullDetailRead(ClassRead):
    """
    Dashboard completo da turma: Curso + Disciplinas + Módulos + Progresso.

    4 Pilares:
    ⚡ Optimization: 2 queries otimizadas com selectinload (vs N+1)
    📈 Scalability: Esquema extensível para futuras features (alunos, notas)
    ⚙️ Stability: Progresso calculado server-side (fonte de verdade única)
    🔐 Security: Filtrado por org_id no service layer
    """

    course: CourseBasic | None = None
    subjects: list[SubjectProgressRead] = []
    model_config = ConfigDict(from_attributes=True)


# --- ATUALIZAÇÃO DE PROGRESSO ---


class ClassProgressUpdate(BaseModel):
    """Atualizar horas completadas de um módulo para uma turma"""

    module_id: int
    hours_completed: float = Field(..., ge=0, description="Horas já lecionadas")


class ClassProgressBulkUpdate(BaseModel):
    """Atualizar progresso de múltiplos módulos de uma vez"""

    progress: list[ClassProgressUpdate] = Field(
        ..., min_length=1, description="Lista de atualizações"
    )


# ==========================================
#  CONFIGURAÇÕES DA ESCOLA (Sprint 0)
# ==========================================

DESC_ACADEMIC_YEAR = "Ano letivo no formato 'AAAA/AAAA' (ex: '2025/2026')"
DESC_REGION_CODE = "Município/distrito para feriados regionais (ex: 'Lisboa', 'Porto')"
DESC_HARD_END_DATE = "Data-limite rígida para término das aulas (hard stop do gerador)"
DESC_LUNCH_START = "Hora de início da janela de almoço (ex: 12:00)"
DESC_LUNCH_END = "Hora de fim da janela de almoço (ex: 14:00)"
DESC_LUNCH_MIN = "Duração mínima de almoço em minutos dentro da janela"
DESC_REPAIR_WINDOW_DAYS = "Janela fixa de estabilidade (em dias) para o modo de reparação"
ERR_LUNCH_WINDOW_PAIR = "Defina início e fim da janela de almoço em conjunto"
ERR_LUNCH_WINDOW_ORDER = "A hora de fim da janela de almoço deve ser posterior ao início"
ERR_LUNCH_WINDOW_DURATION = "A duração mínima de almoço excede a janela configurada"


def validate_lunch_window(start: time | None, end: time | None, minimum: int | None) -> None:
    """Validate the shared lunch-window invariant used by setup flows."""
    if (start is None) != (end is None):
        raise ValueError(ERR_LUNCH_WINDOW_PAIR)
    if start is None or end is None:
        return
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    if end_minutes <= start_minutes:
        raise ValueError(ERR_LUNCH_WINDOW_ORDER)
    if minimum is not None and minimum < 1:
        raise ValueError(ERR_LUNCH_WINDOW_DURATION)
    if minimum is not None and minimum > (end_minutes - start_minutes):
        raise ValueError(ERR_LUNCH_WINDOW_DURATION)


ERR_TARGET_BEFORE_START = "A data-alvo de fim não pode ser anterior ao início das aulas"
ERR_HARD_BEFORE_START = "A data-limite rígida não pode ser anterior ao início das aulas"
ERR_HARD_BEFORE_TARGET = "A data-limite rígida não pode ser anterior à data-alvo de fim"


class OrganizationSettingsUpsert(BaseModel):
    """Cria ou atualiza as configurações da escola."""

    model_config = ConfigDict(extra="forbid")

    school_start_date: date | None = Field(None, description="Primeiro dia de aulas")
    school_hard_end_date: date | None = Field(None, description=DESC_HARD_END_DATE)
    repair_stability_window_days: int | None = Field(
        None,
        ge=0,
        le=60,
        description=DESC_REPAIR_WINDOW_DAYS,
    )
    automatic_holidays_enabled: bool | None = Field(
        None, description="Importar feriados nacionais automaticamente"
    )

    @staticmethod
    def _validate_school_dates(
        start_date: date | None,
        hard_end_date: date | None,
    ) -> None:
        if start_date and hard_end_date and hard_end_date < start_date:
            raise ValueError(ERR_HARD_BEFORE_START)

    @model_validator(mode="after")
    def validate_school_dates_only(self):
        self._validate_school_dates(
            self.school_start_date,
            self.school_hard_end_date,
        )
        return self


class OrganizationSettingsRead(BaseModel):
    id: int
    organization_id: int
    school_start_date: date | None = None
    school_hard_end_date: date | None = None
    repair_stability_window_days: int | None = None
    automatic_holidays_enabled: bool = False
    model_config = ConfigDict(from_attributes=True)


class OrganizationGridSettingsUpsert(BaseModel):
    lunch_window_start: time | None = Field(None, description=DESC_LUNCH_START)
    lunch_window_end: time | None = Field(None, description=DESC_LUNCH_END)
    lunch_min_duration_minutes: int | None = Field(None, ge=1, description=DESC_LUNCH_MIN)

    @staticmethod
    def _validate_lunch_inputs(start: time | None, end: time | None, minimum: int | None) -> None:
        validate_lunch_window(start, end, minimum)

    @model_validator(mode="after")
    def validate_lunch_window(self):
        self._validate_lunch_inputs(
            self.lunch_window_start,
            self.lunch_window_end,
            self.lunch_min_duration_minutes,
        )
        return self


class OrganizationGridSettingsRead(BaseModel):
    id: int
    organization_id: int
    lunch_window_start: time | None = None
    lunch_window_end: time | None = None
    lunch_min_duration_minutes: int | None = None

    model_config = ConfigDict(from_attributes=True)


class HolidaysSyncResponse(BaseModel):
    imported_count: int
    message: str


class SchoolCalendarEventCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    start_date: date
    end_date: date
    event_type: CalendarEventType

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError("A data de fim não pode ser anterior à data de início")
        return self


class SchoolCalendarEventRead(BaseModel):
    id: int
    organization_id: int
    name: str
    start_date: date
    end_date: date
    event_type: CalendarEventType
    source: CalendarEventSource

    model_config = ConfigDict(from_attributes=True)


# --- GERADOR DE TIMESLOTS ---
class TimeslotBulkCreate(BaseModel):
    start_time: time
    end_time: time
    slot_duration_minutes: int = Field(..., gt=0, description="Duração de cada aula (ex: 50 ou 90)")
    break_duration_minutes: int = Field(0, ge=0, description="Intervalo entre aulas")
    days_of_week: list[int] = Field(
        ..., min_length=1, max_length=7, description="Lista de dias (0=Seg, 4=Sex)"
    )

    @model_validator(mode="after")
    def validate_grid(self):
        if self.end_time <= self.start_time:
            raise ValueError("A hora de fecho deve ser posterior à hora de abertura.")
        if any(day < 0 or day > 6 for day in self.days_of_week):
            raise ValueError("Os dias da semana devem estar entre 0 e 6.")
        if len(set(self.days_of_week)) != len(self.days_of_week):
            raise ValueError("Os dias da semana não podem estar duplicados.")
        available_minutes = (
            self.end_time.hour * 60
            + self.end_time.minute
            - self.start_time.hour * 60
            - self.start_time.minute
        )
        if available_minutes < self.slot_duration_minutes:
            raise ValueError("A janela horária deve permitir pelo menos uma aula completa.")
        return self


class GridConfigurationCommand(BaseModel):
    grid_settings: OrganizationGridSettingsUpsert
    timeslots: TimeslotBulkCreate

    @model_validator(mode="after")
    def validate_lunch_inside_grid(self):
        lunch_start = self.grid_settings.lunch_window_start
        lunch_end = self.grid_settings.lunch_window_end
        if lunch_start is not None and (
            lunch_start < self.timeslots.start_time or lunch_end > self.timeslots.end_time
        ):
            raise ValueError("A janela de almoço deve ficar dentro do horário de abertura.")
        return self


class GridConfigurationResponse(BaseModel):
    message: str
    generated_count: int
    changed: bool
    grid_regenerated: bool


# ==========================================
#  DISCIPLINAS DA TURMA (Class-Subject Link)
#  Gestão curso-cêntrica de professores
# ==========================================


class ClassSubjectCreate(BaseModel):
    """Adicionar uma disciplina a uma turma (para o grade_level atual)"""

    subject_id: int


class ClassSubjectUpdate(BaseModel):
    """Atribuir ou alterar professor de uma disciplina da turma"""

    teacher_id: int | None = Field(
        None, description="ID do professor (null para remover atribuição)"
    )


class TeacherSimple(BaseModel):
    """Versão simplificada de Teacher para dropdowns"""

    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class ClassSubjectRead(BaseModel):
    """Disciplina da turma com professor atribuído"""

    id: int
    subject_id: int
    subject_name: str
    required_room_type: RoomType
    grade_level: int
    teacher_id: int | None = None
    teacher_name: str | None = None


class ClassSubjectsListRead(BaseModel):
    """Lista completa de disciplinas da turma para a página ClassSubjects"""

    class_id: int
    class_name: str
    course_name: str | None = None
    course_abbreviation: str | None = None
    grade_level: int
    subjects: list[ClassSubjectRead] = []


class EligibleTeacherRead(BaseModel):
    """Professor elegível para lecionar uma disciplina (tem competência)"""

    id: int
    name: str
    is_assigned_elsewhere: bool = False  # True se já dá esta disciplina noutra turma
    current_classes_count: int = 0  # Quantas turmas já tem


# ==========================================
#  SPRINT 2 — OCORRÊNCIAS DE AULAS
# ==========================================

DESC_OCCURRENCE_STATUS = "Estado da ocorrência: GIVEN | GAP | SUBSTITUTED"
DESC_OCCURRENCE_CREATE_ACTIVE_BLOCK_ID = "ID do bloco publicado para iniciar ocorrência operacional"


class LessonOccurrenceRead(BaseModel):
    """Registo histórico do que aconteceu numa aula agendada."""

    id: int
    organization_id: int
    active_schedule_block_id: int | None = None
    date: date
    status: LessonOccurrenceStatus | None = None
    operational_state: OperationalOccurrenceState
    revision: int = 1
    is_active: bool = True
    version: int = 1
    class_id: int | None = None
    class_name: str | None = None
    subject_id: int | None = None
    subject_name: str | None = None
    timeslot_id: int | None = None
    timeslot_start_time: time | None = None
    timeslot_end_time: time | None = None
    planned_hours: float
    planned_teacher_id: int | None = None
    planned_teacher_name: str | None = None
    executed_teacher_id: int | None = None
    executed_teacher_name: str | None = None
    planned_module_id: int | None = None
    executed_module_id: int | None = None
    substitute_teacher_id: int | None = None
    substitute_subject_id: int | None = None
    hours_given: float
    decided_by_membership_id: int | None = None
    decided_by_membership_name: str | None = None
    decided_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by_membership_id: int | None = None
    revoked_reason: str | None = None
    lesson_log_summary: str | None = None
    lesson_log_notes: str | None = None
    reason: str | None = None
    creation_source: str | None = None
    created_at: datetime

    model_config = model_config


class LessonOccurrenceListRead(BaseModel):
    items: list[LessonOccurrenceRead]
    total: int
    limit: int
    offset: int


class LessonOccurrenceCreate(BaseModel):
    """Payload para criar ocorrência operacional a partir de um bloco do horário."""

    action: Literal["CREATE_OCCURRENCE"] = "CREATE_OCCURRENCE"
    active_schedule_block_id: int = Field(
        ..., gt=0, description=DESC_OCCURRENCE_CREATE_ACTIVE_BLOCK_ID
    )
    mode: Literal["manual_admin", "lesson_log"] = Field(default="manual_admin", max_length=50)

    model_config = ConfigDict(extra="forbid")


class LessonOccurrenceUpdate(BaseModel):
    """Payload para o diretor registar uma falta ou substituição."""

    status: LessonOccurrenceStatus = Field(..., description=DESC_OCCURRENCE_STATUS)
    version: int = Field(..., ge=1)
    substitute_teacher_id: int | None = Field(
        None, gt=0, description="ID do professor substituto (obrigatório se status=SUBSTITUTED)"
    )
    substitute_subject_id: int | None = Field(
        None, gt=0, description="ID da disciplina dada pelo substituto"
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def check_substituted_requirements(self) -> LessonOccurrenceUpdate:
        if self.status == LessonOccurrenceStatus.REVOKED:
            raise ValueError("REVOKED usa o endpoint de cancelamento, nao PATCH normal")
        if self.status == LessonOccurrenceStatus.SUBSTITUTED:
            if self.substitute_teacher_id is None:
                raise ValueError("substitute_teacher_id é obrigatório quando status=SUBSTITUTED")
            if self.substitute_subject_id is None:
                raise ValueError("substitute_subject_id é obrigatório quando status=SUBSTITUTED")
            return self

        if self.substitute_teacher_id is not None or self.substitute_subject_id is not None:
            raise ValueError(
                "substitute_teacher_id e substitute_subject_id só podem ser enviados com status=SUBSTITUTED"
            )
        return self


class LessonOccurrenceCancel(BaseModel):
    version: int = Field(..., ge=1)
    cancel_completed_substitute_log: bool = False

    model_config = ConfigDict(extra="forbid")


class DebtItem(BaseModel):
    """Dívida de horas por turma/disciplina.

    Compatibilidade:
    - gap_occurrences / hours_owed = visão operacional total (inclui futuro decidido).
    - *_overdue = subconjunto vencido até a data de referência (as_of_date).
    """

    class_id: int
    class_name: str
    subject_id: int
    subject_name: str
    teacher_id: int | None = None
    teacher_name: str | None = None
    gap_occurrences: int
    hours_owed: float
    gap_occurrences_overdue: int = 0
    hours_owed_overdue: float = 0.0


class DebtListRead(BaseModel):
    """Lista de dívidas agrupadas por turma/disciplina.

    Compatibilidade:
    - total_gaps / total_hours_owed mantêm a visão operacional total.
    - total_*_overdue expõem a visão vencida até as_of_date.
    """

    total_gaps: int
    total_hours_owed: float
    total_gaps_overdue: int = 0
    total_hours_owed_overdue: float = 0.0
    as_of_date: date
    items: list[DebtItem]


class AvailableSubstituteRead(BaseModel):
    """Professor disponível para substituir num slot específico."""

    teacher_id: int
    teacher_name: str
    subject_id: int
    subject_name: str
    class_id: int
    class_name: str


class SubstituteRecommendationRead(BaseModel):
    """Candidato elegível para substituição com ranking e critérios objetivos."""

    rank: int
    teacher_id: int
    teacher_name: str
    subject_id: int
    subject_name: str
    class_id: int
    class_name: str
    substitutions_in_period: int
    daily_load_hours: float
    days_since_last_substitution: int | None = None
    justification: str


class OccurrenceObservabilitySummaryRead(BaseModel):
    """Contadores operacionais mínimos de ocorrências por organização."""

    window_days: int
    total_events: int
    decisions_success: int
    validation_failures: int
    conflicts: int


class TeacherEndpointObservabilityEndpointRead(BaseModel):
    """Métricas agregadas por endpoint crítico do fluxo professor."""

    endpoint_key: str
    total_requests: int
    status_2xx: int
    status_403: int
    status_5xx: int
    error_rate_percent: float
    p95_latency_ms: int


class TeacherEndpointAlertRead(BaseModel):
    """Alerta operacional calculado para o período analisado."""

    endpoint_key: str
    alert_code: str
    severity: str
    threshold: str
    observed_value: str


class TeacherEndpointObservabilitySummaryRead(BaseModel):
    """Resumo mínimo de monitorização de endpoints do professor."""

    window_minutes: int
    total_events: int
    endpoints: list[TeacherEndpointObservabilityEndpointRead]
    alerts: list[TeacherEndpointAlertRead]


# ==========================================
#  SPRINT 3 — RASCUNHOS E DIFF DE HORÁRIOS
# ==========================================


class ScheduleDraftRead(BaseModel):
    """Resumo de um rascunho de horário pendente de aprovação."""

    generation_id: str
    count: int
    earliest_date: date | None = None
    latest_date: date | None = None


class DraftComparisonSummaryRead(BaseModel):
    """Estatísticas agregadas de comparação entre o rascunho e o publicado."""

    delta_projected_end_date_days: int
    end_date_spread_days: int
    churn_outside_frozen_ratio: float
    total_blocks_changed: int
    backlog_remaining_hours: float
    aggregate_gap_variation: int


class ScheduleDiffRead(BaseModel):
    """Resultado do diff entre rascunho e horário ativo."""

    generation_id: str
    added: int
    removed: int
    unchanged: int
    total_draft: int
    total_active: int
    repair_window_days: int | None = None
    frozen_until: date | None = None
    compared_from_date: date | None = None
    statistics: DraftComparisonSummaryRead | None = None


class AuditGenerationSummaryRead(BaseModel):
    """Resumo de uma geração ativa para seleção no dashboard técnico."""

    generation_id: str
    blocks_count: int
    start_date: date | None = None
    end_date: date | None = None


class AuditRoomUsageRead(BaseModel):
    room_type: str
    blocks_count: int


class ScheduleGenerationAuditRead(BaseModel):
    """Métricas técnicas de auditoria por geração."""

    generation_id: str
    blocks_count: int
    start_date: date | None = None
    end_date: date | None = None
    classes_total: int
    classes_with_week_slots: int
    classes_empty_week: int
    week_slots_min: int
    week_slots_max: int
    week_slots_avg: float
    weekly_fairness_spread: float
    duplicate_teacher_slots: int
    duplicate_class_slots: int
    teachers_with_week_slots: int
    teacher_week_slots_min: int
    teacher_week_slots_max: int
    teacher_week_slots_avg: float
    room_type_usage: list[AuditRoomUsageRead]


# ==========================================
#  SPRINT 4 — VISUALIZAÇÃO SEMANAL
# ==========================================


class WeekTimeslotInfo(BaseModel):
    id: int
    day_of_week: int
    start_time: str
    end_time: str


class WeekSubjectInfo(BaseModel):
    id: int
    name: str


class WeekTeacherInfo(BaseModel):
    id: int
    name: str


class WeekRoomInfo(BaseModel):
    id: int
    name: str


class WeekClassInfo(BaseModel):
    id: int
    name: str


class TeacherScheduleHorizonRead(BaseModel):
    """Metadados mínimos para a visão semanal do professor autenticado."""

    min_week_start: date
    week_start_recommended: date
    hard_end_date: date
    active_generation_id: str | None = None


class WeekModuleInfo(BaseModel):
    id: int
    name: str
    hours_total: int


class WeekSlotRead(BaseModel):
    """Um bloco de aula numa semana: slot planeado + ocorrência real."""

    active_schedule_block_id: int | None = None
    operational_block_id: int | None = None
    block_source: Literal["planned", "active", "operational"] = "planned"
    date: str | None = None
    timeslot: WeekTimeslotInfo
    subject: WeekSubjectInfo | None = None
    teacher: WeekTeacherInfo | None = None
    room: WeekRoomInfo | None = None
    class_info: WeekClassInfo | None = None
    module: WeekModuleInfo | None = None
    is_past: bool
    occurrence_status: str | None = None
    hours_given: float | None = None
    occurrence_id: int | None = None
    occurrence_decided_at: datetime | None = None
    can_create_occurrence: bool
    can_decide_occurrence: bool
    # WBS Fase 1: campos de registo de execução
    lesson_log_id: int | None = None
    lesson_log_status: LessonLogStatus | None = None
    lesson_log_summary: str | None = None
    lesson_log_notes: str | None = None
    lesson_log_logged_at: datetime | None = None
    # WBS Fase 6: estado do fecho semanal do professor
    week_timesheet_status: str | None = None
    timesheet_id: int | None = None
    # WBS V3 Fase 4: indicador de bloco de substituição
    is_substituted_block: bool = False


# ==========================================
#  WBS FASE 1 — LESSON LOG (REGISTO DE EXECUÇÃO)
# ==========================================


class LessonLogCreate(BaseModel):
    """Payload para registar/atualizar o estado de execução de uma aula."""

    status: LessonLogStatus
    summary: str | None = Field(None, max_length=2000, description="Sumário da aula (opcional)")
    notes: str | None = Field(None, max_length=1000, description="Notas livres (opcional)")


class LessonLogRead(BaseModel):
    """Leitura completa de um registo de execução de aula."""

    id: int
    organization_id: int
    active_schedule_block_id: int | None = None
    operational_block_id: int | None = None
    status: LessonLogStatus
    summary: str | None = None
    notes: str | None = None
    logged_by_membership_id: int | None = None
    logged_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
#  WBS FASE 1 — TEACHER WEEKLY TIMESHEET
# ==========================================


class TimesheetStatusUpdate(BaseModel):
    """Payload para mudar o estado de uma timesheet semanal."""

    status: TimesheetStatus


class TeacherWeeklyTimesheetRead(BaseModel):
    """Leitura de uma timesheet semanal (usada no painel admin e no horario do professor)."""

    id: int
    organization_id: int
    teacher_id: int
    teacher_name: str | None = None
    week_start_date: date
    week_end_date: date
    status: TimesheetStatus
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    approved_by_membership_id: int | None = None
    created_at: datetime
    # WBS Fase 7.3: contagens de slots para o painel esquerdo
    total_slots: int = 0
    registered_slots: int = 0
    completed_slots: int = 0
    occurrence_slots: int = 0

    model_config = ConfigDict(from_attributes=True)


class TeacherWeeklyTimesheetListRead(TeacherWeeklyTimesheetRead):
    """Leitura admin de uma timesheet real ou virtual da semana selecionada."""

    id: int | None
    created_at: datetime | None = None


# ==========================================
#  PROGRESSO DO PROFESSOR (Visão Privada)
# ==========================================


class TeacherModuleProgressRead(BaseModel):
    """Progresso de um módulo numa disciplina de uma turma do professor."""

    module_id: int = Field(validation_alias=AliasChoices("module_id", "id"))
    module_name: str = Field(validation_alias=AliasChoices("module_name", "name"))
    module_code: str | None = Field(
        default=None, validation_alias=AliasChoices("module_code", "code")
    )
    hours_total: float
    hours_completed: float
    hours_debt: float
    is_completed: bool
    percentage: float


class TeacherSubjectProgressRead(BaseModel):
    """Disciplina com módulos e progresso agregado para uma turma do professor."""

    subject_id: int = Field(validation_alias=AliasChoices("subject_id", "id"))
    subject_name: str = Field(validation_alias=AliasChoices("subject_name", "name"))
    required_room_type: RoomType
    modules: list[TeacherModuleProgressRead] = []
    total_hours: float = 0.0
    completed_hours: float = 0.0
    overall_percentage: float = 0.0


class TeacherClassProgressRead(BaseModel):
    """Turma com disciplinas e progresso do professor autenticado."""

    class_id: int
    class_name: str
    course_name: str | None = None
    grade_level: int
    subjects: list[TeacherSubjectProgressRead] = []


# ==========================================
#  DASHBOARD V1 — COMMAND CENTER
# ==========================================


class AlertCounts(BaseModel):
    pending_occurrences_today: int = Field(ge=0, description="Ocorrências de hoje por decidir")
    pending_occurrences_total: int = Field(
        ge=0, description="Total de ocorrências por decidir (qualquer data)"
    )
    pending_timesheets: int = Field(ge=0, description="Timesheets SUBMITTED por aprovar")
    pending_drafts: int = Field(ge=0, description="Rascunhos de horário pendentes")
    active_substitutions_today: int = Field(ge=0, description="Substituições ativas hoje")


class ResourceCounts(BaseModel):
    teachers_count: int = Field(ge=0)
    classes_count: int = Field(ge=0)
    courses_count: int = Field(ge=0)
    subjects_count: int = Field(ge=0)
    rooms_count: int = Field(ge=0)
    rooms_by_type: dict[str, int] = Field(default_factory=dict)


class ScheduleHealthWidget(BaseModel):
    generation_id: str | None = Field(None, description="None se não houver geração ativa")
    blocks_count: int = 0
    classes_total: int = 0
    classes_empty_week: int = 0
    week_slots_avg: float = 0.0
    duplicate_teacher_slots: int = 0
    duplicate_class_slots: int = 0
    weekly_fairness_spread: float = 0.0
    teacher_week_slots_avg: float = 0.0


class ClassProgressSummary(BaseModel):
    class_id: int
    class_name: str
    course_id: int | None = None
    course_name: str | None = None
    grade_level: int
    overall_percentage: float = Field(ge=0.0, le=100.0)
    completed_hours: float = 0.0
    total_hours: float = 0.0


class DebtSummary(BaseModel):
    total_gaps: int = 0
    total_hours_owed: float = 0.0
    total_gaps_overdue: int = 0
    total_hours_owed_overdue: float = 0.0
    affected_classes_count: int = 0
    as_of_date: date


class PreparationDashboardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["PREPARATION"] = "PREPARATION"
    organization_name: str
    foundation_status: OrganizationFoundationStatus
    foundation_completed_at: datetime | None = None
    bases: BasesReadinessResponse
    prevalidation: PreflightReport


class OperationalDashboardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["OPERATIONAL"] = "OPERATIONAL"
    organization_name: str
    first_real_schedule_approved_at: datetime
    resources: ResourceCounts
    alerts: AlertCounts | None = None
    schedule_health: ScheduleHealthWidget | None = None
    class_progress: list[ClassProgressSummary] = Field(default_factory=list)
    debts: DebtSummary | None = None


DashboardResponse = Annotated[
    PreparationDashboardResponse | OperationalDashboardResponse,
    Field(discriminator="mode"),
]
