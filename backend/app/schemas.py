from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator
from datetime import time, datetime, date
from typing import Any, Optional
from .models import RoomType, UserRole, ConstraintType, PreferenceLevel


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

# --- TEACHER (PROFESSOR) ---
class TeacherBase(BaseModel):
    name: str
    email: Optional[EmailStr] = None

class TeacherCreate(TeacherBase):
    create_user_account: bool = False

class TeacherRead(TeacherBase):
    id: int
    organization_id: int
    user_id: Optional[int] = None
    login_email: Optional[str] = None
    # Opcional: Incluir lista de disponibilidades quando pedes o professor
    # availabilities: List[AvailabilityRead] = [] 

    model_config = ConfigDict(from_attributes=True)

class TeacherUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    # No futuro, se adicionares 'email' ou 'phone' ao Teacher, adicionas aqui também.

# --- Class (Turma) ---
class ClassBase(BaseModel):
    name: str
    size: int = Field(default=25, gt=0, description="Número de alunos da turma")

class ClassCreate(ClassBase):
    pass

# Novo Schema de Update
class ClassUpdate(BaseModel):
    name: Optional[str] = None
    size: Optional[int] = None

class ClassRead(ClassBase):
    id: int
    organization_id: int
    model_config = model_config

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

# --- LESSON (AULA A ALOCAR) ---
class LessonBase(BaseModel):
    class_id: int
    subject_id: int
    teacher_id: int
    num_per_week: int = Field(..., ge=0) # Geater or Equal
    is_double: bool = False

class LessonCreate(LessonBase):
    num_per_week: int = Field(..., gt=0) # Greater Than 0

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