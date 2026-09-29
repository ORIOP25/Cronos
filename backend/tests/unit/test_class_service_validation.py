from types import SimpleNamespace

import pytest

from app import schemas
from app.core.exceptions import AppError
from app.services import class_service


class _NoopDb:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.flushes = 0
        self.refreshes = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        self.flushes += 1

    async def refresh(self, _obj):
        self.refreshes += 1


async def test_update_class_in_course_rejects_partial_year_update_without_mutating(monkeypatch):
    db_class = SimpleNamespace(
        name="TGPSI 10A",
        size=25,
        grade_level=10,
        start_year=2025,
        end_year=2028,
        is_archived=False,
    )

    async def fake_get_class_by_course_and_org(*_args):
        return db_class

    monkeypatch.setattr(
        class_service,
        "_get_class_by_course_and_org",
        fake_get_class_by_course_and_org,
    )

    db = _NoopDb()
    with pytest.raises(AppError) as error:
        await class_service.update_class_in_course(
            db,
            course_id=1,
            class_id=1,
            class_in=schemas.ClassUpdateInCourse(start_year=2028),
            organization_id=1,
        )

    assert error.value.kind == "bad_request"
    assert error.value.code == "bad_request"
    assert db_class.start_year == 2025
    assert db.commits == 0
