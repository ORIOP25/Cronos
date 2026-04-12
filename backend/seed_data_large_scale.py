# Ficheiro: backend/seed_data_large_scale.py
# Seed de escala alargada para validar o gerador em cenário realista multi-escola.
# Corre: docker compose exec backend python seed_data_large_scale.py
import math
import sys
import datetime
from sqlalchemy import text

from app.db.database import SessionLocalSync, engine_sync, Base
from app import models
from app.core.security import hash_password, verify_password
from app.models import UserRole, PreferenceLevel, RoomType


# =====================================================================
#  CONFIGURAÇÃO DO CENÁRIO
# =====================================================================

# Requisito A: assumir dia de referência como 15 de setembro.
ASSUMED_TODAY = datetime.date(2025, 9, 15)
SCHOOL_TARGET_END = datetime.date(2026, 6, 30)
SCHOOL_HARD_END = datetime.date(2026, 7, 31)

ORG_COUNT = 3
COURSES_PER_ORG = 10
SUBJECTS_PER_CLASS_MIN = 8
SUBJECTS_PER_CLASS_MAX = 9
MODULES_PER_SUBJECT_MIN = 6
MODULES_PER_SUBJECT_MAX = 7
MODULE_HOURS_MIN = 25
MODULE_HOURS_MAX = 35

CLASS_BLUEPRINTS = [
    {"grade": 10, "start": 2025, "end": 2028, "suffix": "25/28", "size": 26},
    {"grade": 11, "start": 2024, "end": 2027, "suffix": "24/27", "size": 24},
    {"grade": 12, "start": 2023, "end": 2026, "suffix": "23/26", "size": 22},
]

# Regra: 1 professor para cada 8 turmas, por disciplina.
CLASSES_PER_ORG = COURSES_PER_ORG * len(CLASS_BLUEPRINTS)
TEACHER_CLASS_RATIO = 8
TEACHERS_PER_SUBJECT_POOL = math.ceil(CLASSES_PER_ORG / TEACHER_CLASS_RATIO)
TEACHERS_PER_ORG = SUBJECTS_PER_CLASS_MAX * TEACHERS_PER_SUBJECT_POOL

# Regra: 1 sala para cada 1.5 turmas
ROOMS_PER_CLASS_RATIO = 1.5
ROOMS_PER_ORG = math.ceil(CLASSES_PER_ORG / ROOMS_PER_CLASS_RATIO)
ROOMS_GYM_COUNT = max(1, math.ceil(ROOMS_PER_ORG * 0.05))
ROOMS_LAB_COUNT = max(2, math.ceil(ROOMS_PER_ORG * 0.25))
ROOMS_NORMAL_COUNT = max(1, ROOMS_PER_ORG - ROOMS_LAB_COUNT - ROOMS_GYM_COUNT)

ROOMS_TEMPLATE = (
    [
        {"name": f"Sala Normal {i:02d}", "capacity": 30, "type": RoomType.normal}
        for i in range(1, ROOMS_NORMAL_COUNT + 1)
    ]
    + [
        {"name": f"Lab Informatica {i:02d}", "capacity": 24, "type": RoomType.lab}
        for i in range(1, ROOMS_LAB_COUNT + 1)
    ]
    + [
        {"name": f"Espaco Educacao Fisica {i:02d}", "capacity": 60, "type": RoomType.gym}
        for i in range(1, ROOMS_GYM_COUNT + 1)
    ]
)

ROOM_TYPE_CYCLE = [RoomType.normal, RoomType.lab, RoomType.normal, RoomType.lab, RoomType.gym, RoomType.normal]

DISCIPLINE_CATALOG = [
    "Matematica",
    "Portugues",
    "Ingles",
    "Programacao",
    "Redes",
    "Sistemas",
    "Fisica",
    "Educacao_Fisica",
    "Area_Integracao",
]


# =====================================================================
#  UTILITÁRIOS
# =====================================================================

