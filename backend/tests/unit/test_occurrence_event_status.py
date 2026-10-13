from contextlib import nullcontext

from app.services import occurrence_service


class _Session:
    def __init__(self):
        self.added = []

    def begin_nested(self):
        return nullcontext()

    def add(self, item):
        self.added.append(item)

    def flush(self):
        pass


def test_a_decision_status_read_from_the_v1_payload_is_recorded():
    session = _Session()
    occurrence_service.log_occurrence_event_safe_sync(
        session,
        organization_id=1,
        event_type=occurrence_service.OBS_EVENT_DECIDE,
        result=occurrence_service.OBS_RESULT_SUCCESS,
        occurrence_id=7,
        decision_status="GAP",
    )
    assert [event.decision_status for event in session.added] == ["GAP"]
