# Ficheiro: app/services/teacher_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, delete
from app import models, schemas
from app.models import Availability, Teacher
from app.schemas import AvailabilitySelfCreate


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
    Retorna professores com email, login_email e status is_active.
    LEFT JOIN com User para obter dados de autenticação.
    """
    # 1. Query: Selecionamos Teacher + email + is_active do User
    stmt = (
        select(models.Teacher, models.User.email, models.User.is_active)
        .outerjoin(models.User, models.User.teacher_id == models.Teacher.id)
        .where(models.Teacher.organization_id == org_id)
        .options(selectinload(models.Teacher.subjects))
        .order_by(models.Teacher.name)
        .offset(skip)
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    # 2. Mapeamento: Transformamos as tuplas em objetos com dados injetados
    final_list = []
    for teacher, user_email, is_active in rows:
        # Injetar campos no objeto ORM (mantém relações carregadas intactas)
        setattr(teacher, "login_email", user_email)
        setattr(teacher, "email", user_email)
        # Se is_active for None (sem User), assumimos False
        setattr(teacher, "is_active", is_active if is_active is not None else False)
        final_list.append(teacher)
        
    return final_list

async def create_teacher(db: AsyncSession, teacher_in: schemas.TeacherCreate, org_id: int):
    # 1. Separar dados: O que é do Professor vs O que é da Relação
    # Retiramos os IDs das disciplinas para uma lista à parte
    subject_ids = teacher_in.subject_ids

    # Criamos os dados para a tabela Teacher, excluindo o que não é coluna dela
    teacher_data = teacher_in.model_dump(exclude={'subject_ids', 'create_user_account', 'email', 'password'})

    # 2. Criar a Instância do Professor
    db_teacher = models.Teacher(**teacher_data, organization_id=org_id)

    # 3. Tratar as Disciplinas (Relação N:M)
    if subject_ids:
        query_subs = select(models.Subject).where(
            models.Subject.id.in_(subject_ids),
            models.Subject.organization_id == org_id
        )
        result_subs = await db.execute(query_subs)
        subjects_objects = result_subs.scalars().all()
        
        db_teacher.subjects = list(subjects_objects)

    try:
        # 4. Adicionar à Sessão e Obter ID
        db.add(db_teacher)
        await db.flush() # Flush garante que db_teacher.id é gerado agora
        await db.refresh(db_teacher)

        # 5. Lógica de User (Criar SEMPRE que tiver email)
        if teacher_in.email:
            from app.services import user_service
            from app.models import UserRole
            
            # Determinar o estado da conta (Ativo/Inativo) conforme o switch
            is_active_status = teacher_in.create_user_account
            
            user_create_data = schemas.UserCreate(
                email=teacher_in.email,
                password=teacher_in.password if teacher_in.password else "ChangeMeNow"
            )
            
            # Criar o utilizador (por defeito, create_user cria com is_active=True)
            new_user = await user_service.create_user(
                db, 
                user_create_data, 
                org_id=org_id, 
                role=UserRole.teacher,
                teacher_id=db_teacher.id 
            )
            
            # Forçar o estado correto (Ativo ou Inativo conforme o switch)
            new_user.is_active = is_active_status
            db.add(new_user)

        # 6. Gravar tudo na BD
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    # 7. Retornar o Professor com dados atualizados (Single Source of Truth)
    return await get_teacher_details(db, db_teacher.id, org_id)

# Helper Function
async def get_teacher_with_subjects(db: AsyncSession, teacher_id: int, org_id: int):
    query = select(models.Teacher).where(
        models.Teacher.id == teacher_id,
        models.Teacher.organization_id == org_id
    ).options(selectinload(models.Teacher.subjects))
    
    result = await db.execute(query)
    return result.scalars().first()

async def delete_teacher(
    db: AsyncSession, 
    teacher_id: int,
    org_id: int
) -> str:
    """
    Remove um professor. 
    1. Verifica dependências de aulas (Erro se tiver).
    2. Remove o User associado (se tiver).
    3. Remove o Teacher.
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

    # 2. VERIFICAÇÃO DE INTEGRIDADE (Aulas)
    # Não podemos apagar se tiver aulas.
    query_dependency = select(models.Lesson).where(models.Lesson.teacher_id == teacher_id)
    result_dependency = await db.execute(query_dependency)
    if result_dependency.first():
        return "DEPENDENCY_ERROR"

    # 3. LIMPEZA DE UTILIZADOR (Resolve o IntegrityError)
    # Antes de apagar o Teacher, temos de apagar o User que aponta para ele.
    query_user = select(models.User).where(models.User.teacher_id == teacher_id)
    result_user = await db.execute(query_user)
    user = result_user.scalars().first()
    
    if user:
        await db.delete(user) # Apaga o login primeiro

    # 4. Apagar o Professor
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
    Atualiza um professor. Permite:
    - Mudar nome, email, competências
    - Ativar/desativar a conta de acesso via create_user_account
    """
    # 1. Buscar Teacher + Disciplinas (Eager Loading)
    query = select(models.Teacher).where(
        models.Teacher.id == teacher_id,
        models.Teacher.organization_id == org_id
    ).options(selectinload(models.Teacher.subjects))

    result = await db.execute(query)
    teacher = result.scalars().first()
    
    if not teacher:
        return None

    # 2. Preparar dados (Excluir email e create_user_account porque têm lógica especial)
    update_data = teacher_in.model_dump(
        exclude_unset=True, 
        exclude={"subject_ids", "email", "create_user_account"}
    )

    # 3. Atualizar campos simples do Professor
    for field, value in update_data.items():
        setattr(teacher, field, value)

    # 4. Atualizar Disciplinas
    if teacher_in.subject_ids is not None and len(teacher_in.subject_ids) > 0:
        query_subjects = select(models.Subject).where(
            models.Subject.id.in_(teacher_in.subject_ids),
            models.Subject.organization_id == org_id
        )
        result_subjects = await db.execute(query_subjects)
        new_subjects = result_subjects.scalars().all()
        teacher.subjects = list(new_subjects)
    elif teacher_in.subject_ids is not None:
        # Se enviou lista vazia, limpa as disciplinas
        teacher.subjects = []

    # 5. Lógica de User e Email (REFINADA)
    
    # 5.1 Buscar o user atual (se existir)
    query_user = select(models.User).where(models.User.teacher_id == teacher_id)
    result_user = await db.execute(query_user)
    user = result_user.scalars().first()

    # 5.2 Se mudou o email, atualiza no User (se existir)
    if teacher_in.email and user:
        user.email = teacher_in.email
        db.add(user)
    
    # 5.3 Se mudou o estado da conta (Ativar/Desativar)
    if teacher_in.create_user_account is not None:
        if user:
            # Caso 1: User existe, apenas atualizamos o switch
            user.is_active = teacher_in.create_user_account
            db.add(user)
        elif teacher_in.create_user_account and teacher_in.email:
            # Caso 2: Não tinha user, mas agora quer CRIAR (ativar)
            # Precisamos do email para criar a conta
            from app.services import user_service
            from app.models import UserRole
            
            user_create_data = schemas.UserCreate(
                email=teacher_in.email,
                password="1234"
            )
            # Criar o user (por defeito is_active=True, que é o que queremos)
            await user_service.create_user(
                db, user_create_data, org_id=org_id, 
                role=UserRole.teacher, teacher_id=teacher.id
            )
        # Caso 3: Quer desativar (create_user_account=False) mas não tem user
        # -> Nada a fazer, não há User para desativar

    # 6. Gravar tudo na BD
    db.add(teacher)
    await db.commit()
    
    # 7. Retornar dados frescos (Single Source of Truth)
    return await get_teacher_details(db, teacher_id, org_id)

async def get_teacher_details(db: AsyncSession, teacher_id: int, org_id: int):
    # 1. Query: Selecionamos também o campo is_active do User
    stmt = (
        select(models.Teacher, models.User.email, models.User.is_active)
        .outerjoin(models.User, models.User.teacher_id == models.Teacher.id)
        .where(
            models.Teacher.id == teacher_id,
            models.Teacher.organization_id == org_id
        )
        .options(selectinload(models.Teacher.subjects))
    )
    
    result = await db.execute(stmt)
    row = result.first()
    
    if not row:
        return None
    
    # 2. Desembrulhamos os 3 valores (Teacher, email, is_active)
    teacher, email, is_active = row
    
    # 3. Injetamos os valores no objeto Teacher para o Pydantic conseguir ler
    setattr(teacher, "login_email", email)
    setattr(teacher, "email", email)
    # Se is_active for None (não tem User), assumimos False
    setattr(teacher, "is_active", is_active if is_active is not None else False)
    
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


async def get_teacher_availability(
    db: AsyncSession,
    teacher_id: int,
    org_id: int,
) -> list[dict] | str:
    """Lê disponibilidades de um professor dentro da organização autenticada."""
    teacher_query = select(models.Teacher).where(
        models.Teacher.id == teacher_id,
        models.Teacher.organization_id == org_id,
    )
    teacher_result = await db.execute(teacher_query)
    db_teacher = teacher_result.scalars().first()
    if not db_teacher:
        return "NOT_FOUND"

    rows = await db.execute(
        select(models.Availability.timeslot_id, models.Availability.score)
        .join(models.Timeslot, models.Availability.timeslot_id == models.Timeslot.id)
        .where(
            models.Availability.teacher_id == teacher_id,
            models.Timeslot.organization_id == org_id,
        )
        .order_by(models.Timeslot.day_of_week, models.Timeslot.start_time, models.Availability.id)
    )

    return [
        {
            "timeslot_id": row.timeslot_id,
            "score": row.score,
        }
        for row in rows.all()
    ]

async def set_teacher_availability(
    db: AsyncSession, 
    teacher_id: int, 
    availabilities: list[AvailabilitySelfCreate],
    org_id: int
):
    """
    Define as disponibilidades de um professor.
    Estratégia: Apagar as antigas para esse professor e inserir as novas (Bulk Update).
    Isto é mais simples do que fazer update linha a linha.
    """
    # 1. Validar que o professor pertence a esta organização
    teacher_query = select(models.Teacher).where(
        models.Teacher.id == teacher_id,
        models.Teacher.organization_id == org_id
    )
    teacher_result = await db.execute(teacher_query)
    db_teacher = teacher_result.scalars().first()

    if not db_teacher:
        return "NOT_FOUND"

    # 2. Validar payload antes de qualquer mutação (evita alterações parciais em erro)
    timeslot_ids = [item.timeslot_id for item in availabilities]
    if len(timeslot_ids) != len(set(timeslot_ids)):
        return "DUPLICATE_TIMESLOT"

    # 3. Validar que todos os timeslots pertencem à organização
    if availabilities:
        timeslot_query = select(models.Timeslot.id).where(
            models.Timeslot.id.in_(timeslot_ids),
            models.Timeslot.organization_id == org_id
        )
        timeslot_result = await db.execute(timeslot_query)
        valid_ids = {row[0] for row in timeslot_result.all()}
        if len(valid_ids) != len(set(timeslot_ids)):
            return "INVALID_TIMESLOT"

    # 4. Mutação transacional
    try:
        # (outras estratégias são possíveis, mas replace-all mantém consistência simples)
        await db.execute(delete(Availability).where(Availability.teacher_id == teacher_id))

        new_records = [
            Availability(
                teacher_id=teacher_id,
                timeslot_id=item.timeslot_id,
                score=item.score.value  # Guardamos o inteiro (-1, 0, 1, 2)
            )
            for item in availabilities
        ]

        db.add_all(new_records)
        await db.commit()
        return {"status": "success", "count": len(new_records)}
    except Exception:
        await db.rollback()
        raise

# ==========================================
#  FUNÇÕES SÍNCRONAS (Para usar no Solver/Celery)
# ==========================================

def get_teachers_by_org_sync(db: Session, org_id: int):
    """Retorna todos os professores (Sync - Bloqueante)."""
    return db.query(models.Teacher).filter(models.Teacher.organization_id == org_id).all()