def clean_database():
    """DROP todas as tabelas (PostgreSQL-specific)."""
    print("\n1/3  A eliminar todas as tabelas (PostgreSQL)...")

    with engine_sync.connect() as conn:
        conn.execute(text("SET session_replication_role = replica;"))
        conn.commit()

        result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        tables = [row[0] for row in result.fetchall()]

        for table in tables:
            try:
                conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE;'))
                conn.commit()
                print(f"   + {table}")
            except Exception as exc:
                conn.rollback()
                print(f"   x Erro ao dropar {table}: {str(exc)[:80]}")

        # Limpar tipos ENUM órfãos para evitar conflito em migrations Alembic.
        enum_result = conn.execute(text(
            """
            SELECT t.typname
            FROM pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = 'public' AND t.typtype = 'e'
            """
        ))
        enum_types = [row[0] for row in enum_result.fetchall()]

        for enum_name in enum_types:
            try:
                conn.execute(text(f'DROP TYPE IF EXISTS "{enum_name}" CASCADE;'))
                conn.commit()
                print(f"   + enum {enum_name}")
            except Exception as exc:
                conn.rollback()
                print(f"   x Erro ao dropar enum {enum_name}: {str(exc)[:80]}")

        try:
            conn.execute(text("SET session_replication_role = DEFAULT;"))
            conn.commit()
        except Exception:
            conn.rollback()

    print("   Todas as tabelas eliminadas!")


def create_tables():
    """Cria tabelas pelo metadata atual do modelo.

    Nota operacional:
    o schema de runtime do projeto está alinhado ao ORM atual usado pela aplicação
    e pelos testes de regressão. Mantemos create_all aqui para garantir seed
    consistente com o servidor em execução.
    """
    print("\n2/3  A criar tabelas novas (metadata atual)...")
    Base.metadata.create_all(bind=engine_sync)
    print("   Tabelas criadas com sucesso!")


def _create_timeslots(db, org_id: int):
    """Grelha horária padrão: Seg-Sex, 08:30-17:30 (9 blocos)."""
    ts_map = {}
    slot_start_hour = 8
    slot_start_min = 30
    slots_per_day = 9

    for day in range(5):
        for i in range(slots_per_day):
            h = slot_start_hour + i
            start_time = datetime.time(h, slot_start_min)
            end_time = datetime.time(h + 1, slot_start_min)
            ts = models.Timeslot(
                day_of_week=day,
                start_time=start_time,
                end_time=end_time,
                organization_id=org_id,
            )
            db.add(ts)
            ts_map[(day, h)] = ts

    db.flush()
    for key in ts_map:
        db.refresh(ts_map[key])
    return ts_map


def _seed_teacher_availability(db, teacher_objs: list[models.Teacher], ts_map: dict):
    """Cumpre preflight: todos os professores com disponibilidade declarada."""
    count = 0
    for teacher in teacher_objs:
        for ts in ts_map.values():
            score = PreferenceLevel.NEUTRAL.value
            if ts.day_of_week == 2 and ts.start_time.hour in (8, 9):
                score = PreferenceLevel.AVOID.value
            db.add(models.Availability(
                teacher_id=teacher.id,
                timeslot_id=ts.id,
                score=score,
            ))
            count += 1
    return count


def _room_type_for_subject(index: int) -> RoomType:
    return ROOM_TYPE_CYCLE[index % len(ROOM_TYPE_CYCLE)]


def _discipline_name_for_index(index: int) -> str:
    if 1 <= index <= len(DISCIPLINE_CATALOG):
        return DISCIPLINE_CATALOG[index - 1]
    return f"Disciplina_{index:02d}"


def _module_progress_for_grade(grade_level: int, module_order: int, seed_value: int) -> tuple[int, bool]:
    _ = (grade_level, module_order, seed_value)
    return (0, False)


