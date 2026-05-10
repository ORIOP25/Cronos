# Ficheiro: backend/seed_data_small_realistic.py
# Seed manual realista em escala reduzida.
# Objetivo: testes manuais com nomes claros e dados completos do modelo.
# Entrada canonica recomendada:
#   docker compose exec backend python seed_data.py --profile small-realistic --reset
# Entrada direta (equivale ao comando canonico):
#   docker compose exec backend python seed_data_small_realistic.py
#
# ATENCAO: este script APAGA todos os dados existentes e recria a BD.
# Usa DROP SCHEMA + Alembic para garantir consistencia do estado de migracoes.

import datetime
import sys
import subprocess
from sqlalchemy import text

from app.db.database import SessionLocalSync, engine_sync
from app import models
from app.core.security import hash_password, verify_password
from app.models import UserRole, PreferenceLevel, RoomType


# =====================================================================
#  CONFIGURACAO DO CENARIO (ESCALA REDUZIDA E REALISTA)
# =====================================================================

ASSUMED_TODAY = datetime.date(2025, 9, 15)
SCHOOL_TARGET_END = datetime.date(2026, 6, 30)
SCHOOL_HARD_END = datetime.date(2026, 7, 31)
ACADEMIC_YEAR = "2025/2026"

ORGANIZATION_INFO = {
    "name": "Escola Profissional do Norte",
    "admin_name": "Ana Silva",
    "admin_email": "ana.silva@escola.pt",
    "admin_password": "1234",
}

COURSES = [
    {
        "name": "Tecnico de Gestao e Programacao de Sistemas Informaticos",
        "abbreviation": "TGPSI",
    },
    {
        "name": "Tecnico de Apoio a Gestao",
        "abbreviation": "TAG",
    },
    {
        "name": "Tecnico de Desporto",
        "abbreviation": "TDESP",
    },
]

CLASS_BLUEPRINTS = [
    {"grade": 10, "start": 2025, "end": 2028, "label": "10A", "size": 26},
    {"grade": 11, "start": 2024, "end": 2027, "label": "11A", "size": 24},
    {"grade": 12, "start": 2023, "end": 2026, "label": "12A", "size": 22},
]

ROOMS_TEMPLATE = [
    {"name": "Sala 101", "capacity": 28, "type": RoomType.normal},
    {"name": "Sala 102", "capacity": 28, "type": RoomType.normal},
    {"name": "Sala 201", "capacity": 30, "type": RoomType.normal},
    {"name": "Sala 202", "capacity": 30, "type": RoomType.normal},
    {"name": "Sala Multiusos", "capacity": 32, "type": RoomType.normal},
    {"name": "Laboratorio Informatica 1", "capacity": 24, "type": RoomType.lab},
    {"name": "Laboratorio Informatica 2", "capacity": 24, "type": RoomType.lab},
    {"name": "Laboratorio Redes", "capacity": 22, "type": RoomType.lab},
    {"name": "Pavilhao Desportivo", "capacity": 60, "type": RoomType.gym},
]

SUBJECT_DEFINITIONS = {
    "portugues": {"name": "Portugues", "room_type": RoomType.normal},
    "ingles": {"name": "Ingles", "room_type": RoomType.normal},
    "matematica": {"name": "Matematica", "room_type": RoomType.normal},
    "area_integracao": {"name": "Area de Integracao", "room_type": RoomType.normal},
    "programacao": {"name": "Programacao", "room_type": RoomType.lab},
    "redes": {"name": "Redes", "room_type": RoomType.lab},
    "sistemas_operativos": {"name": "Sistemas Operativos", "room_type": RoomType.lab},
    "economia": {"name": "Economia", "room_type": RoomType.normal},
    "contabilidade": {"name": "Contabilidade", "room_type": RoomType.normal},
    "gestao": {"name": "Gestao", "room_type": RoomType.normal},
    "direito": {"name": "Direito", "room_type": RoomType.normal},
    "teoria_desporto": {"name": "Teoria do Desporto", "room_type": RoomType.normal},
    "anatomia": {"name": "Anatomia e Fisiologia", "room_type": RoomType.normal},
    "modalidades": {"name": "Modalidades Coletivas", "room_type": RoomType.gym},
    "treino_desportivo": {"name": "Treino Desportivo", "room_type": RoomType.gym},
    "educacao_fisica": {"name": "Educacao Fisica", "room_type": RoomType.gym},
}

