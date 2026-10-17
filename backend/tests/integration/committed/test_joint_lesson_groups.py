"""Joint lesson group configuration API (WBS 4.3-4.5)."""

from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import models
from app.config import settings
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularExecution,
    CurricularExecutionCredit,
    CurricularRequirement,
)
from app.services.room_type_service import ensure_initial_room_types
from tests._support.db_fixtures import (
    MOCK_ORG_ID,
    create_teacher_profile,
    get_school_room_type_id,
)

API = settings.API_V1_STR


async def _seed_catalog(db_session, *, classes: int = 2, modules: int = 3):
    organization = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == MOCK_ORG_ID)
    )
    await ensure_initial_room_types(db_session, organization.id)
    course = models.Course(
        name="Curso", abbreviation="CRS", organization_id=organization.id, is_archived=False
    )
    subject = models.Subject(
        name="Português",
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
        organization_id=organization.id,
        is_archived=False,
    )
    db_session.add_all([course, subject])
    await db_session.flush()
    module_ids = []
    for order in range(modules):
        module = models.Module(
            organization_id=organization.id,
            name=f"M{order + 1}",
            required_minutes=50,
            order=order,
            subject_id=subject.id,
        )
        db_session.add(module)
        module_ids.append(module)
    await db_session.flush()
    class_ids = []
    link_ids = []
    for index in range(classes):
        school_class = models.Class(
            name=f"Turma {index}",
            size=20,
            course_id=course.id,
            grade_level=10,
            start_year=2025,
            end_year=2028,
            organization_id=organization.id,
            is_archived=False,
        )
        db_session.add(school_class)
        await db_session.flush()
        link = models.ClassSubjectLink(
            organization_id=organization.id,
            class_id=school_class.id,
            subject_id=subject.id,
            grade_level=10,
        )
        db_session.add(link)
        await db_session.flush()
        class_ids.append(school_class.id)
        link_ids.append(link.id)
        await db_session.execute(
            models.class_subject_module.insert().values(
                [
                    {
                        "organization_id": organization.id,
                        "class_subject_link_id": link.id,
                        "module_id": module.id,
                    }
                    for module in module_ids
                ]
            )
        )
    teacher = await create_teacher_profile(
        db_session, organization_id=organization.id, subject_ids=[subject.id]
    )
    year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 6, 30),
        timezone="Europe/Lisbon",
        is_active=True,
    )
    db_session.add(year)
    await db_session.commit()
    return {
        "organization_id": organization.id,
        "course_id": course.id,
        "subject_id": subject.id,
        "module_ids": [module.id for module in module_ids],
        "class_ids": class_ids,
        "link_ids": link_ids,
        "teacher_id": teacher.id,
    }


def _write_payload(seed, *, class_ids=None, module_ids=None, teacher_id=None, subject=True):
    return {
        "subject_id": seed["subject_id"] if subject else None,
        "class_ids": class_ids if class_ids is not None else seed["class_ids"],
        "module_ids": module_ids if module_ids is not None else seed["module_ids"],
        "teacher_id": teacher_id if teacher_id is not None else seed["teacher_id"],
    }


async def _active_year_id(db_session, organization_id):
    return await db_session.scalar(
        select(models.SchedulerSchoolYear.id).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )


async def _mark_module_started(db_session, seed, class_id, module_id, *, year_id=None, minutes=50):
    """Create the current-year projection rows that mark a module as started."""
    if year_id is None:
        year_id = await _active_year_id(db_session, seed["organization_id"])
    membership_id = await db_session.scalar(
        select(models.OrganizationMembership.id).where(
            models.OrganizationMembership.organization_id == seed["organization_id"],
            models.OrganizationMembership.can_admin.is_(True),
        )
    )
    assignment = CurricularAssignment(
        organization_id=seed["organization_id"],
        school_year_id=year_id,
        class_id=class_id,
        subject_id=seed["subject_id"],
        teacher_id=seed["teacher_id"],
    )
    db_session.add(assignment)
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=seed["organization_id"],
            assignment_id=assignment.id,
            module_id=module_id,
            sequence=1,
            required_minutes=50,
        )
    )
    await db_session.flush()
    execution = CurricularExecution(
        organization_id=seed["organization_id"],
        assignment_id=assignment.id,
        origin=f"test:{class_id}:{module_id}:{year_id}",
        revision=1,
        author_membership_id=membership_id,
        reason="test",
        recorded_at=datetime(2025, 9, 10, 10, tzinfo=UTC),
        planning_relevant=True,
    )
    db_session.add(execution)
    await db_session.flush()
    db_session.add(
        CurricularExecutionCredit(
            organization_id=seed["organization_id"],
            execution_id=execution.id,
            module_id=module_id,
            offset_minutes=0,
            delta_minutes=minutes,
        )
    )
    await db_session.commit()
    return assignment