def _module_count_for_subject(subject_seq: int, class_counter: int) -> int:
    span = MODULES_PER_SUBJECT_MAX - MODULES_PER_SUBJECT_MIN + 1
    return MODULES_PER_SUBJECT_MIN + ((subject_seq + class_counter) % span)


def _subject_count_for_class(class_counter: int) -> int:
    span = SUBJECTS_PER_CLASS_MAX - SUBJECTS_PER_CLASS_MIN + 1
    return SUBJECTS_PER_CLASS_MIN + (class_counter % span)


def _module_hours_for_subject(subject_seq: int, module_order: int, class_counter: int) -> int:
    span = MODULE_HOURS_MAX - MODULE_HOURS_MIN + 1
    return MODULE_HOURS_MIN + ((subject_seq + module_order + class_counter) % span)


def _seed_subject_bundle_for_class(
    db,
    org,
    course,
    klass,
    teacher_pools: dict[int, list[models.Teacher]],
    class_counter: int,
    subject_seq: int,
    counters: dict,
) -> int:
    subject_count = _subject_count_for_class(class_counter)
    for subject_index in range(1, subject_count + 1):
        discipline_name = _discipline_name_for_index(subject_index)
        subject_name = f"{discipline_name} U{subject_seq:04d}"
        subject_code = f"D{subject_index:02d}S{subject_seq:04d}"
        room_type = _room_type_for_subject(subject_seq)
        subject_teacher_pool = teacher_pools[subject_index]
        assigned_teacher = subject_teacher_pool[(class_counter - 1) % len(subject_teacher_pool)]

        subject = models.Subject(
            name=subject_name,
            required_room_type=room_type,
            organization_id=org.id,
        )
        db.add(subject)
        db.flush()
        counters["subjects"] += 1

        subject.courses.append(course)
        subject.teachers.append(assigned_teacher)

        db.add(models.ClassSubjectLink(
            class_id=klass.id,
            subject_id=subject.id,
            grade_level=klass.grade_level,
            teacher_id=assigned_teacher.id,
        ))
        counters["links"] += 1

        db.add(models.Lesson(
            teacher_id=assigned_teacher.id,
            subject_id=subject.id,
            class_id=klass.id,
            organization_id=org.id,
        ))
        counters["lessons"] += 1

        module_count = _module_count_for_subject(subject_seq, class_counter)
        for module_order in range(1, module_count + 1):
            module_hours = _module_hours_for_subject(subject_seq, module_order, class_counter)
            module = models.Module(
                name=f"Modulo {subject_code}-{module_order}",
                code=f"{subject_code}M{module_order}",
                hours_total=module_hours,
                order=module_order,
                subject_id=subject.id,
            )
            db.add(module)
            db.flush()
            counters["modules"] += 1

            variation_seed = (klass.id * 37) + (subject_seq * 11) + module_order
            hours_completed, is_completed = _module_progress_for_grade(
                klass.grade_level,
                module_order,
                variation_seed,
            )

            db.add(models.ClassProgress(
                class_id=klass.id,
                module_id=module.id,
                hours_completed=hours_completed,
                is_completed=is_completed,
            ))
            counters["progress"] += 1

        subject_seq += 1

    return subject_seq


