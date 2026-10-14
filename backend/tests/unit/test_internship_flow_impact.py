from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.internship_flow_service import compute_impact


async def test_preview_with_no_published_v1_lessons_needs_no_confirmation():
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(all=lambda: [])

    impact = await compute_impact(db, 1, [2], date(2026, 9, 1), date(2026, 9, 4))

    assert impact.lessons == ()
    assert impact.requires_confirmation is False
    assert impact.fingerprint is None
