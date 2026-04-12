import enum
from datetime import datetime, time, timezone, date as date_type
from typing import List, Optional
from sqlalchemy import (
    Column, Integer, String, Boolean,
    ForeignKey, Date, DateTime, Time,
    Text, Enum as SAEnum, UniqueConstraint, Table, Float, event,
)
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base

# --- FK Reference Constants (SonarQube S1192) ---
FK_ORG_ID = "organization.id"
FK_TEACHER_ID = "teacher.id"
FK_SUBJECT_ID = "subject.id"
FK_CLASS_ID = "class.id"
FK_TIMESLOT_ID = "timeslot.id"
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

class UserRole(str, enum.Enum):
    admin = "admin"
    teacher = "teacher"
    student = "student"

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
    Column("course_id", ForeignKey("course.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", ForeignKey(FK_SUBJECT_ID, ondelete="CASCADE"), primary_key=True),
)

# Tabela Relacional entre Professores e Disciplinas
teacher_subject_link = Table(
    "teacher_subject_link",
    Base.metadata,
    Column("teacher_id", ForeignKey(FK_TEACHER_ID, ondelete="CASCADE"), primary_key=True),
    Column("subject_id", ForeignKey(FK_SUBJECT_ID, ondelete="CASCADE"), primary_key=True),
)

# Tabela Relacional: Disciplinas de uma Turma (com professor opcional)
# Esta tabela define que disciplinas uma turma tem num determinado grade_level
# e quem é o professor atribuído a cada uma.
class ClassSubjectLink(Base):
    __tablename__ = "class_subject_link"

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey(FK_CLASS_ID, ondelete="CASCADE"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey(FK_SUBJECT_ID, ondelete="CASCADE"), index=True)
    grade_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 10, 11, 12
    teacher_id: Mapped[Optional[int]] = mapped_column(ForeignKey(FK_TEACHER_ID, ondelete=ON_DELETE_SET_NULL), nullable=True)

    # Relacionamentos
    class_: Mapped["Class"] = relationship()
    subject: Mapped["Subject"] = relationship()
    teacher: Mapped[Optional["Teacher"]] = relationship()

    __table_args__ = (
        UniqueConstraint("class_id", "subject_id", "grade_level", name="uq_class_subject_grade"),
    )

class Availability(Base):
    __tablename__ = "availability"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey(FK_TEACHER_ID), index=True)
    timeslot_id: Mapped[int] = mapped_column(ForeignKey(FK_TIMESLOT_ID), index=True)
    
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

    courses: Mapped[List["Course"]] = relationship(back_populates="organization", cascade=CASCADE_ALL_DELETE)
    
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

    settings: Mapped[List["OrganizationSettings"]] = relationship(back_populates="organization", cascade=CASCADE_ALL_DELETE)
    calendar_events: Mapped[List["SchoolCalendarEvent"]] = relationship(back_populates="organization", cascade=CASCADE_ALL_DELETE)

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name='{self.name}')>"


# Modelo "User" (O Diretor/Admin)
class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # O Papel do utilizador (Admin por defeito)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.admin, nullable=False)
    # Se for admin, isto fica NULL. Se for professor, aponta para o ID dele.
    teacher_id: Mapped[Optional[int]] = mapped_column(ForeignKey(FK_TEACHER_ID), nullable=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID))
    organization: Mapped["Organization"] = relationship(back_populates="users")
    # Atalho para aceder aos dados do professor (se existirem)
    teacher_profile: Mapped[Optional["Teacher"]] = relationship()
    # Permite bloquear utilizadores sem apagar o histórico (Soft Delete)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


# 5. Modelo "Teacher"
class Teacher(Base):
    __tablename__ = "teacher"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Chave Estrangeira: Liga o Professor à sua Organization
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID))
    
    # Relacionamento: Permite-nos fazer my_teacher.organization
    organization: Mapped["Organization"] = relationship(back_populates="teachers")

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

    def __repr__(self) -> str:
        return f"<Teacher(id={self.id}, name='{self.name}')>"


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
    
    # A ligação à Organização
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID))
    
    # As "peças" da aula
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

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey(FK_ORG_ID), index=True)
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

    def __repr__(self) -> str:
        return f"<ScheduleOutput(lesson_id={self.lesson_id}, timeslot_id={self.timeslot_id})>"
    
# --- CONFIGURAÇÕES DA ESCOLA (Sprint 0) ---

class OrganizationSettings(Base):
    """Configurações anuais da escola (uma por ano letivo).
    Chave lógica: (org_id, academic_year) — vários ativos em simultâneo
    porque os cursos profissionais duram 3 anos.
    """
    __tablename__ = "organization_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), index=True)
    academic_year: Mapped[str] = mapped_column(String(10), nullable=False)  # Ex: "2025/2026"
    school_start_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    school_target_end_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    school_hard_end_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    region_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Ex: "Lisboa"
    lunch_window_start: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    lunch_window_end: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    lunch_min_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    repair_stability_window_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="settings")

    __table_args__ = (
        UniqueConstraint("org_id", "academic_year", name="uq_org_academic_year"),
    )

    def __repr__(self) -> str:
        return f"<OrganizationSettings(org_id={self.org_id}, year='{self.academic_year}')>"