def _seed_single_organization(db, org_idx: int, subject_seq: int, counters: dict) -> int:
    org = models.Organization(
        name=f"Escola Profissional Cluster {org_idx}",
        plan_status="active",
    )
    db.add(org)
    db.flush()
    counters["orgs"] += 1

    db.add(models.User(
        name=f"Admin Escola {org_idx}",
        email=f"admin{org_idx}@cluster.pt",
        hashed_password=hash_password("1234"),
        role=UserRole.admin,
        organization_id=org.id,
        is_active=True,
    ))

    db.add(models.OrganizationSettings(
        org_id=org.id,
        academic_year="2025/2026",
        school_start_date=ASSUMED_TODAY,
        school_target_end_date=SCHOOL_TARGET_END,
        school_hard_end_date=SCHOOL_HARD_END,
        repair_stability_window_days=14,
        region_code="11",
        lunch_window_start=datetime.time(12, 0),
        lunch_window_end=datetime.time(14, 0),
        lunch_min_duration_minutes=60,
    ))

    db.add(models.SchoolCalendarEvent(
        org_id=org.id,
        academic_year="2025/2026",
        name="Restauracao da Independencia",
        start_date=datetime.date(2025, 12, 1),
        end_date=datetime.date(2025, 12, 1),
        event_type=models.CalendarEventType.national_holiday,
        source=models.CalendarEventSource.auto,
    ))

    for room_tpl in ROOMS_TEMPLATE:
        db.add(models.Room(
            name=f"E{org_idx} {room_tpl['name']}",
            capacity=room_tpl["capacity"],
            type=room_tpl["type"],
            organization_id=org.id,
        ))

    db.flush()
    ts_map = _create_timeslots(db, org.id)

    teacher_pools: dict[int, list[models.Teacher]] = {}
    all_teachers: list[models.Teacher] = []
    for subject_index in range(1, SUBJECTS_PER_CLASS_MAX + 1):
        teacher_pools[subject_index] = []
        for pool_idx in range(1, TEACHERS_PER_SUBJECT_POOL + 1):
            teacher = models.Teacher(
                name=f"Prof E{org_idx} D{subject_index:02d} P{pool_idx:02d}",
                organization_id=org.id,
            )
            db.add(teacher)
            db.flush()

            db.add(models.User(
                name=f"Prof E{org_idx} D{subject_index:02d} P{pool_idx:02d}",
                email=f"prof.e{org_idx}.d{subject_index:02d}.{pool_idx:02d}@cluster.pt",
                hashed_password=hash_password("1234"),
                role=UserRole.teacher,
                teacher_id=teacher.id,
                organization_id=org.id,
                is_active=True,
            ))
            teacher_pools[subject_index].append(teacher)
            all_teachers.append(teacher)
            counters["teachers"] += 1

    counters["availability"] += _seed_teacher_availability(db, all_teachers, ts_map)

    class_counter = 0
    for course_idx in range(1, COURSES_PER_ORG + 1):
        course = models.Course(
            name=f"Curso E{org_idx}-{course_idx:02d}",
            abbreviation=f"E{org_idx}C{course_idx:02d}",
            organization_id=org.id,
        )
        db.add(course)
        db.flush()
        counters["courses"] += 1

        for class_tpl in CLASS_BLUEPRINTS:
            class_counter += 1
            klass = models.Class(
                name=f"E{org_idx} C{course_idx:02d} {class_tpl['suffix']}",
                size=class_tpl["size"],
                start_year=class_tpl["start"],
                end_year=class_tpl["end"],
                grade_level=class_tpl["grade"],
                course_id=course.id,
                organization_id=org.id,
            )
            db.add(klass)
            db.flush()
            counters["classes"] += 1

            subject_seq = _seed_subject_bundle_for_class(
                db,
                org,
                course,
                klass,
                teacher_pools,
                class_counter,
                subject_seq,
                counters,
            )

    db.commit()
    print(
        f"[OK] Escola {org_idx}: cursos={COURSES_PER_ORG}, "
        f"turmas={CLASSES_PER_ORG}, professores={TEACHERS_PER_ORG}"
    )
    return subject_seq


def _validate_seed_admin_credentials(db) -> None:
    """Valida consistência mínima dos logins admin seedados."""
    for org_idx in range(1, ORG_COUNT + 1):
        email = f"admin{org_idx}@cluster.pt"
        user = db.execute(
            text(
                """
                SELECT email, hashed_password, is_active
                FROM \"user\"
                WHERE email = :email
                """
            ),
            {"email": email},
        ).first()

        if user is None:
            raise RuntimeError(f"Login admin esperado não encontrado: {email}")

        hashed_password = str(user[1])
        is_active = bool(user[2])
        if not is_active:
            raise RuntimeError(f"Login admin inativo no seed: {email}")
        if not verify_password("1234", hashed_password):
            raise RuntimeError(f"Password seed inválida para admin: {email}")