COURSE_CURRICULA = {
    "TGPSI": [
        "portugues",
        "ingles",
        "matematica",
        "area_integracao",
        "programacao",
        "redes",
        "sistemas_operativos",
        "educacao_fisica",
    ],
    "TAG": [
        "portugues",
        "ingles",
        "matematica",
        "area_integracao",
        "economia",
        "contabilidade",
        "gestao",
        "direito",
        "educacao_fisica",
    ],
    "TDESP": [
        "portugues",
        "ingles",
        "matematica",
        "area_integracao",
        "teoria_desporto",
        "anatomia",
        "modalidades",
        "treino_desportivo",
    ],
}

TEACHER_PROFILES = [
    {"name": "Ana Matos", "email": "ana.matos@epnorte.pt", "subjects": ["portugues"]},
    {"name": "Bruno Costa", "email": "bruno.costa@epnorte.pt", "subjects": ["ingles"]},
    {"name": "Carla Sousa", "email": "carla.sousa@epnorte.pt", "subjects": ["matematica"]},
    {"name": "Diana Moreira", "email": "diana.moreira@epnorte.pt", "subjects": ["area_integracao", "direito"]},
    {"name": "Eduardo Pires", "email": "eduardo.pires@epnorte.pt", "subjects": ["programacao", "sistemas_operativos"]},
    {"name": "Filipa Neves", "email": "filipa.neves@epnorte.pt", "subjects": ["redes", "programacao"]},
    {"name": "Goncalo Freitas", "email": "goncalo.freitas@epnorte.pt", "subjects": ["economia", "gestao"]},
    {"name": "Helena Teixeira", "email": "helena.teixeira@epnorte.pt", "subjects": ["contabilidade"]},
    {"name": "Ines Nunes", "email": "ines.nunes@epnorte.pt", "subjects": ["educacao_fisica", "modalidades", "treino_desportivo"]},
    {"name": "Joao Ribeiro", "email": "joao.ribeiro@epnorte.pt", "subjects": ["anatomia", "teoria_desporto"]},
]

MODULE_TEMPLATES = [
    ("Fundamentos", 30),
    ("Aplicacao Pratica", 30),
    ("Projeto", 35),
    ("Consolidacao", 25),
]


# =====================================================================
#  UTILITARIOS
# =====================================================================

def _create_timeslots(db, organization_id: int) -> dict[tuple[int, int], models.Timeslot]:
    """Grelha padrao: Seg-Sex, 08:30-16:30 (8 blocos)."""
    ts_map: dict[tuple[int, int], models.Timeslot] = {}
    for day in range(5):
        for hour in range(8, 16):
            timeslot = models.Timeslot(
                day_of_week=day,
                start_time=datetime.time(hour, 30),
                end_time=datetime.time(hour + 1, 30),
                organization_id=organization_id,
            )
            db.add(timeslot)
            ts_map[(day, hour)] = timeslot

    db.flush()
    for key in ts_map:
        db.refresh(ts_map[key])
    return ts_map


def _availability_score(teacher_idx: int, day_of_week: int, start_hour: int) -> int:
    """Padrao simples e legivel para preferencia de disponibilidade."""
    score = PreferenceLevel.NEUTRAL.value

    if day_of_week == 0 and start_hour == 8:
        score = PreferenceLevel.AVOID.value

    if teacher_idx % 4 == 0 and day_of_week == 4 and start_hour >= 14:
        score = PreferenceLevel.IMPOSSIBLE.value

    return score


