from app.services.operational_seed_service import (
    seed_and_publish_operational_scenarios,
)


async def test_operational_seed_generates_approves_and_is_idempotent(
    runtime_db_session,
):
    first = await seed_and_publish_operational_scenarios(runtime_db_session)
    second = await seed_and_publish_operational_scenarios(runtime_db_session)

    assert first["signature"] == second["signature"]
    assert first["signature"]["active_block_count"] == 2
    assert len(first["signature"]["active_stable_keys"]) == 2
