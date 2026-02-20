# Ficheiro: backend/seed_data.py
# Seed completo e realista para Ensino Profissional Português.
# Corre: docker compose exec backend python seed_data.py
import sys
import datetime
from sqlalchemy import text
from app.db.database import SessionLocalSync, engine_sync, Base
from app import models
from app.core.security import hash_password
from app.models import UserRole, PreferenceLevel, RoomType


# =====================================================================
#  CONSTANTES — Dados de seed centralizados
# =====================================================================

SCHOOL_NAME = "Escola Profissional de Tecnologia e Gestão"

# --- Professores (5) ---
TEACHERS = [
    {"name": "Ana Silva",       "email": "ana.silva@escola.pt",       "pass": "1234"},
    {"name": "Bruno Costa",     "email": "bruno.costa@escola.pt",     "pass": "1234"},
    {"name": "Carla Mendes",    "email": "carla.mendes@escola.pt",    "pass": "1234"},
    {"name": "Daniel Ferreira", "email": "daniel.ferreira@escola.pt", "pass": "1234"},
    {"name": "Eva Rodrigues",   "email": "eva.rodrigues@escola.pt",   "pass": "1234"},
]

# --- Salas (6, tipos variados) ---
ROOMS = [
    {"name": "Sala 101",                    "capacity": 30, "type": RoomType.normal},
    {"name": "Sala 102",                    "capacity": 28, "type": RoomType.normal},
    {"name": "Sala 103",                    "capacity": 26, "type": RoomType.normal},
    {"name": "Laboratório de Informática",  "capacity": 20, "type": RoomType.lab},
    {"name": "Laboratório de Multimédia",   "capacity": 18, "type": RoomType.lab},
    {"name": "Pavilhão Gimnodesportivo",    "capacity": 60, "type": RoomType.gym},
]

# --- Cursos (3) ---
COURSES = [
    {"name": "Técnico de Gestão e Programação de Sistemas Informáticos", "abbr": "TGPSI"},
    {"name": "Técnico de Multimédia",                                     "abbr": "TMM"},
    {"name": "Técnico de Apoio à Gestão Desportiva",                      "abbr": "TAGD"},
]