def _seed_teacher_availability(db, teacher_objs: list[models.Teacher], ts_map: dict[tuple[int, int], models.Timeslot]) -> int:
    count = 0
    for teacher_idx, teacher in enumerate(teacher_objs, start=1):
        for timeslot in ts_map.values():
            db.add(models.Availability(
                teacher_id=teacher.id,
                timeslot_id=timeslot.id,
                score=_availability_score(teacher_idx, timeslot.day_of_week, timeslot.start_time.hour),
            ))
            count += 1
    return count


def _subject_code(subject_key: str) -> str:
    compact = "".join(ch for ch in subject_key.upper() if ch.isalnum())
    return compact[:8]


def _progress_for_grade(grade_level: int, module_order: int, hours_total: int) -> tuple[float, bool]:
    if grade_level == 10:
        return 0.0, False

    if grade_level == 11:
        if module_order == 1:
            return float(hours_total), True
        if module_order == 2:
            return float(max(1, int(hours_total * 0.6))), False
        return 0.0, False

    if module_order in (1, 2):
        return float(hours_total), True
    if module_order == 3:
        return float(max(1, int(hours_total * 0.8))), False
    return 0.0, False


def _ensure_curricula_consistency() -> None:
    for course in COURSES:
        abbreviation = course["abbreviation"]
        if abbreviation not in COURSE_CURRICULA:
            raise RuntimeError(f"Curriculo em falta para curso: {abbreviation}")

    all_subject_keys = {
        subject_key
        for curriculum in COURSE_CURRICULA.values()
        for subject_key in curriculum
    }

    missing_subject_defs = [key for key in sorted(all_subject_keys) if key not in SUBJECT_DEFINITIONS]
    if missing_subject_defs:
        raise RuntimeError(f"Subject definition em falta: {missing_subject_defs}")

    teacher_coverage: dict[str, int] = {key: 0 for key in all_subject_keys}
    for profile in TEACHER_PROFILES:
        for subject_key in profile["subjects"]:
            if subject_key in teacher_coverage:
                teacher_coverage[subject_key] += 1

    missing_teacher = [key for key, count in teacher_coverage.items() if count == 0]
    if missing_teacher:
        raise RuntimeError(f"Sem professor para disciplinas: {missing_teacher}")


def _validate_seed_credentials(db) -> None:
    admin_email = ORGANIZATION_INFO["admin_email"]
    admin = db.execute(
        text(
            """
            SELECT email, hashed_password, is_active
            FROM "user"
            WHERE email = :email
            """
        ),
        {"email": admin_email},
    ).first()

    if admin is None:
        raise RuntimeError(f"Login admin esperado nao encontrado: {admin_email}")

    if not bool(admin[2]):
        raise RuntimeError(f"Login admin inativo: {admin_email}")

    if not verify_password(ORGANIZATION_INFO["admin_password"], str(admin[1])):
        raise RuntimeError(f"Password seed invalida para admin: {admin_email}")


def _create_base_entities(db) -> tuple[models.Organization, dict[tuple[int, int], models.Timeslot]]:
    organization = models.Organization(
        name=ORGANIZATION_INFO["name"],
        plan_status="active",
    )
    db.add(organization)
    db.flush()

    db.add(models.User(
        name=ORGANIZATION_INFO["admin_name"],
        email=ORGANIZATION_INFO["admin_email"],
        hashed_password=hash_password(ORGANIZATION_INFO["admin_password"]),
        role=UserRole.admin,
        organization_id=organization.id,
        is_active=True,
    ))

    db.add(models.OrganizationSettings(
        organization_id=organization.id,
        school_start_date=ASSUMED_TODAY,
        school_target_end_date=SCHOOL_TARGET_END,
        school_hard_end_date=SCHOOL_HARD_END,
        repair_stability_window_days=1,
    ))

    db.add(models.OrganizationGridSettings(
        organization_id=organization.id,
        lunch_window_start=datetime.time(12, 30),
        lunch_window_end=datetime.time(14, 0),
        lunch_min_duration_minutes=60,
    ))

    db.add(models.SchoolCalendarEvent(
        organization_id=organization.id,
        name="Dia da Restauracao da Independencia",
        start_date=datetime.date(2025, 12, 1),
        end_date=datetime.date(2025, 12, 1),
        event_type=models.CalendarEventType.national_holiday,
        source=models.CalendarEventSource.auto,
    ))

    for room_tpl in ROOMS_TEMPLATE:
        db.add(models.Room(
            name=room_tpl["name"],
            capacity=room_tpl["capacity"],
            type=room_tpl["type"],
            organization_id=organization.id,
        ))

    db.flush()
    timeslots = _create_timeslots(db, organization.id)
    return organization, timeslots


