from scripts.check_scheduler_baseline import (
    BASELINE_REVISION,
    baseline_status,
    chain_root,
    installed_head,
)


def test_current_chain_root_is_the_consolidated_baseline():
    assert chain_root() == BASELINE_REVISION
    assert installed_head() is not None


def test_a_non_baseline_chain_root_requires_explicit_acceptance():
    ok, message = baseline_status("0010_scheduler_failure_reference", accepted=False)

    assert ok is False
    assert "W12" in message
    assert "0010_scheduler_failure_reference" in message


def test_a_non_baseline_head_can_be_accepted_for_a_local_experiment():
    assert baseline_status("0010_scheduler_failure_reference", accepted=True)[0] is True


def test_the_consolidated_baseline_passes_without_acceptance():
    assert baseline_status(BASELINE_REVISION, accepted=False)[0] is True


def test_missing_revision_is_rejected():
    assert baseline_status(None, accepted=True)[0] is False
