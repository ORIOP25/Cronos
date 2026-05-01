from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator, computed_field
from datetime import time, datetime, date
from typing import Any, Optional, Literal
from .models import (
    RoomType, UserRole, ConstraintType, PreferenceLevel,
    CalendarEventType, CalendarEventSource, LessonOccurrenceStatus,
    LessonLogStatus, TimesheetStatus, List,
)


# --- CONFIGURAÇÃO GLOBAL ---
# Esta é a "magia" que diz ao Pydantic para ler dados
# diretamente dos nossos modelos SQLAlchemy (ex: ler um objeto "Teacher" da BD
# e convertê-lo num schema "TeacherRead").
model_config = ConfigDict(from_attributes=True)

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
#  AUTENTICAÇÃO & USERS
# ==========================================

class Token(BaseModel):
    access_token: str
    token_type: str
    organization_id: int
    organization_name: str
    user_email: str  
    role: str 
    teacher_id: Optional[int] = None

class TokenData(BaseModel):
    email: str | None = None

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class RegisterRequest(BaseModel):
    """Payload para registo de nova conta (Organização + Admin)."""
    school_name: str = Field(..., min_length=2, max_length=100, description="Nome da instituição/escola")
    admin_name: str = Field(..., min_length=2, max_length=150, description="Nome do administrador")
    email: EmailStr
    password: str = Field(..., min_length=6, description="Password (mínimo 6 caracteres)")

class UserRead(UserBase):
    id: int
    name: str | None = None
    role: UserRole
    teacher_id: int | None = None
    organization_id: int

    model_config = model_config

class UserResponse(UserBase):
    id: int
    organization_id: int
    # role: UserRole = UserRole.ADMIN # Descomentar se usares roles no futuro
    
    model_config = model_config

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
    # Email: Será obrigatório em TeacherCreate, opcional em TeacherRead (compatibilidade)
    email: Optional[EmailStr] = None

class TeacherCreate(TeacherBase):
    # Email opcional — se fornecido, permite criar conta de acesso ao professor
    create_user_account: bool = False
    password: str | None = Field(None, min_length=6, description="Password de acesso (obrigatória se create_user_account=True)")
    subject_ids: list[int] = Field(default_factory=list, description=DESC_SUBJECT_IDS)

    @model_validator(mode='after')
    def password_required_if_creating_account(self):
        if self.create_user_account and not self.password:
            raise ValueError('A password é obrigatória quando create_user_account é verdadeiro')
        return self

class TeacherRead(TeacherBase):
    id: int
    organization_id: int
    user_id: Optional[int] = None
    login_email: Optional[str] = None
    # NOVO: Para o frontend saber se a conta está ativa ou inativa
    is_active: bool = False
    subject_ids: list[int] = Field(default_factory=list, description=DESC_SUBJECT_IDS)
    # Opcional: Incluir lista de disponibilidades quando pedes o professor
    # availabilities: List[AvailabilityRead] = [] 

    model_config = ConfigDict(from_attributes=True)

class TeacherUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    subject_ids: list[int] = Field(default_factory=list, description=DESC_SUBJECT_IDS)
    # NOVO: Para permitir ativar/desativar a conta de acesso via API
    create_user_account: Optional[bool] = None

# --- Class (Turma) ---
class ClassBase(BaseModel):
    name: str
    size: int = Field(default=25, gt=0, description=DESC_CLASS_SIZE)

class ClassCreate(ClassBase):
    course_id: int = Field(..., description="ID do curso (obrigatório — turmas pertencem sempre a um curso)")
    grade_level: int = Field(..., ge=10, le=12, description=DESC_GRADE_LEVEL)
    start_year: int = Field(..., description=DESC_START_YEAR)
    end_year: int = Field(..., description=DESC_END_YEAR)

    @model_validator(mode='after')
    def validate_year_window(self):
        if self.end_year <= self.start_year:
            raise ValueError(ERR_YEAR_RANGE)
        return self

