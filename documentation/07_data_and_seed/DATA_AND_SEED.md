# Data and Seed Specifications

## Purpose
This document specifies the deterministic operational seed, generated records, and execution routine.

## Intended Reader
This document targets developers, QA engineers, and automated test runners.

## Prerequisites
Set up backend environment variables and start PostgreSQL.

## What the System Does
The backend provides `backend/seed_data.py`. It creates two isolated tenants and publishes one generated schedule per tenant.

## Available Seed Scenarios

| Profile Name | Included Entities | Primary Purpose |
| :--- | :--- | :--- |
| `canonical_operational_v1` | 2 organizations, 2 admin-teachers, 2 courses, 2 classes, 2 subjects, 2 rooms | Tenant isolation and scheduler lifecycle testing |

## Seed Identities

| Role | Email Address | Password | Organization |
| :--- | :--- | :--- | :--- |
| **Admin and Teacher** | `admin.operacional.a@seed.pt` | None | Escola Piloto Operacional A |
| **Admin and Teacher** | `admin.operacional.b@seed.pt` | None | Escola Piloto Operacional B |

The seed creates local account rows and synthetic Clerk identifiers. It does not create Clerk passwords or interactive login users.

## Seed Execution Command
Execute the seed script using Python:

```bash
cd backend
python seed_data.py
```

The command is idempotent. It prints a signature containing the profile, reference date, counts, and active stable keys.

## Contracts and Invariants
- Seeding scripts must generate valid foreign key relationships and set mandatory `organization_id` values.
- Each seed tenant receives its own `organization_id` and forced RLS context.
- The seed uses the canonical generation and approval services.
- Repeated execution preserves the same signature and does not duplicate active blocks.

## Failure Modes
- Database Not Migrated: Running the seed without current migrations raises schema or security-function errors.
- No Valid Schedule: The seed raises an error if canonical generation produces no draft.

## Verification Procedure
Run `pytest tests/test_operational_seed.py -v`. Then run `python -m scripts.audit_database_integrity`.

## Source Map
- Seed Runner: `backend/seed_data.py`
- Seed Service: `backend/app/services/operational_seed_service.py`

## Related Documents
- [Local Runtime](../09_ops_observability/LOCAL_RUNTIME.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
