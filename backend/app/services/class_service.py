import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, delete, func
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload

from app import models, schemas
from app.core.exceptions import AppError
from app.scheduler.infrastructure.operations import (
    adjust_class_progress,
    class_progress_map,
)
from app.services import joint_lesson_service, resource_removal
from app.services.scheduler_state_service import record_scheduler_change

# A disciplina de uma ligação com os módulos e o tipo da escola, em bloco.
_LINK_SUBJECT_OPTIONS = (
    selectinload(models.ClassSubjectLink.subject).selectinload(models.Subject.modules),
    selectinload(models.ClassSubjectLink.subject).joinedload(models.Subject.room_type),
)


def _class_demand_snapshot(item: models.Class) -> dict:
    return {
        "size": item.size,
        "start_year": item.start_year,
        "end_year": item.end_year,
        "grade_level": item.grade_level,
        "course_id": item.course_id,
        "is_archived": item.is_archived,
        "home_room_id": item.home_room_id,
    }


def _class_subject_snapshot(link: models.ClassSubjectLink, module_ids) -> dict:
    return {
        "class_id": link.class_id,
        "subject_id": link.subject_id,
        "grade_level": link.grade_level,
        "teacher_id": link.teacher_id,
        "module_ids": sorted(module_ids),
    }


async def _load_link_module_ids(db: AsyncSession, organization_id: int, link_id: int) -> list[int]:
    rows = await db.execute(
        select(models.class_subject_module.c.module_id)
        .where(
            models.class_subject_module.c.organization_id == organization_id,
            models.class_subject_module.c.class_subject_link_id == link_id,
        )
        .order_by(models.class_subject_module.c.module_id)
    )
    return [row[0] for row in rows.all()]


async def _replace_link_modules(
    db: AsyncSession, organization_id: int, link_id: int, module_ids: list[int]
) -> None:
    await db.execute(
        delete(models.class_subject_module).where(
            models.class_subject_module.c.organization_id == organization_id,
            models.class_subject_module.c.class_subject_link_id == link_id,
        )
    )
    if module_ids:
        await db.execute(
            models.class_subject_module.insert().values(
                [
                    {
                        "organization_id": organization_id,
                        "class_subject_link_id": link_id,
                        "module_id": module_id,
                    }
                    for module_id in module_ids
                ]
            )
        )


# --- HELPERS INTERNOS ---
async def _joint_group_for_link(db: AsyncSession, organization_id: int, link_id: int) -> int | None:
    return await db.scalar(
        select(models.joint_lesson_group_member.c.group_id).where(
            models.joint_lesson_group_member.c.organization_id == organization_id,
            models.joint_lesson_group_member.c.class_subject_link_id == link_id,
        )
    )


async def _joint_module_ids(db: AsyncSession, organization_id: int, group_id: int) -> list[int]:
    rows = await db.execute(
        select(models.joint_lesson_group_module.c.module_id).where(
            models.joint_lesson_group_module.c.organization_id == organization_id,
            models.joint_lesson_group_module.c.group_id == group_id,
        )
    )
    return [row[0] for row in rows.all()]


async def _joint_member_link_ids(
    db: AsyncSession, organization_id: int, group_id: int
) -> list[int]:
    rows = await db.execute(
        select(models.joint_lesson_group_member.c.class_subject_link_id).where(
            models.joint_lesson_group_member.c.organization_id == organization_id,
            models.joint_lesson_group_member.c.group_id == group_id,
        )
    )
    return [row[0] for row in rows.all()]


async def _get_class_by_org(db: AsyncSession, class_id: int, organization_id: int):
    """Busca uma turma por id + organization_id (isolamento de tenant)."""
    result = await db.execute(
        select(models.Class).where(
            models.Class.id == class_id, models.Class.organization_id == organization_id
        )
    )
    return result.scalars().first()


async def _active_room_of_school(db: AsyncSession, room_id: int, organization_id: int):
    """Sala ativa da escola; outra escola, arquivada ou um id de tipo dão 404."""
    room = await db.scalar(
        select(models.Room).where(
            models.Room.id == room_id,
            models.Room.organization_id == organization_id,
            models.Room.is_archived.is_(False),
        )
    )
    if room is None:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Room {room_id} was not found in organization {organization_id}.",
        )
    return room


async def _get_course_by_org(db: AsyncSession, course_id: int, organization_id: int):
    result = await db.execute(
        select(models.Course).where(
            models.Course.id == course_id, models.Course.organization_id == organization_id
        )
    )
    return result.scalars().first()


async def _get_class_by_course_and_org(
    db: AsyncSession, class_id: int, course_id: int, organization_id: int
):
    result = await db.execute(
        select(models.Class).where(
            models.Class.id == class_id,
            models.Class.course_id == course_id,
            models.Class.organization_id == organization_id,
        )
    )
    return result.scalars().first()


