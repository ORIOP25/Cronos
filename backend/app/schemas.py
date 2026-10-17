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
from .scheduler.domain.timetable import BreakOverride, build_daily_slots

END_BEFORE_START_MESSAGE = "A data de fim não pode ser anterior à data de início"
DUPLICATE_CLASSES_MESSAGE = "As turmas não podem estar duplicadas."


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


PRESENCE_MIN_HOURS_MESSAGE = "O mínimo tem de estar entre 1 e 12 horas."
PRESENCE_GAP_HOURS_MESSAGE = "O furo máximo tem de estar entre 0 e 12 horas."
PRESENCE_PAIR_MESSAGE = "Indique o mínimo e o furo máximo, ou deixe os dois vazios."


class TeacherPresence(BaseModel):
    """Optional, school-defined presence rule of one teacher (D01, D02, D05, D06)."""

    model_config = ConfigDict(extra="forbid")

    lunch_required: bool = True
    minimum_hours: Annotated[int, Field(strict=True)] | None = Field(
        default=None, description="Mínimo de horas por presença"
    )
    max_gap_hours: Annotated[int, Field(strict=True)] | None = Field(
        default=None, description="Furo máximo dentro da presença"
    )

    @model_validator(mode="after")
    def validate_presence(self):
        if self.minimum_hours is not None and not 1 <= self.minimum_hours <= 12:
            raise ValueError(PRESENCE_MIN_HOURS_MESSAGE)
        if self.max_gap_hours is not None and not 0 <= self.max_gap_hours <= 12:
            raise ValueError(PRESENCE_GAP_HOURS_MESSAGE)
        if (self.minimum_hours is None) != (self.max_gap_hours is None):
            raise ValueError(PRESENCE_PAIR_MESSAGE)
        return self

    @classmethod
    def from_teacher(cls, teacher: Any) -> TeacherPresence:
        return cls(
            lunch_required=teacher.lunch_required,
            minimum_hours=teacher.minimum_presence_hours,
            max_gap_hours=teacher.maximum_presence_gap_hours,
        )


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
    teacher_presence: TeacherPresence | None = None
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
    can_manage_foundation: bool


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
    can_manage_foundation: bool


class SessionBootstrapResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: SessionBootstrapOrganization
    member: SessionBootstrapMember
    foundation_status: OrganizationFoundationStatus


# --- Foundation & Readiness Schemas ---
class BreakOverridePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    after_slot: int = Field(
        ..., ge=1, description="Aula após a qual ocorre a pausa (a primeira é 1)"
    )
    duration_minutes: int = Field(..., ge=0, le=60, description="Duração da pausa em minutos")