async def _seed_skewed_catalog(db_session):
    """Seed a subject where class ids and link ids never coincide."""
    organization = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == MOCK_ORG_ID)
    )
    course = models.Course(
        name="Curso", abbreviation="CRS", organization_id=organization.id, is_archived=False
    )
    subject = models.Subject(
        name="Português",
        organization_id=organization.id,
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    other_subject = models.Subject(
        name="Matemática",
        organization_id=organization.id,
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    third_subject = models.Subject(
        name="Inglês",
        organization_id=organization.id,
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    db_session.add_all([course, subject, other_subject, third_subject])
    await db_session.flush()
    module = models.Module(
        organization_id=organization.id,
        name="M1",
        required_minutes=50,
        order=0,
        subject_id=subject.id,
    )
    db_session.add(module)
    await db_session.flush()

    def _class(name):
        return models.Class(
            name=name,
            size=20,
            course_id=course.id,
            grade_level=10,
            start_year=2025,
            end_year=2028,
            organization_id=organization.id,
        )

    dummy = _class("Dummy")
    class_a = _class("A")
    class_b = _class("B")
    db_session.add_all([dummy, class_a, class_b])
    await db_session.flush()
    # Two dummy links advance the link sequence past the class sequence.
    db_session.add_all(
        [
            models.ClassSubjectLink(
                organization_id=organization.id,
                class_id=dummy.id,
                subject_id=other_subject.id,
                grade_level=10,
            ),
            models.ClassSubjectLink(
                organization_id=organization.id,
                class_id=dummy.id,
                subject_id=third_subject.id,
                grade_level=10,
            ),
        ]
    )
    await db_session.flush()
    link_a = models.ClassSubjectLink(
        organization_id=organization.id,
        class_id=class_a.id,
        subject_id=subject.id,
        grade_level=10,
    )
    link_b = models.ClassSubjectLink(
        organization_id=organization.id,
        class_id=class_b.id,
        subject_id=subject.id,
        grade_level=10,
    )
    db_session.add_all([link_a, link_b])
    await db_session.flush()
    for link in (link_a, link_b):
        await db_session.execute(
            models.class_subject_module.insert().values(
                organization_id=organization.id,
                class_subject_link_id=link.id,
                module_id=module.id,
            )
        )
    teacher = await create_teacher_profile(
        db_session, organization_id=organization.id, subject_ids=[subject.id]
    )
    db_session.add(
        models.SchedulerSchoolYear(
            organization_id=organization.id,
            label="2025/2026",
            start_date=date(2025, 9, 1),
            hard_end_date=date(2026, 6, 30),
            timezone="Europe/Lisbon",
            is_active=True,
        )
    )
    await db_session.commit()
    assert link_a.id != class_a.id
    assert link_b.id != class_b.id
    return {
        "organization_id": organization.id,
        "course_id": course.id,
        "subject_id": subject.id,
        "module_ids": [module.id],
        "class_ids": [class_a.id, class_b.id],
        "link_ids": [link_a.id, link_b.id],
        "teacher_id": teacher.id,
    }


async def test_create_propagates_teacher_and_records_change(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session)
    response = await async_client.post(
        f"{API}/joint-lesson-groups",
        json=_write_payload(seed),
        headers=clerk_admin_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["subject_id"] == seed["subject_id"]
    assert body["teacher_id"] == seed["teacher_id"]
    assert [item["class_id"] for item in body["classes"]] == sorted(seed["class_ids"])
    assert body["module_ids"] == sorted(seed["module_ids"])

    teachers = (
        (
            await db_session.execute(
                select(models.ClassSubjectLink.teacher_id).where(
                    models.ClassSubjectLink.id.in_(seed["link_ids"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert teachers == [seed["teacher_id"], seed["teacher_id"]]

    event = await db_session.scalar(
        select(models.SchedulerStateVersionEvent.entity_type).where(
            models.SchedulerStateVersionEvent.organization_id == seed["organization_id"],
            models.SchedulerStateVersionEvent.entity_type == "JOINT_LESSON_GROUP",
        )
    )
    assert event == "JOINT_LESSON_GROUP"

    subjects = await async_client.get(
        f"{API}/classes/{seed['class_ids'][0]}/subjects", headers=clerk_admin_headers
    )
    assert subjects.status_code == 200
    joint = next(
        item for item in subjects.json()["subjects"] if item["subject_id"] == seed["subject_id"]
    )
    assert joint["joint_group"]["id"] == body["id"]

    updated = await async_client.put(
        f"{API}/joint-lesson-groups/{body['id']}",
        json=_write_payload(seed, module_ids=seed["module_ids"][:2]),
        headers=clerk_admin_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["module_ids"] == sorted(seed["module_ids"][:2])

    deleted = await async_client.delete(
        f"{API}/joint-lesson-groups/{body['id']}", headers=clerk_admin_headers
    )
    assert deleted.status_code == 204

    subjects = await async_client.get(
        f"{API}/classes/{seed['class_ids'][0]}/subjects", headers=clerk_admin_headers
    )
    joint = next(
        item for item in subjects.json()["subjects"] if item["subject_id"] == seed["subject_id"]
    )
    assert joint["joint_group"] is None


async def test_candidates_exclude_self_without_subject_and_joined(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session, classes=4)
    created = await async_client.post(
        f"{API}/joint-lesson-groups",
        json=_write_payload(seed, class_ids=seed["class_ids"][:2]),
        headers=clerk_admin_headers,
    )
    assert created.status_code == 201, created.text

    # The fourth class loses the subject and must not be a candidate.
    await db_session.execute(
        models.class_subject_module.delete().where(
            models.class_subject_module.c.class_subject_link_id == seed["link_ids"][3]
        )
    )
    await db_session.execute(
        models.ClassSubjectLink.__table__.delete().where(
            models.ClassSubjectLink.id == seed["link_ids"][3]
        )
    )
    await db_session.commit()

    response = await async_client.get(
        f"{API}/subjects/{seed['subject_id']}/joint-candidates",
        params={"class_id": seed["class_ids"][0]},
        headers=clerk_admin_headers,
    )
    assert response.status_code == 200, response.text
    candidate_ids = {item["class_id"] for item in response.json()}
    assert seed["class_ids"][0] not in candidate_ids
    assert seed["class_ids"][1] not in candidate_ids
    assert seed["class_ids"][2] in candidate_ids
    assert seed["class_ids"][3] not in candidate_ids
    candidate = next(item for item in response.json() if item["class_id"] == seed["class_ids"][2])
    assert candidate["selected_module_ids"] == sorted(seed["module_ids"])


async def test_joint_module_cannot_be_unchecked_and_teacher_propagates(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session)
    created = await async_client.post(
        f"{API}/joint-lesson-groups", json=_write_payload(seed), headers=clerk_admin_headers
    )
    assert created.status_code == 201, created.text

    locked = await async_client.patch(
        f"{API}/classes/{seed['class_ids'][0]}/subjects/{seed['subject_id']}",
        json={"module_ids": seed["module_ids"][1:]},
        headers=clerk_admin_headers,
    )
    assert locked.status_code == 409, locked.text
    assert locked.json()["detail"]["code"] == "JOINT_MODULE_LOCKED"

    second = await create_teacher_profile(
        db_session, organization_id=seed["organization_id"], subject_ids=[seed["subject_id"]]
    )
    await db_session.commit()
    changed = await async_client.patch(
        f"{API}/classes/{seed['class_ids'][0]}/subjects/{seed['subject_id']}",
        json={"teacher_id": second.id},
        headers=clerk_admin_headers,
    )
    assert changed.status_code == 200, changed.text
    teachers = (
        (
            await db_session.execute(
                select(models.ClassSubjectLink.teacher_id).where(
                    models.ClassSubjectLink.id.in_(seed["link_ids"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert set(teachers) == {second.id}


async def test_member_link_and_class_are_in_use(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session)
    await async_client.post(
        f"{API}/joint-lesson-groups", json=_write_payload(seed), headers=clerk_admin_headers
    )

    removed = await async_client.delete(
        f"{API}/classes/{seed['class_ids'][0]}/subjects/{seed['subject_id']}",
        headers=clerk_admin_headers,
    )
    assert removed.status_code == 409, removed.text

    archived = await async_client.delete(
        f"{API}/courses/{seed['course_id']}/classes/{seed['class_ids'][0]}",
        headers=clerk_admin_headers,
    )
    assert archived.status_code == 409, archived.text

    subject_deleted = await async_client.delete(
        f"{API}/subjects/{seed['subject_id']}",
        headers=clerk_admin_headers,
    )
    assert subject_deleted.status_code == 409, subject_deleted.text


async def test_joint_module_cannot_be_removed_from_subject(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session)
    await async_client.post(
        f"{API}/joint-lesson-groups", json=_write_payload(seed), headers=clerk_admin_headers
    )

    response = await async_client.patch(
        f"{API}/subjects/{seed['subject_id']}",
        json={
            "name": "Português",
            "modules": [
                {"id": module_id, "name": f"M{index}", "hours_total": 1, "order": index}
                for index, module_id in enumerate(seed["module_ids"][1:])
            ],
        },
        headers=clerk_admin_headers,
    )
    assert response.status_code == 409, response.text


async def test_group_from_another_organization_is_not_found(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    await _seed_catalog(db_session)
    other_org = models.Organization(
        name="Outra", clerk_org_id="org_other_joint", plan_status="active"
    )
    db_session.add(other_org)
    await db_session.flush()
    await ensure_initial_room_types(db_session, other_org.id)
    other_subject = models.Subject(
        name="Português",
        room_type_id=await get_school_room_type_id(db_session, other_org.id, "Normal"),
        organization_id=other_org.id,
        is_archived=False,
    )
    db_session.add(other_subject)
    await db_session.flush()
    other_group = models.JointLessonGroup(organization_id=other_org.id, subject_id=other_subject.id)
    db_session.add(other_group)
    await db_session.commit()

    response = await async_client.delete(
        f"{API}/joint-lesson-groups/{other_group.id}", headers=clerk_admin_headers
    )
    assert response.status_code == 404, response.text


async def test_non_admin_cannot_create_joint_group(
    async_client: AsyncClient, clerk_admin_headers, clerk_teacher_headers, db_session
):
    seed = await _seed_catalog(db_session)
    response = await async_client.post(
        f"{API}/joint-lesson-groups",
        json=_write_payload(seed),
        headers=clerk_teacher_headers,
    )
    assert response.status_code == 403, response.text


@pytest.mark.parametrize("class_count", [1])
async def test_too_few_classes_is_rejected(
    async_client: AsyncClient, clerk_admin_headers, db_session, class_count
):
    seed = await _seed_catalog(db_session, classes=2)
    response = await async_client.post(
        f"{API}/joint-lesson-groups",
        json=_write_payload(seed, class_ids=seed["class_ids"][:class_count]),
        headers=clerk_admin_headers,
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "JOINT_TOO_FEW_CLASSES"


async def test_candidates_use_class_ids_not_link_ids(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_skewed_catalog(db_session)

    response = await async_client.get(
        f"{API}/subjects/{seed['subject_id']}/joint-candidates",
        params={"class_id": seed["class_ids"][0]},
        headers=clerk_admin_headers,
    )
    assert response.status_code == 200, response.text
    returned = {item["class_id"] for item in response.json()}
    assert returned == {seed["class_ids"][1]}
    assert seed["link_ids"][1] not in returned


async def test_candidates_with_group_id_include_current_members(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session, classes=3)
    created = await async_client.post(
        f"{API}/joint-lesson-groups",
        json=_write_payload(seed, class_ids=seed["class_ids"][:2]),
        headers=clerk_admin_headers,
    )
    assert created.status_code == 201, created.text
    group_id = created.json()["id"]

    default = await async_client.get(
        f"{API}/subjects/{seed['subject_id']}/joint-candidates",
        params={"class_id": seed["class_ids"][0]},
        headers=clerk_admin_headers,
    )
    default_ids = {item["class_id"] for item in default.json()}
    assert default_ids == {seed["class_ids"][2]}

    editing = await async_client.get(
        f"{API}/subjects/{seed['subject_id']}/joint-candidates",
        params={"class_id": seed["class_ids"][0], "group_id": group_id},
        headers=clerk_admin_headers,
    )
    assert editing.status_code == 200, editing.text
    editing_ids = {item["class_id"] for item in editing.json()}
    assert editing_ids == set(seed["class_ids"])
    source = next(item for item in editing.json() if item["class_id"] == seed["class_ids"][0])
    assert source["selected_module_ids"] == sorted(seed["module_ids"])
    assert source["started_module_ids"] == []


async def test_candidates_group_id_validates_tenant_subject_and_membership(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session, classes=3)
    created = await async_client.post(
        f"{API}/joint-lesson-groups",
        json=_write_payload(seed, class_ids=seed["class_ids"][:2]),
        headers=clerk_admin_headers,
    )
    group_id = created.json()["id"]

    other = await async_client.get(
        f"{API}/subjects/{seed['subject_id']}/joint-candidates",
        params={"class_id": seed["class_ids"][0], "group_id": 999_999},
        headers=clerk_admin_headers,
    )
    assert other.status_code == 404, other.text

    # A class that is not a member of the group is refused.
    outsider = await async_client.get(
        f"{API}/subjects/{seed['subject_id']}/joint-candidates",
        params={"class_id": seed["class_ids"][2], "group_id": group_id},
        headers=clerk_admin_headers,
    )
    assert outsider.status_code == 404, outsider.text


async def test_teacher_and_modules_are_required_and_tenant_scoped(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session)
    base = _write_payload(seed)

    missing_teacher = dict(base)
    missing_teacher.pop("teacher_id")
    response = await async_client.post(
        f"{API}/joint-lesson-groups", json=missing_teacher, headers=clerk_admin_headers
    )
    assert response.status_code == 422, response.text

    null_teacher = {**base, "teacher_id": None}
    response = await async_client.post(
        f"{API}/joint-lesson-groups", json=null_teacher, headers=clerk_admin_headers
    )
    assert response.status_code == 422, response.text

    unknown_teacher = {**base, "teacher_id": 999_999}
    response = await async_client.post(
        f"{API}/joint-lesson-groups", json=unknown_teacher, headers=clerk_admin_headers
    )
    assert response.status_code == 404, response.text

    unknown_module = {**base, "module_ids": [999_999]}
    response = await async_client.post(
        f"{API}/joint-lesson-groups", json=unknown_module, headers=clerk_admin_headers
    )
    assert response.status_code == 404, response.text

    duplicate_modules = {**base, "module_ids": [seed["module_ids"][0], seed["module_ids"][0]]}
    response = await async_client.post(
        f"{API}/joint-lesson-groups", json=duplicate_modules, headers=clerk_admin_headers
    )
    assert response.status_code == 400, response.text

    duplicate_classes = {**base, "class_ids": [seed["class_ids"][0], seed["class_ids"][0]]}
    response = await async_client.post(
        f"{API}/joint-lesson-groups", json=duplicate_classes, headers=clerk_admin_headers
    )
    assert response.status_code == 400, response.text


async def test_started_module_blocks_delete_and_edit(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session, classes=3)
    created = await async_client.post(
        f"{API}/joint-lesson-groups", json=_write_payload(seed), headers=clerk_admin_headers
    )
    assert created.status_code == 201, created.text
    group_id = created.json()["id"]
    await _mark_module_started(db_session, seed, seed["class_ids"][0], seed["module_ids"][0])

    unchanged = await async_client.put(
        f"{API}/joint-lesson-groups/{group_id}",
        json=_write_payload(seed),
        headers=clerk_admin_headers,
    )
    assert unchanged.status_code == 200, unchanged.text

    remove_module = await async_client.put(
        f"{API}/joint-lesson-groups/{group_id}",
        json=_write_payload(seed, module_ids=seed["module_ids"][1:]),
        headers=clerk_admin_headers,
    )
    assert remove_module.status_code == 409, remove_module.text
    assert remove_module.json()["detail"]["code"] == "JOINT_MODULE_STARTED"

    remove_class = await async_client.put(
        f"{API}/joint-lesson-groups/{group_id}",
        json=_write_payload(seed, class_ids=seed["class_ids"][:2]),
        headers=clerk_admin_headers,
    )
    assert remove_class.status_code == 409, remove_class.text
    assert remove_class.json()["detail"]["code"] == "JOINT_CLASS_STARTED"

    deleted = await async_client.delete(
        f"{API}/joint-lesson-groups/{group_id}", headers=clerk_admin_headers
    )
    assert deleted.status_code == 409, deleted.text
    assert deleted.json()["detail"]["code"] == "JOINT_MODULE_STARTED"

    still_there = await async_client.get(
        f"{API}/classes/{seed['class_ids'][0]}/subjects", headers=clerk_admin_headers
    )
    joint = next(
        item for item in still_there.json()["subjects"] if item["subject_id"] == seed["subject_id"]
    )
    assert joint["joint_group"]["id"] == group_id

    editing = await async_client.get(
        f"{API}/subjects/{seed['subject_id']}/joint-candidates",
        params={"class_id": seed["class_ids"][0], "group_id": group_id},
        headers=clerk_admin_headers,
    )
    source = next(item for item in editing.json() if item["class_id"] == seed["class_ids"][0])
    assert source["started_module_ids"] == [seed["module_ids"][0]]


async def test_create_with_a_started_module_is_rejected(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session)
    await _mark_module_started(db_session, seed, seed["class_ids"][0], seed["module_ids"][0])

    response = await async_client.post(
        f"{API}/joint-lesson-groups", json=_write_payload(seed), headers=clerk_admin_headers
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "JOINT_MODULE_STARTED"


async def test_previous_year_progress_does_not_start_a_module(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session)
    old_year = models.SchedulerSchoolYear(
        organization_id=seed["organization_id"],
        label="2024/2025",
        start_date=date(2024, 9, 1),
        hard_end_date=date(2025, 6, 30),
        timezone="Europe/Lisbon",
        is_active=False,
    )
    db_session.add(old_year)
    await db_session.commit()
    await _mark_module_started(
        db_session, seed, seed["class_ids"][0], seed["module_ids"][0], year_id=old_year.id
    )

    created = await async_client.post(
        f"{API}/joint-lesson-groups", json=_write_payload(seed), headers=clerk_admin_headers
    )
    assert created.status_code == 201, created.text

    deleted = await async_client.delete(
        f"{API}/joint-lesson-groups/{created.json()['id']}", headers=clerk_admin_headers
    )
    assert deleted.status_code == 204, deleted.text


async def test_candidates_include_source_flag_supplies_source_facts(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session, classes=2)
    await db_session.execute(
        models.ClassSubjectLink.__table__.update()
        .where(models.ClassSubjectLink.id == seed["link_ids"][0])
        .values(teacher_id=seed["teacher_id"])
    )
    await db_session.commit()
    await _mark_module_started(db_session, seed, seed["class_ids"][0], seed["module_ids"][0])

    default = await async_client.get(
        f"{API}/subjects/{seed['subject_id']}/joint-candidates",
        params={"class_id": seed["class_ids"][0]},
        headers=clerk_admin_headers,
    )
    default_ids = {item["class_id"] for item in default.json()}
    assert seed["class_ids"][0] not in default_ids
    assert default_ids == {seed["class_ids"][1]}

    included = await async_client.get(
        f"{API}/subjects/{seed['subject_id']}/joint-candidates",
        params={"class_id": seed["class_ids"][0], "include_source": True},
        headers=clerk_admin_headers,
    )
    assert included.status_code == 200, included.text
    assert {item["class_id"] for item in included.json()} == set(seed["class_ids"])
    source = next(item for item in included.json() if item["class_id"] == seed["class_ids"][0])
    assert source["started_module_ids"] == [seed["module_ids"][0]]
    assert source["selected_module_ids"] == sorted(seed["module_ids"])
    assert source["teacher_id"] == seed["teacher_id"]


async def test_candidates_include_source_from_another_org_is_not_found(
    async_client: AsyncClient, clerk_admin_headers, db_session
):
    seed = await _seed_catalog(db_session)
    other_org = models.Organization(
        name="Outra", clerk_org_id="org_include_source_other", plan_status="active"
    )
    db_session.add(other_org)
    await db_session.flush()
    await ensure_initial_room_types(db_session, other_org.id)
    other_subject = models.Subject(
        name="Português",
        organization_id=other_org.id,
        room_type_id=await get_school_room_type_id(db_session, other_org.id, "Normal"),
    )
    other_course = models.Course(
        name="Outro curso", abbreviation="OC", organization_id=other_org.id
    )
    db_session.add_all([other_subject, other_course])
    await db_session.flush()
    other_class = models.Class(
        name="Outra turma",
        size=20,
        course_id=other_course.id,
        grade_level=10,
        start_year=2025,
        end_year=2028,
        organization_id=other_org.id,
    )
    db_session.add(other_class)
    await db_session.commit()

    response = await async_client.get(
        f"{API}/subjects/{seed['subject_id']}/joint-candidates",
        params={"class_id": other_class.id, "include_source": True},
        headers=clerk_admin_headers,
    )
    assert response.status_code == 404, response.text