async def _selected_module_map(
    db: AsyncSession, organization_id: int, link_ids: list[int]
) -> dict[int, set[int]]:
    """Módulos marcados por ligação turma-disciplina, numa só consulta."""
    if not link_ids:
        return {}
    result = await db.execute(
        select(
            models.class_subject_module.c.class_subject_link_id,
            models.class_subject_module.c.module_id,
        ).where(
            models.class_subject_module.c.organization_id == organization_id,
            models.class_subject_module.c.class_subject_link_id.in_(link_ids),
        )
    )
    selected: dict[int, set[int]] = {}
    for link_id, module_id in result.all():
        selected.setdefault(link_id, set()).add(module_id)
    return selected


async def _selected_module_ids(db: AsyncSession, organization_id: int, link_id: int) -> set[int]:
    result = await db.execute(
        select(models.class_subject_module.c.module_id).where(
            models.class_subject_module.c.organization_id == organization_id,
            models.class_subject_module.c.class_subject_link_id == link_id,
        )
    )
    return set(result.scalars().all())


async def _subject_catalogue_with_selection(
    db: AsyncSession, organization_id: int, links: list[models.ClassSubjectLink]
) -> tuple[dict[int, list[models.Module]], dict[int, set[int]]]:
    """Módulos de cada disciplina e seleção por ligação, numa só consulta.

    O ``outerjoin`` devolve o catálogo e as linhas marcadas juntos, para que a
    contagem de consultas não cresça com o número de disciplinas.
    """
    if not links:
        return {}, {}
    subject_ids = [link.subject_id for link in links]
    link_ids = [link.id for link in links]
    rows = await db.execute(
        select(models.Module, models.class_subject_module.c.class_subject_link_id)
        .outerjoin(
            models.class_subject_module,
            and_(
                models.class_subject_module.c.organization_id == models.Module.organization_id,
                models.class_subject_module.c.module_id == models.Module.id,
                models.class_subject_module.c.class_subject_link_id.in_(link_ids),
            ),
        )
        .where(
            models.Module.organization_id == organization_id,
            models.Module.subject_id.in_(subject_ids),
        )
        .order_by(models.Module.subject_id, models.Module.order)
    )
    modules_by_subject: dict[int, list[models.Module]] = {}
    selected_by_link: dict[int, set[int]] = {}
    for module, selected_link_id in rows.all():
        modules_by_subject.setdefault(module.subject_id, []).append(module)
        if selected_link_id is not None:
            selected_by_link.setdefault(selected_link_id, set()).add(module.id)
    return modules_by_subject, selected_by_link


# --- ASYNC (API) ---
async def get_classes_by_org(db: AsyncSession, organization_id: int):
    # Ordenar por nome
    result = await db.execute(
        select(models.Class)
        .where(
            models.Class.organization_id == organization_id,
            models.Class.is_archived.is_(False),
        )
        .order_by(models.Class.name)
    )
    return result.scalars().all()


async def get_classes_by_course(db: AsyncSession, course_id: int, organization_id: int):
    query = (
        select(models.Class)
        .where(
            models.Class.course_id == course_id,
            models.Class.organization_id == organization_id,
            models.Class.is_archived.is_(False),
        )
        .order_by(models.Class.grade_level, models.Class.name)
    )
    result = await db.execute(query)
    return result.scalars().all()


async def create_class_in_course(
    db: AsyncSession,
    course_id: int,
    item: schemas.ClassCreateInCourse,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    db_course = await _get_course_by_org(db, course_id, organization_id)
    if not db_course:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Course {course_id} was not found in organization {organization_id}.",
        )
    if db_course.is_archived:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Course {course_id} is archived and cannot receive new classes.",
        )

    db_item = models.Class(
        **item.model_dump(), course_id=course_id, organization_id=organization_id
    )
    db.add(db_item)
    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="CLASS_DEMAND",
        entity_id=db_item.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after=_class_demand_snapshot(db_item),
        changed_by_membership_id=changed_by_membership_id,
        active_resource=not db_item.is_archived,
    )
    await db.flush()
    await db.refresh(db_item)
    return db_item


async def update_class_in_course(
    db: AsyncSession,
    course_id: int,
    class_id: int,
    class_in: schemas.ClassUpdateInCourse,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    db_class = await _get_class_by_course_and_org(db, class_id, course_id, organization_id)
    if not db_class:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Class {class_id} was not found in course {course_id}.",
        )
    if db_class.is_archived:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Class {class_id} is archived and cannot be edited.",
        )
    update_data = class_in.model_dump(exclude_unset=True)
    next_start_year = update_data.get("start_year", db_class.start_year)
    next_end_year = update_data.get("end_year", db_class.end_year)

    if next_end_year <= next_start_year:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail="The class end year must be greater than its start year.",
        )

    home_room_id = update_data.get("home_room_id")
    if home_room_id is not None:
        home_room = await _active_room_of_school(db, home_room_id, organization_id)
        class_size = update_data.get("size", db_class.size)
        if home_room.capacity < class_size:
            raise AppError(
                kind="validation",
                code="home_room_capacity",
                detail=f"Room {home_room.id} has {home_room.capacity} seats for a class of {class_size}.",
                public_context={
                    "room_name": home_room.name,
                    "room_capacity": home_room.capacity,
                    "class_size": class_size,
                },
            )

    before = _class_demand_snapshot(db_class)
    for field, value in update_data.items():
        setattr(db_class, field, value)

    db.add(db_class)
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="CLASS_DEMAND",
        entity_id=db_class.id,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before=before,
        after=_class_demand_snapshot(db_class),
        changed_by_membership_id=changed_by_membership_id,
        active_resource=not db_class.is_archived,
    )
    await db.flush()
    await db.refresh(db_class)
    return db_class


