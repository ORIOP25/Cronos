"""
Fixtures e helpers partilhados pelos testes de lógica de negócio (split).
"""

from uuid import uuid4

from httpx import AsyncClient

from app.config import settings
from tests.conftest import create_teacher_user

API = settings.API_V1_STR


async def _create_teacher_auth_headers(
    db_session, *, teacher_id: int, organization_id: int
) -> tuple[dict, str]:
    """Cria utilizador teacher autenticado para testes de self-service.
    Returns headers and the persisted Clerk user ID used by the auth dependency override.
    """
    cid = f"teacher_avail_{uuid4().hex[:8]}"
    await create_teacher_user(
        db_session,
        clerk_user_id=cid,
        email=f"teacher.avail.{uuid4().hex[:8]}@escola.pt",
        name="Teacher Availability User",
        org_id=organization_id,
        teacher_id=teacher_id,
    )
    await db_session.commit()
    return {"Authorization": f"Bearer test_{cid}"}, cid


async def _setup_course_class_subject(client: AsyncClient, headers: dict):
    """Cria Curso + Turma + Disciplina com módulos, devolve IDs."""
    sub_resp = await client.post(
        f"{API}/subjects/",
        json={
            "name": "Programação",
            "required_room_type": "lab",
            "modules": [
                {"name": "M1", "code": "P01", "hours_total": 25, "order": 0},
                {"name": "M2", "code": "P02", "hours_total": 50, "order": 1},
            ],
        },
        headers=headers,
    )
    subject_id = sub_resp.json()["id"]
    modules = sub_resp.json()["modules"]

    course_resp = await client.post(
        f"{API}/courses/",
        json={"name": "Técnico Informática", "abbreviation": "TI", "subject_ids": [subject_id]},
        headers=headers,
    )
    course_id = course_resp.json()["id"]

    class_resp = await client.post(
        f"{API}/classes/",
        json={
            "name": "Turma TI-A",
            "course_id": course_id,
            "grade_level": 10,
            "start_year": 2025,
            "end_year": 2028,
        },
        headers=headers,
    )
    class_id = class_resp.json()["id"]

    await client.post(
        f"{API}/classes/{class_id}/subjects",
        json={"subject_id": subject_id},
        headers=headers,
    )

    return {
        "course_id": course_id,
        "class_id": class_id,
        "subject_id": subject_id,
        "module_ids": [m["id"] for m in modules],
        "module_hours": [m["hours_total"] for m in modules],
    }
