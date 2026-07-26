# Data and Seed Specifications

## Purpose
This document specifies database seed scenarios, data fixtures, default credentials, and seed execution routines.

## Intended Reader
This document targets developers, QA engineers, and automated test runners.

## Prerequisites
Set up backend environment variables and start PostgreSQL.

## What the System Does
The backend provides a database seed script (`backend/scripts/seed.py`) that populates the database with realistic educational datasets.

## Available Seed Scenarios

| Scenario Name | Included Entities | Primary Purpose |
| :--- | :--- | :--- |
| `small-realistic` | 1 Organization, 3 Courses, 9 Classes, 10 Teachers, 25 Subjects, Rooms | Development, local manual testing, walkthroughs |
| `multi-course` | 2 Organizations, 8 Courses, 24 Classes, 40 Teachers, Full Shift Grids | Multi-tenant isolation testing, performance bench |
| `stress-test` | Multi-school, 500+ classes, heavy constraint loads | Solver V2 engine capacity and scalability testing |

## Default Account Credentials (`small-realistic`)

| Role | Email Address | Password | Organization |
| :--- | :--- | :--- | :--- |
| **Administrator** | `ana.silva@escola.pt` | `1234` | Escola Profissional do Norte |
| **Teacher** | `ana.matos@epnorte.pt` | `1234` | Escola Profissional do Norte |
| **Teacher** | `carlos.gomes@epnorte.pt` | `1234` | Escola Profissional do Norte |

## Seed Execution Command
Execute the seed script using Python:

```bash
python backend/scripts/seed.py --scenario small-realistic
```

To reset existing data before seeding:

```bash
python backend/scripts/seed.py --scenario small-realistic --reset
```

## Contracts and Invariants
- Seeding scripts must generate valid foreign key relationships and set mandatory `organization_id` values.
- Default passwords in seed datasets are restricted to local development environments.

## Failure Modes
- Database Not Migrated: Running seed on an outdated schema raises missing table errors. Run `alembic upgrade head` first.

## Verification Procedure
Run seed script and inspect populated tables using `python -m scripts.audit_database_integrity`.

## Source Map
- Seed Runner: `backend/scripts/seed.py`
- Seed Scenarios Module: `backend/app/db/seed_data.py`

## Related Documents
- [Local Runtime](../09_ops_observability/LOCAL_RUNTIME.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