async def clear_home_room(
    db: AsyncSession,
    organization_id: int,
    room_id: int,
    changed_by_membership_id: int | None = None,
) -> None:
    """Deixa em Automática as turmas que tinham a sala como sala da turma (D09).

    Corre na mesma transação da remoção da sala e regista cada turma como alteração.
    """
    classes = (
        await db.scalars(
            select(models.Class).where(
                models.Class.organization_id == organization_id,
                models.Class.home_room_id == room_id,
            )
        )
    ).all()
    for db_class in classes:
        before = _class_demand_snapshot(db_class)
        db_class.home_room_id = None
        await record_scheduler_change(
            db,
            organization_id,
            entity_type="CLASS_DEMAND",
            entity_id=db_class.id,
            operation=models.SchedulerStateChangeOperation.UPDATE,
            before=before,
            after=_class_demand_snapshot(db_class),
            changed_by_membership_id=changed_by_membership_id,
            active_resource=not db_class.is_archived,
        )
    await db.flush()


async def delete_class_in_course(
    db: AsyncSession,
    course_id: int,
    class_id: int,
    organization_id: int,
    changed_by_membership_id: int | None = None,
) -> str:
    """Remove uma turma da gestão atual e devolve o efeito aplicado.

    Uma turma publicada ou com operação em curso fica bloqueada. Com histórico
    (horários, sumários, progresso ou fluxos) é arquivada; sem referências é
    eliminada fisicamente. As disciplinas atribuídas e as regras são retiradas
    na mesma transação.
    """
    db_class = await _get_class_by_course_and_org(db, class_id, course_id, organization_id)
    if not db_class:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Class {class_id} was not found in course {course_id}.",
        )

    if await resource_removal.class_in_use(db, organization_id, class_id):
        raise AppError(
            kind="conflict",
            code="resource_in_use",
            detail=f"Class {class_id} is used by the active schedule.",
        )

    before = _class_demand_snapshot(db_class)
    effect = (
        "archive"
        if await resource_removal.class_has_history(db, organization_id, class_id)
        else "hard_delete"
    )
    await resource_removal.remove_class_configuration(db, organization_id, class_id)

    if effect == "hard_delete":
        operation = models.SchedulerStateChangeOperation.DELETE
        after = None
        await db.execute(delete(models.Class).where(models.Class.id == class_id))
    else:
        operation = models.SchedulerStateChangeOperation.UPDATE
        db_class.is_archived = True
        after = _class_demand_snapshot(db_class)

    await record_scheduler_change(
        db,
        organization_id,
        entity_type="CLASS_DEMAND",
        entity_id=db_class.id,
        operation=operation,
        before=before,
        after=after,
        changed_by_membership_id=changed_by_membership_id,
        active_resource=False,
    )
    await db.flush()
    return effect


# ==========================================
#  DASHBOARD DA TURMA (ClassFullDetail)
# ==========================================


def _build_module_data(module, progress_map: dict) -> dict:
    """Constrói dados de um módulo com o seu progresso atual."""
    progress = progress_map.get(module.id)
    completed_minutes, debt_minutes = progress or (0, 0)
    hours_done = completed_minutes / 60
    hours_debt = debt_minutes / 60
    completed = completed_minutes >= module.hours_total * 60
    pct = (
        min(100.0, round((hours_done / module.hours_total) * 100, 1))
        if module.hours_total > 0
        else 0.0
    )

    return {
        "id": module.id,
        "name": module.name,
        "code": module.code,
        "hours_total": float(module.hours_total),
        "order": module.order,
        "hours_completed": round(hours_done, 1),
        "hours_debt": round(hours_debt, 1),
        "is_completed": completed,
        "percentage": pct,
    }


def _subject_modules_payload(modules, selected_ids: set[int]) -> list[dict]:
    """Lista os módulos da disciplina por ordem, marcando os selecionados."""
    return [
        {
            "id": module.id,
            "name": module.name,
            "code": module.code,
            "hours_total": float(module.hours_total),
            "order": module.order,
            "selected": module.id in selected_ids,
        }
        for module in sorted(modules, key=lambda m: m.order)
    ]


def _build_subject_with_progress(subject, selected_modules, progress_map: dict) -> dict:
    """Constrói dados de uma disciplina a partir dos módulos selecionados."""
    modules_data = []
    subject_total = 0.0
    subject_completed = 0.0

    for module in sorted(selected_modules, key=lambda m: m.order):
        module_data = _build_module_data(module, progress_map)
        modules_data.append(module_data)
        subject_total += module.hours_total
        progress = progress_map.get(module.id)
        if progress:
            subject_completed += progress[0] / 60

    overall_pct = (
        min(100.0, round((subject_completed / subject_total) * 100, 1))
        if subject_total > 0
        else 0.0
    )

    return {
        "id": subject.id,
        "name": subject.name,
        "room_type": subject.room_type,
        "modules": modules_data,
        "total_hours": round(subject_total, 1),
        "completed_hours": round(subject_completed, 1),
        "overall_percentage": overall_pct,
    }


