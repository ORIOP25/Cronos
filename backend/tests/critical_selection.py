"""Authoritative critical CI selection for the backend fast job.

The fast backend gate runs only the paths declared here. The full corpus stays
available locally and in the long job; it is deselected, never deleted.

The root runner consumes ``critical_manifest.json``, which is generated from
this module. ``tests/unit/test_critical_selection_policy.py`` fails if the
committed manifest drifts from this policy.

The critical coverage scope is declared here as ``CRITICAL_SOURCES`` and exposed
through the manifest ``coverage.sources`` list. The runner joins that list and
runs ``coverage report --include=<joined sources> --fail-under=<fail_under>``.
``pyproject.toml`` keeps its whole-application default, so the optional full
developer run reports the honest whole-app metric.

``DB_CASES`` holds exact pytest node IDs. They select a small critical proof from
a large module without collecting the whole module.

Usage::

    python -m tests.critical_selection manifest   # JSON for the root runner
    python -m tests.critical_selection unit       # one unit path per line
    python -m tests.critical_selection db         # one database selector per line
    python -m tests.critical_selection sources    # one coverage source per line
"""

from __future__ import annotations

import json
import sys

# Critical unit tests. They run without a database and keep the loopback-only
# socket policy. The guard test ships with the selection so CI enforces it.
UNIT_PATHS: tuple[str, ...] = (
    "tests/unit/test_scheduler_constraint_policy.py",
    "tests/unit/test_constraint_schemas.py",
    "tests/unit/test_scheduler_room_eligibility.py",
    "tests/unit/test_scheduler_candidate_validation.py",
    "tests/unit/test_scheduler_candidate_contracts.py",
    "tests/unit/test_scheduler_lunch_break_v1.py",
    "tests/unit/test_scheduler_resource_exclusivity_v1.py",
    "tests/unit/test_scheduler_progress_domain.py",
    "tests/unit/test_scheduler_debt_domain.py",
    "tests/unit/test_scheduler_module_projection.py",
    "tests/unit/test_lesson_time_rule.py",
    "tests/unit/test_task_dispatcher.py",
    "tests/unit/test_member_capability_policy.py",
    "tests/unit/test_tenant_context_helpers.py",
    "tests/unit/test_authorized_parties_config.py",
    "tests/unit/test_session_bootstrap_service.py",
    "tests/unit/test_request_body_limit.py",
    "tests/unit/test_client_ip.py",
    "tests/unit/test_rgpd_contracts.py",
    "tests/unit/test_critical_selection_policy.py",
)

# Critical database test files. They require the real PostgreSQL/Redis stack with
# the Alembic schema, the isolated ``cronos_testdb`` worker databases and the
# migrator/router credentials. SQLite or mocked persistence is not a substitute.
DB_PATHS: tuple[str, ...] = (
    "tests/contracts/test_rls_database_policies.py",
    "tests/contracts/test_rate_limiting.py",
    "tests/contracts/test_migration_foundation_contract.py",
    "tests/contracts/test_session_bootstrap_integration.py",
    "tests/integration/transactional/test_clerk_auth.py",
    "tests/integration/transactional/test_scheduler_state_service.py",
    "tests/integration/committed/test_scheduler_tenant_isolation.py",
    "tests/integration/committed/test_scheduler_v1_occurrences.py",
    "tests/integration/committed/test_privacy_maintenance.py",
    "tests/integration/committed/test_privacy_administrative_erasure.py",
)

# Exact node IDs from large modules. The whole webhook module is far too slow for
# the fast gate, so the signature guard and the Svix idempotency proof stay here.
DB_CASES: tuple[str, ...] = (
    "tests/integration/committed/test_webhooks.py::test_webhook_invalid_signature_rejected",
    "tests/integration/committed/test_webhooks.py::test_webhook_idempotency_uses_svix_event_id",
)

# Critical coverage scope for the fast gate. The runner reports this scope only;
# ``pyproject.toml`` keeps the whole-application default for the optional full run.
CRITICAL_SOURCES: tuple[str, ...] = (
    "app/api/deps.py",
    "app/api/v1/endpoints/webhooks.py",
    "app/core/auth.py",
    "app/core/client_ip.py",
    "app/core/clerk.py",
    "app/core/ratelimit.py",
    "app/db/tenant.py",
    "app/middleware/request_body_limit.py",
    "app/scheduler/domain/candidate.py",
    "app/scheduler/domain/candidate_validation.py",
    "app/scheduler/domain/constraint_policy.py",
    "app/scheduler/domain/debt.py",
    "app/scheduler/domain/demand.py",
    "app/scheduler/domain/lesson_time.py",
    "app/scheduler/domain/projection.py",
    "app/scheduler/infrastructure/task_dispatcher.py",
    "app/services/privacy_maintenance_service.py",
    "app/services/session_bootstrap_service.py",
)

CRITICAL_COVERAGE_MIN = 80

# Exact source policies that stay stricter than the critical aggregate.
PROTECTED_INCLUDES: tuple[tuple[str, int], ...] = (
    ("app/scheduler/domain/constraint_policy.py", 100),
    ("app/scheduler/domain/candidate_validation.py", 90),
)

# The unit group keeps the loopback-only socket policy. It runs two workers so
# it does not oversubscribe the host while the database group uses four.
_UNIT_ARGS = ("--disable-socket", "--allow-hosts=127.0.0.1,localhost")


def db_selectors() -> tuple[str, ...]:
    """Return the database group selectors: whole files plus exact node IDs."""
    return (*DB_PATHS, *DB_CASES)


def manifest() -> dict:
    """Return the JSON manifest consumed by ``scripts/test.mjs critical``."""
    return {
        "groups": [
            {
                "name": "unit",
                "paths": list(UNIT_PATHS),
                "args": list(_UNIT_ARGS),
                "workers": 2,
            },
            {
                "name": "db",
                "paths": list(db_selectors()),
                "args": [],
                "workers": 4,
            },
        ],
        "coverage": {
            "fail_under": CRITICAL_COVERAGE_MIN,
            "sources": list(CRITICAL_SOURCES),
            "includes": [
                {"path": path, "fail_under": threshold} for path, threshold in PROTECTED_INCLUDES
            ],
        },
    }


_SELECTIONS = {
    "manifest": lambda: json.dumps(manifest(), indent=2),
    "unit": lambda: "\n".join(UNIT_PATHS),
    "db": lambda: "\n".join(db_selectors()),
    "sources": lambda: "\n".join(CRITICAL_SOURCES),
}


def main(argv: list[str] | None = None) -> int:
    selection = (argv if argv is not None else sys.argv[1:]) or ["manifest"]
    if len(selection) != 1 or selection[0] not in _SELECTIONS:
        choices = "|".join(_SELECTIONS)
        raise SystemExit(f"usage: python -m tests.critical_selection [{choices}]")
    print(_SELECTIONS[selection[0]]())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