# --- Disciplinas + Módulos (3 disciplinas por curso × 3 módulos cada) ---
# Cada disciplina indica para que cursos pertence (índice do COURSES acima)
# e que tipo de sala necessita.
SUBJECTS = [
    # ========== TGPSI ==========
    {
        "name": "Programação e Sistemas de Informação",
        "room_type": RoomType.lab,
        "courses": [0],          # Só TGPSI
        "teachers": [0],         # Ana Silva
        "modules": [
            {"name": "Introdução à Programação",           "code": "PSI01", "hours": 36, "order": 1},
            {"name": "Mecanismos de Controlo de Execução",  "code": "PSI02", "hours": 36, "order": 2},
            {"name": "Programação por Objetos",             "code": "PSI03", "hours": 36, "order": 3},
        ],
    },
    {
        "name": "Redes de Comunicação",
        "room_type": RoomType.lab,
        "courses": [0],
        "teachers": [1],         # Bruno Costa
        "modules": [
            {"name": "Comunicação de Dados",     "code": "RC01", "hours": 27, "order": 1},
            {"name": "Redes de Computadores",    "code": "RC02", "hours": 36, "order": 2},
            {"name": "Redes de Área Alargada",   "code": "RC03", "hours": 27, "order": 3},
        ],
    },
    {
        "name": "Sistemas Operativos",
        "room_type": RoomType.lab,
        "courses": [0],
        "teachers": [1],         # Bruno Costa
        "modules": [
            {"name": "Instalação e Configuração de Sistemas Operativos", "code": "SO01", "hours": 24, "order": 1},
            {"name": "Administração de Redes Locais",                    "code": "SO02", "hours": 30, "order": 2},
            {"name": "Administração de Servidores",                      "code": "SO03", "hours": 30, "order": 3},
        ],
    },
    # ========== MULTIMÉDIA ==========
    {
        "name": "Design Multimédia",
        "room_type": RoomType.lab,
        "courses": [1],          # Só TMM
        "teachers": [2],         # Carla Mendes
        "modules": [
            {"name": "Teoria da Imagem e do Design", "code": "DM01", "hours": 25, "order": 1},
            {"name": "Design de Páginas Web",         "code": "DM02", "hours": 50, "order": 2},
            {"name": "Animação 2D",                   "code": "DM03", "hours": 50, "order": 3},
        ],
    },
    {
        "name": "Produção Audiovisual",
        "room_type": RoomType.lab,
        "courses": [1],
        "teachers": [2],         # Carla Mendes
        "modules": [
            {"name": "Captação de Imagem",   "code": "PA01", "hours": 25, "order": 1},
            {"name": "Edição de Vídeo",       "code": "PA02", "hours": 50, "order": 2},
            {"name": "Pós-Produção de Vídeo", "code": "PA03", "hours": 25, "order": 3},
        ],
    },
    {
        "name": "Técnicas de Multimédia",
        "room_type": RoomType.lab,
        "courses": [1],
        "teachers": [0],         # Ana Silva (polivalente)
        "modules": [
            {"name": "Imagem Vetorial",     "code": "TM01", "hours": 25, "order": 1},
            {"name": "Imagem Bitmap",        "code": "TM02", "hours": 25, "order": 2},
            {"name": "Publicação Digital",   "code": "TM03", "hours": 25, "order": 3},
        ],
    },
    # ========== GESTÃO DESPORTIVA ==========
    {
        "name": "Organização e Gestão do Desporto",
        "room_type": RoomType.normal,
        "courses": [2],          # Só TAGD
        "teachers": [3],         # Daniel Ferreira
        "modules": [
            {"name": "Sistema Desportivo Português",  "code": "OGD01", "hours": 50, "order": 1},
            {"name": "Gestão de Eventos Desportivos",  "code": "OGD02", "hours": 50, "order": 2},
            {"name": "Marketing Desportivo",           "code": "OGD03", "hours": 25, "order": 3},
        ],
    },
    {
        "name": "Práticas de Atividades Físicas",
        "room_type": RoomType.gym,
        "courses": [2],
        "teachers": [4],         # Eva Rodrigues
        "modules": [
            {"name": "Atletismo",           "code": "PAF01", "hours": 50, "order": 1},
            {"name": "Ginástica",            "code": "PAF02", "hours": 50, "order": 2},
            {"name": "Desportos Coletivos",  "code": "PAF03", "hours": 50, "order": 3},
        ],
    },
    {
        "name": "Psicologia do Desporto",
        "room_type": RoomType.normal,
        "courses": [2],
        "teachers": [3],         # Daniel Ferreira
        "modules": [
            {"name": "Introdução à Psicologia",   "code": "PD01", "hours": 25, "order": 1},
            {"name": "Motivação e Performance",     "code": "PD02", "hours": 25, "order": 2},
            {"name": "Dinâmica de Grupos",          "code": "PD03", "hours": 25, "order": 3},
        ],
    },
]

# --- Turmas (6 — 3 para TGPSI, 2 para TMM, 1 para TAGD) ---
CLASSES = [
    # TGPSI — 3 anos em simultâneo
    {"name": "TGPSI 25/28", "course_idx": 0, "grade": 10, "start": 2025, "end": 2028, "size": 26},
    {"name": "TGPSI 24/27", "course_idx": 0, "grade": 11, "start": 2024, "end": 2027, "size": 24},
    {"name": "TGPSI 23/26", "course_idx": 0, "grade": 12, "start": 2023, "end": 2026, "size": 22},
    # TMM — 2 anos
    {"name": "TMM 25/28",   "course_idx": 1, "grade": 10, "start": 2025, "end": 2028, "size": 25},
    {"name": "TMM 24/27",   "course_idx": 1, "grade": 11, "start": 2024, "end": 2027, "size": 23},
    # TAGD — 1 ano
    {"name": "TAGD 25/28",  "course_idx": 2, "grade": 10, "start": 2025, "end": 2028, "size": 28},
]