class FoundationInternshipFlow(BaseModel):
    """Draft-friendly row: a partially filled flow survives autosave."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=150)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("A data de fim do fluxo não pode ser anterior à data de início")
        return self


class FoundationDraftData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    school_start_date: date | None = None
    school_hard_end_date: date | None = None
    preferred_end_date: date | None = None
    repair_stability_window_days: int = Field(default=14, ge=0, le=60)
    days_of_week: list[int] | None = None
    opening_time: time | None = None
    closing_time: time | None = None
    slot_duration_minutes: int | None = Field(default=None, ge=15, le=120)
    break_duration_minutes: int | None = Field(default=None, ge=0, le=60)
    break_overrides: list[BreakOverridePayload] | None = None
    lunch_window_start: time | None = None
    lunch_window_end: time | None = None
    lunch_min_duration_minutes: int | None = Field(default=None, ge=1, le=180)
    automatic_holidays_enabled: bool = False
    internship_flows: list[FoundationInternshipFlow] = Field(default_factory=list)

    @field_validator("repair_stability_window_days", mode="before")
    @classmethod
    def default_missing_repair_stability_window(cls, value: int | None) -> int:
        return 14 if value is None else value

    @model_validator(mode="after")
    def validate_unique_break_override_positions(self):
        overrides = self.break_overrides or []
        positions = [override.after_slot for override in overrides]
        if len(set(positions)) != len(positions):
            raise ValueError("Só pode existir um ajuste de intervalo por aula.")
        if self.school_start_date and self.school_hard_end_date:
            for flow in self.internship_flows:
                if flow.start_date is None or flow.end_date is None:
                    continue
                if (
                    flow.start_date < self.school_start_date
                    or flow.end_date > self.school_hard_end_date
                ):
                    raise ValueError("Os fluxos de estágio devem estar dentro do período letivo.")
        return self


class FoundationDraftWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(..., ge=0)
    current_step: int = Field(default=1, ge=1, le=10)
    data: FoundationDraftData


class FoundationDraftRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    current_step: int = Field(default=1, ge=1, le=10)
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
    context: dict[str, str | int | None] = Field(default_factory=dict)


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
    is_archived: bool = False
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
        expected = list(range(len(self.modules)))

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
        expected = list(range(len(self.modules)))
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
    is_archived: bool = False
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
    is_archived: bool = False
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
        from app.scheduler.domain.constraint_policy import SchoolConstraintPolicy

        result = SchoolConstraintPolicy.parse(
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


class AvailabilitySelfCreate(BaseModel):
    """Disponibilidade sem teacher_id (usa ID do path/autenticacao)."""

    timeslot_id: int
    score: PreferenceLevel = PreferenceLevel.NEUTRAL


WeeklyAvailabilityPayload = Annotated[
    list[AvailabilitySelfCreate], Field(max_length=MAX_WEEKLY_TIMETABLE_SLOTS)
]

MAX_CLASS_AVAILABILITY_COPY_TARGETS = 500


class ClassAvailabilityCopyRequest(BaseModel):
    """Targets of a class-availability copy. Between 1 and 500 class ids."""

    target_class_ids: Annotated[
        list[StrictPositiveInt],
        Field(min_length=1, max_length=MAX_CLASS_AVAILABILITY_COPY_TARGETS),
    ]


class AvailabilitySelfRead(BaseModel):
    """Leitura self-service de disponibilidade do professor autenticado."""

    timeslot_id: int
    score: PreferenceLevel = PreferenceLevel.NEUTRAL


class AvailabilityRead(AvailabilityBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


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
    class_availability: BulkImportFilePayload | None = None
    teacher_availability: BulkImportFilePayload | None = None
    teacher_presence: BulkImportFilePayload | None = None

    @model_validator(mode="after")
    def require_a_file(self):
        if not any(
            getattr(self, resource) is not None
            for resource in (
                "rooms",
                "subjects",
                "courses",
                "teachers",
                "assignments",
                "class_availability",
                "teacher_availability",
                "teacher_presence",
            )
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
    is_archived: bool = False
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
    preferred_end_date: date | None = Field(
        None, description="Data-alvo preferencial para a conclusão das aulas"
    )
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
        preferred_end_date: date | None = None,
    ) -> None:
        if start_date and hard_end_date and hard_end_date < start_date:
            raise ValueError(ERR_HARD_BEFORE_START)
        if start_date and preferred_end_date and preferred_end_date < start_date:
            raise ValueError(ERR_TARGET_BEFORE_START)
        if hard_end_date and preferred_end_date and hard_end_date < preferred_end_date:
            raise ValueError(ERR_HARD_BEFORE_TARGET)

    @model_validator(mode="after")
    def validate_school_dates_only(self):
        self._validate_school_dates(
            self.school_start_date,
            self.school_hard_end_date,
            self.preferred_end_date,
        )
        return self


class OrganizationSettingsRead(BaseModel):
    id: int
    organization_id: int
    school_start_date: date | None = None
    school_hard_end_date: date | None = None
    preferred_end_date: date | None = None
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


class SchoolCalendarEventCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    start_date: date
    end_date: date
    event_type: CalendarEventType
    class_ids: list[int] = Field(default_factory=list)
    confirmation_fingerprint: str | None = None

    @model_validator(mode="after")
    def validate_payload(self):
        if self.end_date < self.start_date:
            raise ValueError(END_BEFORE_START_MESSAGE)
        if self.class_ids and self.event_type != CalendarEventType.internship_flow:
            raise ValueError("Só um fluxo de estágio pode abranger turmas.")
        if len(set(self.class_ids)) != len(self.class_ids):
            raise ValueError(DUPLICATE_CLASSES_MESSAGE)
        return self


class SchoolCalendarEventUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    start_date: date
    end_date: date
    class_ids: list[int] = Field(default_factory=list)
    confirmation_fingerprint: str | None = None

    @model_validator(mode="after")
    def validate_payload(self):
        if self.end_date < self.start_date:
            raise ValueError(END_BEFORE_START_MESSAGE)
        if len(set(self.class_ids)) != len(self.class_ids):
            raise ValueError(DUPLICATE_CLASSES_MESSAGE)
        return self


class CalendarEventChangePreviewRequest(BaseModel):
    operation: Literal["create", "update", "delete"]
    event_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    start_date: date | None = None
    end_date: date | None = None
    class_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_payload(self):
        if self.operation in ("update", "delete") and self.event_id is None:
            raise ValueError("Indique o fluxo a alterar.")
        if self.operation in ("create", "update"):
            if self.name is None or self.start_date is None or self.end_date is None:
                raise ValueError("Indique o nome e as datas do fluxo.")
            if self.end_date < self.start_date:
                raise ValueError(END_BEFORE_START_MESSAGE)
        if len(set(self.class_ids)) != len(self.class_ids):
            raise ValueError(DUPLICATE_CLASSES_MESSAGE)
        return self


class AffectedLessonRead(BaseModel):
    lesson_id: int
    class_id: int
    class_name: str | None = None
    subject_id: int
    subject_name: str | None = None
    date: date
    timeslot_id: int
    duration_minutes: int


class CalendarEventChangePreviewRead(BaseModel):
    requires_confirmation: bool
    confirmation_fingerprint: str | None = None
    affected_lessons: list[AffectedLessonRead] = Field(default_factory=list)
    message: str


class SchoolCalendarEventRead(BaseModel):
    id: int
    organization_id: int
    school_year_start_year: int | None = None
    applies_to_current_school_year: bool = True
    name: str
    start_date: date
    end_date: date
    event_type: CalendarEventType
    source: CalendarEventSource
    class_ids: list[int] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# --- GERADOR DE TIMESLOTS ---
class TimeslotBulkCreate(BaseModel):
    start_time: time
    end_time: time
    slot_duration_minutes: int = Field(..., gt=0, description="Duração de cada aula (ex: 50 ou 90)")
    break_duration_minutes: int = Field(0, ge=0, description="Intervalo entre aulas")
    break_overrides: list[BreakOverridePayload] = Field(
        default_factory=list,
        description="Ajustes pontuais da pausa após uma aula (a primeira aula é 1)",
    )
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
        positions = [override.after_slot for override in self.break_overrides]
        if len(set(positions)) != len(positions):
            raise ValueError("Só pode existir um ajuste de intervalo por aula.")
        slots = build_daily_slots(
            opening_time=self.start_time,
            closing_time=self.end_time,
            slot_duration_minutes=self.slot_duration_minutes,
            break_duration_minutes=self.break_duration_minutes,
            break_overrides=tuple(
                BreakOverride(
                    after_slot=override.after_slot,
                    duration_minutes=override.duration_minutes,
                )
                for override in self.break_overrides
            ),
        )
        if not slots:
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


# --- GRID CHANGE PREVIEW (W05) ---
class GridChangePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeslots: TimeslotBulkCreate


class GridConfigurationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: int | None = None
    effective_date: date | None = None
    state: str | None = None
    configuration: dict | None = None
    source: Literal["VERSION", "BLOCKS", "NONE"]


class GridChangeDailyDifference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_of_week: int
    current_lessons: int
    proposed_lessons: int
    delta: int


class GridChangeTimeslotRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_of_week: int
    start_time: time
    end_time: time


class GridChangeAffectedAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_timeslot_id: int
    current: GridChangeTimeslotRef
    proposed: GridChangeTimeslotRef | None = None
    match: Literal["EXACT", "MOVED", "REMOVED"]
    ambiguous: bool = False
    requires_decision: bool
    teachers: list[dict]
    classes: list[dict] = Field(default_factory=list)


class GridChangeAffectedConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    constraint_id: int
    current_timeslot_id: int
    rule_type: str
    rule_payload: dict
    proposed: GridChangeTimeslotRef | None = None
    proposed_timeslot_id: int | None = None
    match: Literal["EXACT", "MOVED", "REMOVED"]
    ambiguous: bool = False
    requires_decision: bool


class GridChangePendingLesson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurrence_id: int
    date: date
    class_id: int | None = None
    subject_id: int | None = None


class GridChangePreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_editable_date: date
    current_configuration: dict | None = None
    proposed_configuration: dict
    daily: list[GridChangeDailyDifference]
    affected_availabilities: list[GridChangeAffectedAvailability]
    affected_constraints: list[GridChangeAffectedConstraint]
    lessons_without_closure: list[GridChangePendingLesson]
    minutes_completed: int
    minutes_protected: int
    minutes_planned_after_boundary: int
    minutes_remaining: int
    fingerprint: str
    pending_grid_version_id: int | None = None
    can_propose: bool
    blockers: list[str] = Field(default_factory=list)


class GridChangeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_timeslot_id: int = Field(..., ge=1)
    action: Literal["COPY", "DISCARD"]


class GridChangeProposeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeslots: TimeslotBulkCreate
    fingerprint: str = Field(..., min_length=64, max_length=64)
    decisions: list[GridChangeDecision] = Field(default_factory=list)
    idempotency_key: str | None = Field(None, min_length=1, max_length=100)


class GridBlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day_of_week: int
    start_time: time
    end_time: time


class WeekGridDayRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    version_id: int | None = None
    effective_date: date | None = None
    blocks: list[GridBlockRead]


class WeekGridVersionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: list[WeekGridDayRead]
    transition_date: date | None = None


class GridChangeProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_version_id: int
    job_id: int
    strategy: Literal["GRID_CHANGE"]
    effective_date: date
    first_editable_date: date
    status: str
    created: bool


class GridChangePendingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_version_id: int
    effective_date: date
    configuration: dict | None = None
    job_id: int | None = None
    job_status: str | None = None
    blocks: list[GridBlockRead]


# ==========================================
#  DISCIPLINAS DA TURMA (Class-Subject Link)
#  Gestão curso-cêntrica de professores
# ==========================================


class JointLessonGroupClassRead(BaseModel):
    """Uma turma membro de uma aula conjunta"""

    class_id: int
    class_name: str
    course_abbreviation: str | None = None
    grade_level: int


class JointLessonGroupRead(BaseModel):
    """Aula conjunta devolvida pela API de configuração"""

    id: int
    subject_id: int
    subject_name: str
    teacher_id: int | None = None
    classes: list[JointLessonGroupClassRead] = []
    module_ids: list[int] = []


class JointLessonGroupWrite(BaseModel):
    """Criação ou substituição de uma aula conjunta"""

    subject_id: int | None = Field(None, description="Só no POST")
    class_ids: list[int] = Field(..., min_length=1)
    module_ids: list[int] = []
    teacher_id: int = Field(..., gt=0, description="Professor competente na disciplina")


class JointCandidateRead(BaseModel):
    """Turma candidata a entrar numa aula conjunta"""

    class_id: int
    class_name: str
    course_abbreviation: str | None = None
    grade_level: int
    teacher_id: int | None = None
    selected_module_ids: list[int] = []
    started_module_ids: list[int] = []


class ClassSubjectCreate(BaseModel):
    """Adicionar uma disciplina a uma turma (para o grade_level atual)"""

    subject_id: int


class ClassSubjectUpdate(BaseModel):
    """Atribuir professor e/ou selecionar módulos de uma disciplina da turma"""

    teacher_id: int | None = Field(
        None, description="ID do professor (null para remover atribuição)"
    )
    module_ids: list[int] | None = Field(
        None, description="IDs dos módulos selecionados (lista vazia para limpar)"
    )


class ClassSubjectModuleRead(BaseModel):
    """Módulo de uma disciplina da turma, com a marcação de seleção"""

    id: int
    name: str
    code: str | None = None
    hours_total: float
    order: int
    selected: bool


class ClassSubjectRead(BaseModel):
    """Disciplina da turma com professor atribuído e módulos"""

    id: int
    subject_id: int
    subject_name: str
    required_room_type: RoomType
    grade_level: int
    teacher_id: int | None = None
    teacher_name: str | None = None
    modules: list[ClassSubjectModuleRead] = []
    joint_group: JointLessonGroupRead | None = None


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


class JointLessonClassStateRead(BaseModel):
    """Per-class state of a joint lesson occurrence (J13)."""

    class_id: int
    class_name: str
    operational_state: str | None = None
    status: str | None = None
    version: int | None = None
    id: int | None = None


class JointLessonStateRead(BaseModel):
    """Member classes of a joint lesson with their operational state (J13)."""

    classes: list[JointLessonClassStateRead] = []


class LessonOccurrenceRead(BaseModel):
    """Registo histórico do que aconteceu numa aula agendada."""

    id: int
    organization_id: int
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
    substitute_subject_name: str | None = None
    substitute_block_id: int | None = None
    substitute_execution_status: str | None = None
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
    ends_at: datetime | None = None
    can_complete: bool = False
    blocked_reason: str | None = None
    # WBS 5.2 (J13): joint lesson per-class state.
    joint_lesson: JointLessonStateRead | None = None

    model_config = model_config


class LessonOccurrenceListRead(BaseModel):
    items: list[LessonOccurrenceRead]
    total: int
    limit: int
    offset: int


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
    # WBS 5.2 (J13): decide several member classes of a joint lesson at once.
    class_ids: list[int] | None = Field(
        None, description="Turmas da aula conjunta a decidir; por omissão só a linha indicada."
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


class SubstituteExclusionRead(BaseModel):
    """Motivo estruturado de exclusão de um candidato a substituto."""

    code: str
    message: str
    setup: str


class SubstituteDiagnosticCandidateRead(BaseModel):
    teacher_id: int
    teacher_name: str
    subject_id: int
    subject_name: str
    eligible: bool
    exclusions: list[SubstituteExclusionRead]


class SubstituteDiagnosticsRead(BaseModel):
    occurrence_id: int
    eligible_count: int
    candidates: list[SubstituteDiagnosticCandidateRead]
    setup_actions: list[str]


# ==========================================
#  SPRINT 3 — RASCUNHOS E DIFF DE HORÁRIOS
# ==========================================


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


class WeekClassLessonInfo(BaseModel):
    """One member class of a joint lesson in the weekly view (J17)."""

    id: int
    name: str
    lesson_log_status: LessonLogStatus | None = None
    lesson_db_id: int | None = None
    operational_block_id: int | None = None
    substitute_execution_status: str | None = None


class TeacherScheduleHorizonRead(BaseModel):
    """Metadados mínimos para a visão semanal do professor autenticado."""

    min_week_start: date
    week_start_recommended: date
    hard_end_date: date
    active_generation_id: str | None = None


class WeekModuleInfo(BaseModel):
    id: int
    name: str
    hours_total: float


class WeekSliceRead(BaseModel):
    """Uma parcela curricular de uma aula: módulo, offset e minutos exatos."""

    module_id: int
    module_name: str | None = None
    offset_minutes: int
    minutes: int
    completed_minutes: int = 0
    remaining_minutes: int = 0


class WeekSlotRead(BaseModel):
    """Um bloco de aula numa semana: slot planeado + ocorrência real."""

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
    # Scheduler v1: aula com identidade estável e várias parcelas modulares
    scheduler_lesson_id: int | None = None
    credit_minutes: int | None = None
    slices: list[WeekSliceRead] = Field(default_factory=list)
    # Scheduler v1: estado da substituição planeada e guarda temporal
    substitute_execution_status: str | None = None
    ends_at: datetime | None = None
    can_complete: bool = False
    blocked_reason: str | None = None
    # WBS 5.7 (J17): joint lesson weekly view.
    joint_classes: list[WeekClassInfo] = Field(default_factory=list)
    class_infos: list[WeekClassLessonInfo] = Field(default_factory=list)


# ==========================================
#  WBS FASE 1 — LESSON LOG (REGISTO DE EXECUÇÃO)
# ==========================================


class LessonLogCreate(BaseModel):
    """Payload para registar/atualizar o estado de execução de uma aula."""

    status: LessonLogStatus
    summary: str | None = Field(None, max_length=2000, description="Sumário da aula (opcional)")
    notes: str | None = Field(None, max_length=1000, description="Notas livres (opcional)")
    # WBS 5.3.4: member classes absent when concluding a joint substitution.
    absent_class_ids: list[int] = Field(default_factory=list)


class LessonLogRead(BaseModel):
    """Leitura completa de um registo de execução de aula."""

    id: int
    organization_id: int
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


class ScheduleConflictLesson(BaseModel):
    lesson_id: int
    class_name: str
    teacher_id: int
    teacher_name: str
    subject_name: str
    school_date: date
    starts_at: datetime
    ends_at: datetime


class ScheduleHealthWidget(BaseModel):
    generation_id: str | None = Field(None, description="None se não houver geração ativa")
    blocks_count: int = 0
    classes_total: int = 0
    classes_archived: int = 0
    classes_empty_week: int = 0
    week_slots_avg: float = 0.0
    duplicate_teacher_slots: int = 0
    duplicate_class_slots: int = 0
    conflicting_lessons: list[ScheduleConflictLesson] = Field(default_factory=list)
    weekly_fairness_spread: float = 0.0
    teacher_week_slots_avg: float = 0.0
    annual_class_average: float = 0.0
    annual_teacher_average: float = 0.0
    teachers_total: int = 0
    period_start: date | None = None
    period_end: date | None = None


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


# ==========================================
#  SCHEDULER v1 — CICLO DE VIDA (W08/W09)
# ==========================================


class SchedulerV1SchoolYearRead(BaseModel):
    id: int
    label: str
    start_date: date
    preferred_end_date: date | None = None
    hard_end_date: date
    timezone: str


class SchedulerV1RevisionsRead(BaseModel):
    input: int
    planning: int
    last_completed_planning: int | None = None
    last_successful_generation_at: str | None = None


class SchedulerV1EligibilityRead(BaseModel):
    can_generate: bool
    reasons: list[str] = Field(default_factory=list)
    blocker: str | None = None


class SchedulerV1JobDiagnosticRead(BaseModel):
    """One proven per-class or per-teacher diagnostic of a scheduler job."""

    code: str
    minimum_missing_minutes: int | None = None
    class_id: int | None = None
    class_name: str | None = None
    course_id: int | None = None
    subject_name: str | None = None
    teacher_id: int | None = None
    teacher_name: str | None = None


class SchedulerV1JobRead(BaseModel):
    id: int
    strategy: str
    status: str
    result_code: str | None = None
    stop_reason: str | None = None
    queue_position: int | None = None
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    cancellation_requested: bool = False
    proposal_id: int | None = None
    summary: dict | None = None
    diagnostics: list[SchedulerV1JobDiagnosticRead] = Field(default_factory=list)


class SchedulerV1ProposalRead(BaseModel):
    proposal_id: int
    status: str
    created_at: datetime
    decided_at: datetime | None = None
    base_version_id: int | None = None
    policy_version: str
    is_stale: bool = False
    stale_reason: str | None = None
    can_approve: bool = False
    strategy: str | None = None
    metrics: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    diagnostics: list[dict] = Field(default_factory=list)
    quality_summary: dict = Field(default_factory=dict)


class SchedulerV1PhysicalChangeRead(BaseModel):
    change_type: str
    lesson_id: int
    class_id: int
    subject_id: int
    before: dict | None = None
    after: dict | None = None


class SchedulerV1ModularChangeRead(BaseModel):
    lesson_id: int
    class_id: int
    subject_id: int
    before: list[dict] = Field(default_factory=list)
    after: list[dict] = Field(default_factory=list)


class SchedulerV1ProposalDiffRead(BaseModel):
    is_first_generation: bool
    physical: list[SchedulerV1PhysicalChangeRead] = Field(default_factory=list)
    modular: list[SchedulerV1ModularChangeRead] = Field(default_factory=list)
    counts: dict = Field(default_factory=dict)


class SchedulerV1StatusRead(BaseModel):
    configured: bool
    school_year: SchedulerV1SchoolYearRead | None = None
    publication_state: str = "UNPUBLISHED"
    active_version_id: int | None = None
    active_proposal_id: int | None = None
    revisions: SchedulerV1RevisionsRead
    eligibility: SchedulerV1EligibilityRead
    default_strategy: str
    active_job: SchedulerV1JobRead | None = None
    pending_proposal: SchedulerV1ProposalRead | None = None


class SchedulerV1GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(..., min_length=1, max_length=160)
    expected_input_revision: int = Field(..., ge=0)


class SchedulerV1GenerateResponse(BaseModel):
    job: SchedulerV1JobRead


class SchedulerV1ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_input_revision: int | None = Field(None, ge=0)


class SchedulerV1CancelResponse(BaseModel):
    job: SchedulerV1JobRead


class SchedulerV1ApproveResponse(BaseModel):
    proposal_id: int
    status: str
    active_version_id: int
    approved_at: datetime


class SchedulerV1RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(None, max_length=500)


class SchedulerV1RejectResponse(BaseModel):
    proposal_id: int
    status: str
    rejected_at: datetime


class SchedulerV1LessonLogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["COMPLETED", "OCCURRENCE"]
    summary: str | None = Field(None, max_length=2000)
    notes: str | None = Field(None, max_length=1000)
    # Joint lesson only: member classes that did not attend (J12).
    absent_class_ids: list[int] = Field(default_factory=list)


class LessonLogClassRead(BaseModel):
    """Per-class outcome of a joint lesson registration (J12)."""

    class_id: int
    status: str
    credited_minutes: int = 0


class SchedulerV1LessonLogResponse(BaseModel):
    lesson_id: int
    status: str
    credited_minutes: int = 0
    debt_minutes: int = 0
    revision: int = 1
    classes: list[LessonLogClassRead] = Field(default_factory=list)
