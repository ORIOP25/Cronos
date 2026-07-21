"""Integration tests for POST /api/v1/schedule/constraints/ with real DB."""

import datetime

import pytest
import pytest_asyncio

from app import models
from tests.conftest import (
    ADMIN_USER_ID,
    MOCK_ORG_ID,
    create_org_and_user,
    create_teacher_profile,
)

CONSTRAINTS_URL = "/api/v1/schedule/constraints/"


@pytest_asyncio.fixture
async def admin_with_teacher(db_session, async_client):
    """Create org, admin user, teacher, and timeslot for constraint tests."""
    org, _user = await create_org_and_user(
        db_session,
        clerk_user_id=ADMIN_USER_ID,
        email="admin@test.com",
        role="admin",
        clerk_org_id=MOCK_ORG_ID,
    )
    teacher = await create_teacher_profile(
        db_session, organization_id=org.id, name="Prof. Constraint"
    )
    timeslot = models.Timeslot(
        organization_id=org.id,
        day_of_week=0,
        start_time=datetime.time(8, 0),
        end_time=datetime.time(9, 0),
    )
    db_session.add(timeslot)
    await db_session.commit()
    headers = {"Authorization": f"Bearer test_{ADMIN_USER_ID}"}
    return org, teacher, timeslot, headers


@pytest.mark.parametrize(
    "label,payload_fn",
    [
        (
            "timeslot_id",
            lambda t, ts: {
                "rule_type": "teacher_unavailable",
                "rule_payload": {"teacher_id": t.id, "timeslot_id": ts.id},
            },
        ),
        (
            "day_of_week",
            lambda t, ts: {
                "rule_type": "teacher_unavailable",
                "rule_payload": {"teacher_id": t.id, "day_of_week": 2},
            },
        ),
        (
            "date",
            lambda t, ts: {
                "rule_type": "teacher_unavailable",
                "rule_payload": {"teacher_id": t.id, "date": "2026-08-03"},
            },
        ),
        (
            "date+timeslot_id",
            lambda t, ts: {
                "rule_type": "teacher_unavailable",
                "rule_payload": {
                    "teacher_id": t.id,
                    "date": "2026-08-03",
                    "timeslot_id": ts.id,
                },
            },
        ),
    ],
)
async def test_teacher_unavailable_constraint_persists(
    admin_with_teacher, async_client, db_session, label, payload_fn
):
    org, teacher, timeslot, headers = admin_with_teacher
    payload = payload_fn(teacher, timeslot)

    resp = await async_client.post(CONSTRAINTS_URL, json=payload, headers=headers)
    assert resp.status_code == 200, f"[{label}] {resp.text}"

    data = resp.json()
    assert data["rule_type"] == "teacher_unavailable"

    # Verify persisted row
    row = await db_session.get(models.Constraint, data["id"])
    assert row is not None
    assert row.teacher_id == teacher.id

    rp = payload["rule_payload"]
    if "date" in rp:
        assert row.constraint_date == datetime.date(2026, 8, 3)
        assert isinstance(row.constraint_date, datetime.date)
        assert data["rule_payload"]["date"] == "2026-08-03"
    else:
        assert row.constraint_date is None

    if "timeslot_id" in rp:
        assert row.timeslot_id == timeslot.id
    elif label != "date+timeslot_id":
        assert row.timeslot_id is None

    if "day_of_week" in rp:
        assert row.day_of_week == 2
    else:
        assert row.day_of_week is None

    # Non-applicable columns must be NULL
    assert row.class_id is None
    assert row.subject_id is None
    assert row.room_id is None