async def get_class_full_details(db: AsyncSession, class_id: int, organization_id: int):
    """
    Busca turma com curso, disciplinas, módulos e progresso.
    Retorna a árvore completa para o dashboard da turma (ClassDetails.jsx).

    FONTE DE VERDADE: ClassSubjectLink (as disciplinas atribuídas à turma),
    NÃO a lista de disciplinas do curso. Isto permite que cada turma tenha
    disciplinas diferentes, refletindo a gestão feita na página ClassSubjects.

    4 Pilares:
    🔐 Security: Filtra por organization_id — cada organização só vê suas turmas
    ⚡ Optimization: 2 queries com selectinload (vs N+1 de lazy loading)
    ⚙️ Stability: Progresso calculado server-side como fonte de verdade única
    📈 Scalability: Padrão extensível para futuras features (alunos, notas)
    """
    # 1. Buscar turma com curso
    query = (
        select(models.Class)
        .where(models.Class.id == class_id, models.Class.organization_id == organization_id)
        .options(
            selectinload(models.Class.course),
            joinedload(models.Class.home_room).joinedload(models.Room.room_type),
        )
    )
    result = await db.execute(query)
    db_class = result.scalars().first()

    if not db_class:
        return None

    # 2. Construir base da resposta
    response = {
        "id": db_class.id,
        "name": db_class.name,
        "size": db_class.size,
        "grade_level": db_class.grade_level,
        "start_year": db_class.start_year,
        "end_year": db_class.end_year,
        "organization_id": db_class.organization_id,
        "course_id": db_class.course_id,
        "course": db_class.course,
        "home_room_id": db_class.home_room_id,
        "home_room": db_class.home_room,
        "subjects": [],
    }

    # 3. Buscar disciplinas da turma via ClassSubjectLink (fonte de verdade)
    links_query = (
        select(models.ClassSubjectLink)
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.class_id == class_id,
            models.ClassSubjectLink.grade_level == db_class.grade_level,
        )
        .options(*_LINK_SUBJECT_OPTIONS)
    )
    links_result = await db.execute(links_query)
    links = links_result.scalars().all()

    if not links:
        return response

    # 4. Buscar progresso EXPLICITAMENTE por class_id (isolamento de turma).
    #    A nova contabilização v1 é a fonte de verdade quando existir.
    progress_map = await class_progress_map(db, organization_id, class_id)
    if progress_map is None:
        progress_query = (
            select(
                models.ProgressLedgerEntry.module_id,
                func.coalesce(func.sum(models.ProgressLedgerEntry.completed_minutes_delta), 0),
                func.coalesce(func.sum(models.ProgressLedgerEntry.debt_minutes_delta), 0),
            )
            .where(
                models.ProgressLedgerEntry.organization_id == organization_id,
                models.ProgressLedgerEntry.class_id == class_id,
            )
            .group_by(models.ProgressLedgerEntry.module_id)
        )
        progress_result = await db.execute(progress_query)
        progress_map = {row[0]: (int(row[1]), int(row[2])) for row in progress_result.all()}

    # 5. Construir árvore de disciplinas com progresso dos módulos marcados
    selected_map = await _selected_module_map(db, organization_id, [link.id for link in links])
    for link in sorted(links, key=lambda item: item.subject.name if item.subject else ""):
        subject = link.subject
        if not subject:
            continue
        selected_ids = selected_map.get(link.id, set())
        selected_modules = [module for module in subject.modules if module.id in selected_ids]
        response["subjects"].append(
            _build_subject_with_progress(subject, selected_modules, progress_map)
        )

    return response


