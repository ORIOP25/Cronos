import enum
from datetime import datetime, time
from typing import List, Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    Date,
    DateTime,
    Time,
    Text,
    Enum as SAEnum,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base

# Enum para Tipos de Sala
# Isto garante que o tipo de sala só pode ser um destes valores
class RoomType(str, enum.Enum):
    normal = "normal"
    lab = "lab"
    gym = "gym"
    art = "art"  # Exemplo futuro

# Enum para os Papéis de Utilizador
class UserRole(str, enum.Enum):
    admin = "admin"
    teacher = "teacher"
    student = "student"

class ConstraintType(str, enum.Enum):
    # Regras de Sala/Tempo
    specific_room = "specific_room"
    lock_time = "lock_time"
    
    # Regras de Professor (Novas)
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

class Availability(Base):
    __tablename__ = "availability"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teacher.id"), index=True)
    timeslot_id: Mapped[int] = mapped_column(ForeignKey("timeslot.id"), index=True)
    
    # O Score (-1 a 2)
    score: Mapped[int] = mapped_column(Integer, default=PreferenceLevel.NEUTRAL.value, nullable=False)

    # Relacionamentos (Ajusta os nomes se as tuas classes Teacher/Timeslot forem diferentes)
    teacher: Mapped["Teacher"] = relationship(back_populates="availabilities")
    timeslot: Mapped["Timeslot"] = relationship()

    __table_args__ = (
        UniqueConstraint('teacher_id', 'timeslot_id', name='uq_teacher_timeslot_availability'),
    )

# Modelo "Organization" (O Colégio)
# Esta é a tabela "mãe" de quase todas as outras.
class Organization(Base):
    __tablename__ = "organization"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Campo para o plano de subscrição (do Ponto 3.6 do Charter)
    plan_status: Mapped[str] = mapped_column(String(50), default="inactive")

    # --- Relacionamentos ---
    # Isto cria "atalhos" em Python para aceder aos dados ligados.
    # Ex: my_organization.users, my_organization.teachers, etc.
    users: Mapped[List["User"]] = relationship(back_populates="organization")
    teachers: Mapped[List["Teacher"]] = relationship(back_populates="organization")
    classes: Mapped[List["Class"]] = relationship(back_populates="organization")
    rooms: Mapped[List["Room"]] = relationship(back_populates="organization")
    subjects: Mapped[List["Subject"]] = relationship(back_populates="organization")
    timeslots: Mapped[List["Timeslot"]] = relationship(back_populates="organization")

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name='{self.name}')>"


# Modelo "User" (O Diretor/Admin)
class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # O Papel do utilizador (Admin por defeito)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.admin, nullable=False)
    # Se for admin, isto fica NULL. Se for professor, aponta para o ID dele.
    teacher_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teacher.id"), nullable=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"))
    organization: Mapped["Organization"] = relationship(back_populates="users")
    # Atalho para aceder aos dados do professor (se existirem)
    teacher_profile: Mapped[Optional["Teacher"]] = relationship()
    # Permite bloquear utilizadores sem apagar o histórico (Soft Delete)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