# --- Horas de progresso já dadas (turmas do 11º e 12º) ---
# Formato: (class_idx, subject_idx, module_order, hours_done, is_completed)
PROGRESS_OVERRIDES = [
    # TGPSI 24/27 (11º) — completaram M1, M2 a meio
    (1, 0, 1, 36, True),   # PSI M1 completo
    (1, 0, 2, 20, False),  # PSI M2 a meio
    (1, 1, 1, 27, True),   # RC M1 completo
    (1, 1, 2, 15, False),  # RC M2 a meio
    (1, 2, 1, 24, True),   # SO M1 completo
    (1, 2, 2, 10, False),  # SO M2 a meio
    # TGPSI 23/26 (12º) — mais avançados
    (2, 0, 1, 36, True),   # PSI M1 completo
    (2, 0, 2, 36, True),   # PSI M2 completo
    (2, 0, 3, 18, False),  # PSI M3 a meio
    (2, 1, 1, 27, True),   # RC M1 completo
    (2, 1, 2, 36, True),   # RC M2 completo
    (2, 1, 3, 10, False),  # RC M3 a meio
    (2, 2, 1, 24, True),   # SO M1 completo
    (2, 2, 2, 30, True),   # SO M2 completo
    (2, 2, 3, 15, False),  # SO M3 a meio
    # TMM 24/27 (11º)
    (4, 3, 1, 25, True),   # DM M1 completo
    (4, 3, 2, 30, False),  # DM M2 a meio
    (4, 4, 1, 25, True),   # PA M1 completo
    (4, 4, 2, 20, False),  # PA M2 a meio
    (4, 5, 1, 25, True),   # TM M1 completo
    (4, 5, 2, 10, False),  # TM M2 a meio
]


# =====================================================================
#  FUNÇÕES
# =====================================================================

def clean_database():
    """DROP todas as tabelas (POSTGRESQL-SPECIFIC)"""
    print("\n1/3  A eliminar todas as tabelas (PostgreSQL)...")

    with engine_sync.connect() as conn:
        conn.execute(text("SET session_replication_role = replica;"))
        conn.commit()

        result = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))
        tables = [row[0] for row in result.fetchall()]

        for table in tables:
            try:
                conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE;'))
                conn.commit()
                print(f"   + {table}")
            except Exception as e:
                conn.rollback()
                print(f"   x Erro ao dropar {table}: {str(e)[:80]}")

        try:
            conn.execute(text("SET session_replication_role = DEFAULT;"))
            conn.commit()
        except Exception:
            conn.rollback()

    print("   Todas as tabelas eliminadas!")


def create_tables():
    """CREATE tabelas a partir de models.py"""
    print("\n2/3  A criar tabelas novas...")
    Base.metadata.create_all(bind=engine_sync)
    print("   Todas as tabelas criadas!")


