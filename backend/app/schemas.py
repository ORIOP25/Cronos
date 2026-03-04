from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator, computed_field
from datetime import time, datetime, date
from typing import Any, Optional
from .models import (
    RoomType, UserRole, ConstraintType, PreferenceLevel,
    CalendarEventType, CalendarEventSource, LessonOccurrenceStatus, List,
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
    hours_completed: int = 0
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
    hours_completed: int = Field(..., ge=0, description="Horas já lecionadas")

class ClassProgressBulkUpdate(BaseModel):
    """Atualizar progresso de múltiplos módulos de uma vez"""
    progress: list[ClassProgressUpdate] = Field(..., min_length=1, description="Lista de atualizações")

# ==========================================
#  CONFIGURAÇÕES DA ESCOLA (Sprint 0)
# ==========================================

DESC_ACADEMIC_YEAR = "Ano letivo no formato 'AAAA/AAAA' (ex: '2025/2026')"
DESC_REGION_CODE = "Município/distrito para feriados regionais (ex: 'Lisboa', 'Porto')"


class OrganizationSettingsUpsert(BaseModel):
    """Cria ou atualiza as configurações de um ano letivo.
    Chave lógica: (org_id, academic_year).
    """
    academic_year: str = Field(..., pattern=r'^\d{4}/\d{4}$', description=DESC_ACADEMIC_YEAR)
    school_start_date: date | None = Field(None, description="Primeiro dia de aulas")
    school_target_end_date: date | None = Field(None, description="Data-alvo para fim das aulas (benchmark do solver)")
    region_code: str | None = Field(None, description=DESC_REGION_CODE)


class OrganizationSettingsRead(BaseModel):
    id: int
    org_id: int
    academic_year: str
    school_start_date: date | None = None
    school_target_end_date: date | None = None
    region_code: str | None = None

    model_config = ConfigDict(from_attributes=True)


class HolidaysSyncResponse(BaseModel):
    academic_year: str
    imported_count: int
    message: str


class AvailableRegionsResponse(BaseModel):
    regions: list[str]


class SchoolCalendarEventCreate(BaseModel):
    academic_year: str = Field(..., pattern=r'^\d{4}/\d{4}$', description=DESC_ACADEMIC_YEAR)
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
    academic_year: str
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


class LessonOccurrenceRead(BaseModel):
    """Registo histórico do que aconteceu numa aula agendada."""
    id: int
    org_id: int
    schedule_output_id: Optional[int] = None
    date: date
    status: LessonOccurrenceStatus
    substitute_teacher_id: Optional[int] = None
    substitute_subject_id: Optional[int] = None
    hours_given: float
    created_at: datetime

    model_config = model_config


class LessonOccurrenceUpdate(BaseModel):
    """Payload para o diretor registar uma falta ou substituição."""
    status: LessonOccurrenceStatus = Field(..., description=DESC_OCCURRENCE_STATUS)
    substitute_teacher_id: Optional[int] = Field(
        None, description="ID do professor substituto (obrigatório se status=SUBSTITUTED)"
    )
    substitute_subject_id: Optional[int] = Field(
        None, description="ID da disciplina dada pelo substituto"
    )

    @model_validator(mode="after")
    def check_substituted_requires_teacher(self) -> "LessonOccurrenceUpdate":
        if (
            self.status == LessonOccurrenceStatus.SUBSTITUTED
            and self.substitute_teacher_id is None
        ):
            raise ValueError("substitute_teacher_id é obrigatório quando status=SUBSTITUTED")
        return self


class DebtItem(BaseModel):
    """Uma dívida de horas de aula para uma turma/disciplina."""
    class_id: int
    class_name: str
    subject_id: int
    subject_name: str
    teacher_id: Optional[int] = None
    teacher_name: Optional[str] = None
    gap_occurrences: int
    hours_owed: float


class DebtListRead(BaseModel):
    """Lista de dívidas de horas agrupadas por turma."""
    total_gaps: int
    total_hours_owed: float
    items: list[DebtItem]


class AvailableSubstituteRead(BaseModel):
    """Professor disponível para substituir num slot específico."""
    teacher_id: int
    teacher_name: str
    subject_id: int
    subject_name: str
    class_id: int
    class_name: str


# ==========================================
#  SPRINT 3 — RASCUNHOS E DIFF DE HORÁRIOS
# ==========================================

class ScheduleDraftRead(BaseModel):
    """Resumo de um rascunho de horário pendente de aprovação."""
    generation_id: str
    count: int
    earliest_date: date | None = None
    latest_date: date | None = None


class ScheduleDiffRead(BaseModel):
    """Résultat du diff entre rascunho e horário ativo."""
    generation_id: str
    added: int
    removed: int
    unchanged: int
    total_draft: int
    total_active: int