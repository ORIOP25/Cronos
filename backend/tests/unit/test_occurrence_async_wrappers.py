from app.services import occurrence_service


class RunSyncSession:
    def __init__(self, sync_session):
        self.sync_session = sync_session

    async def run_sync(self, callback):
        return callback(self.sync_session)


async def test_get_occurrence_passes_run_sync_session_before_named_arguments(monkeypatch):
    sync_session = object()
    expected = object()

    def fake_get_occurrence_sync(db, *, occurrence_id, organization_id):
        assert db is sync_session
        assert occurrence_id == 11
        assert organization_id == 22
        return expected

    monkeypatch.setattr(occurrence_service, "get_occurrence_sync", fake_get_occurrence_sync)

    result = await occurrence_service.get_occurrence(
        RunSyncSession(sync_session), occurrence_id=11, organization_id=22
    )

    assert result is expected


async def test_get_debts_passes_run_sync_session_before_named_arguments(monkeypatch):
    sync_session = object()
    expected = object()

    def fake_get_debts_sync(db, *, organization_id, class_id):
        assert db is sync_session
        assert organization_id == 22
        assert class_id == 33
        return expected

    monkeypatch.setattr(occurrence_service, "get_debts_sync", fake_get_debts_sync)

    result = await occurrence_service.get_debts(
        RunSyncSession(sync_session), organization_id=22, class_id=33
    )

    assert result is expected