class ClassUpdate(BaseModel):
    name: Optional[str] = None
    size: Optional[int] = Field(None, gt=0, description=DESC_CLASS_SIZE)
    grade_level: Optional[int] = Field(None, ge=10, le=12, description=DESC_GRADE_LEVEL)
    start_year: Optional[int] = Field(None, description=DESC_START_YEAR)
    end_year: Optional[int] = Field(None, description=DESC_END_YEAR)

    @model_validator(mode='after')
    def validate_year_window_if_present(self):
        if self.start_year is not None and self.end_year is not None and self.end_year <= self.start_year:
            raise ValueError(ERR_YEAR_RANGE)
        return self


class ClassCreateInCourse(ClassBase):
    grade_level: int = Field(..., ge=10, le=12, description=DESC_GRADE_LEVEL)
    start_year: int = Field(..., description=DESC_START_YEAR)
    end_year: int = Field(..., description=DESC_END_YEAR)

    @model_validator(mode='after')
    def validate_year_window(self):
        if self.end_year <= self.start_year:
            raise ValueError(ERR_YEAR_RANGE)
        return self


class ClassUpdateInCourse(BaseModel):
    name: Optional[str] = None
    size: Optional[int] = Field(None, gt=0, description=DESC_CLASS_SIZE)
    grade_level: Optional[int] = Field(None, ge=10, le=12, description=DESC_GRADE_LEVEL)
    start_year: Optional[int] = Field(None, description=DESC_START_YEAR)
    end_year: Optional[int] = Field(None, description=DESC_END_YEAR)

    @model_validator(mode='after')
    def validate_year_window_if_present(self):
        if self.start_year is not None and self.end_year is not None and self.end_year <= self.start_year:
            raise ValueError(ERR_YEAR_RANGE)
        return self

class ClassRead(ClassBase):
    id: int
    organization_id: int
    course_id: Optional[int] = None
    grade_level: int
    start_year: int
    end_year: int
    model_config = model_config

# --- MÓDULOS ---
class ModuleBase(BaseModel):
    name: str
    code: Optional[str] = None
    hours_total: int = Field(..., gt=0, description=DESC_HOURS_TOTAL)
    order: int = Field(..., ge=0, description="Ordem sequencial do módulo (0, 1, 2...)")

class ModuleCreate(ModuleBase):
    pass

class ModuleUpsert(BaseModel):
    """Módulo para upsert: se id presente = atualizar, se ausente = criar"""
    id: Optional[int] = None
    name: str
    code: Optional[str] = None
    hours_total: int = Field(..., gt=0, description=DESC_HOURS_TOTAL)
    order: int = Field(..., ge=0, description="Ordem sequencial do módulo")

class ModuleUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    hours_total: Optional[int] = Field(None, gt=0, description=DESC_HOURS_TOTAL)
    subject_id: Optional[int] = None

class ModuleRead(ModuleBase):
    id: int
    subject_id: int
    model_config = ConfigDict(from_attributes=True)

# --- SUBJECT ---
class SubjectBase(BaseModel):
    name: str
    required_room_type: RoomType = RoomType.normal

class SubjectCreate(SubjectBase):
    modules: list[ModuleCreate] = Field(default_factory=list, description="Lista de módulos iniciais")

    @model_validator(mode='after')
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
    name: Optional[str] = None
    required_room_type: Optional[RoomType] = None
    modules: Optional[list[ModuleUpsert]] = None

class SubjectRead(SubjectBase):
    id: int
    organization_id: int
    modules: list[ModuleRead] = []
    model_config = model_config

# --- ROOM (SALA) ---
class RoomBase(BaseModel):
    name: str
    type: RoomType
    capacity: int = 30

class RoomCreate(RoomBase):
    pass

class RoomUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[RoomType] = None
    capacity: Optional[int] = None

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
    @model_validator(mode='after')
    def check_times(self):
        if self.end_time <= self.start_time:
            raise ValueError('A hora de fim deve ser posterior à hora de início')
        return self

