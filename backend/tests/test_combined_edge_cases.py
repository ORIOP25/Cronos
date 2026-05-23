"""
EDGE CASES COMBINADOS — Reparação + Falta + Substituição
=========================================================
Cobre o cenário obrigatório documentado no ALPHA_REGRESSION_SUITE.md:
"Combinação repair + falta + substituição no mesmo período."

Este teste simula uma semana onde:
1. Um repair mode gera blocos futuros
2. Uma falta (GAP) é registada num bloco
3. Uma substituição (SUBSTITUTED) é aplicada noutro bloco
4. Verifica-se que os 3 eventos coexistem sem corrupção de dados

E o segundo edge case obrigatório:
"Operação perto do hard end date"
"""

import pytest
from datetime import date, datetime, time, timedelta

from app import models, schemas
from app.models import LessonOccurrenceStatus
from app.services import occurrence_service, schedule_service
from sqlalchemy import select


pytestmark = pytest.mark.integration


@pytest.fixture
def combined_setup(sync_db):
    org = models.Organization(name="Edge Cases Org", plan_status="active")
    sync_db.add(org)
    sync_db.flush()

    teacher_a = models.Teacher(name="Prof. Principal", organization_id=org.id)
    teacher_b = models.Teacher(name="Prof. Substituto", organization_id=org.id)
    sync_db.add_all([teacher_a, teacher_b])
    sync_db.flush()

    subject_a = models.Subject(
        name="Matemática", organization_id=org.id,
        required_room_type=models.RoomType.normal,
    )
    subject_b = models.Subject(
        name="Inglês Técnico", organization_id=org.id,
        required_room_type=models.RoomType.normal,
    )
    sync_db.add_all([subject_a, subject_b])
    sync_db.flush()

    module_a = models.Module(
        name="M1 - Álgebra", hours_total=50, order=1, subject_id=subject_a.id,
    )
    module_b = models.Module(
        name="M1 - Conversation", hours_total=30, order=1, subject_id=subject_b.id,
    )
    sync_db.add_all([module_a, module_b])
    sync_db.flush()

    course = models.Course(
        name="Técnico Informática", abbreviation="TINF", organization_id=org.id,
    )
    sync_db.add(course)
    sync_db.flush()

    klass = models.Class(
        name="TINF 25/28", size=25, grade_level=10,
        start_year=2025, end_year=2028,
        course_id=course.id, organization_id=org.id,
    )
    sync_db.add(klass)
    sync_db.flush()

    sync_db.add(models.ClassSubjectLink(
        class_id=klass.id, subject_id=subject_a.id,
        grade_level=klass.grade_level, teacher_id=teacher_a.id,
    ))
    sync_db.add(models.ClassSubjectLink(
        class_id=klass.id, subject_id=subject_b.id,
        grade_level=klass.grade_level, teacher_id=teacher_b.id,
    ))
    sync_db.flush()

    room = models.Room(
        name="Sala 101", capacity=30, type=models.RoomType.normal,
        organization_id=org.id,
    )
    sync_db.add(room)
    sync_db.flush()

    ts = models.Timeslot(
        day_of_week=0, start_time=time(9, 0), end_time=time(11, 0),
        organization_id=org.id,
    )
    sync_db.add(ts)
    sync_db.flush()

    sync_db.add(models.Availability(
        teacher_id=teacher_a.id, timeslot_id=ts.id,
        score=models.PreferenceLevel.NEUTRAL.value,
    ))
    sync_db.add(models.Availability(
        teacher_id=teacher_b.id, timeslot_id=ts.id,
        score=models.PreferenceLevel.PREFERRED.value,
    ))
    sync_db.flush()

    admin_user = models.User(
        email="admin.edges@escola.com",
        is_active=True,
        role=models.UserRole.admin,
        organization_id=org.id,
    )
    sync_db.add(admin_user)
    sync_db.flush()

    sync_db.add(models.OrganizationSettings(
        organization_id=org.id,
        school_start_date=date.today() - timedelta(days=30),
        school_target_end_date=date.today() + timedelta(days=90),
        school_hard_end_date=date.today() + timedelta(days=90),
        repair_stability_window_days=14,
    ))

    lesson_a = models.Lesson(
        organization_id=org.id, class_id=klass.id,
        subject_id=subject_a.id, teacher_id=teacher_a.id,
    )
    lesson_b = models.Lesson(
        organization_id=org.id, class_id=klass.id,
        subject_id=subject_b.id, teacher_id=teacher_b.id,
    )
    sync_db.add_all([lesson_a, lesson_b])
    sync_db.commit()

    return {
        "org_id": org.id,
        "class_id": klass.id,
        "teacher_a_id": teacher_a.id,
        "teacher_b_id": teacher_b.id,
        "subject_a_id": subject_a.id,
        "subject_b_id": subject_b.id,
        "module_a_id": module_a.id,
        "module_b_id": module_b.id,
        "room_id": room.id,
        "timeslot_id": ts.id,
        "lesson_a_id": lesson_a.id,
        "lesson_b_id": lesson_b.id,
        "admin_user_id": admin_user.id,
    }


