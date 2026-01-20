from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator, computed_field
from datetime import time, datetime, date
from typing import Any, Optional
from .models import RoomType, UserRole, ConstraintType, PreferenceLevel, List


# --- CONFIGURAÇÃO GLOBAL ---
# Esta é a "magia" que diz ao Pydantic para ler dados
# diretamente dos nossos modelos SQLAlchemy (ex: ler um objeto "Teacher" da BD
# e convertê-lo num schema "TeacherRead").
model_config = ConfigDict(from_attributes=True)

# ==========================================
#  AUTENTICAÇÃO & USERS
# ==========================================

class Token(BaseModel):
    access_token: str
    token_type: str
    organization_id: int
    user_email: str  
    role: str 
    teacher_id: Optional[int] = None

class TokenData(BaseModel):
    email: str | None = None

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserRead(UserBase):
    id: int
    # Enviamos a role e o teacher_id para o frontend saber quem é
    role: UserRole
    teacher_id: int | None = None 

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
    # SOBRESCRITA: Email OBRIGATÓRIO para novos professores
    email: EmailStr
    create_user_account: bool = False
    subject_ids: list[int] = Field(default_factory=list, description="IDs das disciplinas associadas")

class TeacherRead(TeacherBase):
    id: int
    organization_id: int
    user_id: Optional[int] = None
    login_email: Optional[str] = None
    # NOVO: Para o frontend saber se a conta está ativa ou inativa
    is_active: bool = False
    subject_ids: list[int] = Field(default_factory=list, description="IDs das disciplinas associadas")
    # Opcional: Incluir lista de disponibilidades quando pedes o professor
    # availabilities: List[AvailabilityRead] = [] 

    model_config = ConfigDict(from_attributes=True)

class TeacherUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    subject_ids: list[int] = Field(default_factory=list, description="IDs das disciplinas associadas")
    # NOVO: Para permitir ativar/desativar a conta de acesso via API
    create_user_account: Optional[bool] = None

# --- Class (Turma) ---
class ClassBase(BaseModel):
    name: str
    size: int = Field(default=25, gt=0, description="Número de alunos da turma")

class ClassCreate(ClassBase):
    course_id: Optional[int] = None
    pass

# Novo Schema de Update
class ClassUpdate(BaseModel):
    name: Optional[str] = None
    size: Optional[int] = None

class ClassRead(ClassBase):
    id: int
    organization_id: int
    model_config = model_config
    course_id: Optional[int] = None

# --- SUBJECT (DISCIPLINA) ---
class SubjectBase(BaseModel):
    name: str
    required_room_type: RoomType = RoomType.normal

class SubjectCreate(SubjectBase):
    pass

class SubjectUpdate(BaseModel):
    name: Optional[str] = None
    required_room_type: Optional[RoomType] = None

class SubjectRead(SubjectBase):
    id: int
    organization_id: int
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
    
    class Config:
        from_attributes = True

# --- LESSON (ATRIBUIÇÃO DE PROFESSOR) ---
# 
# NOVO PADRÃO (Service Distribution):
# Uma "Lesson" é agora a Atribuição de um Professor a uma Disciplina/Turma.
# O Solver calculará dinamicamente quantas vezes por semana o professor dá aulas.
#
# - Turma: A que turma é? (ex: 10º TGEI)
# - Disciplina: Qual disciplina? (ex: Matemática)
# - Professor: Quem leciona? (ex: Prof. Silva) [VALIDADO: deve ter competência]
# - num_per_week: Deixa opcional/comentado. O Solver calcula isto baseado em:
#   * Currículo do curso (quantas horas tem a disciplina)
#   * Progresso/Módulos atrasados
#   * Disponibilidade do professor
# - is_double: Se a aula é de 2h seguidas
#
# Esta abordagem elimina micro-gestão manual e permite escalabilidade.

class LessonBase(BaseModel):
    class_id: int
    subject_id: int
    teacher_id: int
    # NOVO: num_per_week é opcional. O Solver define isto dinamicamente.
    num_per_week: int = Field(default=1, ge=0, description="Opcional. Solver calcula.")
    is_double: bool = False

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
    model_config = model_config


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

    class Config:
        from_attributes = True

# Schema para a sugestão (resposta do algoritmo)
class ReplacementSuggestion(BaseModel):
    teacher_id: int
    teacher_name: str
    priority: int  # 1 (Mesma Disciplina), 2 (Mesma Área), 3 (Livre)
    reason: str    # Ex: "Livre e da mesma disciplina"

# --- CURSOS ---
class CourseBase(BaseModel):
    name: str

class CourseCreate(CourseBase):
    subject_ids: list[int] = Field(default_factory=list, description="IDs das disciplinas que compõem o curso")

class CourseUpdate(BaseModel):
    name: Optional[str] = None
    subject_ids: Optional[list[int]] = None

class CourseRead(CourseBase):
    id: int
    organization_id: int
    subject_ids: list[int] = Field(default_factory=list, description="IDs das disciplinas associadas")
    model_config = ConfigDict(from_attributes=True)

# --- MÓDULOS ---
class ModuleBase(BaseModel):
    name: str
    code: Optional[str] = None
    hours_total: int = Field(..., gt=0, description="Carga horária total do módulo")
    subject_id: int

class ModuleCreate(ModuleBase):
    pass

class ModuleUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    hours_total: Optional[int] = Field(None, gt=0, description="Carga horária total do módulo")
    subject_id: Optional[int] = None

class ModuleRead(ModuleBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# --- GERADOR DE TIMESLOTS (BULK) ---
class TimeslotBulkCreate(BaseModel):
    start_time: time
    end_time: time
    slot_duration_minutes: int = Field(..., gt=0, description="Duração de cada aula (ex: 50 ou 90)")
    break_duration_minutes: int = Field(0, ge=0, description="Intervalo entre aulas")
    days_of_week: List[int] = Field(..., description="Lista de dias (0=Seg, 4=Sex)")