class TimeslotCreate(TimeslotBase):
    pass

class TimeslotUpdate(BaseModel):
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    start_time: Optional[time] = None
    end_time: Optional[time] = None

    @model_validator(mode='after')
    def check_times(self):
        # Apenas valida se ambos os campos estiverem presentes no update
        # (Para updates parciais complexos, a lógica seria mais extensa, 
        # mas para este MVP assume-se que se mudas horas, deves ter cuidado)
        if self.start_time and self.end_time:
             if self.end_time <= self.start_time:
                raise ValueError('A hora de fim deve ser posterior à hora de início')
        return self

class TimeslotRead(TimeslotBase):
    id: int
    organization_id: int

    model_config = ConfigDict(from_attributes=True)

# --- LESSON (ATRIBUIÇÃO DE PROFESSOR) ---
# 
# Padrão (Service Distribution):
# Uma "Lesson" é a Atribuição de um Professor a uma Disciplina/Turma.
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
class ConstraintBase(BaseModel):
    rule_type: ConstraintType
    rule_payload: Any  # Flexível para aceitar JSON complexo

class ConstraintCreate(ConstraintBase):
    pass

class ConstraintRead(ConstraintBase):
    id: int
    organization_id: int
    model_config = model_config

# --- Disponibilidade ---
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


class AvailabilitySelfRead(BaseModel):
    """Leitura self-service de disponibilidade do professor autenticado."""
    timeslot_id: int
    score: PreferenceLevel = PreferenceLevel.NEUTRAL