async def update_class_progress(
    db: AsyncSession,
    class_id: int,
    progress_updates: list[schemas.ClassProgressUpdate],
    organization_id: int,
    *,
    membership_id: int | None = None,
    now_utc: datetime | None = None,
):
    """
    Atualiza o progresso de módulos para uma turma (upsert).
    Auto-calcula is_completed quando hours_completed >= hours_total.

    FONTE DE VERDADE: ClassSubjectLink — só permite atualizar módulos
    de disciplinas effectivamente atribuídas à turma.

    4 Pilares:
    🔐 Security: Valida turma pertence à org + módulo pertence às disciplinas da turma
    ⚡ Optimization: Upsert batch via ON CONFLICT (evita N queries individuais)
    ⚙️ Stability: Transação atómica — ou atualiza tudo ou nada
    📈 Scalability: Suporta atualização de múltiplos módulos de uma vez
    """
    # 1. Validar turma existe e pertence à org
    db_class = await _get_class_by_org(db, class_id, organization_id)

    if not db_class:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Class {class_id} was not found in organization {organization_id}.",
        )

    # 2. Carregar a seleção atual do ano da turma e validar os módulos pedidos
    #    antes de qualquer escrita, no caminho v1 ou no caminho legado.
    links_query = (
        select(models.ClassSubjectLink)
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.class_id == class_id,
            models.ClassSubjectLink.grade_level == db_class.grade_level,
        )
        .options(*_LINK_SUBJECT_OPTIONS)
    )
    links_result = await db.execute(links_query)
    links = links_result.scalars().all()

    if not links:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Class {class_id} has no assigned subjects.",
        )

    # Construir mapa dos módulos marcados: {module_id: hours_total}
    selected_map = await _selected_module_map(db, organization_id, [link.id for link in links])
    valid_modules = {
        module.id: module.hours_total
        for link in links
        if link.subject is not None
        for module in link.subject.modules
        if module.id in selected_map.get(link.id, set())
    }

    for update in progress_updates:
        if update.module_id not in valid_modules:
            raise AppError(
                kind="bad_request",
                code="bad_request",
                detail=f"Module {update.module_id} is not assigned to class {class_id}.",
            )

    # 3. Quando a nova contabilização existe, os acertos vão para o ledger v1.
    if membership_id is not None:
        handled = await adjust_class_progress(
            db,
            organization_id,
            class_id,
            progress_updates,
            membership_id=membership_id,
            now_utc=now_utc or datetime.now(UTC),
        )
        if handled:
            return

    # 4. Sem dados v1, mantém o caminho legado (removido na W12).
    # Append adjustments; the ledger is the only stored progress truth.
    for update in progress_updates:
        hours_total = valid_modules[update.module_id]
        target_minutes = int(round(min(update.hours_completed, hours_total) * 60))
        current_minutes = await db.scalar(
            select(
                func.coalesce(func.sum(models.ProgressLedgerEntry.completed_minutes_delta), 0)
            ).where(
                models.ProgressLedgerEntry.organization_id == organization_id,
                models.ProgressLedgerEntry.class_id == class_id,
                models.ProgressLedgerEntry.module_id == update.module_id,
            )
        )
        delta = target_minutes - int(current_minutes or 0)
        if delta:
            db.add(
                models.ProgressLedgerEntry(
                    organization_id=organization_id,
                    source_type="MANUAL_ADJUSTMENT",
                    source_id=class_id,
                    class_id=class_id,
                    module_id=update.module_id,
                    completed_minutes_delta=delta,
                    debt_minutes_delta=0,
                    idempotency_key=f"manual:{organization_id}:{class_id}:{update.module_id}:{uuid.uuid4()}",
                )
            )

    await db.flush()


# ==========================================
#  DISCIPLINAS DA TURMA (Class-Subject Link)
#  Gestão curso-cêntrica de professores
# ==========================================


async def get_class_subjects(db: AsyncSession, class_id: int, organization_id: int):
    """
    Lista disciplinas associadas à turma (para o grade_level atual).
    Inclui professor atribuído (se houver).

    Retorna: ClassSubjectsListRead
    """
    # 1. Buscar turma com curso
    class_query = (
        select(models.Class)
        .where(models.Class.id == class_id, models.Class.organization_id == organization_id)
        .options(selectinload(models.Class.course))
    )

    result = await db.execute(class_query)
    db_class = result.scalars().first()

    if not db_class:
        return None

    # 2. Buscar disciplinas associadas à turma para o grade_level atual
    links_query = (
        select(models.ClassSubjectLink)
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.class_id == class_id,
            models.ClassSubjectLink.grade_level == db_class.grade_level,
        )
        .options(
            selectinload(models.ClassSubjectLink.subject).joinedload(models.Subject.room_type),
            selectinload(models.ClassSubjectLink.teacher),
        )
    )

    links_result = await db.execute(links_query)
    links = links_result.scalars().all()

    # 3. Catálogo e seleção numa só consulta; construir a resposta
    catalogue, selected_by_link = await _subject_catalogue_with_selection(
        db, organization_id, links
    )

    # 3b. Junção de cada ligação, numa única consulta em lote (J02).
    link_ids = [link.id for link in links]
    joint_by_link = await joint_lesson_service.load_joint_groups_by_link(
        db, organization_id, link_ids
    )

    # 4. Construir resposta
    subjects_data = []
    for link in sorted(links, key=lambda item: item.subject.name if item.subject else ""):
        subjects_data.append(
            {
                "id": link.id,
                "subject_id": link.subject_id,
                "subject_name": link.subject.name if link.subject else "",
                "room_type": link.subject.room_type if link.subject else None,
                "grade_level": link.grade_level,
                "teacher_id": link.teacher_id,
                "teacher_name": link.teacher.name if link.teacher else None,
                "modules": _subject_modules_payload(
                    catalogue.get(link.subject_id, []), selected_by_link.get(link.id, set())
                ),
                "joint_group": joint_by_link.get(link.id),
            }
        )

    return {
        "class_id": db_class.id,
        "class_name": db_class.name,
        "course_name": db_class.course.name if db_class.course else None,
        "course_abbreviation": db_class.course.abbreviation if db_class.course else None,
        "grade_level": db_class.grade_level,
        "subjects": subjects_data,
    }


