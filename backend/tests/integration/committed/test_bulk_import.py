import base64
from uuid import uuid4

from httpx import AsyncClient

from app.config import settings

API = settings.API_V1_STR


def csv_payload(filename: str, content: str) -> dict[str, str]:
    return {
        "filename": filename,
        "content_base64": base64.b64encode(("\ufeff" + content).encode("utf-8")).decode("ascii"),
    }


def valid_files() -> dict[str, dict[str, str]]:
    suffix = uuid4().hex[:8]
    subject = f"Programação {suffix}"
    course = f"Curso {suffix}"
    teacher_email = f"teacher.{suffix}@example.com"
    return {
        "rooms": csv_payload("salas.csv", f"name;type;capacity\r\nSala {suffix};lab;24\r\n"),
        "subjects": csv_payload(
            "disciplinas.csv",
            f"name;required_room_type;module_name;module_code;module_hours;module_order\r\n"
            f"{subject};lab;Módulo {suffix};M{suffix};30;1\r\n",
        ),
        "courses": csv_payload(
            "cursos.csv",
            f"abbreviation;name;class_name;grade_level;start_year;end_year;size\r\n"
            f"C{suffix[:5].upper()};{course};10.º A;10;2025;2028;24\r\n",
        ),
        "teachers": csv_payload(
            "professores.csv",
            f"name;email;competency_subject\r\nProfessor {suffix};{teacher_email};{subject}\r\n",
        ),
        "assignments": csv_payload(
            "atribuicoes.csv",
            f"course_abbreviation;class_name;subject_name;teacher_email\r\n"
            f"C{suffix[:5].upper()};10.º A;{subject};{teacher_email}\r\n",
        ),
    }


async def test_bulk_import_validate_and_commit_is_atomic_and_tenant_scoped(
    async_client: AsyncClient, clerk_admin_headers: dict
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


async def test_bulk_import_rejects_example_without_writing(
    async_client: AsyncClient, clerk_admin_headers: dict
):
    before = await async_client.get(f"{API}/rooms/", headers=clerk_admin_headers)
    response = await async_client.post(
        f"{API}/imports/validate",
        json={
            "files": {
                "rooms": csv_payload(
                    "salas.csv",
                    "name;type;capacity\r\nSala de Exemplo;normal;30\r\n",
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
    response = await async_client.get(
        f"{API}/imports/templates/rooms", headers=clerk_admin_headers
    )
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "filename=\"salas.csv\"" in response.headers["content-disposition"]

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
                    "salas.csv",
                    "name;type;capacity\r\nSala de Exemplo;normal;30\r\n",
                )
            }
        },
        headers=clerk_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["context"]["can_commit"] is False
