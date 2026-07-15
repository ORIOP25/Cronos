import pytest
from sqlalchemy import text


pytestmark = [pytest.mark.integration, pytest.mark.postgresql]


@pytest.mark.asyncio
async def test_orm_metadata_create_and_drop_cycle(orm_schema_session):
    """The fixture creates from ORM metadata and drops it during teardown."""
    assert await orm_schema_session.scalar(
        text("SELECT to_regclass('public.lesson_occurrence') IS NOT NULL")
    ) is True
    assert await orm_schema_session.scalar(
        text("SELECT to_regclass('public.active_schedule_blocks') IS NOT NULL")
    ) is True