def run_seed() -> None:
    """Carga completa com 1 organizacao e 3 cursos completos (10/11/12)."""
    db = SessionLocalSync()
    try:
        print("\n3/3  A preencher dados de teste (escala reduzida e realista)...\n")
        _ensure_curricula_consistency()

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
            "rooms": 0,
            "timeslots": 0,
        }

        organization, ts_map = _create_base_entities(db)
        counters["orgs"] = 1
        counters["rooms"] = len(ROOMS_TEMPLATE)
        counters["timeslots"] = len(ts_map)

        teacher_by_email: dict[str, models.Teacher] = {}
        subject_teacher_pool: dict[str, list[models.Teacher]] = {
            key: [] for key in SUBJECT_DEFINITIONS
        }

        for profile in TEACHER_PROFILES:
            teacher = models.Teacher(
                name=profile["name"],
                organization_id=organization.id,
            )
            db.add(teacher)
            db.flush()

            db.add(models.User(
                name=profile["name"],
                email=profile["email"],
                hashed_password=hash_password("1234"),
                role=UserRole.teacher,
                teacher_id=teacher.id,
                organization_id=organization.id,
                is_active=True,
            ))

            teacher_by_email[profile["email"]] = teacher
            counters["teachers"] += 1

            for subject_key in profile["subjects"]:
                subject_teacher_pool[subject_key].append(teacher)

        db.flush()
        all_teachers = list(teacher_by_email.values())
        counters["availability"] = _seed_teacher_availability(db, all_teachers, ts_map)

        course_by_abbreviation: dict[str, models.Course] = {}
        for course_data in COURSES:
            course = models.Course(
                name=course_data["name"],
                abbreviation=course_data["abbreviation"],
                organization_id=organization.id,
            )
            db.add(course)
            db.flush()
            course_by_abbreviation[course.abbreviation] = course
            counters["courses"] += 1

        used_subject_keys = sorted({
            subject_key
            for curriculum in COURSE_CURRICULA.values()
            for subject_key in curriculum
        })

        subject_by_key: dict[str, models.Subject] = {}
        modules_by_subject_id: dict[int, list[models.Module]] = {}

        for subject_key in used_subject_keys:
            subject_info = SUBJECT_DEFINITIONS[subject_key]
            subject = models.Subject(
                name=subject_info["name"],
                required_room_type=subject_info["room_type"],
                organization_id=organization.id,
            )
            db.add(subject)
            db.flush()
            subject_by_key[subject_key] = subject
            counters["subjects"] += 1

            code_prefix = _subject_code(subject_key)
            subject_modules: list[models.Module] = []
            for order, (module_label, module_hours) in enumerate(MODULE_TEMPLATES, start=1):
                module = models.Module(
                    name=f"{subject_info['name']} - {module_label}",
                    code=f"{code_prefix}M{order}",
                    hours_total=module_hours,
                    order=order,
                    subject_id=subject.id,
                )
                db.add(module)
                db.flush()
                subject_modules.append(module)
                counters["modules"] += 1

            modules_by_subject_id[subject.id] = subject_modules

        for course_abbreviation, curriculum_keys in COURSE_CURRICULA.items():
            course = course_by_abbreviation[course_abbreviation]

            for subject_key in curriculum_keys:
                subject = subject_by_key[subject_key]
                if subject not in course.subjects:
                    course.subjects.append(subject)

                for teacher in subject_teacher_pool[subject_key]:
                    if teacher not in subject.teachers:
                        subject.teachers.append(teacher)

            db.flush()

            course_classes: list[models.Class] = []
            for class_tpl in CLASS_BLUEPRINTS:
                klass = models.Class(
                    name=f"{class_tpl['label']} {course_abbreviation}",
                    size=class_tpl["size"],
                    start_year=class_tpl["start"],
                    end_year=class_tpl["end"],
                    grade_level=class_tpl["grade"],
                    course_id=course.id,
                    organization_id=organization.id,
                )
                db.add(klass)
                db.flush()
                course_classes.append(klass)
                counters["classes"] += 1

            for class_index, klass in enumerate(course_classes):
                for subject_key in curriculum_keys:
                    subject = subject_by_key[subject_key]
                    teacher_pool = subject_teacher_pool[subject_key]
                    assigned_teacher = teacher_pool[class_index % len(teacher_pool)]

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
                        organization_id=organization.id,
                    ))
                    counters["lessons"] += 1

                    for module in modules_by_subject_id[subject.id]:
                        hours_completed, is_completed = _progress_for_grade(
                            klass.grade_level,
                            module.order,
                            module.hours_total,
                        )
                        db.add(models.ClassProgress(
                            class_id=klass.id,
                            module_id=module.id,
                            hours_completed=hours_completed,
                            hours_debt=0.0,
                            is_completed=is_completed,
                        ))
                        counters["progress"] += 1

        db.commit()
        _validate_seed_credentials(db)

        print("\n" + "=" * 72)
        print("  RESUMO DO SEED (ESCALA REDUZIDA E REALISTA)")
        print("=" * 72)
        print(f"  Organizacoes:              {counters['orgs']}")
        print(f"  Cursos:                    {counters['courses']}")
        print(f"  Turmas:                    {counters['classes']} (3 cursos x 3 anos)")
        print(f"  Professores:               {counters['teachers']}")
        print(f"  Salas:                     {counters['rooms']}")
        print(f"  Blocos horarios:           {counters['timeslots']}")
        print(f"  Disciplinas (unicas):      {counters['subjects']}")
        print(f"  Modulos (unicos):          {counters['modules']}")
        print(f"  ClassSubjectLinks:         {counters['links']}")
        print(f"  Lessons:                   {counters['lessons']}")
        print(f"  Progress records:          {counters['progress']}")
        print(f"  Availabilities:            {counters['availability']}")
        print("=" * 72)

        print("\n  LOGINS PRINCIPAIS:")
        print(f"   Admin -> {ORGANIZATION_INFO['admin_email']} / {ORGANIZATION_INFO['admin_password']}")
        print("   Professor -> ana.matos@epnorte.pt / 1234")
        print("   Professor -> eduardo.pires@epnorte.pt / 1234")

        print("\n  [OK] Credenciais admin validadas apos carga")
        print("  [INFO] Seed preparado para testes manuais de operacao e navegacao")

    except Exception as exc:
        print(f"\n[ERRO] Erro critico no seed: {exc}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()
        print("\nSeed terminado.")


def main() -> None:
    print("=" * 72)
    print("  SMALL-REALISTIC SEED (via Alembic)")
    print("  ATENCAO: todos os dados existentes serao APAGADOS!")
    print("=" * 72)

    try:
        print("\n1/3  A resetar base de dados (DROP SCHEMA public)...")
        with engine_sync.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
            conn.commit()
        print("   Schema public recriado com sucesso!")

        print("\n2/3  A executar migracoes Alembic...")
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        print("   Migracoes concluidas!")

        run_seed()

        print("\n" + "=" * 72)
        print("  BASE DE DADOS INICIALIZADA COM SUCESSO!")
        print("=" * 72)
    except Exception as exc:
        print(f"\n[ERRO] Erro critico: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