async def add_class_subject(
    db: AsyncSession,
    class_id: int,
    subject_id: int,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    """
    Adiciona uma disciplina à turma (para o grade_level atual).

    Validações:
    - Turma existe e pertence à org
    - Disciplina existe e pertence à org
    - Disciplina não está já associada à turma neste grade_level
    """
    # 1. Buscar turma
    db_class = await _get_class_by_org(db, class_id, organization_id)

    if not db_class:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Class {class_id} was not found in organization {organization_id}.",
        )
    if db_class.is_archived:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Class {class_id} is archived and cannot receive new subjects.",
        )

    # 2. Buscar disciplina
    subject_query = select(models.Subject).where(
        models.Subject.id == subject_id, models.Subject.organization_id == organization_id
    )
    subject_result = await db.execute(subject_query)
    db_subject = subject_result.scalars().first()

    if not db_subject:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Subject {subject_id} was not found in organization {organization_id}.",
        )
    if db_subject.is_archived:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Subject {subject_id} is archived and cannot be assigned.",
        )

    # 3. Verificar se já existe
    existing_query = select(models.ClassSubjectLink).where(
        models.ClassSubjectLink.organization_id == organization_id,
        models.ClassSubjectLink.class_id == class_id,
        models.ClassSubjectLink.subject_id == subject_id,
        models.ClassSubjectLink.grade_level == db_class.grade_level,
    )
    existing_result = await db.execute(existing_query)

    if existing_result.scalars().first():
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Subject {subject_id} is already assigned to class {class_id}.",
        )

    # 4. Criar associação
    link = models.ClassSubjectLink(
        organization_id=organization_id,
        class_id=class_id,
        subject_id=subject_id,
        grade_level=db_class.grade_level,
        teacher_id=None,
    )
    db.add(link)

    # 5. Sync currículo: garantir que a disciplina está no course_subject_link
    existing_cs = await db.execute(
        select(models.course_subject_link).where(
            models.course_subject_link.c.organization_id == organization_id,
            models.course_subject_link.c.course_id == db_class.course_id,
            models.course_subject_link.c.subject_id == subject_id,
        )
    )
    if not existing_cs.first():
        await db.execute(
            models.course_subject_link.insert().values(
                organization_id=organization_id, course_id=db_class.course_id, subject_id=subject_id
            )
        )

    await db.flush()
    # D03: a new class subject starts with every module of the subject selected.
    module_ids = (
        await db.scalars(
            select(models.Module.id)
            .where(
                models.Module.organization_id == organization_id,
                models.Module.subject_id == subject_id,
            )
            .order_by(models.Module.order)
        )
    ).all()
    if module_ids:
        await db.execute(
            models.class_subject_module.insert(),
            [
                {
                    "organization_id": organization_id,
                    "class_subject_link_id": link.id,
                    "module_id": module_id,
                }
                for module_id in module_ids
            ],
        )
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="CLASS_SUBJECT_ASSIGNMENT",
        entity_id=link.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after=_class_subject_snapshot(link, module_ids),
        changed_by_membership_id=changed_by_membership_id,
        active_resource=not db_class.is_archived,
    )
    await db.flush()
    await db.refresh(link)

    return link


