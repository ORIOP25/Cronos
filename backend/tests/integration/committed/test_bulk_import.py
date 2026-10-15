import base64
import csv
import io
from datetime import date, time
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.config import settings
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from app.services.scheduler_state_service import SchedulerStateService

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
        organization_id=1, name="Programação", required_room_type=models.RoomType.normal
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