class SchoolCalendarEvent(Base):
    """Pausas letivas e feriados (hard constraint para o solver).
    source=AUTO: importado via package holidays Python.
    source=MANUAL: adicionado pelo diretor.
    """
    __tablename__ = "school_calendar_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), index=True)
    academic_year: Mapped[str] = mapped_column(String(10), nullable=False)
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

    id = Column(Integer, primary_key=True, index=True)
    
    # Qual é a aula original que vai sofrer alteração?
    lesson_id = Column(Integer, ForeignKey("lesson.id"), nullable=False)
    timeslot_id = Column(Integer, ForeignKey(FK_TIMESLOT_ID), nullable=False)
    
    # A data específica (ex: 2026-03-12). Isto diferencia a mudança pontual da permanente.
    date = Column(Date, nullable=False, index=True)
    
    # Quem faltou e quem vai substituir
    original_teacher_id = Column(Integer, ForeignKey(FK_TEACHER_ID), nullable=False)
    substitute_teacher_id = Column(Integer, ForeignKey(FK_TEACHER_ID), nullable=False)
    substitute_subject_id = Column(Integer, ForeignKey(FK_SUBJECT_ID), nullable=True)

    # Auditoria e Estado
    status = Column(String, default="PENDING") # PENDING, CONFIRMED, CANCELLED
    reason = Column(Text, nullable=True) # Ex: "Baixa médica"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relacionamentos
    lesson = relationship("Lesson")
    timeslot = relationship("Timeslot")
    original_teacher = relationship("Teacher", foreign_keys=[original_teacher_id])
    substitute_teacher = relationship("Teacher", foreign_keys=[substitute_teacher_id])
    substitute_subject = relationship("Subject", foreign_keys=[substitute_subject_id])


# --- OCORRÊNCIAS DE AULAS (Sprint 2) ---

class LessonOccurrence(Base):
    """Registo imutável do que aconteceu numa data específica.
    NEVER delete — é histórico permanente (D24).
    schedule_output_id usa ON DELETE SET NULL para preservar o registo
    mesmo que o horário seja regenerado.
    """
    __tablename__ = "lesson_occurrence"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID, ondelete="CASCADE"), index=True)

    # Liga ao slot planeado (pode ficar NULL se o horário for removido)
    schedule_output_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("schedule_output.id", ondelete=ON_DELETE_SET_NULL),
        nullable=True,
        index=True,
    )

    # Data em que deveria ter ocorrido
    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)

    # O que aconteceu: GIVEN | GAP | SUBSTITUTED
    status: Mapped[LessonOccurrenceStatus] = mapped_column(
        SAEnum(LessonOccurrenceStatus), nullable=False
    )

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
        nullable=False,
    )

    # Relacionamentos
    organization: Mapped["Organization"] = relationship()
    schedule_output: Mapped[Optional["ScheduleOutput"]] = relationship()
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

    # Uma ocorrência por slot planeado (evita duplicados do cron)
    __table_args__ = (
        UniqueConstraint(
            "schedule_output_id", "date",
            name="uq_lesson_occurrence_output_date",
        ),
    )

    def __repr__(self) -> str:
        return f"<LessonOccurrence(id={self.id}, date='{self.date}', status='{self.status}')>"


@event.listens_for(LessonOccurrence, "before_delete")
def _prevent_lesson_occurrence_delete(mapper, connection, target) -> None:  # noqa: ARG001
    raise ValueError("LessonOccurrence é histórico imutável e não pode ser removida")


# --- ENSINO PROFISSIONAL / MODULAR ---

class Course(Base):
    """Ex: Técnico de Gestão e Programação de Sistemas Informáticos"""
    __tablename__ = "course"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    abbreviation: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # Ex: "TGEI"
    organization_id: Mapped[int] = mapped_column(ForeignKey(FK_ORG_ID))
    
    organization: Mapped["Organization"] = relationship(back_populates="courses")
    classes: Mapped[List["Class"]] = relationship(back_populates="course")
    
    # Relação N:M com Subject - Define a Matriz Curricular
    subjects: Mapped[List["Subject"]] = relationship(
        secondary=course_subject_link,
        back_populates="courses"
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
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # Ex: "0789"
    hours_total: Mapped[int] = mapped_column(Integer, nullable=False)  # Sem default - admin define
    order: Mapped[int] = mapped_column(Integer, nullable=False)  # Sequência no currículo (1, 2, 3...)
    
    # Um módulo pertence a uma disciplina macro (ex: pertence a "Programação")
    subject_id: Mapped[int] = mapped_column(ForeignKey(FK_SUBJECT_ID))
    subject: Mapped["Subject"] = relationship(back_populates="modules")

    # Garante ordem única por disciplina
    __table_args__ = (
        UniqueConstraint("subject_id", "order", name="uq_module_order_per_subject"),
    )

    def __repr__(self) -> str:
        return f"<Module(id={self.id}, code='{self.code}', hours={self.hours_total})>"

class ClassProgress(Base):
    """Rastreia quantas horas a turma já fez de um módulo"""
    __tablename__ = "class_progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    
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
        UniqueConstraint("class_id", "module_id", name="uq_class_module"),
    )