# 5. Modelo "Teacher" (Professor)
class Teacher(Base):
    __tablename__ = "teacher"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Chave Estrangeira: Liga o Professor à sua Organization
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"))
    
    # Relacionamento: Permite-nos fazer my_teacher.organization
    organization: Mapped["Organization"] = relationship(back_populates="teachers")

    availabilities: Mapped[List["Availability"]] = relationship(back_populates="teacher", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Teacher(id={self.id}, name='{self.name}')>"


# 6. Modelo "Class" (Turma)
class Class(Base):
    __tablename__ = "class"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Chave Estrangeira: Liga a Turma à sua Organization
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"))
    
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
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"))
    
    # Relacionamento: Permite-nos fazer my_room.organization
    organization: Mapped["Organization"] = relationship(back_populates="rooms")

    def __repr__(self) -> str:
        return f"<Room(id={self.id}, name='{self.name}', type='{self.type.value}')>"


# 8. Modelo "Subject" (Disciplina)
class Subject(Base):
    __tablename__ = "subject"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Chave Estrangeira: Liga a Disciplina à sua Organization
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"))
    
    # Relacionamento: Permite-nos fazer my_subject.organization
    organization: Mapped["Organization"] = relationship(back_populates="subjects")

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
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"))
    
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
    
    # A ligação à Organização
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"))
    
    # As "peças" da aula
    class_id: Mapped[int] = mapped_column(ForeignKey("class.id"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subject.id"), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teacher.id"), index=True)
    
    # As "regras" da aula
    num_per_week: Mapped[int] = mapped_column(Integer, default=1)
    is_double: Mapped[bool] = mapped_column(Boolean, default=False)

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
# (Como definido no Ponto 3.5 do Charter)
class Constraint(Base):
    __tablename__ = "constraint"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), index=True)
    # O tipo de regra, ex: 'teacher_unavailable', 'class_must_use_room'
    rule_type = Column(SAEnum(ConstraintType), nullable=False)
    
    # O "payload" da regra (um JSON flexível)
    # Ex: {"teacher_id": 1, "day": 2, "period": "morning"}
    rule_payload = Column(JSON, nullable=False)
    
    # Relacionamento
    organization: Mapped["Organization"] = relationship()

    def __repr__(self) -> str:
        return f"<Constraint(id={self.id}, type='{self.rule_type}')>"
    
# 12. Modelo "ScheduleOutput" (O Horário Final)
# (Como definido no Ponto 3.5 do Charter)
class ScheduleOutput(Base):
    __tablename__ = "schedule_output"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)

    # A "aula" que foi agendada (ex: Matemática do 10A)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id"), index=True)
    
    # O "bloco" onde ela foi agendada (ex: Segunda 09:00)
    timeslot_id: Mapped[int] = mapped_column(ForeignKey("timeslot.id"), index=True)
    
    # A "sala" que foi usada (ex: Sala 1.1)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), index=True)
    
    # ID para versionar (ex: "Geração de Verão 2025")
    generation_id: Mapped[str] = mapped_column(String(100), index=True)

    # Relacionamentos
    organization: Mapped["Organization"] = relationship()
    lesson: Mapped["Lesson"] = relationship()
    timeslot: Mapped["Timeslot"] = relationship()
    room: Mapped["Room"] = relationship()

    def __repr__(self) -> str:
        return f"<ScheduleOutput(lesson_id={self.lesson_id}, timeslot_id={self.timeslot_id})>"
    
# -- SUBSTITUIÇÕES --
class Substitution(Base):
    __tablename__ = "substitutions"

    id = Column(Integer, primary_key=True, index=True)
    
    # Qual é a aula original que vai sofrer alteração?
    lesson_id = Column(Integer, ForeignKey("lesson.id"), nullable=False)
    timeslot_id = Column(Integer, ForeignKey("timeslot.id"), nullable=False)
    
    # A data específica (ex: 2026-03-12). Isto diferencia a mudança pontual da permanente.
    date = Column(Date, nullable=False, index=True)
    
    # Quem faltou e quem vai substituir
    original_teacher_id = Column(Integer, ForeignKey("teacher.id"), nullable=False)
    substitute_teacher_id = Column(Integer, ForeignKey("teacher.id"), nullable=False)
    
    # Auditoria e Estado
    status = Column(String, default="PENDING") # PENDING, CONFIRMED, CANCELLED
    reason = Column(Text, nullable=True) # Ex: "Baixa médica"
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    lesson = relationship("Lesson")
    timeslot = relationship("Timeslot")
    original_teacher = relationship("Teacher", foreign_keys=[original_teacher_id])
    substitute_teacher = relationship("Teacher", foreign_keys=[substitute_teacher_id])