# Ficheiro: app/services/teacher_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from app import models, schemas
from app.models import Availability, PreferenceLevel, User, UserRole
from app.schemas import AvailabilityCreate
from app.core.security import hash_password
from typing import List

# ==========================================
#  FUNÇÕES ASSÍNCRONAS (Para usar na API/FastAPI)
# ==========================================

async def get_teachers_by_org(
    db: AsyncSession, 
    org_id: int, 
    skip: int = 0, 
    limit: int = 100
):
    """
    Retorna professores e verifica se têm login associado (LEFT JOIN).
    """
    # 1. Query: Seleciona o Professor E o email do User (se existir)
    stmt = (
        select(models.Teacher, models.User.email)
        .outerjoin(models.User, models.User.teacher_id == models.Teacher.id)
        .where(models.Teacher.organization_id == org_id)
        .order_by(models.Teacher.name) # Boa prática: ordenar alfabeticamente
        .offset(skip)
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    # 2. Mapeamento: Transformamos a tupla (Teacher, email) num dicionário
    # Isto é necessário para preencher o campo 'login_email' do Schema
    final_list = []
    for teacher, user_email in rows:
        teacher_dict = {
            "id": teacher.id,
            "name": teacher.name,
            "email": user_email, # Email de contacto (info do professor)
            "organization_id": teacher.organization_id,
            "login_email": user_email # Email de login (info do user, se existir)
        }
        final_list.append(teacher_dict)
        
    return final_list

async def create_teacher(db: AsyncSession, teacher: schemas.TeacherCreate, org_id: int):
    """
    Cria um novo professor. 
    Se o payload trouxer 'create_user_account=True' e 'email', 
    invoca o user_service para criar o Login separadamente.
    """
    
    # [CORREÇÃO CRÍTICA]
    # Instanciamos o modelo Teacher APENAS com os campos que existem na tabela Teacher.
    # Ignoramos propositadamente o 'teacher.email' aqui, pois ele pertence ao User, não ao Teacher.
    db_teacher = models.Teacher(
        name=teacher.name, 
        organization_id=org_id
    )
    
    db.add(db_teacher)
    
    # Flush para obter o ID do professor (db_teacher.id) antes do commit final
    await db.flush() 
    await db.refresh(db_teacher)

    # Lógica de criação de User (Separada e desacoplada)
    if teacher.create_user_account and teacher.email:
        # Importação local para evitar ciclo de dependência
        from app.services import user_service
        from app.models import UserRole
        
        # Prepara os dados para o user_service
        user_in = schemas.UserCreate(
            email=teacher.email,
            password="1234" # Password provisória
        )
        
        # O user_service encarrega-se de criar o registo na tabela 'user'
        # e ligá-lo a este professor via 'teacher_id'
        await user_service.create_user(
            db, 
            user_in, 
            org_id=org_id, 
            role=UserRole.teacher,
            teacher_id=db_teacher.id 
        )

    # Commit atómico: ou cria ambos, ou falha ambos
    await db.commit()
    
    return db_teacher

async def delete_teacher(
    db: AsyncSession, 
    teacher_id: int,
    org_id: int
) -> str:
    """
    Remove um professor.
    Retorna: 'SUCCESS', 'NOT_FOUND' ou 'DEPENDENCY_ERROR'.
    """
    # 1. Buscar o professor
    query = select(models.Teacher).where(
        models.Teacher.id == teacher_id,
        models.Teacher.organization_id == org_id
    )
    result = await db.execute(query)
    teacher = result.scalars().first()
    
    if not teacher:
        return "NOT_FOUND"

    # 2. VERIFICAÇÃO DE INTEGRIDADE (Visão Sénior) 🛡️
    # Não podemos apagar um professor se ele tiver Aulas (Lessons) atribuídas.
    # Isso deixaria as aulas órfãs e quebraria o horário.
    query_dependency = select(models.Lesson).where(models.Lesson.teacher_id == teacher_id)
    result_dependency = await db.execute(query_dependency)
    if result_dependency.first():
        return "DEPENDENCY_ERROR"

    # 3. Apagar
    await db.delete(teacher)
    await db.commit()
    return "SUCCESS"

async def update_teacher(
    db: AsyncSession, 
    teacher_id: int, 
    teacher_in: schemas.TeacherUpdate,
    org_id: int
):
    """
    Atualiza um professor. Verifica se pertence à organização.
    """
    # 1. Buscar o professor (garantindo que é da escola certa)
    query = select(models.Teacher).where(
        models.Teacher.id == teacher_id,
        models.Teacher.organization_id == org_id
    )
    result = await db.execute(query)
    teacher = result.scalars().first()
    
    if not teacher:
        return None

    # 2. Atualizar campos apenas se foram enviados (exclude_unset)
    update_data = teacher_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(teacher, field, value)

    # 3. Gravar
    db.add(teacher)
    await db.commit()
    await db.refresh(teacher)
    return teacher

async def find_replacement_teacher(
    db: AsyncSession, 
    org_id: int, 
    unavailable_slot_id: int, 
    exclude_teacher_id: int
):
    """
    Encontra professores que podem substituir numa aula.
    Lógica de Prioridade:
    1. (Melhor) Preferencial (Score 2)
    2. (Normal) Neutro / Sem Registo (Score 1)
    3. (Pior) Evitar (Score 0) -> Fundo da lista
    Excluídos: Impossível (Score -1)
    """
    # 1. Buscar todos os professores
    all_teachers = await get_teachers_by_org(db, org_id)
    
    # 2. Buscar as preferências de TODOS os professores para este slot específico
    avail_stmt = select(Availability).where(
        Availability.timeslot_id == unavailable_slot_id
    )
    avail_results = await db.execute(avail_stmt)
    
    # Mapa rápido: { teacher_id: score }
    teacher_scores = {av.teacher_id: av.score for av in avail_results.scalars().all()}

    suggestions = []
    
    for teacher in all_teachers:
        if teacher.id == exclude_teacher_id:
            continue
            
        # Obter score (Default = 1/Neutro se não tiver registo)
        score = teacher_scores.get(teacher.id, 1) #
        
        # FILTRO RÍGIDO: Se for Impossível (-1), salta fora.
        if score == -1:
            continue

        # DEFINIR PRIORIDADE (Menor número = Aparece primeiro na lista)
        # 1: Top (Reserva para lógica futura de "Já dá aulas à turma")
        # 2: Preferencial (Score 2)
        # 3: Neutro (Score 1)
        # 4: Evitar (Score 0) -> Fundo da lista
        
        priority = 3 # Default
        reason = "Disponível"

        if score == 2:
            priority = 2
            reason = "Preferencial (Marcado a Verde)"
        elif score == 0:
            priority = 4
            reason = "Evitar (Marcado a Laranja)"
        
        suggestions.append({
            "teacher_id": teacher.id,
            "teacher_name": teacher.name,
            "priority": priority,
            "reason": reason
        })
        
    # Ordenar: Prioridade (crescente), depois Nome (alfabético)
    suggestions.sort(key=lambda x: (x['priority'], x['teacher_name']))
    return suggestions

async def set_teacher_availability(
    db: AsyncSession, 
    teacher_id: int, 
    availabilities: list[AvailabilityCreate]
):
    """
    Define as disponibilidades de um professor.
    Estratégia: Apagar as antigas para esse professor e inserir as novas (Bulk Update).
    Isto é mais simples do que fazer update linha a linha.
    """
    # 1. Limpar disponibilidades antigas deste professor
    # (Ou apenas as que colidirem, mas limpar tudo é mais seguro para garantir consistência)
    await db.execute(delete(Availability).where(Availability.teacher_id == teacher_id))
    
    # 2. Preparar novos objetos
    new_records = [
        Availability(
            teacher_id=teacher_id,
            timeslot_id=item.timeslot_id,
            score=item.score.value # Guardamos o inteiro (-1, 0, 1, 2)
        )
        for item in availabilities
    ]
    
    # 3. Inserir em massa
    db.add_all(new_records)
    await db.commit()
    return {"status": "success", "count": len(new_records)}

# ==========================================
#  FUNÇÕES SÍNCRONAS (Para usar no Solver/Celery)
# ==========================================

def get_teachers_by_org_sync(db: Session, org_id: int):
    """Retorna todos os professores (Sync - Bloqueante)."""
    return db.query(models.Teacher).filter(models.Teacher.organization_id == org_id).all()