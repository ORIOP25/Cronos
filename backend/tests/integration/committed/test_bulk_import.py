import base64
import csv
import io
from datetime import date, time
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.config import settings

API = settings.API_V1_STR


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
            f"Sigla do curso;Nome do curso;Nome da turma;Ano escolar;Ano de início;Ano de fim;Número de alunos\r\n"
            f"C{suffix[:5].upper()};{course};10.º A;10;2025;2028;24\r\n",
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
            organization_id=1, name=row["Nome da disciplina"], is_archived=True
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
        archived = models.Subject(organization_id=1, name="Nome Livre", is_archived=True)
        active = models.Subject(organization_id=1, name="Nome Atual")
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


async def _prepare_class_grid(client: AsyncClient, headers: dict) -> list[dict]:
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
                "days_of_week": [0, 4],
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
        "Sigla do curso;Nome do curso;Nome da turma;Ano escolar;Ano de início;Ano de fim;Número de alunos\r\n"
        f"{abbreviation};Curso {suffix};10.º A;10;2025;2028;24\r\n",
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