class AvailabilityRead(AvailabilityBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

# --- SCHEDULE OUTPUT (O RESULTADO FINAL) ---
class ScheduleOutputBase(BaseModel):
    lesson_id: int
    timeslot_id: int
    room_id: int
    generation_id: str

class ScheduleOutputRead(ScheduleOutputBase):
    id: int
    organization_id: int
    lesson_date: Optional[date] = Field(None, alias="date")
    is_draft: bool = False
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# --- GERADOR DE HORÁRIOS (Sprint 1) ---
class ScheduleGenerateRequest(BaseModel):
    """Pedido de geração de horário.

    mode="full"   — gera de raiz para todas as turmas ativas.
    mode="repair" — regenera com perturbação mínima face ao horário atual.
    """
    mode: str = "full"


class SchedulePreflightPrimaryWindow(BaseModel):
    rolling_weeks: int
    start_date: date
    end_date: date
    total_days: int
    blocked_days: int
    usable_days: int


class SchedulePreflightHardEndFeasibility(BaseModel):
    start_date: date
    hard_end_date: date
    backlog_hours: float
    capacity_hours: float
    expected_residual_hours: float
    feasible_until_hard_end: bool


class SchedulePreflightSummary(BaseModel):
    mode: str
    primary_window: Optional[SchedulePreflightPrimaryWindow] = None
    hard_end_feasibility: Optional[SchedulePreflightHardEndFeasibility] = None


class ScheduleGenerateResponse(BaseModel):
    task_id: str
    status: str
    solver_version: str
    preflight: SchedulePreflightSummary


# --- SUBSTITUTIONS ---

class SubstitutionBase(BaseModel):
    lesson_id: int
    timeslot_id: int
    original_teacher_id: int
    date: date  # Campo crítico para a mudança pontual
    reason: Optional[str] = None

class SubstitutionCreate(SubstitutionBase):
    # O ID do professor substituto é enviado aqui
    substitute_teacher_id: int 

class SubstitutionResponse(SubstitutionBase):
    id: int
    substitute_teacher_id: int
    status: str
    created_at: datetime
    
    # Para facilitar a leitura no frontend (opcional, mas recomendado)
    original_teacher_name: Optional[str] = None
    substitute_teacher_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# Schema para a sugestão (resposta do algoritmo)
class ReplacementSuggestion(BaseModel):
    teacher_id: int
    teacher_name: str
    priority: int  # 1 (Mesma Disciplina), 2 (Mesma Área), 3 (Livre)
    reason: str    # Ex: "Livre e da mesma disciplina"

# --- CURSOS ---
# Classes Auxiliares
class ClassConfigCreate(BaseModel):
    """Define as regras para criar uma turma automática"""
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
    abbreviation: str = Field(..., min_length=2, max_length=10, description="Sigla do curso (ex: TGEI)")

class CourseCreate(CourseBase):
    subject_ids: list[int] = Field(default_factory=list, description="IDs das disciplinas que compõem o curso")
    teacher_assignments: list[TeacherAssignmentCreate] = Field(default_factory=list, description="Professores por disciplina")
    classes_config: list[ClassConfigCreate] = Field(default_factory=list, description="Configuração das turmas a criar")

class CourseUpdate(BaseModel):
    name: Optional[str] = None
    abbreviation: Optional[str] = None
    subject_ids: Optional[list[int]] = None

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
    subjects: list[SubjectSimple] = Field(default_factory=list, description="Disciplinas do curso (sem módulos)")
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
    course: Optional[CourseBasic] = None
    model_config = ConfigDict(from_attributes=True)

# --- PROGRESSO DE MÓDULOS (Dashboard da Turma) ---

class ModuleProgressRead(BaseModel):
    """Módulo com informação de progresso para uma turma específica"""
    id: int
    name: str
    code: Optional[str] = None
    hours_total: int
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
    total_hours: int = 0
    completed_hours: int = 0
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
    course: Optional[CourseBasic] = None
    subjects: list[SubjectProgressRead] = []
    model_config = ConfigDict(from_attributes=True)

# --- ATUALIZAÇÃO DE PROGRESSO ---

class ClassProgressUpdate(BaseModel):
    """Atualizar horas completadas de um módulo para uma turma"""
    module_id: int
    hours_completed: float = Field(..., ge=0, description="Horas já lecionadas")

class ClassProgressBulkUpdate(BaseModel):
    """Atualizar progresso de múltiplos módulos de uma vez"""
    progress: list[ClassProgressUpdate] = Field(..., min_length=1, description="Lista de atualizações")

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
ERR_TARGET_BEFORE_START = "A data-alvo de fim não pode ser anterior ao início das aulas"
ERR_HARD_BEFORE_START = "A data-limite rígida não pode ser anterior ao início das aulas"
ERR_HARD_BEFORE_TARGET = "A data-limite rígida não pode ser anterior à data-alvo de fim"


class OrganizationSettingsUpsert(BaseModel):
    """Cria ou atualiza as configurações da escola."""
    school_start_date: date | None = Field(None, description="Primeiro dia de aulas")
    school_target_end_date: date | None = Field(None, description="Data-alvo para fim das aulas (benchmark do solver)")
    school_hard_end_date: date | None = Field(None, description=DESC_HARD_END_DATE)
    repair_stability_window_days: int | None = Field(
        None,
        ge=1,
        description=DESC_REPAIR_WINDOW_DAYS,
    )

    @staticmethod
    def _validate_school_dates(
        start_date: date | None,
        target_end_date: date | None,
        hard_end_date: date | None,
    ) -> None:
        if start_date and target_end_date and target_end_date < start_date:
            raise ValueError(ERR_TARGET_BEFORE_START)
        if start_date and hard_end_date and hard_end_date < start_date:
            raise ValueError(ERR_HARD_BEFORE_START)
        if target_end_date and hard_end_date and hard_end_date < target_end_date:
            raise ValueError(ERR_HARD_BEFORE_TARGET)

    @model_validator(mode='after')
    def validate_school_dates_only(self):
        self._validate_school_dates(
            self.school_start_date,
            self.school_target_end_date,
            self.school_hard_end_date,
        )
        return self


class OrganizationSettingsRead(BaseModel):
    id: int
    org_id: int
    school_start_date: date | None = None
    school_target_end_date: date | None = None
    school_hard_end_date: date | None = None
    repair_stability_window_days: int | None = None

    model_config = ConfigDict(from_attributes=True)

class OrganizationGridSettingsUpsert(BaseModel):
    lunch_window_start: time | None = Field(None, description=DESC_LUNCH_START)
    lunch_window_end: time | None = Field(None, description=DESC_LUNCH_END)
    lunch_min_duration_minutes: int | None = Field(None, ge=1, description=DESC_LUNCH_MIN)

    @staticmethod
    def _validate_lunch_inputs(start: time | None, end: time | None, minimum: int | None) -> None:
        if (start is None) != (end is None):
            raise ValueError(ERR_LUNCH_WINDOW_PAIR)
        if start is None or end is None:
            return

        start_minutes = start.hour * 60 + start.minute
        end_minutes = end.hour * 60 + end.minute
        if end_minutes <= start_minutes:
            raise ValueError(ERR_LUNCH_WINDOW_ORDER)
        if minimum is not None and minimum > (end_minutes - start_minutes):
            raise ValueError(ERR_LUNCH_WINDOW_DURATION)

    @model_validator(mode='after')
    def validate_lunch_window(self):
        self._validate_lunch_inputs(
            self.lunch_window_start,
            self.lunch_window_end,
            self.lunch_min_duration_minutes,
        )
        return self

class OrganizationGridSettingsRead(BaseModel):
    id: int
    org_id: int
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

    @model_validator(mode='after')
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError('A data de fim não pode ser anterior à data de início')
        return self


class SchoolCalendarEventRead(BaseModel):
    id: int
    org_id: int
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
    days_of_week: List[int] = Field(..., description="Lista de dias (0=Seg, 4=Sex)")

# ==========================================
#  DISCIPLINAS DA TURMA (Class-Subject Link)
#  Gestão curso-cêntrica de professores
# ==========================================

class ClassSubjectCreate(BaseModel):
    """Adicionar uma disciplina a uma turma (para o grade_level atual)"""
    subject_id: int

class ClassSubjectUpdate(BaseModel):
    """Atribuir ou alterar professor de uma disciplina da turma"""
    teacher_id: Optional[int] = Field(None, description="ID do professor (null para remover atribuição)")

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
    teacher_id: Optional[int] = None
    teacher_name: Optional[str] = None
    
class ClassSubjectsListRead(BaseModel):
    """Lista completa de disciplinas da turma para a página ClassSubjects"""
    class_id: int
    class_name: str
    course_name: Optional[str] = None
    course_abbreviation: Optional[str] = None
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
DESC_OCCURRENCE_CREATE_SCHEDULE_OUTPUT_ID = "ID do bloco planeado (ScheduleOutput) para iniciar ocorrência operacional"


class LessonOccurrenceRead(BaseModel):
    """Registo histórico do que aconteceu numa aula agendada."""
    id: int
    org_id: int
    schedule_output_id: Optional[int] = None
    date: date
    status: LessonOccurrenceStatus
    class_id: Optional[int] = None
    class_name: Optional[str] = None
    subject_id: Optional[int] = None
    subject_name: Optional[str] = None
    timeslot_id: Optional[int] = None
    timeslot_start_time: Optional[time] = None
    timeslot_end_time: Optional[time] = None
    planned_hours: float
    planned_teacher_id: Optional[int] = None
    planned_teacher_name: Optional[str] = None
    executed_teacher_id: Optional[int] = None
    executed_teacher_name: Optional[str] = None
    planned_module_id: Optional[int] = None
    executed_module_id: Optional[int] = None
    substitute_teacher_id: Optional[int] = None
    substitute_subject_id: Optional[int] = None
    hours_given: float
    decided_by_user_id: Optional[int] = None
    decided_by_user_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: datetime

    model_config = model_config


class LessonOccurrenceCreate(BaseModel):
    """Payload para criar ocorrência operacional a partir de um bloco do horário."""
    action: Literal["CREATE_OCCURRENCE"] = "CREATE_OCCURRENCE"
    schedule_output_id: int = Field(..., gt=0, description=DESC_OCCURRENCE_CREATE_SCHEDULE_OUTPUT_ID)
    mode: str = Field(default="manual_admin", max_length=50)
    reason: Optional[str] = Field(None, max_length=250)

    model_config = ConfigDict(extra="forbid")


class LessonOccurrenceUpdate(BaseModel):
    """Payload para o diretor registar uma falta ou substituição."""
    status: LessonOccurrenceStatus = Field(..., description=DESC_OCCURRENCE_STATUS)
    substitute_teacher_id: Optional[int] = Field(
        None, description="ID do professor substituto (obrigatório se status=SUBSTITUTED)"
    )
    substitute_subject_id: Optional[int] = Field(
        None, description="ID da disciplina dada pelo substituto"
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def check_substituted_requirements(self) -> "LessonOccurrenceUpdate":
        if self.status == LessonOccurrenceStatus.SUBSTITUTED:
            if self.substitute_teacher_id is None:
                raise ValueError("substitute_teacher_id é obrigatório quando status=SUBSTITUTED")
            if self.substitute_subject_id is None:
                raise ValueError("substitute_subject_id é obrigatório quando status=SUBSTITUTED")
            return self

        if self.substitute_teacher_id is not None or self.substitute_subject_id is not None:
            raise ValueError("substitute_teacher_id e substitute_subject_id só podem ser enviados com status=SUBSTITUTED")
        return self


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
    teacher_id: Optional[int] = None
    teacher_name: Optional[str] = None
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
    days_since_last_substitution: Optional[int] = None
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
    """Résultat du diff entre rascunho e horário ativo."""
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
    active_generation_id: Optional[str] = None
    

class WeekModuleInfo(BaseModel):
    id: int
    name: str
    hours_total: int


class WeekSlotRead(BaseModel):
    """Um bloco de aula numa semana: slot planeado + ocorrência real."""
    schedule_output_id: int
    date: Optional[str] = None
    timeslot: WeekTimeslotInfo
    subject: Optional[WeekSubjectInfo] = None
    teacher: Optional[WeekTeacherInfo] = None
    room: Optional[WeekRoomInfo] = None
    class_info: Optional[WeekClassInfo] = None
    module: Optional[WeekModuleInfo] = None
    is_past: bool
    occurrence_status: Optional[str] = None
    hours_given: Optional[float] = None
    occurrence_id: Optional[int] = None
    occurrence_decided_at: Optional[datetime] = None
    can_create_occurrence: bool
    can_decide_occurrence: bool
    # WBS Fase 1: campos de registo de execução
    lesson_log_id: Optional[int] = None
    lesson_log_status: Optional[LessonLogStatus] = None
    lesson_log_summary: Optional[str] = None
    lesson_log_notes: Optional[str] = None
    lesson_log_logged_at: Optional[datetime] = None
    # WBS Fase 6: estado do fecho semanal do professor
    week_timesheet_status: Optional[str] = None
    timesheet_id: Optional[int] = None


# ==========================================
#  WBS FASE 1 — LESSON LOG (REGISTO DE EXECUÇÃO)
# ==========================================

class LessonLogCreate(BaseModel):
    """Payload para registar/atualizar o estado de execução de uma aula."""
    status: LessonLogStatus
    summary: Optional[str] = Field(None, max_length=2000, description="Sumário da aula (opcional)")
    notes: Optional[str] = Field(None, max_length=1000, description="Notas livres (opcional)")


class LessonLogRead(BaseModel):
    """Leitura completa de um registo de execução de aula."""
    id: int
    org_id: int
    schedule_output_id: int
    status: LessonLogStatus
    summary: Optional[str] = None
    notes: Optional[str] = None
    logged_by_user_id: Optional[int] = None
    logged_at: Optional[datetime] = None
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
    org_id: int
    teacher_id: int
    teacher_name: Optional[str] = None
    week_start_date: date
    week_end_date: date
    status: TimesheetStatus
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by_user_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)