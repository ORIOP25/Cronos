"""School room types: listing, editing and the idempotent initial seeding.

Room types belong to one school. The Normal type is fixed, a type in use cannot
be removed, and a type only kept by archived objects is archived so a later
create with the same name restores it. Names are compared with accents and case
folded (``fold_text``); the case-only unique index cannot express that, so every
catalogue write locks the school row before the lookup and the mutation.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.core.exceptions import AppError
from app.services import resource_removal
from app.services.bulk_import_policy import fold_text

DEFAULT_ROOM_TYPES: tuple[tuple[str, bool], ...] = (
    ("Normal", True),
    ("Laboratório", False),
    ("Ginásio", False),
    ("Artes", False),
)


def _not_found() -> AppError:
    return AppError(kind="not_found", code="resource_not_found", detail="Room type not found")


def _name_taken() -> AppError:
    return AppError(
        kind="conflict", code="room_type_name_taken", detail="Room type name already exists"
    )


def _normal_is_fixed() -> AppError:
    return AppError(
        kind="conflict",
        code="room_type_fixed",
        detail="The Normal room type cannot be renamed or removed",
    )


async def _lock_catalogue(db: AsyncSession, organization_id: int) -> None:
    """Serialize the room-type writes of one school.

    The folded-name uniqueness is a service rule, so the school row is locked
    before the fold lookup and the mutation. This is the organization-first lock
    order already used by the foundation and settings services, and it keeps a
    concurrent create or rename from committing a name that only differs by case
    or accents.
    """
    locked = await db.scalar(
        select(models.Organization.id)
        .where(models.Organization.id == organization_id)
        .with_for_update()
    )
    if locked is None:
        raise AppError(kind="not_found", code="resource_not_found", detail="Organization not found")


async def _load_active(
    db: AsyncSession, organization_id: int, room_type_id: int
) -> models.SchoolRoomType:
    room_type = await db.scalar(
        select(models.SchoolRoomType).where(
            models.SchoolRoomType.id == room_type_id,
            models.SchoolRoomType.organization_id == organization_id,
            models.SchoolRoomType.is_archived.is_(False),
        )
    )
    if room_type is None:
        raise _not_found()
    return room_type


async def resolve_active_room_type(
    db: AsyncSession, organization_id: int, room_type_id: int | None
) -> models.SchoolRoomType:
    """Tipo de sala que uma sala ou disciplina tem de usar.

    Sem identificador vale o tipo Normal da escola. Qualquer identificador
    desconhecido, de outra escola ou arquivado tem a mesma resposta de não
    encontrado da API dos tipos. A escola é bloqueada primeiro, pela mesma ordem
    das escritas do catálogo, para que uma remoção em curso não deixe um objeto
    ativo a apontar para um tipo arquivado.
    """
    await _lock_catalogue(db, organization_id)
    if room_type_id is not None:
        return await _load_active(db, organization_id, room_type_id)

    normal = await db.scalar(
        select(models.SchoolRoomType).where(
            models.SchoolRoomType.organization_id == organization_id,
            models.SchoolRoomType.is_normal.is_(True),
            models.SchoolRoomType.is_archived.is_(False),
        )
    )
    if normal is None:
        raise _not_found()
    return normal


async def _find_by_folded_name(
    db: AsyncSession, organization_id: int, name: str
) -> models.SchoolRoomType | None:
    folded = fold_text(name)
    room_types = (
        await db.scalars(
            select(models.SchoolRoomType).where(
                models.SchoolRoomType.organization_id == organization_id
            )
        )
    ).all()
    for room_type in room_types:
        if fold_text(room_type.name) == folded:
            return room_type
    return None


async def _active_counts(
    db: AsyncSession, organization_id: int
) -> tuple[dict[int, int], dict[int, int]]:
    room_counts = dict(
        (
            await db.execute(
                select(models.Room.room_type_id, func.count())
                .where(
                    models.Room.organization_id == organization_id,
                    models.Room.is_archived.is_(False),
                    models.Room.room_type_id.is_not(None),
                )
                .group_by(models.Room.room_type_id)
            )
        ).all()
    )
    subject_counts = dict(
        (
            await db.execute(
                select(models.Subject.room_type_id, func.count())
                .where(
                    models.Subject.organization_id == organization_id,
                    models.Subject.is_archived.is_(False),
                    models.Subject.room_type_id.is_not(None),
                )
                .group_by(models.Subject.room_type_id)
            )
        ).all()
    )
    return room_counts, subject_counts


async def _read(
    db: AsyncSession, organization_id: int, room_type: models.SchoolRoomType
) -> schemas.RoomTypeRead:
    room_counts, subject_counts = await _active_counts(db, organization_id)
    return schemas.RoomTypeRead(
        id=room_type.id,
        name=room_type.name,
        is_normal=room_type.is_normal,
        room_count=room_counts.get(room_type.id, 0),
        subject_count=subject_counts.get(room_type.id, 0),
    )


async def list_room_types(db: AsyncSession, organization_id: int) -> list[schemas.RoomTypeRead]:
    room_types = (
        await db.scalars(
            select(models.SchoolRoomType)
            .where(
                models.SchoolRoomType.organization_id == organization_id,
                models.SchoolRoomType.is_archived.is_(False),
            )
            .order_by(models.SchoolRoomType.is_normal.desc(), models.SchoolRoomType.name)
        )
    ).all()
    room_counts, subject_counts = await _active_counts(db, organization_id)
    return [
        schemas.RoomTypeRead(
            id=room_type.id,
            name=room_type.name,
            is_normal=room_type.is_normal,
            room_count=room_counts.get(room_type.id, 0),
            subject_count=subject_counts.get(room_type.id, 0),
        )
        for room_type in room_types
    ]


async def create_room_type(
    db: AsyncSession, data: schemas.RoomTypeCreate, organization_id: int
) -> schemas.RoomTypeRead:
    await _lock_catalogue(db, organization_id)
    existing = await _find_by_folded_name(db, organization_id, data.name)
    if existing is not None:
        if not existing.is_archived:
            raise _name_taken()
        existing.is_archived = False
        await db.flush()
        return await _read(db, organization_id, existing)

    room_type = models.SchoolRoomType(
        organization_id=organization_id, name=data.name, is_normal=False
    )
    db.add(room_type)
    await db.flush()
    return await _read(db, organization_id, room_type)


async def rename_room_type(
    db: AsyncSession,
    room_type_id: int,
    data: schemas.RoomTypeUpdate,
    organization_id: int,
) -> schemas.RoomTypeRead:
    await _lock_catalogue(db, organization_id)
    room_type = await _load_active(db, organization_id, room_type_id)
    if room_type.is_normal:
        raise _normal_is_fixed()

    conflict = await _find_by_folded_name(db, organization_id, data.name)
    if conflict is not None and conflict.id != room_type.id:
        raise _name_taken()

    room_type.name = data.name
    await db.flush()
    return await _read(db, organization_id, room_type)


async def remove_room_type(db: AsyncSession, room_type_id: int, organization_id: int) -> str:
    await _lock_catalogue(db, organization_id)
    room_type = await _load_active(db, organization_id, room_type_id)
    if room_type.is_normal:
        raise _normal_is_fixed()

    references = await resource_removal.room_type_active_references(
        db, organization_id, room_type_id
    )
    if references["rooms"] or references["subjects"]:
        raise AppError(
            kind="conflict",
            code="resource_in_use",
            detail="Room type is used by active rooms or subjects",
            public_context=references,
        )

    if await resource_removal.room_type_has_history(db, organization_id, room_type_id):
        room_type.is_archived = True
        await db.flush()
        return "archive"

    await db.delete(room_type)
    await db.flush()
    return "hard_delete"


async def ensure_room_type(
    db: AsyncSession, organization_id: int, name: str
) -> models.SchoolRoomType:
    """Tipo ativo com este nome dobrado: usa o existente, restaura o arquivado ou cria-o.

    Usa-o a importação CSV (D18), que cria cada nome uma só vez e nunca liga um
    nome a um tipo de outra escola.
    """
    await _lock_catalogue(db, organization_id)
    room_type = await _find_by_folded_name(db, organization_id, name)
    if room_type is None:
        room_type = models.SchoolRoomType(
            organization_id=organization_id, name=name, is_normal=False
        )
        db.add(room_type)
    room_type.is_archived = False
    await db.flush()
    return room_type


async def ensure_initial_room_types(db: AsyncSession, organization_id: int) -> None:
    """Create the initial types of a school, idempotent by Normal and folded name."""
    await _lock_catalogue(db, organization_id)
    existing = (
        await db.scalars(
            select(models.SchoolRoomType).where(
                models.SchoolRoomType.organization_id == organization_id
            )
        )
    ).all()
    has_normal = any(room_type.is_normal for room_type in existing)
    folded_names = {fold_text(room_type.name) for room_type in existing}
    for name, is_normal in DEFAULT_ROOM_TYPES:
        if (is_normal and has_normal) or fold_text(name) in folded_names:
            continue
        db.add(
            models.SchoolRoomType(organization_id=organization_id, name=name, is_normal=is_normal)
        )
    await db.flush()
