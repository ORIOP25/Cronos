# Ficheiro: backend/seed_data.py
import sys
import datetime
from sqlalchemy import text
from app.db.database import SessionLocalSync
from app import models
from app.core.security import hash_password
from app.models import UserRole, PreferenceLevel

def run_seed():
    db = SessionLocalSync()
    try:
        print("🌱 A iniciar sementeira de dados (Seed)...")

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
                    role=UserRole.admin, # Damos admin para facilidade de testes
                    organization_id=org_id,
                    teacher_id=teacher.id
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
        # Vamos criar horários de Segunda (0) a Sexta (4)
        # Das 08:30 às 17:30 (9 blocos de 1 hora)
        start_hour = 8
        start_min = 30
        
        count_slots = 0
        for day in range(5): # 0=Segunda ... 4=Sexta
            for i in range(9): # 9 tempos por dia
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
        # 5. TURMAS (Classes)
        # ==========================================
        turmas_data = ["10º A", "11º B"]
        for t_name in turmas_data:
            t = db.query(models.Class).filter_by(name=t_name, organization_id=org_id).first()
            if not t:
                t = models.Class(name=t_name, organization_id=org_id)
                db.add(t)
                db.commit()
        print("✅ Turmas criadas.")

        # ==========================================
        # 6. DISCIPLINAS (Subjects)
        # ==========================================
        disciplinas_data = ["Matemática", "História", "Educação Física"]
        for d_name in disciplinas_data:
            d = db.query(models.Subject).filter_by(name=d_name, organization_id=org_id).first()
            if not d:
                d = models.Subject(name=d_name, organization_id=org_id)
                db.add(d)
                db.commit()
        print("✅ Disciplinas criadas.")

        # ==========================================
        # 7. AULAS (Lessons) - Onde tudo se liga
        # ==========================================
        # Recuperar objetos da BD
        pardal = db.query(models.Teacher).filter_by(name="Prof. Pardal", organization_id=org_id).first()
        girafales = db.query(models.Teacher).filter_by(name="Prof. Girafales", organization_id=org_id).first()
        
        math = db.query(models.Subject).filter_by(name="Matemática", organization_id=org_id).first()
        hist = db.query(models.Subject).filter_by(name="História", organization_id=org_id).first()
        gym = db.query(models.Subject).filter_by(name="Educação Física", organization_id=org_id).first()
        
        t10a = db.query(models.Class).filter_by(name="10º A", organization_id=org_id).first()
        t11b = db.query(models.Class).filter_by(name="11º B", organization_id=org_id).first()

        aulas_para_criar = [
            # Pardal dá Matemática ao 10º A (4x semana)
            {"name": "Matemática 10ºA", "teacher": pardal, "subj": math, "klass": t10a, "num": 4},
            # Pardal dá Matemática ao 11º B (4x semana)
            {"name": "Matemática 11ºB", "teacher": pardal, "subj": math, "klass": t11b, "num": 4},
            # Girafales dá História ao 10º A (3x semana)
            {"name": "História 10ºA", "teacher": girafales, "subj": hist, "klass": t10a, "num": 3},
            # Girafales dá Ed. Física ao 11º B (2x semana)
            {"name": "Ed. Física 11ºB", "teacher": girafales, "subj": gym, "klass": t11b, "num": 2},
        ]

        count_lessons = 0
        if all([pardal, girafales, math, hist, gym, t10a, t11b]):
            for aula in aulas_para_criar:
                # [CORREÇÃO] Filtrar pelas chaves estrangeiras, não pelo nome
                exists = db.query(models.Lesson).filter_by(
                    teacher_id=aula["teacher"].id,
                    subject_id=aula["subj"].id,
                    class_id=aula["klass"].id,
                    organization_id=org_id
                ).first()
                
                if not exists:
                    l = models.Lesson(
                        # name=aula["name"],  <-- REMOVIDO (Não existe no modelo)
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
        # 8. DISPONIBILIDADES (Teste do Algoritmo)
        # ==========================================
        # Vamos dizer que o Pardal NÃO PODE (Score -1) à Segunda-Feira de manhã
        # e o Girafales PREFERE (Score 2) à Sexta-Feira à tarde.
        
        print("⚙️ A configurar disponibilidades de teste...")
        
        # Pardal odeia Segunda às 08:30 (Slot 0 do dia 0)
        ts_segunda_manha = db.query(models.Timeslot).filter_by(day_of_week=0, start_time=datetime.time(8, 30), organization_id=org_id).first()
        if pardal and ts_segunda_manha:
            # Verifica se já existe
            av = db.query(models.Availability).filter_by(teacher_id=pardal.id, timeslot_id=ts_segunda_manha.id).first()
            if not av:
                av = models.Availability(
                    teacher_id=pardal.id,
                    timeslot_id=ts_segunda_manha.id,
                    score=-1 # IMPOSSÍVEL (Vermelho)
                )
                db.add(av)
        
        # Girafales adora Sexta às 16:30 (Slot 8 do dia 4)
        ts_sexta_tarde = db.query(models.Timeslot).filter_by(day_of_week=4, start_time=datetime.time(16, 30), organization_id=org_id).first()
        if girafales and ts_sexta_tarde:
            av = db.query(models.Availability).filter_by(teacher_id=girafales.id, timeslot_id=ts_sexta_tarde.id).first()
            if not av:
                av = models.Availability(
                    teacher_id=girafales.id,
                    timeslot_id=ts_sexta_tarde.id,
                    score=2 # PREFERENCIAL (Verde)
                )
                db.add(av)
        
        db.commit()
        print("✅ Disponibilidades de teste aplicadas.")

    except Exception as e:
        print(f"❌ Erro Crítico no Seed: {e}")
        db.rollback()
    finally:
        db.close()
        print("🏁 Seed terminado.")

if __name__ == "__main__":
    run_seed()