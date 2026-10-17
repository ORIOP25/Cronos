import base64
import csv
import io
from datetime import date, time
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.config import settings
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from app.services.scheduler_state_service import SchedulerStateService
from tests._support.db_fixtures import (
    create_org_and_user,
    create_teacher_profile,
    get_school_room_type_id,
)

API = settings.API_V1_STR


TEACHER_PRESENCE_HEADER = (
    "Nome do professor;Email do professor;Hora de almoço;"
    "Mínimo de horas por presença;Furo máximo (horas)\r\n"
)
COURSES_HEADER = (
    "Sigla do curso;Nome do curso;Nome da turma;Ano escolar;Ano de início;Ano de fim;"
    "Número de alunos;Sala da turma\r\n"
)


def teacher_presence_row(
    name: str, email: str, lunch: str = "", minimum: str = "", gap: str = ""
) -> str:
    return f"{name};{email};{lunch};{minimum};{gap}\r\n"


async def _org_id(db_session: AsyncSession) -> int:
    return await db_session.scalar(
        select(models.Organization.id).where(models.Organization.clerk_org_id == "org_test_001")
    )


async def _seed_scheduler_year(db_session, organization_id: int) -> models.SchedulerSchoolYear:
    year = models.SchedulerSchoolYear(
        organization_id=organization_id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
        timezone="Europe/Lisbon",
    )
    db_session.add(year)
    await db_session.flush()
    db_session.add(
        models.SchedulerSchoolYearState(organization_id=organization_id, school_year_id=year.id)
    )
    await db_session.flush()
    return year


def csv_payload(filename: str, content: str, *, bom: bool = True) -> dict[str, str]:
    return {
        "filename": filename,
        "content_base64": base64.b64encode(
            (("\ufeff" if bom else "") + content).encode("utf-8")
        ).decode("ascii"),
    }


def valid_files() -> dict[str, dict[str, str]]:
    suffix = uuid4().hex[:8]
    subject = f"Programação {suffix}"
    course = f"Curso {suffix}"
    teacher_email = f"teacher.{suffix}@example.com"
    return {
        "rooms": csv_payload(
            "Cronos_Salas_Template.csv",
            f"Nome da sala;Tipo de sala;Capacidade\r\nSala {suffix};Laboratório;24\r\n",
        ),
        "subjects": csv_payload(
            "Cronos_DisciplinasEModulos_Template.csv",
            f"Nome da disciplina;Tipo de sala;Nome do módulo;Código do módulo;Horas do módulo;Ordem do módulo\r\n"
            f"{subject};Laboratório;Módulo {suffix};M{suffix};30;1\r\n",
        ),
        "courses": csv_payload(
            "Cronos_CursosETurmas_Template.csv",
            f"{COURSES_HEADER}C{suffix[:5].upper()};{course};10.º A;10;2025;2028;24;\r\n",
        ),
        "teachers": csv_payload(
            "Cronos_ProfessoresECompetencias_Template.csv",
            f"Nome do professor;Email do professor;Nome da disciplina\r\nProfessor {suffix};{teacher_email};{subject}\r\n",
        ),
        "assignments": csv_payload(
            "Cronos_Atribuicoes_Template.csv",
            f"Sigla do curso;Nome da turma;Nome da disciplina;Email do professor\r\n"
            f"C{suffix[:5].upper()};10.º A;{subject};{teacher_email}\r\n",
        ),
    }


async def test_bulk_import_validate_and_commit_is_atomic_and_tenant_scoped(
    async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
):
    files = valid_files()

    validation = await async_client.post(
        f"{API}/imports/validate",
        json={"files": files},
        headers=clerk_admin_headers,
    )
    assert validation.status_code == 200
    assert validation.json()["can_commit"] is True
    assert validation.json()["preview"]["counts"]["assignments"] == 1

    commit = await async_client.post(
        f"{API}/imports/commit",
        json={"files": files},
        headers=clerk_admin_headers,
    )
    assert commit.status_code == 201
    created = commit.json()["created_counts"]
    assert created["rooms"] == 1
    assert created["subjects"] == 1
    assert created["courses"] == 1
    assert created["teachers"] == 1
    assert created["assignments"] == 1

    rooms = await async_client.get(f"{API}/rooms/", headers=clerk_admin_headers)
    assert any(item["name"].startswith("Sala ") for item in rooms.json())

    members = await async_client.get(f"{API}/members", headers=clerk_admin_headers)
    imported = [item for item in members.json()["items"] if item["email"].startswith("teacher.")]
    assert imported and imported[0]["teacher_access_mode"] == "scheduler_only"

    # WBS 2.3.4: the CSV assignment marks every module of the subject.
    imported_modules = set((await db_session.execute(select(models.Module.id))).scalars().all())
    selected_modules = set(
        (await db_session.execute(select(models.class_subject_module.c.module_id))).scalars().all()
    )
    assert imported_modules
    assert selected_modules == imported_modules


@pytest.mark.parametrize("resource", ["subjects", "courses"])
async def test_bulk_import_reuses_archived_names_without_changing_history(
    async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict, resource: str
):
    files = valid_files()
    row = next(
        csv.DictReader(
            io.StringIO(base64.b64decode(files[resource]["content_base64"]).decode("utf-8-sig")),
            delimiter=";",
        )
    )
    if resource == "subjects":
        archived = models.Subject(
            organization_id=1,
            name=row["Nome da disciplina"],
            is_archived=True,
            room_type_id=await get_school_room_type_id(db_session, 1, "Normal"),
        )
    else:
        archived = models.Course(
            organization_id=1,
            name=row["Nome do curso"],
            abbreviation=row["Sigla do curso"],
            is_archived=True,
        )
    db_session.add(archived)
    await db_session.commit()

    validation = await async_client.post(
        f"{API}/imports/validate", json={"files": files}, headers=clerk_admin_headers
    )
    assert validation.status_code == 200
    assert validation.json()["can_commit"] is True

    commit = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_admin_headers
    )
    assert commit.status_code == 201, commit.text
    assert commit.json()["created_counts"][resource] == 1

    await db_session.refresh(archived)
    assert archived.is_archived is True
    active = await db_session.scalar(
        select(type(archived)).where(
            type(archived).organization_id == 1,
            type(archived).name == archived.name,
            type(archived).is_archived.is_(False),
        )
    )
    assert active is not None
    assert active.id != archived.id

    repeated = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_admin_headers
    )
    assert repeated.status_code == 422