async def update_class_subject(
    db: AsyncSession,
    class_id: int,
    subject_id: int,
    payload: schemas.ClassSubjectUpdate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    """
    Atualiza uma associação disciplina-turma: professor e/ou módulos selecionados.

    Usa exclude_unset para distinguir entre 'não enviado' e 'enviado'.
    Uma lista vazia de module_ids é válida e substitui a seleção (D06).

    Validações (antes de qualquer alteração):
    - Associação existe
    - Se teacher_id não é None, professor existe e tem competência na disciplina
    - Módulos repetidos ou de outra disciplina devolvem 400
    - Módulo de outra organização devolve 404
    """
    update_data = payload.model_dump(exclude_unset=True)

    # 1. Buscar turma para obter grade_level
    db_class = await _get_class_by_org(db, class_id, organization_id)

    if not db_class:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Class {class_id} was not found in organization {organization_id}.",
        )
    if db_class.is_archived:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Class {class_id} is archived and cannot be edited.",
        )

    # 2. Buscar associação
    link_query = select(models.ClassSubjectLink).where(
        models.ClassSubjectLink.organization_id == organization_id,
        models.ClassSubjectLink.class_id == class_id,
        models.ClassSubjectLink.subject_id == subject_id,
        models.ClassSubjectLink.grade_level == db_class.grade_level,
    )
    link_result = await db.execute(link_query)
    link = link_result.scalars().first()

    if not link:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Subject {subject_id} is not assigned to class {class_id}.",
        )
    current_module_ids = await _load_link_module_ids(db, organization_id, link.id)
    before = _class_subject_snapshot(link, current_module_ids)
    joint_group_id = await _joint_group_for_link(db, organization_id, link.id)

    # 3. Se teacher_id foi enviado, validar
    if update_data.get("teacher_id") is not None:
        teacher_id = update_data["teacher_id"]
        # Validar professor existe e pertence à org
        teacher_query = (
            select(models.Teacher)
            .where(
                models.Teacher.id == teacher_id,
                models.Teacher.organization_id == organization_id,
            )
            .options(selectinload(models.Teacher.subjects))
        )

        teacher_result = await db.execute(teacher_query)
        db_teacher = teacher_result.scalars().first()

        if not db_teacher:
            raise AppError(
                kind="not_found",
                code="resource_not_found",
                detail=f"Teacher {teacher_id} was not found in organization {organization_id}.",
            )

        # Validar professor tem competência na disciplina
        teacher_subject_ids = [s.id for s in db_teacher.subjects]
        if subject_id not in teacher_subject_ids:
            raise AppError(
                kind="bad_request",
                code="teacher_competency_missing",
                detail=f"Teacher {teacher_id} is not qualified for subject {subject_id}.",
            )

    # 4. Se module_ids foi enviado, validar a lista antes de substituir
    module_ids = update_data.get("module_ids")
    replace_modules = "module_ids" in update_data and module_ids is not None
    unique_module_ids: list[int] = []
    if replace_modules:
        unique_module_ids = list(dict.fromkeys(module_ids))
        if len(unique_module_ids) != len(module_ids):
            raise AppError(
                kind="bad_request",
                code="bad_request",
                detail="module_ids contains duplicate modules.",
            )
        module_rows = (
            await db.execute(
                select(models.Module.id, models.Module.subject_id).where(
                    models.Module.organization_id == organization_id,
                    models.Module.id.in_(unique_module_ids),
                )
            )
        ).all()
        subject_by_module = {
            module_id: module_subject_id for module_id, module_subject_id in module_rows
        }
        for module_id in unique_module_ids:
            if module_id not in subject_by_module:
                raise AppError(
                    kind="not_found",
                    code="resource_not_found",
                    detail=f"Module {module_id} was not found in organization {organization_id}.",
                )
            if subject_by_module[module_id] != subject_id:
                raise AppError(
                    kind="bad_request",
                    code="bad_request",
                    detail=f"Module {module_id} does not belong to subject {subject_id}.",
                )

    # 5. Substituir a seleção de módulos quando enviada.
    #    Numa junção, um módulo da aula conjunta não pode ser retirado (J05).
    next_module_ids = current_module_ids
    if replace_modules:
        next_module_ids = sorted(unique_module_ids)
        if joint_group_id is not None:
            joint_module_ids = await _joint_module_ids(db, organization_id, joint_group_id)
            if set(joint_module_ids) - set(next_module_ids):
                raise AppError(
                    kind="conflict",
                    code="JOINT_MODULE_LOCKED",
                    detail="Retire primeiro este módulo da aula conjunta.",
                )
        await _replace_link_modules(db, organization_id, link.id, next_module_ids)

    # 6. Aplicar alterações ao professor
    if "teacher_id" in update_data:
        link.teacher_id = update_data["teacher_id"]

    # 5b. Numa junção, o professor muda em todas as ligações membro (J06).
    if joint_group_id is not None and "teacher_id" in update_data:
        member_link_ids = await _joint_member_link_ids(db, organization_id, joint_group_id)
        await db.execute(
            sql_update(models.ClassSubjectLink)
            .where(
                models.ClassSubjectLink.organization_id == organization_id,
                models.ClassSubjectLink.id.in_(member_link_ids),
            )
            .values(teacher_id=link.teacher_id)
            .execution_options(synchronize_session=False)
        )

    await record_scheduler_change(
        db,
        organization_id,
        entity_type="CLASS_SUBJECT_ASSIGNMENT",
        entity_id=link.id,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before=before,
        after=_class_subject_snapshot(link, next_module_ids),
        changed_by_membership_id=changed_by_membership_id,
        active_resource=not db_class.is_archived,
    )
    await db.flush()
    await db.refresh(link)

    return link


async def remove_class_subject(
    db: AsyncSession,
    class_id: int,
    subject_id: int,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    """
    Remove uma disciplina da turma (para o grade_level atual).
    """
    # 1. Buscar turma
    db_class = await _get_class_by_org(db, class_id, organization_id)

    if not db_class:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Class {class_id} was not found in organization {organization_id}.",
        )

    # 2. Buscar associação
    link_query = select(models.ClassSubjectLink).where(
        models.ClassSubjectLink.organization_id == organization_id,
        models.ClassSubjectLink.class_id == class_id,
        models.ClassSubjectLink.subject_id == subject_id,
        models.ClassSubjectLink.grade_level == db_class.grade_level,
    )
    link_result = await db.execute(link_query)
    link = link_result.scalars().first()

    if not link:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Subject {subject_id} is not assigned to class {class_id}.",
        )
    before = _class_subject_snapshot(
        link, await _load_link_module_ids(db, organization_id, link.id)
    )
    if await _joint_group_for_link(db, organization_id, link.id) is not None:
        raise AppError(
            kind="conflict",
            code="resource_in_use",
            detail="A ligação pertence a uma aula conjunta.",
        )
    # 3. Remover
    await db.delete(link)

    # 4. Sync currículo: se nenhuma outra turma do curso usa esta disciplina, remover do currículo
    course_id = db_class.course_id
    # Subquery: IDs de turmas do mesmo curso
    course_class_ids = select(models.Class.id).where(
        models.Class.organization_id == organization_id,
        models.Class.course_id == course_id,
    )
    other_links = await db.execute(
        select(models.ClassSubjectLink.id).where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.subject_id == subject_id,
            models.ClassSubjectLink.class_id.in_(course_class_ids),
            models.ClassSubjectLink.id != link.id,
        )
    )
    if not other_links.scalars().first():
        await db.execute(
            models.course_subject_link.delete().where(
                models.course_subject_link.c.organization_id == organization_id,
                models.course_subject_link.c.course_id == course_id,
                models.course_subject_link.c.subject_id == subject_id,
            )
        )

    await record_scheduler_change(
        db,
        organization_id,
        entity_type="CLASS_SUBJECT_ASSIGNMENT",
        entity_id=link.id,
        operation=models.SchedulerStateChangeOperation.DELETE,
        before=before,
        after=None,
        changed_by_membership_id=changed_by_membership_id,
        active_resource=not db_class.is_archived,
    )
    await db.flush()


