from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Any, Annotated
from app import schemas, models
from app.api import deps
from app.services import class_service

router = APIRouter()

@router.get("/", response_model=List[schemas.ClassRead])
async def read_classes(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)]
):
    return await class_service.get_classes_by_org(db, current_user.organization_id)

@router.get("/{class_id}", response_model=schemas.ClassFullDetailRead)
async def read_class(
    class_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
) -> Any:
    """
    Retorna dashboard completo da turma: Curso + Disciplinas + Módulos + Progresso.
    
    Usado na página ClassDetails.jsx para exibir:
    - Header da turma (nome, capacidade, ano)
    - Curso associado
    - Lista de disciplinas com módulos e barras de progresso
    
    4 Pilares:
    🔐 Security: Valida org_id — turma só é retornada se pertence à organização
    ⚙️ Stability: 2 queries com selectinload (previne N+1 em async)
    ⚡ Optimization: Progresso calculado server-side com lookup O(1)
    📈 Scalability: Resposta auto-suficiente para o dashboard
    """
    result = await class_service.get_class_full_details(db, class_id, current_user.organization_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    return result

@router.post("/", response_model=schemas.ClassRead)
async def create_class(
    item: schemas.ClassCreate, 
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)]
):
    result = await class_service.create_class(db, item, current_user.organization_id)
    if result == "COURSE_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Curso não encontrado")
    return result

@router.patch("/{class_id}", response_model=schemas.ClassRead)
async def update_class(
    class_id: int,
    item: schemas.ClassUpdate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)]
):
    updated = await class_service.update_class(db, class_id, item, current_user.organization_id)
    if updated == "INVALID_YEAR_RANGE":
        raise HTTPException(status_code=400, detail="Ano de fim deve ser maior que o ano de início")
    if not updated:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    return updated

@router.delete("/{class_id}")
async def delete_class(
    class_id: int, 
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)]
):
    status = await class_service.delete_class(db, class_id, current_user.organization_id)
    
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Turma não encontrada")

    return {"message": "Turma removida com sucesso"}

@router.get("/{class_id}/curriculum", response_model=List[schemas.SubjectRead])
async def get_class_curriculum(
    class_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)]
):
    """
    Retorna o currículo (disciplinas) da turma.
    
    A turma está associada a um curso, e o curso define quais disciplinas ela precisa ter.
    Este endpoint facilita a "Matriz de Distribuição de Serviço" (Atribuição de Professores).
    
    Exemplo de uso:
    - GET /api/v1/classes/5/curriculum → Lista as disciplinas do curso do 10º TGEI
    """
    curriculum = await class_service.get_class_curriculum(
        db, 
        class_id, 
        current_user.organization_id
    )
    return curriculum


# ==========================================
#  PROGRESSO DA TURMA (Módulos)
# ==========================================

