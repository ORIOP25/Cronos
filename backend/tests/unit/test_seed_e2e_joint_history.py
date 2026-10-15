from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from scripts import seed_e2e_joint_history as seed


def test_history_shift_keeps_the_default_when_it_already_ends_the_block():
    now = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)

    assert seed.history_shift_until_ended(
        datetime(2026, 9, 15, 10, 0, tzinfo=UTC), now=now
    ) == timedelta(days=14)


def test_history_shift_grows_by_whole_weeks_until_the_block_ended():
    now = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)

    # 14 days leaves 09-14 10:00 after `now`, so one whole week is added.
    assert seed.history_shift_until_ended(
        datetime(2026, 9, 28, 10, 0, tzinfo=UTC), now=now
    ) == timedelta(days=21)


@pytest.mark.parametrize(
    ("url", "name"),
    [
        ("postgresql+asyncpg://cronos_app:secret@db:5432/cronos_test_db", "cronos_test_db"),
        ("postgresql+psycopg2://cronos_migrator:secret@db:5432/cronos_ci_db", "cronos_ci_db"),
        ("postgresql+asyncpg://cronos_app:secret@db:5432/cronos_test_gw3", "cronos_test_gw3"),
    ],
)
def test_reserved_test_database_accepts_only_reserved_targets(url, name):
    assert seed.reserved_test_database(url) == name


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://cronos_app:secret@db:5432/cronos_db",
        "postgresql+asyncpg://cronos_app:secret@db:5432/production",
        "postgresql+asyncpg://cronos_app:secret@db:5432/cronos_test",
        "postgresql+asyncpg://cronos_app:secret@db:5432/cronos_ci",
        "",
    ],
)
def test_reserved_test_database_refuses_production_and_unknown_targets(url):
    with pytest.raises(ValueError):
        seed.reserved_test_database(url)


def test_validate_target_accepts_only_the_prepared_organization():
    seed.validate_target(
        organization_id=7, expected_clerk_org_id="org_test", clerk_org_id="org_test"
    )
    with pytest.raises(ValueError):
        seed.validate_target(
            organization_id=7, expected_clerk_org_id="org_test", clerk_org_id="org_other"
        )
    with pytest.raises(ValueError):
        seed.validate_target(organization_id=7, expected_clerk_org_id="", clerk_org_id="org_test")
    with pytest.raises(ValueError):
        seed.validate_target(
            organization_id=0, expected_clerk_org_id="org_test", clerk_org_id="org_test"
        )


def test_first_joint_block_selects_the_pair_that_shares_a_stable_key():
    plain = SimpleNamespace(id=1, stable_key="k1", teaching_unit_key="A:1")
    shared_a = SimpleNamespace(id=2, stable_key="k2", teaching_unit_key="S:1")
    shared_b = SimpleNamespace(id=3, stable_key="k2", teaching_unit_key="S:1")
    selected = seed.first_joint_block([(plain, 10), (shared_a, 11), (shared_b, 12)])
    assert selected == [shared_a, shared_b]


def test_first_joint_block_skips_a_deficit_pair_and_refuses_plain_lessons_only():
    deficit_a = SimpleNamespace(id=1, stable_key="d", teaching_unit_key="D:1")
    deficit_b = SimpleNamespace(id=2, stable_key="d", teaching_unit_key="D:1")
    with pytest.raises(ValueError):
        seed.first_joint_block([(deficit_a, 10), (deficit_b, 11)])

    plain = SimpleNamespace(id=3, stable_key="p", teaching_unit_key="A:3")
    with pytest.raises(ValueError):
        seed.first_joint_block([(plain, 10)])