async def get_available_subjects_for_class(db: AsyncSession, class_id: int, organization_id: int):
    """
    Lista disciplinas disponíveis para adicionar à turma.
    (Disciplinas da org que ainda não estão associadas à turma neste grade_level)
    """
    # 1. Buscar turma
    db_class = await _get_class_by_org(db, class_id, organization_id)

    if not db_class:
        return []

    # 2. Buscar IDs das disciplinas já associadas
    existing_query = select(models.ClassSubjectLink.subject_id).where(
        models.ClassSubjectLink.organization_id == organization_id,
        models.ClassSubjectLink.class_id == class_id,
        models.ClassSubjectLink.grade_level == db_class.grade_level,
    )
    existing_result = await db.execute(existing_query)
    existing_ids = {row[0] for row in existing_result.all()}

    # 3. Buscar todas as disciplinas da org que não estão associadas
    if existing_ids:
        subjects_query = (
            select(models.Subject)
            .options(selectinload(models.Subject.modules), joinedload(models.Subject.room_type))
            .where(
                models.Subject.organization_id == organization_id,
                models.Subject.is_archived.is_(False),
                models.Subject.id.notin_(existing_ids),
            )
            .order_by(models.Subject.name)
        )
    else:
        subjects_query = (
            select(models.Subject)
            .options(selectinload(models.Subject.modules), joinedload(models.Subject.room_type))
            .where(
                models.Subject.organization_id == organization_id,
                models.Subject.is_archived.is_(False),
            )
            .order_by(models.Subject.name)
        )

    subjects_result = await db.execute(subjects_query)
    return subjects_result.scalars().all()


async def get_eligible_teachers_for_subject(
    db: AsyncSession, subject_id: int, organization_id: int
):
    """
    Lista professores elegíveis para lecionar uma disciplina.
    (Professores que têm competência na disciplina via teacher_subject_link)

    Também indica quantas turmas o professor já tem atribuídas.

    Optimization (P1): Usa SQL JOIN via teacher_subject_link em vez de
    carregar todos os professores e filtrar em Python.
    """
    from sqlalchemy import func

    # 1. Buscar disciplina para validar que pertence à org
    subject_query = select(models.Subject).where(
        models.Subject.id == subject_id, models.Subject.organization_id == organization_id
    )
    subject_result = await db.execute(subject_query)
    db_subject = subject_result.scalars().first()

    if not db_subject:
        return []

    # 2. Buscar professores com competência via JOIN (não carrega todos)
    teachers_query = (
        select(models.Teacher)
        .join(
            models.teacher_subject_link,
            models.Teacher.id == models.teacher_subject_link.c.teacher_id,
        )
        .join(
            models.OrganizationMembership,
            models.OrganizationMembership.id == models.Teacher.organization_membership_id,
        )
        .where(
            models.teacher_subject_link.c.subject_id == subject_id,
            models.teacher_subject_link.c.organization_id == organization_id,
            models.Teacher.organization_id == organization_id,
            models.OrganizationMembership.organization_id == organization_id,
            models.OrganizationMembership.lifecycle_status
            == models.MembershipLifecycleStatus.active,
            models.OrganizationMembership.can_teach.is_(True),
        )
        .order_by(models.Teacher.name)
    )

    teachers_result = await db.execute(teachers_query)
    eligible = teachers_result.scalars().all()

    if not eligible:
        return []

    # 3. Contar quantas turmas cada professor já tem para esta disciplina
    counts_query = (
        select(
            models.ClassSubjectLink.teacher_id,
            func.count(models.ClassSubjectLink.id).label("count"),
        )
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.subject_id == subject_id,
            models.ClassSubjectLink.teacher_id.isnot(None),
        )
        .group_by(models.ClassSubjectLink.teacher_id)
    )

    counts_result = await db.execute(counts_query)
    counts_map = {row[0]: row[1] for row in counts_result.all()}

    # 4. Construir resposta
    result = []
    for teacher in eligible:
        result.append(
            {
                "id": teacher.id,
                "name": teacher.name,
                "is_assigned_elsewhere": teacher.id in counts_map,
                "current_classes_count": counts_map.get(teacher.id, 0),
            }
        )

    return result