@pytest.mark.parametrize("resource", ["subjects", "courses"])
async def test_resource_update_reuses_archived_names(
    async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict, resource: str
):
    if resource == "subjects":
        archived = models.Subject(
            organization_id=1,
            name="Nome Livre",
            is_archived=True,
            room_type_id=await get_school_room_type_id(db_session, 1, "Normal"),
        )
        active = models.Subject(
            organization_id=1,
            name="Nome Atual",
            room_type_id=await get_school_room_type_id(db_session, 1, "Normal"),
        )
        payload = {"name": archived.name}
    else:
        archived = models.Course(
            organization_id=1, name="Curso Histórico", abbreviation="LIVRE", is_archived=True
        )
        active = models.Course(organization_id=1, name="Curso Atual", abbreviation="ATUAL")
        payload = {"abbreviation": archived.abbreviation}
    db_session.add_all([archived, active])
    await db_session.commit()

    response = await async_client.patch(
        f"{API}/{resource}/{active.id}", json=payload, headers=clerk_admin_headers
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(archived)
    assert archived.is_archived is True


async def test_bulk_import_rejects_example_without_writing(
    async_client: AsyncClient, clerk_admin_headers: dict
):
    before = await async_client.get(f"{API}/rooms/", headers=clerk_admin_headers)
    response = await async_client.post(
        f"{API}/imports/validate",
        json={
            "files": {
                "rooms": csv_payload(
                    "Cronos_Salas_Template.csv",
                    "Nome da sala;Tipo de sala;Capacidade\r\nSala de Exemplo;Normal;30\r\n",
                )
            }
        },
        headers=clerk_admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["can_commit"] is False
    assert any(issue["code"] == "template_example_present" for issue in response.json()["issues"])
    after = await async_client.get(f"{API}/rooms/", headers=clerk_admin_headers)
    assert len(after.json()) == len(before.json())


async def test_bulk_import_template_has_bom_and_safe_filename(
    async_client: AsyncClient, clerk_admin_headers: dict
):
    response = await async_client.get(f"{API}/imports/templates/rooms", headers=clerk_admin_headers)
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert 'filename="Cronos_Salas_Template.csv"' in response.headers["content-disposition"]
    assert response.content.decode("utf-8-sig").splitlines()[0] == (
        "Nome da sala;Tipo de sala;Capacidade"
    )

    unknown = await async_client.get(
        f"{API}/imports/templates/unknown", headers=clerk_admin_headers
    )
    assert unknown.status_code == 404


async def test_bulk_import_commit_rejects_invalid_revalidation(
    async_client: AsyncClient, clerk_admin_headers: dict
):
    response = await async_client.post(
        f"{API}/imports/commit",
        json={
            "files": {
                "rooms": csv_payload(
                    "Cronos_Salas_Template.csv",
                    "Nome da sala;Tipo de sala;Capacidade\r\nSala de Exemplo;Normal;30\r\n",
                )
            }
        },
        headers=clerk_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["context"]["can_commit"] is False


async def test_bulk_import_accepts_comma_delimited_file_without_bom(
    async_client: AsyncClient, clerk_admin_headers: dict
):
    response = await async_client.post(
        f"{API}/imports/validate",
        json={
            "files": {
                "rooms": csv_payload(
                    "Cronos_Salas_Template.csv",
                    'Nome da sala,Tipo de sala,Capacidade\r\n"Sala, Norte; bloco",artes,20\r\n',
                    bom=False,
                )
            }
        },
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["can_commit"] is True


async def _create_room_type(client: AsyncClient, headers: dict, name: str = "Oficina") -> int:
    resp = await client.post(f"{API}/room-types/", json={"name": name}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_bulk_import_links_the_school_room_type_by_name(
    async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
):
    """S2/R02: a importação liga a sala e a disciplina ao tipo da escola, pelo nome."""
    oficina = await _create_room_type(async_client, clerk_admin_headers)
    suffix = uuid4().hex[:8]

    files = {
        "rooms": csv_payload(
            "Cronos_Salas_Template.csv",
            f"Nome da sala;Tipo de sala;Capacidade\r\nOficina {suffix};oficina;20\r\n",
        ),
        "subjects": csv_payload(
            "Cronos_DisciplinasEModulos_Template.csv",
            "Nome da disciplina;Tipo de sala;Nome do módulo;Código do módulo;"
            "Horas do módulo;Ordem do módulo\r\n"
            f"Oficina {suffix};OFICINA;Módulo {suffix};M{suffix};30;1\r\n",
        ),
    }

    validation = await async_client.post(
        f"{API}/imports/validate", json={"files": files}, headers=clerk_admin_headers
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["can_commit"] is True, validation.text

    commit = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_admin_headers
    )
    assert commit.status_code == 201, commit.text

    org_id = await _org_id(db_session)
    room_type_id = await db_session.scalar(
        select(models.Room.room_type_id).where(
            models.Room.organization_id == org_id,
            models.Room.name == f"Oficina {suffix}",
        )
    )
    subject_type_id = await db_session.scalar(
        select(models.Subject.room_type_id).where(
            models.Subject.organization_id == org_id,
            models.Subject.name == f"Oficina {suffix}",
        )
    )
    assert room_type_id == oficina
    assert subject_type_id == oficina


async def _other_school_admin_headers(db_session: AsyncSession) -> dict:
    await create_org_and_user(
        db_session,
        clerk_user_id="import_admin_b",
        clerk_org_id="org_import_b",
        org_name="Escola Secundária",
    )
    await db_session.commit()
    return {"Authorization": "Bearer test_import_admin_b"}


async def test_bulk_import_does_not_link_a_room_type_of_another_school(
    async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
):
    """S14/R02: um nome igual ao tipo de outra escola cria um tipo novo desta escola."""
    headers_b = await _other_school_admin_headers(db_session)
    oficina_b = await _create_room_type(async_client, headers_b)

    suffix = uuid4().hex[:8]
    files = {
        "rooms": csv_payload(
            "Cronos_Salas_Template.csv",
            f"Nome da sala;Tipo de sala;Capacidade\r\nSala {suffix};Oficina;20\r\n",
        )
    }

    validation = await async_client.post(
        f"{API}/imports/validate", json={"files": files}, headers=clerk_admin_headers
    )
    assert validation.status_code == 200
    assert validation.json()["can_commit"] is True, validation.text
    assert validation.json()["preview"]["counts"]["room_types"] == 1

    commit = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_admin_headers
    )
    assert commit.status_code == 201, commit.text

    org_id = await _org_id(db_session)
    room_type_id = await db_session.scalar(
        select(models.Room.room_type_id).where(
            models.Room.organization_id == org_id,
            models.Room.name == f"Sala {suffix}",
        )
    )
    assert room_type_id is not None
    assert room_type_id != oficina_b
    assert (
        await db_session.scalar(
            select(models.SchoolRoomType.organization_id).where(
                models.SchoolRoomType.id == room_type_id
            )
        )
        == org_id
    )


async def test_bulk_import_creates_one_room_type_for_both_spellings_and_previews_it(
    async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
):
    """S14/R25: o mesmo nome nas salas e nas disciplinas cria um só tipo."""
    suffix = uuid4().hex[:8]
    files = {
        "rooms": csv_payload(
            "Cronos_Salas_Template.csv",
            f"Nome da sala;Tipo de sala;Capacidade\r\nSala {suffix};ateliê {suffix};20\r\n",
        ),
        "subjects": csv_payload(
            "Cronos_DisciplinasEModulos_Template.csv",
            "Nome da disciplina;Tipo de sala;Nome do módulo;Código do módulo;"
            "Horas do módulo;Ordem do módulo\r\n"
            f"Atelier {suffix};ATELIE {suffix};Módulo {suffix};M{suffix};30;1\r\n",
        ),
    }

    validation = await async_client.post(
        f"{API}/imports/validate", json={"files": files}, headers=clerk_admin_headers
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["can_commit"] is True, validation.text
    assert validation.json()["preview"]["counts"]["room_types"] == 1
    assert {
        "resource": "room_types",
        "name": f"ateliê {suffix}",
    } in validation.json()["preview"]["items"]

    commit = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_admin_headers
    )
    assert commit.status_code == 201, commit.text
    assert commit.json()["created_counts"]["room_types"] == 1

    org_id = await _org_id(db_session)
    type_ids = set(
        (
            await db_session.scalars(
                select(models.SchoolRoomType.id).where(
                    models.SchoolRoomType.organization_id == org_id,
                    models.SchoolRoomType.name.in_([f"ateliê {suffix}", f"ATELIE {suffix}"]),
                )
            )
        ).all()
    )
    assert len(type_ids) == 1
    room_type_id = await db_session.scalar(
        select(models.Room.room_type_id).where(
            models.Room.organization_id == org_id, models.Room.name == f"Sala {suffix}"
        )
    )
    subject_type_id = await db_session.scalar(
        select(models.Subject.room_type_id).where(
            models.Subject.organization_id == org_id, models.Subject.name == f"Atelier {suffix}"
        )
    )
    assert room_type_id == subject_type_id == type_ids.pop()


async def test_bulk_import_restores_an_archived_room_type_with_the_same_id(
    async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
):
    """S14/R25: um nome arquivado é restaurado com o mesmo identificador."""
    suffix = uuid4().hex[:8]
    archived_id = await _create_room_type(
        async_client, clerk_admin_headers, name=f"Oficina {suffix}"
    )
    await db_session.execute(
        update(models.SchoolRoomType)
        .where(models.SchoolRoomType.id == archived_id)
        .values(is_archived=True)
    )
    await db_session.commit()
    files = {
        "rooms": csv_payload(
            "Cronos_Salas_Template.csv",
            f"Nome da sala;Tipo de sala;Capacidade\r\nSala {suffix};oficina {suffix};20\r\n",
        )
    }

    validation = await async_client.post(
        f"{API}/imports/validate", json={"files": files}, headers=clerk_admin_headers
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["can_commit"] is True, validation.text

    commit = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_admin_headers
    )
    assert commit.status_code == 201, commit.text

    restored = await db_session.get(models.SchoolRoomType, archived_id)
    await db_session.refresh(restored)
    assert restored.is_archived is False
    org_id = await _org_id(db_session)
    room_type_id = await db_session.scalar(
        select(models.Room.room_type_id).where(
            models.Room.organization_id == org_id, models.Room.name == f"Sala {suffix}"
        )
    )
    assert room_type_id == archived_id


async def test_bulk_import_sets_the_home_room_of_a_new_class_from_the_same_batch(
    async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
):
    """S14/R26: a sala da turma pode vir do ficheiro de salas do mesmo lote."""
    suffix = uuid4().hex[:8]
    abbreviation = f"C{suffix[:5].upper()}"
    files = {
        "rooms": csv_payload(
            "Cronos_Salas_Template.csv",
            f"Nome da sala;Tipo de sala;Capacidade\r\nSala Turma {suffix};Normal;30\r\n",
        ),
        "courses": csv_payload(
            "Cronos_CursosETurmas_Template.csv",
            COURSES_HEADER
            + f"{abbreviation};Curso {suffix};10.º A;10;2025;2028;25;sala turma {suffix}\r\n"
            + f"{abbreviation};Curso {suffix};10.º B;10;2025;2028;25;\r\n",
        ),
    }

    commit = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_admin_headers
    )
    assert commit.status_code == 201, commit.text

    org_id = await _org_id(db_session)
    room_id = await db_session.scalar(
        select(models.Room.id).where(
            models.Room.organization_id == org_id,
            models.Room.name == f"Sala Turma {suffix}",
        )
    )
    home_rooms = dict(
        (
            await db_session.execute(
                select(models.Class.name, models.Class.home_room_id)
                .join(models.Course, models.Course.id == models.Class.course_id)
                .where(
                    models.Course.organization_id == org_id,
                    models.Course.abbreviation == abbreviation,
                )
            )
        ).all()
    )
    assert home_rooms == {"10.º A": room_id, "10.º B": None}


@pytest.mark.parametrize(
    ("home_room", "code", "message"),
    [
        (
            "Sala Fantasma",
            "home_room_not_found",
            "Sala não encontrada. Escreva o nome de uma sala existente ou do ficheiro de salas.",
        ),
        (
            "Sala Pequena",
            "home_room_capacity",
            "A sala Sala Pequena não tem lugares para os 25 alunos da turma.",
        ),
    ],
)
async def test_bulk_import_refuses_an_unknown_or_too_small_home_room_without_writing(
    async_client: AsyncClient,
    db_session: AsyncSession,
    clerk_admin_headers: dict,
    home_room: str,
    code: str,
    message: str,
):
    suffix = uuid4().hex[:8]
    files = {
        "rooms": csv_payload(
            "Cronos_Salas_Template.csv",
            "Nome da sala;Tipo de sala;Capacidade\r\nSala Pequena;Normal;24\r\n",
        ),
        "courses": csv_payload(
            "Cronos_CursosETurmas_Template.csv",
            COURSES_HEADER
            + f"C{suffix[:5].upper()};Curso {suffix};10.º A;10;2025;2028;25;{home_room}\r\n",
        ),
    }

    validation = await async_client.post(
        f"{API}/imports/validate", json={"files": files}, headers=clerk_admin_headers
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["can_commit"] is False
    assert {
        "code": code,
        "severity": "error",
        "resource": "courses",
        "line": 2,
        "field": "home_room",
        "message": message,
    } in validation.json()["issues"], validation.text

    commit = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_admin_headers
    )
    assert commit.status_code == 422


async def test_bulk_import_does_not_find_a_room_of_another_school_as_home_room(
    async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
):
    """S14/R02: a sala da turma de outra escola não existe na escola que importa."""
    headers_b = await _other_school_admin_headers(db_session)
    suffix = uuid4().hex[:8]
    created = await async_client.post(
        f"{API}/rooms/",
        json={"name": f"Sala Alheia {suffix}", "capacity": 30},
        headers=headers_b,
    )
    assert created.status_code == 200, created.text

    files = {
        "courses": csv_payload(
            "Cronos_CursosETurmas_Template.csv",
            COURSES_HEADER
            + f"C{suffix[:5].upper()};Curso {suffix};10.º A;10;2025;2028;25;Sala Alheia {suffix}\r\n",
        ),
    }

    validation = await async_client.post(
        f"{API}/imports/validate", json={"files": files}, headers=clerk_admin_headers
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["can_commit"] is False
    assert any(issue["code"] == "home_room_not_found" for issue in validation.json()["issues"]), (
        validation.text
    )


async def _prepare_class_grid(
    client: AsyncClient, headers: dict, days_of_week: tuple[int, ...] = (0, 4)
) -> list[dict]:
    settings_resp = await client.post(
        f"{API}/school/settings/",
        json={"school_start_date": "2025-09-01", "school_hard_end_date": "2026-07-31"},
        headers=headers,
    )
    assert settings_resp.status_code == 200
    grid_resp = await client.post(
        f"{API}/school/grid-settings/regenerate",
        json={
            "grid_settings": {},
            "timeslots": {
                "start_time": "08:00",
                "end_time": "10:00",
                "slot_duration_minutes": 50,
                "break_duration_minutes": 10,
                "days_of_week": list(days_of_week),
            },
        },
        headers=headers,
    )
    assert grid_resp.status_code == 200
    blocks = (await client.get(f"{API}/timeslots/", headers=headers)).json()
    assert blocks
    return blocks


def _grid_hours(blocks: list[dict]) -> list[str]:
    return sorted({block["start_time"][:5] for block in blocks})


def _class_availability_header(hours: list[str]) -> str:
    return "Sigla do curso;Nome da turma;Dia;" + ";".join(hours)


async def _seed_class(
    db_session, *, name: str, abbreviation: str, is_archived: bool = False
) -> models.Class:
    course = models.Course(
        name=f"Curso {abbreviation}", abbreviation=abbreviation, organization_id=1
    )
    db_session.add(course)
    await db_session.flush()
    klass = models.Class(
        name=name,
        size=20,
        start_year=2025,
        end_year=2028,
        grade_level=10,
        course_id=course.id,
        organization_id=1,
        is_archived=is_archived,
    )
    db_session.add(klass)
    await db_session.commit()
    return klass


async def _class_availability_rows(db_session, class_id: int) -> dict[int, int]:
    rows = (
        await db_session.execute(
            select(models.ClassAvailability.timeslot_id, models.ClassAvailability.score).where(
                models.ClassAvailability.class_id == class_id
            )
        )
    ).all()
    return {int(timeslot_id): int(score) for timeslot_id, score in rows}


async def test_class_availability_template_reflects_the_visible_grid(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    klass = await _seed_class(db_session, name="TGEI 25/28", abbreviation="TGEI")

    response = await async_client.get(
        f"{API}/imports/templates/class_availability", headers=clerk_admin_headers
    )

    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert (
        'filename="Cronos_DisponibilidadeTurmas_Template.csv"'
        in response.headers["content-disposition"]
    )
    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines[0] == _class_availability_header(hours)
    monday = next(line for line in lines[1:] if line.split(";")[2] == "Segunda")
    assert monday.startswith("TGEI;TGEI 25/28;Segunda;")
    assert "Neutro" in monday

    ordered = sorted(block["id"] for block in blocks)
    put = await async_client.put(
        f"{API}/classes/{klass.id}/availability",
        json=[{"timeslot_id": timeslot_id, "score": -1} for timeslot_id in ordered],
        headers=clerk_admin_headers,
    )
    assert put.status_code == 200

    updated = await async_client.get(
        f"{API}/imports/templates/class_availability", headers=clerk_admin_headers
    )
    monday = next(
        line for line in updated.content.decode("utf-8-sig").splitlines()[1:] if "Segunda" in line
    )
    assert "Impossível" in monday
    assert "Neutro" not in monday


async def test_class_availability_template_without_blocks_returns_the_exact_message(
    async_client: AsyncClient, clerk_admin_headers: dict
):
    response = await async_client.get(
        f"{API}/imports/templates/class_availability", headers=clerk_admin_headers
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "bad_request"
    # The client maps this whitelisted reason to the exact Portuguese message.
    assert detail["context"]["reason"] == "no_grid_blocks"


async def test_bulk_import_commit_replaces_the_grid_and_leaves_other_classes_unchanged(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    first_hour = hours[0]
    monday_first = next(
        block
        for block in blocks
        if block["day_of_week"] == 0 and block["start_time"].startswith(first_hour)
    )
    klass = await _seed_class(db_session, name="TGEI 25/28", abbreviation="TGEI")
    other = await _seed_class(db_session, name="Outra Turma", abbreviation="OUT")
    db_session.add(
        models.ClassAvailability(
            organization_id=1, class_id=other.id, timeslot_id=monday_first["id"], score=0
        )
    )
    await db_session.commit()

    cells = ["Evitar"] + ["" for _ in hours[1:]]
    content = (
        _class_availability_header(hours)
        + "\r\n"
        + "TGEI;TGEI 25/28;Segunda;"
        + ";".join(cells)
        + "\r\n"
    )
    files = {
        "class_availability": csv_payload("Cronos_DisponibilidadeTurmas_Template.csv", content)
    }

    validation = await async_client.post(
        f"{API}/imports/validate", json={"files": files}, headers=clerk_admin_headers
    )
    assert validation.status_code == 200
    assert validation.json()["can_commit"] is True
    assert validation.json()["preview"]["counts"]["class_availability"] == 1

    commit = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_admin_headers
    )
    assert commit.status_code == 201, commit.text
    assert commit.json()["created_counts"]["class_availability"] == 1

    assert await _class_availability_rows(db_session, klass.id) == {monday_first["id"]: 0}
    assert await _class_availability_rows(db_session, other.id) == {monday_first["id"]: 0}
    events = list(
        (
            await db_session.scalars(
                select(models.SchedulerStateVersionEvent).where(
                    models.SchedulerStateVersionEvent.entity_type == "CLASS_AVAILABILITY",
                    models.SchedulerStateVersionEvent.entity_id == str(klass.id),
                )
            )
        ).all()
    )
    assert len(events) == 1


async def test_bulk_import_commit_keeps_every_day_and_counts_each_class_once(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    klass = await _seed_class(db_session, name="TGEI 25/28", abbreviation="TGEI")
    other = await _seed_class(db_session, name="Outra Turma", abbreviation="OUT")

    other_block = blocks[0]["id"]
    future_version = models.GridVersion(
        organization_id=1,
        effective_date=date(2030, 1, 1),
        state=models.GridVersionState.ACTIVE,
    )
    db_session.add(future_version)
    await db_session.flush()
    future_slot = models.Timeslot(
        organization_id=1,
        grid_version_id=future_version.id,
        day_of_week=0,
        start_time=time(8, 0),
        end_time=time(8, 50),
    )
    db_session.add(future_slot)
    await db_session.flush()
    db_session.add_all(
        [
            models.ClassAvailability(
                organization_id=1, class_id=other.id, timeslot_id=other_block, score=0
            ),
            models.ClassAvailability(
                organization_id=1, class_id=klass.id, timeslot_id=future_slot.id, score=2
            ),
        ]
    )
    await db_session.commit()

    monday_cells = ["Impossível"] + ["" for _ in hours[1:]]
    friday_cells = ["Preferencial"] + ["" for _ in hours[1:]]
    content = (
        _class_availability_header(hours)
        + "\r\n"
        + "TGEI;TGEI 25/28;Segunda;"
        + ";".join(monday_cells)
        + "\r\n"
        + "TGEI;TGEI 25/28;Sexta;"
        + ";".join(friday_cells)
        + "\r\n"
    )
    files = {
        "class_availability": csv_payload("Cronos_DisponibilidadeTurmas_Template.csv", content)
    }

    validation = await async_client.post(
        f"{API}/imports/validate", json={"files": files}, headers=clerk_admin_headers
    )
    assert validation.status_code == 200
    assert validation.json()["can_commit"] is True
    assert validation.json()["preview"]["counts"]["class_availability"] == 1

    commit = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_admin_headers
    )
    assert commit.status_code == 201, commit.text
    assert commit.json()["created_counts"]["class_availability"] == 1

    monday_block = next(
        block
        for block in blocks
        if block["day_of_week"] == 0 and block["start_time"].startswith(hours[0])
    )
    friday_block = next(
        block
        for block in blocks
        if block["day_of_week"] == 4 and block["start_time"].startswith(hours[0])
    )
    saved = await _class_availability_rows(db_session, klass.id)
    assert saved[monday_block["id"]] == -1
    assert saved[friday_block["id"]] == 2
    assert saved[future_slot.id] == 2
    assert await _class_availability_rows(db_session, other.id) == {other_block: 0}

    events = list(
        (
            await db_session.scalars(
                select(models.SchedulerStateVersionEvent).where(
                    models.SchedulerStateVersionEvent.entity_type == "CLASS_AVAILABILITY",
                    models.SchedulerStateVersionEvent.entity_id == str(klass.id),
                )
            )
        ).all()
    )
    assert len(events) == 1


async def test_class_availability_validation_refuses_archived_and_foreign_classes(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    await _seed_class(db_session, name="Turma Arquivada", abbreviation="ARC", is_archived=True)
    foreign_org = models.Organization(name=f"Foreign {uuid4().hex[:6]}", plan_status="active")
    db_session.add(foreign_org)
    await db_session.flush()
    foreign_course = models.Course(
        name="Foreign Course", abbreviation="FOR", organization_id=foreign_org.id
    )
    db_session.add(foreign_course)
    await db_session.flush()
    db_session.add(
        models.Class(
            name="Turma Externa",
            size=20,
            start_year=2025,
            end_year=2028,
            grade_level=10,
            course_id=foreign_course.id,
            organization_id=foreign_org.id,
        )
    )
    await db_session.commit()

    cells = ";".join(["Neutro"] + ["" for _ in hours[1:]])
    content = (
        _class_availability_header(hours)
        + "\r\n"
        + f"ARC;Turma Arquivada;Segunda;{cells}\r\n"
        + f"FOR;Turma Externa;Segunda;{cells}\r\n"
    )

    response = await async_client.post(
        f"{API}/imports/validate",
        json={
            "files": {
                "class_availability": csv_payload(
                    "Cronos_DisponibilidadeTurmas_Template.csv", content
                )
            }
        },
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["can_commit"] is False
    missing = [
        issue for issue in response.json()["issues"] if issue["code"] == "class_reference_missing"
    ]
    assert len(missing) == 2


async def test_bulk_import_commit_applies_the_grid_to_a_class_created_in_the_same_batch(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    suffix = uuid4().hex[:6]
    abbreviation = f"C{suffix[:5].upper()}"
    courses = csv_payload(
        "Cronos_CursosETurmas_Template.csv",
        COURSES_HEADER + f"{abbreviation};Curso {suffix};10.º A;10;2025;2028;24;\r\n",
    )
    availability = csv_payload(
        "Cronos_DisponibilidadeTurmas_Template.csv",
        _class_availability_header(hours)
        + "\r\n"
        + f"{abbreviation};10.º A;Segunda;"
        + ";".join(["Impossível"] + ["" for _ in hours[1:]])
        + "\r\n",
    )

    commit = await async_client.post(
        f"{API}/imports/commit",
        json={"files": {"courses": courses, "class_availability": availability}},
        headers=clerk_admin_headers,
    )

    assert commit.status_code == 201, commit.text
    assert commit.json()["created_counts"]["class_availability"] == 1
    klass = await db_session.scalar(
        select(models.Class).where(models.Class.organization_id == 1, models.Class.name == "10.º A")
    )
    assert klass is not None
    rows = await _class_availability_rows(db_session, klass.id)
    assert rows and set(rows.values()) == {-1}


def _teacher_availability_header(hours: list[str]) -> str:
    return "Nome do professor;Email do professor;Dia;" + ";".join(hours)


async def _seed_teacher(
    db_session: AsyncSession,
    *,
    name: str,
    email: str,
    can_teach: bool = True,
    can_admin: bool = False,
    archived: bool = False,
) -> models.Teacher:
    account = models.User(email=email, name=name)
    db_session.add(account)
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=1,
        account_id=account.id,
        organization_display_name=name,
        lifecycle_status=(
            models.MembershipLifecycleStatus.archived
            if archived
            else models.MembershipLifecycleStatus.active
        ),
        access_status=models.MembershipAccessStatus.none,
        teacher_access_mode=(None if can_admin else models.TeacherAccessMode.scheduler_only),
        can_admin=can_admin,
        can_teach=can_teach,
    )
    db_session.add(membership)
    await db_session.flush()
    teacher = models.Teacher(organization_id=1, organization_membership_id=membership.id)
    db_session.add(teacher)
    await db_session.commit()
    return teacher


async def test_teacher_availability_template_lists_active_teachers_and_current_levels(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    teacher = await _seed_teacher(db_session, name="Ana Silva", email="ana.silva@import.test")
    await _seed_teacher(db_session, name="Arquivada", email="arch@import.test", archived=True)
    await _seed_teacher(
        db_session,
        name="Sem Capacidade",
        email="lost@import.test",
        can_teach=False,
        can_admin=True,
    )
    monday_first = next(
        block
        for block in blocks
        if block["day_of_week"] == 0 and block["start_time"].startswith(hours[0])
    )
    db_session.add(
        models.Availability(
            organization_id=1, teacher_id=teacher.id, timeslot_id=monday_first["id"], score=-1
        )
    )
    await db_session.commit()

    response = await async_client.get(
        f"{API}/imports/templates/teacher_availability", headers=clerk_admin_headers
    )

    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert (
        'filename="Cronos_DisponibilidadeProfessores_Template.csv"'
        in response.headers["content-disposition"]
    )
    text = response.content.decode("utf-8-sig")
    lines = text.splitlines()
    assert lines[0] == _teacher_availability_header(hours)
    assert "ana.silva@import.test" in text
    assert "arch@import.test" not in text
    assert "lost@import.test" not in text
    monday = next(line for line in lines[1:] if line.split(";")[2] == "Segunda")
    assert monday.startswith("Ana Silva;ana.silva@import.test;Segunda;")
    assert "Impossível" in monday


async def test_teacher_availability_template_uses_the_visible_grid_with_a_pending_version(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    await _seed_teacher(db_session, name="Ana Silva", email="ana.silva@import.test")
    pending = models.GridVersion(
        organization_id=1,
        effective_date=date(2030, 1, 1),
        state=models.GridVersionState.PENDING,
    )
    db_session.add(pending)
    await db_session.flush()
    db_session.add(
        models.Timeslot(
            organization_id=1,
            grid_version_id=pending.id,
            day_of_week=0,
            start_time=time(14, 0),
            end_time=time(14, 50),
        )
    )
    await db_session.commit()

    response = await async_client.get(
        f"{API}/imports/templates/teacher_availability", headers=clerk_admin_headers
    )

    assert response.status_code == 200
    header = response.content.decode("utf-8-sig").splitlines()[0]
    assert header == _teacher_availability_header(hours)
    assert "14:00" not in header


async def test_teacher_availability_template_without_blocks_returns_the_exact_message(
    async_client: AsyncClient, clerk_admin_headers: dict
):
    response = await async_client.get(
        f"{API}/imports/templates/teacher_availability", headers=clerk_admin_headers
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "bad_request"
    # The client maps this whitelisted reason to the exact Portuguese message.
    assert detail["context"]["reason"] == "no_grid_blocks"


async def test_teacher_availability_template_without_active_teachers_is_header_only(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    await _seed_teacher(db_session, name="Arquivada", email="arch@import.test", archived=True)
    await _seed_teacher(
        db_session,
        name="Sem Capacidade",
        email="lost@import.test",
        can_teach=False,
        can_admin=True,
    )

    response = await async_client.get(
        f"{API}/imports/templates/teacher_availability", headers=clerk_admin_headers
    )

    assert response.status_code == 200
    assert response.content.decode("utf-8-sig").splitlines() == [
        _teacher_availability_header(hours)
    ]


async def test_teacher_availability_validation_rejects_archived_and_capability_lost_teachers(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    await _seed_teacher(db_session, name="Ana Silva", email="ana.silva@import.test")
    await _seed_teacher(db_session, name="Arquivada", email="arch@import.test", archived=True)
    await _seed_teacher(
        db_session,
        name="Sem Capacidade",
        email="lost@import.test",
        can_teach=False,
        can_admin=True,
    )
    cells = ";".join(["Neutro"] + ["" for _ in hours[1:]])
    content = (
        _teacher_availability_header(hours)
        + "\r\n"
        + f"Ana Silva;ana.silva@import.test;Segunda;{cells}\r\n"
        + f"Arquivada;arch@import.test;Segunda;{cells}\r\n"
        + f"Sem Capacidade;lost@import.test;Segunda;{cells}\r\n"
    )

    response = await async_client.post(
        f"{API}/imports/validate",
        json={
            "files": {
                "teacher_availability": csv_payload(
                    "Cronos_DisponibilidadeProfessores_Template.csv", content
                )
            }
        },
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["can_commit"] is False
    assert payload["preview"]["counts"]["teacher_availability"] == 1
    inactive = [issue for issue in payload["issues"] if issue["code"] == "teacher_inactive"]
    assert len(inactive) == 2
    assert all(issue["field"] == "teacher_email" for issue in inactive)


async def _teacher_availability_rows(db_session: AsyncSession, teacher_id: int) -> dict[int, int]:
    rows = (
        await db_session.execute(
            select(models.Availability.timeslot_id, models.Availability.score).where(
                models.Availability.teacher_id == teacher_id
            )
        )
    ).all()
    return {int(timeslot_id): int(score) for timeslot_id, score in rows}


def _first_block(blocks: list[dict], hours: list[str], day: int) -> dict:
    return next(
        block
        for block in blocks
        if block["day_of_week"] == day and block["start_time"].startswith(hours[0])
    )


async def _account_email(db_session: AsyncSession, teacher: models.Teacher) -> str:
    membership = await db_session.get(
        models.OrganizationMembership, teacher.organization_membership_id
    )
    account = await db_session.get(models.User, membership.account_id)
    return account.email


async def test_bulk_import_commit_targets_the_teacher_id(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    # Advance the account and membership sequences so the target teacher's account,
    # membership and teacher ids are deliberately different (R01).
    decoys = [
        models.User(email=f"decoy{index}@example.com", name=f"Decoy {index}") for index in range(2)
    ]
    db_session.add_all(decoys)
    await db_session.flush()
    db_session.add(
        models.OrganizationMembership(
            organization_id=1,
            account_id=decoys[0].id,
            organization_display_name="Decoy",
            lifecycle_status=models.MembershipLifecycleStatus.active,
            access_status=models.MembershipAccessStatus.none,
            can_admin=True,
            can_teach=False,
            teacher_access_mode=None,
        )
    )
    await db_session.flush()
    teacher = await _seed_teacher(db_session, name="Ana Silva", email="ana.silva@import.test")
    membership = await db_session.get(
        models.OrganizationMembership, teacher.organization_membership_id
    )
    account = await db_session.get(models.User, membership.account_id)
    assert len({teacher.id, membership.id, account.id}) == 3
    cells = ";".join(["Impossível"] + ["" for _ in hours[1:]])
    content = (
        _teacher_availability_header(hours)
        + "\r\n"
        + f"Ana Silva;{account.email};Segunda;{cells}\r\n"
    )

    commit = await async_client.post(
        f"{API}/imports/commit",
        json={
            "files": {
                "teacher_availability": csv_payload(
                    "Cronos_DisponibilidadeProfessores_Template.csv", content
                )
            }
        },
        headers=clerk_admin_headers,
    )

    assert commit.status_code == 201, commit.text
    monday_first = _first_block(blocks, hours, 0)
    expected = {block["id"]: models.PreferenceLevel.NEUTRAL.value for block in blocks}
    expected[monday_first["id"]] = models.PreferenceLevel.IMPOSSIBLE.value
    assert await _teacher_availability_rows(db_session, teacher.id) == expected
    stray = await db_session.scalar(
        select(func.count())
        .select_from(models.Availability)
        .where(models.Availability.teacher_id != teacher.id)
    )
    assert stray == 0


async def test_bulk_import_commit_saves_five_days_as_one_grid(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(
        async_client, clerk_admin_headers, days_of_week=(0, 1, 2, 3, 4)
    )
    hours = _grid_hours(blocks)
    teacher = await _seed_teacher(db_session, name="Ana Silva", email="ana.silva@import.test")
    day_labels = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]
    cells = ";".join(["Impossível"] + ["" for _ in hours[1:]])
    rows = "".join(f"Ana Silva;ana.silva@import.test;{label};{cells}\r\n" for label in day_labels)
    content = _teacher_availability_header(hours) + "\r\n" + rows

    commit = await async_client.post(
        f"{API}/imports/commit",
        json={
            "files": {
                "teacher_availability": csv_payload(
                    "Cronos_DisponibilidadeProfessores_Template.csv", content
                )
            }
        },
        headers=clerk_admin_headers,
    )

    assert commit.status_code == 201, commit.text
    assert commit.json()["created_counts"]["teacher_availability"] == 1
    saved = await _teacher_availability_rows(db_session, teacher.id)
    assert len(saved) == len(blocks)
    impossible_slots = [_first_block(blocks, hours, day)["id"] for day in range(5)]
    for timeslot_id in impossible_slots:
        assert saved[timeslot_id] == models.PreferenceLevel.IMPOSSIBLE.value
    assert sum(1 for score in saved.values() if score == -1) == 5


async def test_bulk_import_commit_preserves_a_teacher_omitted_from_the_file(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    teacher = await _seed_teacher(db_session, name="Ana Silva", email="ana.silva@import.test")
    omitted = await _seed_teacher(db_session, name="Bea Costa", email="bea.costa@import.test")
    monday_first = _first_block(blocks, hours, 0)
    db_session.add(
        models.Availability(
            organization_id=1, teacher_id=omitted.id, timeslot_id=monday_first["id"], score=0
        )
    )
    await db_session.commit()
    cells = ";".join(["Impossível"] + ["" for _ in hours[1:]])
    content = (
        _teacher_availability_header(hours)
        + "\r\n"
        + f"Ana Silva;ana.silva@import.test;Segunda;{cells}\r\n"
    )

    commit = await async_client.post(
        f"{API}/imports/commit",
        json={
            "files": {
                "teacher_availability": csv_payload(
                    "Cronos_DisponibilidadeProfessores_Template.csv", content
                )
            }
        },
        headers=clerk_admin_headers,
    )

    assert commit.status_code == 201, commit.text
    expected = {block["id"]: models.PreferenceLevel.NEUTRAL.value for block in blocks}
    expected[monday_first["id"]] = models.PreferenceLevel.IMPOSSIBLE.value
    assert await _teacher_availability_rows(db_session, teacher.id) == expected
    assert await _teacher_availability_rows(db_session, omitted.id) == {monday_first["id"]: 0}


async def test_bulk_import_commit_applies_the_grid_to_a_teacher_created_in_the_same_batch(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    email = "nova.professora@example.com"
    teachers_file = csv_payload(
        "Cronos_ProfessoresECompetencias_Template.csv",
        f"Nome do professor;Email do professor;Nome da disciplina\r\nNova Professora;{email};\r\n",
    )
    cells = ";".join(["Impossível"] + ["" for _ in hours[1:]])
    availability = csv_payload(
        "Cronos_DisponibilidadeProfessores_Template.csv",
        _teacher_availability_header(hours)
        + "\r\n"
        + f"Nome do ficheiro;{email};Segunda;{cells}\r\n",
    )

    commit = await async_client.post(
        f"{API}/imports/commit",
        json={"files": {"teachers": teachers_file, "teacher_availability": availability}},
        headers=clerk_admin_headers,
    )

    assert commit.status_code == 201, commit.text
    assert commit.json()["created_counts"]["teachers"] == 1
    assert commit.json()["created_counts"]["teacher_availability"] == 1
    created = await db_session.scalar(
        select(models.Teacher)
        .join(
            models.OrganizationMembership,
            models.OrganizationMembership.id == models.Teacher.organization_membership_id,
        )
        .join(models.User, models.User.id == models.OrganizationMembership.account_id)
        .where(models.User.email == email)
    )
    assert created is not None
    monday_first = _first_block(blocks, hours, 0)
    expected = {block["id"]: models.PreferenceLevel.NEUTRAL.value for block in blocks}
    expected[monday_first["id"]] = models.PreferenceLevel.IMPOSSIBLE.value
    assert await _teacher_availability_rows(db_session, created.id) == expected


async def test_bulk_import_commit_only_writes_the_visible_grid_over_a_pending_version(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    teacher = await _seed_teacher(db_session, name="Ana Silva", email="ana.silva@import.test")
    pending = models.GridVersion(
        organization_id=1,
        effective_date=date(2030, 1, 1),
        state=models.GridVersionState.PENDING,
    )
    db_session.add(pending)
    await db_session.flush()
    future_slot = models.Timeslot(
        organization_id=1,
        grid_version_id=pending.id,
        day_of_week=0,
        start_time=time(8, 0),
        end_time=time(8, 50),
    )
    db_session.add(future_slot)
    await db_session.flush()
    db_session.add(
        models.Availability(
            organization_id=1,
            teacher_id=teacher.id,
            timeslot_id=future_slot.id,
            score=2,
        )
    )
    await db_session.commit()
    cells = ";".join(["Impossível"] + ["" for _ in hours[1:]])
    content = (
        _teacher_availability_header(hours)
        + "\r\n"
        + f"Ana Silva;ana.silva@import.test;Segunda;{cells}\r\n"
    )

    commit = await async_client.post(
        f"{API}/imports/commit",
        json={
            "files": {
                "teacher_availability": csv_payload(
                    "Cronos_DisponibilidadeProfessores_Template.csv", content
                )
            }
        },
        headers=clerk_admin_headers,
    )

    assert commit.status_code == 201, commit.text
    saved = await _teacher_availability_rows(db_session, teacher.id)
    assert saved[_first_block(blocks, hours, 0)["id"]] == -1
    assert saved[future_slot.id] == 2


async def test_bulk_import_commit_records_bulk_import_and_changes_the_fingerprint(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    teacher = await _seed_teacher(db_session, name="Ana Silva", email="ana.silva@import.test")
    teacher_id = teacher.id
    monday_first_id = _first_block(blocks, hours, 0)["id"]
    subject = models.Subject(
        organization_id=1,
        name="Programação",
        room_type_id=await get_school_room_type_id(db_session, 1, "Normal"),
    )
    course = models.Course(organization_id=1, name="Curso", abbreviation="TGEI")
    db_session.add_all([subject, course])
    await db_session.flush()
    klass = models.Class(
        organization_id=1,
        name="TGEI 25/28",
        size=20,
        start_year=2025,
        end_year=2028,
        grade_level=10,
        course_id=course.id,
    )
    db_session.add(klass)
    await db_session.flush()
    db_session.add(
        models.ClassSubjectLink(
            organization_id=1,
            class_id=klass.id,
            subject_id=subject.id,
            grade_level=10,
            teacher_id=teacher.id,
        )
    )
    await db_session.execute(
        models.teacher_subject_link.insert().values(
            organization_id=1, teacher_id=teacher.id, subject_id=subject.id
        )
    )
    await db_session.commit()
    state_service = SchedulerStateService(db_session)
    school_year = await state_service.get_active_school_year(1)
    assert school_year is not None
    state = await state_service.get_or_create_state(1, school_year.id)
    school_year_id = school_year.id
    version_before = state.scheduler_state_version
    await db_session.commit()
    fingerprint_service = SchedulerFingerprintService(db_session)
    fingerprint_before = await fingerprint_service.generation_input_fingerprint(
        1, school_year_id, models.ScheduleGenerationStrategy.COMPLETE_GENERATION
    )
    cells = ";".join(["Impossível"] + ["" for _ in hours[1:]])
    content = (
        _teacher_availability_header(hours)
        + "\r\n"
        + f"Ana Silva;ana.silva@import.test;Segunda;{cells}\r\n"
    )

    commit = await async_client.post(
        f"{API}/imports/commit",
        json={
            "files": {
                "teacher_availability": csv_payload(
                    "Cronos_DisponibilidadeProfessores_Template.csv", content
                )
            }
        },
        headers=clerk_admin_headers,
    )

    assert commit.status_code == 201, commit.text
    fingerprint_after = await fingerprint_service.generation_input_fingerprint(
        1, school_year_id, models.ScheduleGenerationStrategy.COMPLETE_GENERATION
    )
    assert fingerprint_after.value != fingerprint_before.value
    assert {
        "teacher_id": teacher_id,
        "timeslot_id": monday_first_id,
        "score": models.PreferenceLevel.IMPOSSIBLE.value,
    } in fingerprint_after.snapshot["teacher_availability"]
    events = list(
        (
            await db_session.scalars(
                select(models.SchedulerStateVersionEvent).where(
                    models.SchedulerStateVersionEvent.entity_type == "TEACHER_AVAILABILITY",
                    models.SchedulerStateVersionEvent.entity_id == str(teacher_id),
                )
            )
        ).all()
    )
    assert len(events) == 1
    assert events[0].operation == models.SchedulerStateChangeOperation.BULK_IMPORT
    await db_session.refresh(state)
    assert state.scheduler_state_version == version_before + 1


async def test_bulk_import_commit_fails_without_partial_writes_when_a_teacher_is_archived(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    teacher = await _seed_teacher(db_session, name="Ana Silva", email="ana.silva@import.test")
    cells = ";".join(["Impossível"] + ["" for _ in hours[1:]])
    files = {
        "rooms": csv_payload(
            "Cronos_Salas_Template.csv",
            "Nome da sala;Tipo de sala;Capacidade\r\nSala R16;Normal;20\r\n",
        ),
        "teacher_availability": csv_payload(
            "Cronos_DisponibilidadeProfessores_Template.csv",
            _teacher_availability_header(hours)
            + "\r\n"
            + f"Ana Silva;ana.silva@import.test;Segunda;{cells}\r\n",
        ),
    }

    validation = await async_client.post(
        f"{API}/imports/validate", json={"files": files}, headers=clerk_admin_headers
    )
    assert validation.status_code == 200
    assert validation.json()["can_commit"] is True

    membership = await db_session.get(
        models.OrganizationMembership, teacher.organization_membership_id
    )
    membership.lifecycle_status = models.MembershipLifecycleStatus.archived
    await db_session.commit()

    commit = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_admin_headers
    )

    assert commit.status_code == 422
    rooms = await db_session.scalar(
        select(func.count()).select_from(models.Room).where(models.Room.name == "Sala R16")
    )
    assert rooms == 0
    assert await _teacher_availability_rows(db_session, teacher.id) == {}


async def test_teacher_availability_template_roundtrip_has_zero_changes(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    teacher = await _seed_teacher(db_session, name="Ana Silva", email="ana.silva@import.test")
    hours = _grid_hours(blocks)
    monday_first = _first_block(blocks, hours, 0)
    db_session.add(
        models.Availability(
            organization_id=1, teacher_id=teacher.id, timeslot_id=monday_first["id"], score=-1
        )
    )
    await db_session.commit()

    template = await async_client.get(
        f"{API}/imports/templates/teacher_availability", headers=clerk_admin_headers
    )
    assert template.status_code == 200
    content = template.content.decode("utf-8-sig")

    validation = await async_client.post(
        f"{API}/imports/validate",
        json={
            "files": {
                "teacher_availability": csv_payload(
                    "Cronos_DisponibilidadeProfessores_Template.csv", content
                )
            }
        },
        headers=clerk_admin_headers,
    )

    assert validation.status_code == 200
    assert validation.json()["can_commit"] is True
    items = [
        item
        for item in validation.json()["preview"]["items"]
        if item["resource"] == "teacher_availability"
    ]
    assert [item["changed_blocks"] for item in items] == [0]


async def test_bulk_import_commit_uses_the_same_email_normalization_as_validation(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    blocks = await _prepare_class_grid(async_client, clerk_admin_headers)
    hours = _grid_hours(blocks)
    # Defensive fixture: a stored account email with repeated internal whitespace,
    # which ``_email`` collapses. The commit map must normalize the same way.
    teacher = await _seed_teacher(db_session, name="Ana Silva", email="ana   silva@example.com")
    cells = ";".join(["Impossível"] + ["" for _ in hours[1:]])
    content = (
        _teacher_availability_header(hours)
        + "\r\n"
        + f"Ana Silva;ana silva@example.com;Segunda;{cells}\r\n"
    )

    commit = await async_client.post(
        f"{API}/imports/commit",
        json={
            "files": {
                "teacher_availability": csv_payload(
                    "Cronos_DisponibilidadeProfessores_Template.csv", content
                )
            }
        },
        headers=clerk_admin_headers,
    )

    assert commit.status_code == 201, commit.text
    monday_first = _first_block(blocks, hours, 0)
    expected = {block["id"]: models.PreferenceLevel.NEUTRAL.value for block in blocks}
    expected[monday_first["id"]] = models.PreferenceLevel.IMPOSSIBLE.value
    assert await _teacher_availability_rows(db_session, teacher.id) == expected


async def test_imports_endpoints_require_an_admin(
    async_client: AsyncClient, clerk_teacher_headers: dict
):
    files = {
        "rooms": csv_payload(
            "Cronos_Salas_Template.csv",
            "Nome da sala;Tipo de sala;Capacidade\r\nSala Nao Admin;Normal;20\r\n",
        )
    }

    template = await async_client.get(
        f"{API}/imports/templates/teacher_availability", headers=clerk_teacher_headers
    )
    validation = await async_client.post(
        f"{API}/imports/validate", json={"files": files}, headers=clerk_teacher_headers
    )
    commit = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_teacher_headers
    )

    assert template.status_code == 403
    assert validation.status_code == 403
    assert commit.status_code == 403


async def test_teacher_presence_commit_applies_after_creation_and_counts_each_change(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    organization_id = await _org_id(db_session)
    await _seed_scheduler_year(db_session, organization_id)
    await db_session.commit()
    suffix = uuid4().hex[:8]
    emails = {name: f"{name.lower()}.{suffix}@example.com" for name in ("Ana", "Bruno", "Carla")}
    teachers = csv_payload(
        "Cronos_ProfessoresECompetencias_Template.csv",
        "Nome do professor;Email do professor;Nome da disciplina\r\n"
        + "".join(f"{name};{emails[name]};\r\n" for name in emails),
    )
    presence = csv_payload(
        "Cronos_PresencaProfessores_Template.csv",
        TEACHER_PRESENCE_HEADER
        + teacher_presence_row("Ana", emails["Ana"], "Sim", "3", "1")
        + teacher_presence_row("Bruno", emails["Bruno"], "Não"),
    )
    files = {"teachers": teachers, "teacher_presence": presence}

    validation = await async_client.post(
        f"{API}/imports/validate", json={"files": files}, headers=clerk_admin_headers
    )
    assert validation.status_code == 200
    assert validation.json()["can_commit"] is True
    assert validation.json()["preview"]["counts"]["teacher_presence"] == 2

    commit = await async_client.post(
        f"{API}/imports/commit", json={"files": files}, headers=clerk_admin_headers
    )
    assert commit.status_code == 201, commit.text
    assert commit.json()["created_counts"]["teacher_presence"] == 2

    saved_rows = (
        await db_session.execute(
            select(
                models.User.email,
                models.Teacher.lunch_required,
                models.Teacher.minimum_presence_hours,
                models.Teacher.maximum_presence_gap_hours,
            )
            .join(
                models.OrganizationMembership,
                models.OrganizationMembership.account_id == models.User.id,
            )
            .join(
                models.Teacher,
                models.Teacher.organization_membership_id == models.OrganizationMembership.id,
            )
            .where(models.User.email.in_(emails.values()))
        )
    ).all()
    saved = {email: (lunch, minimum, gap) for email, lunch, minimum, gap in saved_rows}
    assert saved[emails["Ana"]] == (True, 3, 1)
    assert saved[emails["Bruno"]] == (False, None, None)
    assert saved[emails["Carla"]] == (True, None, None)

    events = (
        await db_session.scalars(
            select(models.SchedulerStateVersionEvent).where(
                models.SchedulerStateVersionEvent.organization_id == organization_id,
                models.SchedulerStateVersionEvent.entity_type == "TEACHER_PRESENCE",
            )
        )
    ).all()
    assert len(events) == 2


async def test_teacher_presence_commit_keeps_an_absent_teacher_and_skips_noop_rows(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    organization_id = await _org_id(db_session)
    await _seed_scheduler_year(db_session, organization_id)
    changed = await create_teacher_profile(
        db_session, organization_id=organization_id, name="Changed"
    )
    untouched = await create_teacher_profile(
        db_session, organization_id=organization_id, name="Untouched"
    )
    changed_account = await db_session.get(
        models.User,
        (
            await db_session.get(models.OrganizationMembership, changed.organization_membership_id)
        ).account_id,
    )
    changed_account.email = f"changed.{uuid4().hex[:8]}@example.com"
    untouched_account = await db_session.get(
        models.User,
        (
            await db_session.get(
                models.OrganizationMembership, untouched.organization_membership_id
            )
        ).account_id,
    )
    untouched_account.email = f"untouched.{uuid4().hex[:8]}@example.com"
    await db_session.commit()

    noop = csv_payload(
        "Cronos_PresencaProfessores_Template.csv",
        TEACHER_PRESENCE_HEADER + teacher_presence_row("Untouched", untouched_account.email),
    )
    commit = await async_client.post(
        f"{API}/imports/commit",
        json={"files": {"teacher_presence": noop}},
        headers=clerk_admin_headers,
    )
    assert commit.status_code == 201, commit.text
    assert commit.json()["created_counts"]["teacher_presence"] == 0

    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(models.SchedulerStateVersionEvent)
            .where(
                models.SchedulerStateVersionEvent.organization_id == organization_id,
                models.SchedulerStateVersionEvent.entity_type == "TEACHER_PRESENCE",
            )
        )
        == 0
    )

    real = csv_payload(
        "Cronos_PresencaProfessores_Template.csv",
        TEACHER_PRESENCE_HEADER
        + teacher_presence_row("Changed", changed_account.email, "Sim", "3", "1"),
    )
    commit = await async_client.post(
        f"{API}/imports/commit",
        json={"files": {"teacher_presence": real}},
        headers=clerk_admin_headers,
    )
    assert commit.status_code == 201, commit.text
    assert commit.json()["created_counts"]["teacher_presence"] == 1

    await db_session.refresh(changed)
    await db_session.refresh(untouched)
    assert (
        changed.lunch_required,
        changed.minimum_presence_hours,
        changed.maximum_presence_gap_hours,
    ) == (True, 3, 1)
    assert (
        untouched.lunch_required,
        untouched.minimum_presence_hours,
        untouched.maximum_presence_gap_hours,
    ) == (True, None, None)


async def test_teacher_presence_validate_rejects_a_teacher_from_another_organization(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    foreign_org = models.Organization(name=f"Foreign {uuid4().hex[:6]}", plan_status="active")
    db_session.add(foreign_org)
    await db_session.flush()
    foreign = await create_teacher_profile(
        db_session, organization_id=foreign_org.id, name="Foreign"
    )
    foreign_account = await db_session.get(
        models.User,
        (
            await db_session.get(models.OrganizationMembership, foreign.organization_membership_id)
        ).account_id,
    )
    foreign_account.email = f"foreign.{uuid4().hex[:8]}@example.com"
    await db_session.commit()

    presence = csv_payload(
        "Cronos_PresencaProfessores_Template.csv",
        TEACHER_PRESENCE_HEADER
        + teacher_presence_row("Foreign", foreign_account.email, "Sim", "3", "1"),
    )

    validation = await async_client.post(
        f"{API}/imports/validate",
        json={"files": {"teacher_presence": presence}},
        headers=clerk_admin_headers,
    )
    assert validation.status_code == 200
    body = validation.json()
    assert body["can_commit"] is False
    assert any(
        issue["code"] == "teacher_reference_missing"
        and issue["message"] == "Professor não encontrado."
        and issue["field"] == "email"
        for issue in body["issues"]
    )

    commit = await async_client.post(
        f"{API}/imports/commit",
        json={"files": {"teacher_presence": presence}},
        headers=clerk_admin_headers,
    )
    assert commit.status_code == 422

    await db_session.refresh(foreign)
    assert (
        foreign.lunch_required,
        foreign.minimum_presence_hours,
        foreign.maximum_presence_gap_hours,
    ) == (True, None, None)


async def test_teacher_presence_template_lists_active_teachers_and_current_values(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    organization_id = await _org_id(db_session)
    teacher = await create_teacher_profile(
        db_session, organization_id=organization_id, name="Zeta Template"
    )
    account = await db_session.get(
        models.User,
        (
            await db_session.get(models.OrganizationMembership, teacher.organization_membership_id)
        ).account_id,
    )
    account.email = "zeta.template@example.invalid"
    teacher.lunch_required = False
    teacher.minimum_presence_hours = 4
    teacher.maximum_presence_gap_hours = 2
    await db_session.commit()

    response = await async_client.get(
        f"{API}/imports/templates/teacher_presence", headers=clerk_admin_headers
    )

    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert (
        'filename="Cronos_PresencaProfessores_Template.csv"'
        in response.headers["content-disposition"]
    )
    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines[0] == (
        "Nome do professor;Email do professor;Hora de almoço;"
        "Mínimo de horas por presença;Furo máximo (horas)"
    )
    assert "Zeta Template;zeta.template@example.invalid;Não;4;2" in lines


async def test_teacher_presence_commit_skips_a_nondefault_noop_row(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    organization_id = await _org_id(db_session)
    await _seed_scheduler_year(db_session, organization_id)
    teacher = await create_teacher_profile(
        db_session, organization_id=organization_id, name="Stable"
    )
    account = await db_session.get(
        models.User,
        (
            await db_session.get(models.OrganizationMembership, teacher.organization_membership_id)
        ).account_id,
    )
    account.email = f"stable.{uuid4().hex[:8]}@example.com"
    teacher.minimum_presence_hours = 2
    teacher.maximum_presence_gap_hours = 1
    await db_session.commit()

    payload = csv_payload(
        "Cronos_PresencaProfessores_Template.csv",
        TEACHER_PRESENCE_HEADER + teacher_presence_row("Stable", account.email, "Sim", "2", "1"),
    )
    commit = await async_client.post(
        f"{API}/imports/commit",
        json={"files": {"teacher_presence": payload}},
        headers=clerk_admin_headers,
    )
    assert commit.status_code == 201, commit.text
    assert commit.json()["created_counts"]["teacher_presence"] == 0
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(models.SchedulerStateVersionEvent)
            .where(
                models.SchedulerStateVersionEvent.organization_id == organization_id,
                models.SchedulerStateVersionEvent.entity_type == "TEACHER_PRESENCE",
            )
        )
        == 0
    )


async def test_teacher_presence_template_excludes_archived_teachers(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    organization_id = await _org_id(db_session)
    archived = await create_teacher_profile(
        db_session, organization_id=organization_id, name="Archived Presence"
    )
    membership = await db_session.get(
        models.OrganizationMembership, archived.organization_membership_id
    )
    account = await db_session.get(models.User, membership.account_id)
    account.email = "archived.presence@example.invalid"
    membership.lifecycle_status = models.MembershipLifecycleStatus.archived
    await db_session.commit()

    response = await async_client.get(
        f"{API}/imports/templates/teacher_presence", headers=clerk_admin_headers
    )

    assert response.status_code == 200
    lines = response.content.decode("utf-8-sig").splitlines()
    assert all("archived.presence@example.invalid" not in line for line in lines)


async def test_teacher_presence_template_excludes_active_members_without_teacher_capability(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
):
    organization_id = await _org_id(db_session)
    teacher = await create_teacher_profile(
        db_session, organization_id=organization_id, name="Sem Capacidade"
    )
    membership = await db_session.get(
        models.OrganizationMembership, teacher.organization_membership_id
    )
    account = await db_session.get(models.User, membership.account_id)
    account.email = "sem.capacidade@example.invalid"
    membership.lifecycle_status = models.MembershipLifecycleStatus.active
    membership.can_admin = True
    membership.can_teach = False
    membership.teacher_access_mode = None
    await db_session.commit()

    response = await async_client.get(
        f"{API}/imports/templates/teacher_presence", headers=clerk_admin_headers
    )

    assert response.status_code == 200
    lines = response.content.decode("utf-8-sig").splitlines()
    assert all("sem.capacidade@example.invalid" not in line for line in lines)