# =====================================================================
#  SEED PRINCIPAL
# =====================================================================

def run_seed():
    """Preenche a BD com cenário alargado multi-escola para stress/control test."""
    db = SessionLocalSync()
    try:
        print("\n3/3  A preencher dados de teste (escala alargada)...\n")
        counters = {
            "orgs": 0,
            "teachers": 0,
            "courses": 0,
            "classes": 0,
            "subjects": 0,
            "modules": 0,
            "links": 0,
            "lessons": 0,
            "progress": 0,
            "availability": 0,
        }

        subject_seq = 1
        for org_idx in range(1, ORG_COUNT + 1):
            subject_seq = _seed_single_organization(db, org_idx, subject_seq, counters)

        _validate_seed_admin_credentials(db)

        print("\n" + "=" * 72)
        print("  RESUMO DO SEED (ESCALA ALARGADA)")
        print("=" * 72)
        print(f"  Dia de referência assumido: {ASSUMED_TODAY}")
        print(f"  Organizações:              {counters['orgs']}")
        print(f"  Professores:               {counters['teachers']}")
        print(f"  Cursos:                    {counters['courses']}")
        print(f"  Turmas:                    {counters['classes']}")
        print(f"  Disciplinas por turma:     {SUBJECTS_PER_CLASS_MIN}-{SUBJECTS_PER_CLASS_MAX}")
        print(f"  Módulos por disciplina:    {MODULES_PER_SUBJECT_MIN}-{MODULES_PER_SUBJECT_MAX}")
        print(f"  Horas por módulo:          {MODULE_HOURS_MIN}-{MODULE_HOURS_MAX}")
        print(f"  Rácio docente/turmas:      1/{TEACHER_CLASS_RATIO}")
        print(f"  Pools docentes/disciplina: {TEACHERS_PER_SUBJECT_POOL}")
        print(f"  Rácio salas/turmas:        1/{ROOMS_PER_CLASS_RATIO}")
        print(f"  Disciplinas (únicas):      {counters['subjects']}")
        print(f"  Módulos (únicos):          {counters['modules']}")
        print(f"  ClassSubjectLinks:         {counters['links']}")
        print(f"  Lessons:                   {counters['lessons']}")
        print(f"  Progress records:          {counters['progress']}")
        print(f"  Availabilities:            {counters['availability']}")
        print(f"  Salas por escola:          {len(ROOMS_TEMPLATE)} ({ROOMS_NORMAL_COUNT} normais, {ROOMS_LAB_COUNT} labs, {ROOMS_GYM_COUNT} EF)")
        print("=" * 72)

        print("\n  LOGINS PEDIDOS (1 admin + 1 professor por organização):")
        for org_idx in range(1, ORG_COUNT + 1):
            print(f"   Escola {org_idx} -> admin{org_idx}@cluster.pt / 1234")
            print(f"   Escola {org_idx} -> prof.e{org_idx}.d01.01@cluster.pt / 1234")
        print("\n  [OK] Credenciais admin seed validadas após carga")
        print("  [INFO] Após reset de schema, reinicie o serviço backend para limpar cache asyncpg.")

    except Exception as exc:
        print(f"\n[ERRO] Erro crítico no seed: {exc}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()
        print("\nSeed terminado.")


def main():
    print("=" * 72)
    print("  INICIALIZAÇÃO DE CENÁRIO ALARGADO (3 escolas, 30 cursos)")
    print("=" * 72)

    try:
        clean_database()
        create_tables()
        run_seed()

        print("\n" + "=" * 72)
        print("  BASE DE DADOS INICIALIZADA COM SUCESSO!")
        print("=" * 72)
    except Exception as exc:
        print(f"\n[ERRO] Erro crítico: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
