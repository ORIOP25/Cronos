# Ficheiro: backend/seed_data.py
"""
Script TUDO-EM-UM: Limpa BD + Recria tabelas + Popula dados de teste
Usa: python seed_data.py (com venv já ativado)

🔒 POSTGRESQL-EXCLUSIVE: Este script é optimizado APENAS para PostgreSQL.
Sem código agnóstico, sem compatibilidade SQLite. Pure Postgres.

Este ficheiro é a FONTE DE VERDADE para inicializar a BD.
Sem ficheiros auxiliares, sem redundância - KISS principle.
"""
import sys
import datetime
from sqlalchemy import text
from app.db.database import SessionLocalSync, engine_sync, Base
from app import models
from app.core.security import hash_password
from app.models import UserRole, PreferenceLevel


def clean_database():
    """🗑️  DROP todas as tabelas (POSTGRESQL-SPECIFIC)"""
    print("\n1️⃣  A eliminar todas as tabelas (PostgreSQL)...")
    
    # PostgreSQL: SEPARATE CONNECTION para DROP (não usa transaction)
    with engine_sync.connect() as connection:
        # PostgreSQL: Desabilitar constraints de FK temporariamente
        connection.execute(text("SET session_replication_role = replica;"))
        connection.commit()
        
        # Obter todas as tabelas (POSTGRESQL - schema 'public')
        result = connection.execute(text("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
        """))
        tables = [row[0] for row in result.fetchall()]
        
        # DROP each table with proper quoting for reserved keywords
        for table in tables:
            try:
                # PostgreSQL: Quoted identifier para reserved keywords
                # Exemplo: "user", "constraint"
                connection.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE;'))
                connection.commit()
                print(f"   ✓ {table}")
            except Exception as e:
                # Rollback failed statement, continue with next table
                connection.rollback()
                print(f"   ✗ Erro ao dropar {table}: {str(e)[:80]}")
        
        # Re-abilitar constraints
        try:
            connection.execute(text("SET session_replication_role = DEFAULT;"))
            connection.commit()
        except Exception as e:
            connection.rollback()
            print(f"   ⚠️ Erro ao restaurar constraints: {e}")
    
    print("   ✓ Todas as tabelas eliminadas!")


def create_tables():
    """🏗️  CREATE tabelas baseado em models.py (fase 2)"""
    print("\n2️⃣  A criar tabelas novas...")
    Base.metadata.create_all(bind=engine_sync)
    print("   ✓ Todas as tabelas criadas!")


def run_seed():
    """🌱 SEED dados de teste (fase 3)"""
    db = SessionLocalSync()
    try:
        print("\n3️⃣  A preencher dados de teste...")

        # ==========================================
        # 1. ORGANIZAÇÃO (A Escola)
        # ==========================================
        org = db.query(models.Organization).filter_by(name="Escola Exemplo").first()
        if not org:
            org = models.Organization(name="Escola Exemplo", plan_status="active")
            db.add(org)
            db.commit()
            db.refresh(org)
            print(f"✅ Organização criada: {org.name} (ID: {org.id})")
        else:
            print(f"ℹ️ Usando organização existente: {org.name}")
        
        org_id = org.id

        # ==========================================
        # 2. PROFESSORES & UTILIZADORES (Auth)
        # ==========================================
        professores_data = [
            {"name": "Prof. Pardal", "email": "pardal@escola.com", "pass": "1234"},
            {"name": "Prof. Girafales", "email": "girafales@escola.com", "pass": "1234"}
        ]

        for p_data in professores_data:
            # 2.1 Criar o Recurso Professor
            teacher = db.query(models.Teacher).filter_by(name=p_data["name"], organization_id=org_id).first()
            if not teacher:
                teacher = models.Teacher(name=p_data["name"], organization_id=org_id)
                db.add(teacher)
                db.commit()
                db.refresh(teacher)

            # 2.2 Criar o Login (User)
            user = db.query(models.User).filter_by(email=p_data["email"]).first()
            if not user:
                user = models.User(
                    email=p_data["email"],
                    hashed_password=hash_password(p_data["pass"]),
                    role=UserRole.admin,
                    organization_id=org_id,
                    teacher_id=teacher.id,
                    is_active=True  # ✅ EXPLÍCITO: garantir que está ativo
                )
                db.add(user)
                db.commit()
                print(f"✅ Professor/User criado: {p_data['name']} ({p_data['email']})")

        # ==========================================
        # 3. SALAS (Rooms)
        # ==========================================
        salas_data = [
            {"name": "Sala 101 (Teórica)", "capacity": 30},
            {"name": "Lab. Ciências", "capacity": 20},
            {"name": "Pavilhão Gimnodesportivo", "capacity": 50}
        ]

        for s_data in salas_data:
            sala = db.query(models.Room).filter_by(name=s_data["name"], organization_id=org_id).first()
            if not sala:
                sala = models.Room(name=s_data["name"], capacity=s_data["capacity"], organization_id=org_id)
                db.add(sala)
                db.commit()
        print("✅ Salas criadas.")

        # ==========================================
        # 4. BLOCOS HORÁRIOS (Timeslots)
        # ==========================================
        start_hour = 8
        start_min = 30
        
        count_slots = 0
        for day in range(5):
            for i in range(9):
                h_start = start_hour + i
                h_end = h_start + 1
                
                t_start = datetime.time(h_start, start_min)
                t_end = datetime.time(h_end, start_min)
                
                exists = db.query(models.Timeslot).filter_by(
                    day_of_week=day, 
                    start_time=t_start, 
                    organization_id=org_id
                ).first()
                
                if not exists:
                    ts = models.Timeslot(
                        day_of_week=day,
                        start_time=t_start,
                        end_time=t_end,
                        organization_id=org_id
                    )
                    db.add(ts)
                    count_slots += 1
        db.commit()
        print(f"✅ {count_slots} novos blocos horários gerados.")

        # ==========================================
        # 5. CURSOS (Courses) - COM CICLOS
        # ==========================================
        course = db.query(models.Course).filter_by(name="Técnico em Informática", organization_id=org_id).first()
        if not course:
            course = models.Course(
                name="Técnico em Informática",
                abbreviation="TI",
                organization_id=org_id
            )
            db.add(course)
            db.commit()
            db.refresh(course)
            print(f"✅ Curso criado: {course.name} ({course.abbreviation})")
        
        # ==========================================
        # 6. TURMAS (Classes)
        # ==========================================
        turmas_para_criar = [
            {"name": "TI 25/28", "grade": 10, "start": 2025, "end": 2028, "size": 25},
            {"name": "TI 24/27", "grade": 11, "start": 2024, "end": 2027, "size": 24},
            {"name": "TI 23/26", "grade": 12, "start": 2023, "end": 2026, "size": 23},
        ]
        
        for turma_data in turmas_para_criar:
            t = db.query(models.Class).filter_by(
                name=turma_data["name"],
                organization_id=org_id,
                course_id=course.id
            ).first()
            if not t:
                t = models.Class(
                    name=turma_data["name"],
                    size=turma_data["size"],
                    course_id=course.id,
                    grade_level=turma_data["grade"],
                    start_year=turma_data["start"],
                    end_year=turma_data["end"],
                    organization_id=org_id
                )
                db.add(t)
                db.commit()
        print("✅ Turmas criadas (com ciclos).")

        # ==========================================
        # 7. DISCIPLINAS (Subjects) COM MÓDULOS
        # ==========================================
        disciplinas_data = [
            {
                "name": "Matemática",
                "modules": [
                    {"name": "Álgebra", "hours": 30, "code": "M001", "order": 1},
                    {"name": "Geometria", "hours": 30, "code": "M002", "order": 2},
                    {"name": "Cálculo", "hours": 20, "code": "M003", "order": 3},
                ]
            },
            {
                "name": "História",
                "modules": [
                    {"name": "História Geral", "hours": 40, "code": "H001", "order": 1},
                    {"name": "História Portuguesa", "hours": 40, "code": "H002", "order": 2},
                ]
            },
            {
                "name": "Educação Física",
                "modules": [
                    {"name": "Desportos Colectivos", "hours": 30, "code": "EF001", "order": 1},
                    {"name": "Ginástica", "hours": 20, "code": "EF002", "order": 2},
                ]
            },
        ]
        
        for disc_data in disciplinas_data:
            d = db.query(models.Subject).filter_by(name=disc_data["name"], organization_id=org_id).first()
            if not d:
                d = models.Subject(name=disc_data["name"], organization_id=org_id)
                db.add(d)
                db.commit()
                db.refresh(d)
                
                for mod_data in disc_data["modules"]:
                    module = models.Module(
                        name=mod_data["name"],
                        code=mod_data["code"],
                        hours_total=mod_data["hours"],
                        order=mod_data["order"],
                        subject_id=d.id
                    )
                    db.add(module)
                db.commit()
                print(f"✅ Disciplina criada: {disc_data['name']} com {len(disc_data['modules'])} módulos")

        # ==========================================
        # 8. AULAS (Lessons)
        # ==========================================
        pardal = db.query(models.Teacher).filter_by(name="Prof. Pardal", organization_id=org_id).first()
        girafales = db.query(models.Teacher).filter_by(name="Prof. Girafales", organization_id=org_id).first()
        
        math = db.query(models.Subject).filter_by(name="Matemática", organization_id=org_id).first()
        hist = db.query(models.Subject).filter_by(name="História", organization_id=org_id).first()
        gym = db.query(models.Subject).filter_by(name="Educação Física", organization_id=org_id).first()
        
        t_10 = db.query(models.Class).filter_by(name="TI 25/28", organization_id=org_id).first()
        t_11 = db.query(models.Class).filter_by(name="TI 24/27", organization_id=org_id).first()
        t_12 = db.query(models.Class).filter_by(name="TI 23/26", organization_id=org_id).first()

        aulas_para_criar = [
            {"teacher": pardal, "subj": math, "klass": t_10, "num": 4},
            {"teacher": pardal, "subj": math, "klass": t_11, "num": 4},
            {"teacher": girafales, "subj": hist, "klass": t_10, "num": 3},
            {"teacher": girafales, "subj": gym, "klass": t_12, "num": 2},
        ]

        count_lessons = 0
        if all([pardal, girafales, math, hist, gym, t_10, t_11, t_12]):
            for aula in aulas_para_criar:
                exists = db.query(models.Lesson).filter_by(
                    teacher_id=aula["teacher"].id,
                    subject_id=aula["subj"].id,
                    class_id=aula["klass"].id,
                    organization_id=org_id
                ).first()
                
                if not exists:
                    l = models.Lesson(
                        teacher_id=aula["teacher"].id,
                        subject_id=aula["subj"].id,
                        class_id=aula["klass"].id,
                        num_per_week=aula["num"],
                        organization_id=org_id
                    )
                    db.add(l)
                    count_lessons += 1
        
        db.commit()
        print(f"✅ {count_lessons} Aulas (Lessons) criadas.")

        # ==========================================
        # 9. PROGRESSO MODULAR (ClassProgress)
        # ==========================================
        if all([t_10, t_11, t_12]):
            for turma in [t_10, t_11, t_12]:
                for subject in course.subjects:
                    for module in subject.modules:
                        existing = db.query(models.ClassProgress).filter_by(
                            class_id=turma.id,
                            module_id=module.id
                        ).first()
                        
                        if not existing:
                            progress = models.ClassProgress(
                                class_id=turma.id,
                                module_id=module.id,
                                hours_completed=0,
                                is_completed=False
                            )
                            db.add(progress)
                
                db.commit()
        
        print("✅ Progresso modular inicializado para todas as turmas.")

        # ==========================================
        # 10. DISPONIBILIDADES
        # ==========================================
        print("⚙️ A configurar disponibilidades de teste...")
        
        ts_segunda_manha = db.query(models.Timeslot).filter_by(day_of_week=0, start_time=datetime.time(8, 30), organization_id=org_id).first()
        if pardal and ts_segunda_manha:
            av = db.query(models.Availability).filter_by(teacher_id=pardal.id, timeslot_id=ts_segunda_manha.id).first()
            if not av:
                av = models.Availability(
                    teacher_id=pardal.id,
                    timeslot_id=ts_segunda_manha.id,
                    score=-1
                )
                db.add(av)
        
        ts_sexta_tarde = db.query(models.Timeslot).filter_by(day_of_week=4, start_time=datetime.time(16, 30), organization_id=org_id).first()
        if girafales and ts_sexta_tarde:
            av = db.query(models.Availability).filter_by(teacher_id=girafales.id, timeslot_id=ts_sexta_tarde.id).first()
            if not av:
                av = models.Availability(
                    teacher_id=girafales.id,
                    timeslot_id=ts_sexta_tarde.id,
                    score=2
                )
                db.add(av)
        
        db.commit()
        print("✅ Disponibilidades de teste aplicadas.")

    except Exception as e:
        print(f"❌ Erro Crítico no Seed: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()
        print("🏁 Seed terminado.")


def main():
    """Orquestrador: Limpa → Cria → Popula"""
    print("=" * 70)
    print("🚀 INICIALIZANDO BASE DE DADOS (PostgreSQL)")
    print("=" * 70)
    
    try:
        clean_database()
        create_tables()
        run_seed()
        
        print("\n" + "=" * 70)
        print("✅ BASE DE DADOS INICIALIZADA COM SUCESSO!")
        print("=" * 70)
        print("\n📊 Dados criados:")
        print("   • 1 Organização (Escola Exemplo)")
        print("   • 2 Professores (Pardal + Girafales)")
        print("   • 1 Curso (Técnico em Informática - TI)")
        print("   • 3 Turmas (TI 25/28, TI 24/27, TI 23/26)")
        print("   • 3 Disciplinas com 7 Módulos no total")
        print("   • 4 Aulas (Lessons) atribuídas")
        print("   • Progresso modular para todas as turmas")
        print("\n🔑 Logins de teste:")
        print("   • pardal@escola.com / 1234")
        print("   • girafales@escola.com / 1234")
        
    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()