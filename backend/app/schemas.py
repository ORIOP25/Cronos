from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator
from datetime import time
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
    email: Optional[str] = None

class TeacherCreate(TeacherBase):
    email: Optional[str] = None

class TeacherRead(TeacherBase):
    id: int
    organization_id: int
    # Opcional: Incluir lista de disponibilidades quando pedes o professor
    # availabilities: List[AvailabilityRead] = [] 

    model_config = ConfigDict(from_attributes=True)

# --- Class (Turma) ---
class ClassBase(BaseModel):
    name: str

class ClassCreate(ClassBase):
    pass

class ClassRead(ClassBase):
    id: int
    organization_id: int
    model_config = model_config

# --- SUBJECT (DISCIPLINA) ---
class SubjectBase(BaseModel):
    name: str

class SubjectCreate(SubjectBase):
    pass

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

class RoomRead(RoomBase):
    id: int
    organization_id: int
    model_config = model_config

class UserRead(UserBase):
    id: int
    # Enviamos a role e o teacher_id para o frontend saber quem é
    role: UserRole
    teacher_id: int | None = None 

    model_config = model_config

# ==========================================
#  HORÁRIOS (Complexo)
# ==========================================

# --- TIMESLOT (BLOCO DE TEMPO) ---
class TimeslotBase(BaseModel):
    # 0=Segunda, 6=Domingo. O 'ge' e 'le' validam o intervalo.
    day_of_week: int = Field(..., ge=0, le=6, description="0=Segunda, 6=Domingo")
    
    # O Pydantic converte automaticamente strings "08:30" para objetos time
    start_time: time
    end_time: time

class TimeslotCreate(TimeslotBase):
    pass

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