def run_seed():
    """Preenche a BD com dados realistas de Ensino Profissional."""
    db = SessionLocalSync()
    try:
        print("\n3/3  A preencher dados de teste...\n")

        # ==================================================
        # 1. ORGANIZAÇÃO
        # ==================================================
        org = models.Organization(name=SCHOOL_NAME, plan_status="active")
        db.add(org)
        db.commit()
        db.refresh(org)
        print(f"[OK] Organização: {org.name} (ID {org.id})")

        # ==================================================
        # 2. PROFESSORES + UTILIZADORES
        # ==================================================
        teacher_objs = []
        for t_data in TEACHERS:
            teacher = models.Teacher(name=t_data["name"], organization_id=org.id)
            db.add(teacher)
            db.flush()

            user = models.User(
                email=t_data["email"],
                hashed_password=hash_password(t_data["pass"]),
                role=UserRole.admin,
                organization_id=org.id,
                teacher_id=teacher.id,
                is_active=True,
            )
            db.add(user)
            teacher_objs.append(teacher)

        db.commit()
        for t in teacher_objs:
            db.refresh(t)
        print(f"[OK] {len(teacher_objs)} Professores + Utilizadores criados")

        # ==================================================
        # 3. SALAS
        # ==================================================
        room_objs = []
        for r_data in ROOMS:
            room = models.Room(
                name=r_data["name"],
                capacity=r_data["capacity"],
                type=r_data["type"],
                organization_id=org.id,
            )
            db.add(room)
            room_objs.append(room)
        db.commit()
        n_normal = sum(1 for r in ROOMS if r["type"] == RoomType.normal)
        n_lab = sum(1 for r in ROOMS if r["type"] == RoomType.lab)
        n_gym = sum(1 for r in ROOMS if r["type"] == RoomType.gym)
        print(f"[OK] {len(room_objs)} Salas ({n_normal} normais, {n_lab} labs, {n_gym} ginásio)")

        # ==================================================
        # 4. BLOCOS HORÁRIOS (Seg-Sex, 08:30 – 17:30)
        # ==================================================
        SLOT_START_HOUR = 8
        SLOT_START_MIN = 30
        SLOTS_PER_DAY = 9  # 08:30-09:30 … 16:30-17:30

        ts_map = {}  # (day, hour) -> Timeslot object
        count_slots = 0
        for day in range(5):
            for i in range(SLOTS_PER_DAY):
                h = SLOT_START_HOUR + i
                t_start = datetime.time(h, SLOT_START_MIN)
                t_end = datetime.time(h + 1, SLOT_START_MIN)
                ts = models.Timeslot(
                    day_of_week=day,
                    start_time=t_start,
                    end_time=t_end,
                    organization_id=org.id,
                )
                db.add(ts)
                ts_map[(day, h)] = ts
                count_slots += 1
        db.commit()
        for key in ts_map:
            db.refresh(ts_map[key])
        print(f"[OK] {count_slots} Blocos horários (Seg-Sex, "
              f"{SLOT_START_HOUR}:{SLOT_START_MIN:02d}-"
              f"{SLOT_START_HOUR + SLOTS_PER_DAY}:{SLOT_START_MIN:02d})")

        # ==================================================
        # 5. CURSOS
        # ==================================================
        course_objs = []
        for c_data in COURSES:
            course = models.Course(
                name=c_data["name"],
                abbreviation=c_data["abbr"],
                organization_id=org.id,
            )
            db.add(course)
            course_objs.append(course)
        db.commit()
        for c in course_objs:
            db.refresh(c)
        print(f"[OK] {len(course_objs)} Cursos: {', '.join(c['abbr'] for c in COURSES)}")

        # ==================================================
        # 6. DISCIPLINAS + MÓDULOS + LIGAÇÕES
        #    (course_subject_link + teacher_subject_link)
        # ==================================================
        subject_objs = []
        module_objs_by_subject = {}  # subject_idx -> [Module, ...]

        for s_idx, s_data in enumerate(SUBJECTS):
            subj = models.Subject(
                name=s_data["name"],
                required_room_type=s_data["room_type"],
                organization_id=org.id,
            )
            db.add(subj)
            db.flush()

            # Módulos
            mods = []
            for m_data in s_data["modules"]:
                mod = models.Module(
                    name=m_data["name"],
                    code=m_data["code"],
                    hours_total=m_data["hours"],
                    order=m_data["order"],
                    subject_id=subj.id,
                )
                db.add(mod)
                mods.append(mod)
            module_objs_by_subject[s_idx] = mods

            # Course <-> Subject
            for c_idx in s_data["courses"]:
                subj.courses.append(course_objs[c_idx])

            # Teacher <-> Subject (competência)
            for t_idx in s_data["teachers"]:
                subj.teachers.append(teacher_objs[t_idx])

            subject_objs.append(subj)

        db.commit()
        for s in subject_objs:
            db.refresh(s)
        for mods in module_objs_by_subject.values():
            for m in mods:
                db.refresh(m)

        total_modules = sum(len(m) for m in module_objs_by_subject.values())
        print(f"[OK] {len(subject_objs)} Disciplinas + {total_modules} Módulos")
        print(f"     Ligações curso-disciplina e professor-disciplina configuradas")

        # ==================================================
        # 7. TURMAS
        # ==================================================
        class_objs = []
        for cl_data in CLASSES:
            klass = models.Class(
                name=cl_data["name"],
                size=cl_data["size"],
                course_id=course_objs[cl_data["course_idx"]].id,
                grade_level=cl_data["grade"],
                start_year=cl_data["start"],
                end_year=cl_data["end"],
                organization_id=org.id,
            )
            db.add(klass)
            class_objs.append(klass)
        db.commit()
        for k in class_objs:
            db.refresh(k)
        print(f"[OK] {len(class_objs)} Turmas criadas")

        # ==================================================
        # 8. CLASS-SUBJECT LINKS (professor -> turma -> disciplina)
        # ==================================================
        csl_count = 0
        for cl_idx, cl_data in enumerate(CLASSES):
            course_idx = cl_data["course_idx"]
            for s_idx, s_data in enumerate(SUBJECTS):
                if course_idx in s_data["courses"]:
                    primary_teacher_idx = s_data["teachers"][0]
                    csl = models.ClassSubjectLink(
                        class_id=class_objs[cl_idx].id,
                        subject_id=subject_objs[s_idx].id,
                        grade_level=cl_data["grade"],
                        teacher_id=teacher_objs[primary_teacher_idx].id,
                    )
                    db.add(csl)
                    csl_count += 1
        db.commit()
        print(f"[OK] {csl_count} Atribuições professor-turma-disciplina")

        # ==================================================
        # 9. AULAS (Lessons)
        # ==================================================
        lesson_count = 0
        for cl_idx, cl_data in enumerate(CLASSES):
            course_idx = cl_data["course_idx"]
            for s_idx, s_data in enumerate(SUBJECTS):
                if course_idx in s_data["courses"]:
                    primary_teacher_idx = s_data["teachers"][0]
                    lesson = models.Lesson(
                        teacher_id=teacher_objs[primary_teacher_idx].id,
                        subject_id=subject_objs[s_idx].id,
                        class_id=class_objs[cl_idx].id,
                        organization_id=org.id,
                    )
                    db.add(lesson)
                    lesson_count += 1
        db.commit()
        print(f"[OK] {lesson_count} Aulas (Lessons)")

        # ==================================================
        # 10. PROGRESSO MODULAR
        # ==================================================
        progress_count = 0
        progress_map = {}  # (class_idx, subject_idx, module_order) -> ClassProgress

        for cl_idx, cl_data in enumerate(CLASSES):
            course_idx = cl_data["course_idx"]
            for s_idx, s_data in enumerate(SUBJECTS):
                if course_idx in s_data["courses"]:
                    for mod in module_objs_by_subject[s_idx]:
                        cp = models.ClassProgress(
                            class_id=class_objs[cl_idx].id,
                            module_id=mod.id,
                            hours_completed=0,
                            is_completed=False,
                        )
                        db.add(cp)
                        progress_map[(cl_idx, s_idx, mod.order)] = cp
                        progress_count += 1

        db.flush()

        # Aplicar horas já dadas
        overrides_applied = 0
        for cl_idx, s_idx, mod_order, hours, completed in PROGRESS_OVERRIDES:
            key = (cl_idx, s_idx, mod_order)
            if key in progress_map:
                progress_map[key].hours_completed = hours
                progress_map[key].is_completed = completed
                overrides_applied += 1

        db.commit()
        print(f"[OK] {progress_count} Registos de progresso "
              f"({overrides_applied} com horas pré-preenchidas)")

        # ==================================================
        # 11. DISPONIBILIDADES (padrão diferente por professor)
        # ==================================================
        avail_count = 0

        # Ana Silva (0): Indisponível segunda de manhã (formação externa)
        for h in [8, 9, 10, 11]:
            if (0, h) in ts_map:
                db.add(models.Availability(
                    teacher_id=teacher_objs[0].id,
                    timeslot_id=ts_map[(0, h)].id,
                    score=PreferenceLevel.IMPOSSIBLE.value,
                ))
                avail_count += 1

        # Bruno Costa (1): Prefere manhãs (score 2), evita sexta à tarde
        for day in range(5):
            for h in [8, 9, 10]:
                if (day, h) in ts_map:
                    db.add(models.Availability(
                        teacher_id=teacher_objs[1].id,
                        timeslot_id=ts_map[(day, h)].id,
                        score=PreferenceLevel.PREFERRED.value,
                    ))
                    avail_count += 1
        for h in [14, 15, 16]:
            if (4, h) in ts_map:
                db.add(models.Availability(
                    teacher_id=teacher_objs[1].id,
                    timeslot_id=ts_map[(4, h)].id,
                    score=PreferenceLevel.AVOID.value,
                ))
                avail_count += 1

        # Carla Mendes (2): Indisponível quarta inteira (dia de formação)
        for h in range(8, 17):
            if (2, h) in ts_map:
                db.add(models.Availability(
                    teacher_id=teacher_objs[2].id,
                    timeslot_id=ts_map[(2, h)].id,
                    score=PreferenceLevel.IMPOSSIBLE.value,
                ))
                avail_count += 1

        # Daniel Ferreira (3): Evita 1º tempo de cada dia
        for day in range(5):
            if (day, 8) in ts_map:
                db.add(models.Availability(
                    teacher_id=teacher_objs[3].id,
                    timeslot_id=ts_map[(day, 8)].id,
                    score=PreferenceLevel.AVOID.value,
                ))
                avail_count += 1

        # Eva Rodrigues (4): Prefere tardes (treinos)
        for day in range(5):
            for h in [14, 15, 16]:
                if (day, h) in ts_map:
                    db.add(models.Availability(
                        teacher_id=teacher_objs[4].id,
                        timeslot_id=ts_map[(day, h)].id,
                        score=PreferenceLevel.PREFERRED.value,
                    ))
                    avail_count += 1

        db.commit()
        print(f"[OK] {avail_count} Disponibilidades (5 padrões diferentes)")

        # ==================================================
        # RESUMO FINAL
        # ==================================================
        print("\n" + "=" * 60)
        print("  RESUMO DOS DADOS DE SEED")
        print("=" * 60)
        print(f"   Organização:  {SCHOOL_NAME}")
        print(f"   Professores:  {len(TEACHERS)}")
        print(f"   Salas:        {len(ROOMS)} ({n_normal} normais, {n_lab} labs, {n_gym} ginásio)")
        print(f"   Timeslots:    {count_slots} (Seg-Sex)")
        print(f"   Cursos:       {len(COURSES)}")
        print(f"   Disciplinas:  {len(SUBJECTS)}")
        print(f"   Módulos:      {total_modules}")
        print(f"   Turmas:       {len(CLASSES)}")
        print(f"   Atribuições:  {csl_count}")
        print(f"   Aulas:        {lesson_count}")
        print(f"   Progresso:    {progress_count} ({overrides_applied} com horas)")
        print(f"   Dispon.:      {avail_count}")
        print()
        print("  LOGINS DE TESTE:")
        for t in TEACHERS:
            print(f"   {t['email']} / {t['pass']}")
        print()
        print("  CURSOS E DISCIPLINAS:")
        for c_idx, c in enumerate(COURSES):
            course_subjects = [s["name"] for s in SUBJECTS if c_idx in s["courses"]]
            print(f"   {c['abbr']}: {c['name']}")
            for sn in course_subjects:
                print(f"     -- {sn}")

    except Exception as e:
        print(f"\n[ERRO] Erro Critico no Seed: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()
        print("\nSeed terminado.")


def main():
    """Orquestrador: Limpa -> Cria -> Popula"""
    print("=" * 60)
    print("  INICIALIZANDO BASE DE DADOS (PostgreSQL)")
    print(f"  Escola: {SCHOOL_NAME}")
    print("=" * 60)

    try:
        clean_database()
        create_tables()
        run_seed()

        print("\n" + "=" * 60)
        print("  BASE DE DADOS INICIALIZADA COM SUCESSO!")
        print("=" * 60)

    except Exception as e:
        print(f"\n[ERRO] ERRO CRITICO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