@router.patch("/{class_id}/progress", response_model=schemas.ClassFullDetailRead)
async def update_class_progress(
    class_id: int,
    payload: schemas.ClassProgressBulkUpdate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> Any:
    """
    Atualiza o progresso de módulos para uma turma (upsert).
    Auto-calcula is_completed quando hours_completed >= hours_total.
    
    Body: { "progress": [{ "module_id": 1, "hours_completed": 25 }, ...] }
    
    Retorna: ClassFullDetailRead atualizado (para refresh imediato na UI)
    
    4 Pilares:
    🔐 Security: Admin only + valida módulo pertence ao curso da turma
    ⚙️ Stability: Transação atómica + clamp de horas (nunca > total)
    ⚡ Optimization: Upsert batch via ON CONFLICT
    📈 Scalability: Suporta N módulos numa única chamada
    """
    status = await class_service.update_class_progress(
        db, class_id, payload.progress, current_user.organization_id
    )
    
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    if status == "NO_SUBJECTS":
        raise HTTPException(status_code=400, detail="Turma sem disciplinas atribuídas — adicione disciplinas primeiro")
    
    if status == "NO_COURSE":
        raise HTTPException(status_code=400, detail="Turma sem curso associado — não é possível registar progresso")
    
    if isinstance(status, str) and status.startswith("INVALID_MODULE:"):
        module_id = status.split(":")[1]
        raise HTTPException(
            status_code=400, 
            detail=f"Módulo {module_id} não pertence às disciplinas desta turma"
        )
    
    # Retornar dados atualizados para refresh na UI
    return await class_service.get_class_full_details(db, class_id, current_user.organization_id)


# ==========================================
#  DISCIPLINAS DA TURMA (Class-Subject Link)
#  Gestão curso-cêntrica de professores
# ==========================================

@router.get("/{class_id}/subjects", response_model=schemas.ClassSubjectsListRead)
async def get_class_subjects(
    class_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    """
    Lista disciplinas associadas à turma (para o grade_level atual).
    Inclui professor atribuído a cada disciplina.
    
    Usado na página ClassSubjects.jsx para mostrar:
    - Quais disciplinas a turma tem
    - Quem é o professor de cada disciplina
    """
    result = await class_service.get_class_subjects(db, class_id, current_user.organization_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    return result


@router.post("/{class_id}/subjects", response_model=schemas.ClassSubjectsListRead)
async def add_class_subject(
    class_id: int,
    payload: schemas.ClassSubjectCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """
    Adiciona uma disciplina à turma (para o grade_level atual).
    
    Validações:
    - Turma existe e pertence à organização
    - Disciplina existe e pertence à organização
    - Disciplina não está já associada à turma
    """
    result = await class_service.add_class_subject(
        db, class_id, payload.subject_id, current_user.organization_id
    )
    
    if result == "CLASS_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    if result == "SUBJECT_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Disciplina não encontrada")
    
    if result == "ALREADY_EXISTS":
        raise HTTPException(status_code=400, detail="Esta disciplina já está associada à turma")
    
    # Retornar lista atualizada
    return await class_service.get_class_subjects(db, class_id, current_user.organization_id)


@router.patch("/{class_id}/subjects/{subject_id}", response_model=schemas.ClassSubjectsListRead)
async def update_class_subject_teacher(
    class_id: int,
    subject_id: int,
    payload: schemas.ClassSubjectUpdate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """
    Atribui ou altera o professor de uma disciplina da turma.
    
    Validações:
    - Associação turma/disciplina existe
    - Se teacher_id não é null, professor tem competência na disciplina
    
    Enviar teacher_id=null para remover a atribuição.
    """
    result = await class_service.update_class_subject_teacher(
        db, class_id, subject_id, payload, current_user.organization_id
    )
    
    if result == "CLASS_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    if result == "LINK_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Esta disciplina não está associada à turma")
    
    if result == "TEACHER_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Professor não encontrado")
    
    if result == "NO_COMPETENCY":
        raise HTTPException(
            status_code=400, 
            detail="Este professor não tem competência para lecionar esta disciplina"
        )
    
    # Retornar lista atualizada
    return await class_service.get_class_subjects(db, class_id, current_user.organization_id)


@router.delete("/{class_id}/subjects/{subject_id}", response_model=schemas.ClassSubjectsListRead)
async def remove_class_subject(
    class_id: int,
    subject_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """
    Remove uma disciplina da turma (para o grade_level atual).
    """
    result = await class_service.remove_class_subject(
        db, class_id, subject_id, current_user.organization_id
    )
    
    if result == "CLASS_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Esta disciplina não está associada à turma")
    
    # Retornar lista atualizada
    return await class_service.get_class_subjects(db, class_id, current_user.organization_id)


@router.get("/{class_id}/available-subjects", response_model=List[schemas.SubjectRead])
async def get_available_subjects(
    class_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    """
    Lista disciplinas disponíveis para adicionar à turma.
    (Disciplinas da organização que ainda não estão associadas à turma)
    """
    return await class_service.get_available_subjects_for_class(
        db, class_id, current_user.organization_id
    )


@router.get("/subjects/{subject_id}/eligible-teachers", response_model=List[schemas.EligibleTeacherRead])
async def get_eligible_teachers(
    subject_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    """
    Lista professores elegíveis para lecionar uma disciplina.
    (Professores que têm competência na disciplina)
    
    Também indica quantas turmas cada professor já tem para esta disciplina.
    """
    return await class_service.get_eligible_teachers_for_subject(
        db, subject_id, current_user.organization_id
    )