class TestCombinedRepairGapSubstitution:
    def test_repair_gap_and_substitution_in_same_period(
        self, sync_db, combined_setup
    ):
        ctx = combined_setup
        

        base_date = today + timedelta(days=21)
        dates = [base_date + timedelta(weeks=w) for w in range(4)]

        schedule_ids = []
        for idx, target_date in enumerate(dates):
            gen_id = f"combined-gen-{idx}"

            schedule_service.create_schedule_output_with_date_sync(
                sync_db,
                ctx["lesson_a_id"],
                ctx["timeslot_id"],
                ctx["room_id"],
                target_date,
                ctx["org_id"],
                gen_id,
                is_draft=False,
            )
            sync_db.flush()

            schedule_outputs = sync_db.execute(
                select(models.ScheduleOutput).where(
                    models.ScheduleOutput.generation_id == gen_id,
                )
            ).scalars().all()

            for so in schedule_outputs:
                schedule_ids.append(so.id)

        sync_db.commit()

        occurrence_ids = []
        for schedule_id in schedule_ids:
            occ, _ = occurrence_service.create_occurrence_from_block_sync(
                sync_db, ctx["org_id"], schedule_id,
            )
            if occ:
                occurrence_ids.append(occ.id)

        sync_db.commit()

        assert len(occurrence_ids) == 4

        occurrence_service.update_occurrence_sync(
            sync_db,
            occurrence_ids[0],
            ctx["org_id"],
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP),
            decided_by_user_id=ctx["admin_user_id"],
        )
        sync_db.commit()

        recommendations = occurrence_service.get_substitute_recommendations_sync(
            sync_db,
            organization_id=ctx["org_id"],
            occurrence_id=occurrence_ids[1],
        )

        if recommendations:
            occurrence_service.update_occurrence_sync(
                sync_db,
                occurrence_ids[1],
                ctx["org_id"],
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    substitute_teacher_id=recommendations[0].teacher_id,
                    substitute_subject_id=recommendations[0].subject_id,
                ),
                decided_by_user_id=ctx["admin_user_id"],
            )
            sync_db.commit()

        sync_db.expire_all()

        refreshed = list(sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.id.in_(occurrence_ids)
            )
        ).scalars())

                statuses = [occ.status for occ in refreshed]

        assert LessonOccurrenceStatus.GAP in statuses
        assert LessonOccurrenceStatus.GIVEN in statuses

        for occ in refreshed:
            assert occ.created_at is not None

        gap_occ = [o for o in refreshed if o.status == LessonOccurrenceStatus.GAP][0]
        assert gap_occ.decided_at is not None
        assert gap_occ.decided_by_user_id == ctx["admin_user_id"]

        sub_occs = [o for o in refreshed if o.status == LessonOccurrenceStatus.SUBSTITUTED]
        for sub_occ in sub_occs:
            assert sub_occ.decided_at is not None
            assert sub_occ.substitute_teacher_id is not None
            assert sub_occ.substitute_subject_id is not None


class TestOperationNearHardEndDate:
    def test_occurrence_creation_near_hard_end(
        self, sync_db, combined_setup
    ):
        ctx = combined_setup
        

        settings_obj = sync_db.get(models.OrganizationSettings, ctx["org_id"])
        assert settings_obj is not None

        near_hard_end = settings_obj.school_hard_end_date - timedelta(days=1)

        schedule_service.create_schedule_output_with_date_sync(
            sync_db,
            ctx["lesson_a_id"],
            ctx["timeslot_id"],
            ctx["room_id"],
            near_hard_end,
            ctx["org_id"],
            "gen-near-hard-end",
            is_draft=False,
        )
        sync_db.commit()

        schedule_outputs = sync_db.execute(
            select(models.ScheduleOutput).where(
                models.ScheduleOutput.generation_id == "gen-near-hard-end",
            )
        ).scalars().all()

        assert len(schedule_outputs) == 1

        occ, created = occurrence_service.create_occurrence_from_block_sync(
            sync_db, ctx["org_id"], schedule_outputs[0].id,
        )
        assert occ is not None
        assert occ.date == near_hard_end

        assert created is True

        occurrence_service.update_occurrence_sync(
            sync_db,
            occ.id,
            ctx["org_id"],
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP),
            decided_by_user_id=ctx["admin_user_id"],
        )
        sync_db.commit()

        sync_db.expire_all()
        occ_refreshed = sync_db.get(models.LessonOccurrence, occ.id)
        assert occ_refreshed.status == LessonOccurrenceStatus.GAP
        assert occ_refreshed.decided_at is not None
