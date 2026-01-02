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
) -> List[models.Teacher]:
    """
    Retorna professores de uma organização com paginação.
    """
    query = select(models.Teacher).where(models.Teacher.organization_id == org_id)
    
    # 2. Aplicamos a paginação na Query SQL
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

async def create_teacher(db: AsyncSession, teacher: schemas.TeacherCreate, org_id: int):
    """
    Cria um novo professor. 
    Se o schema trouxer 'email', cria também o User associado (Login).
    """
    # 1. Criar o Professor (Recurso)
    db_teacher = models.Teacher(
        name=teacher.name, 
        organization_id=org_id
    )
    db.add(db_teacher)
    await db.flush() # Para gerar o ID do professor imediatamente (necessário para o User)

    # 2. Criar o User (Ator), se for pedido
    if teacher.email:
        # Verificar se o email já existe
        stmt = select(User).where(User.email == teacher.email)
        existing_user = await db.execute(stmt)
        if existing_user.scalars().first():
            # Se já existe, não criamos duplicado, mas podíamos ligar (fica para v2)
            print(f"⚠️ User {teacher.email} já existe. Ignorando criação de login.")
        else:
            print(f"👤 Criando login automático para {teacher.name}...")
            new_user = User(
                email=teacher.email,
                hashed_password=hash_password("1234"), # Password provisória padrão
                role=UserRole.teacher,
                organization_id=org_id,
                teacher_id=db_teacher.id # <--- A LIGAÇÃO CRÍTICA
            )
            db.add(new_user)

    await db.commit()
    await db.refresh(db_teacher)
    return db_teacher

async def delete_teacher(db: AsyncSession, teacher_id: int, org_id: int):
    """Apaga um professor pelo ID (Async)."""
    query = select(models.Teacher).where(
        models.Teacher.id == teacher_id,
        models.Teacher.organization_id == org_id
    )
    result = await db.execute(query)
    teacher = result.scalars().first()
    
    if teacher:
        await db.delete(teacher)
        await db.commit()
        return True
    return False

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