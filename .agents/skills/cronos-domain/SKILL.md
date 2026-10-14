---
name: cronos-domain
description: Cronos domain skill for Portuguese Professional Education (Ensino Profissional). Use for courses, classes, subjects, modules, required minutes, curriculum catalog, hour accounting rules, members and capabilities, and school configuration rules.
---

# Cronos Domain

Load `cronos-base` and `ponytail` first.

## Invariants

- **Modules**: subjects contain ordered modules (*Módulos*) with positive `required_minutes`. Order is contiguous from 0 in the API and database, and from 1 in CSV files.
- **Progress**: execution, credits, and debt are append-only. Corrections are new revisions, never edits or deletes.
- **Generation**: the scheduler places remaining module minutes within configured dates and timeslots.
- **Removal**: a resource in use returns `409 resource_in_use`; with history it is archived; otherwise it is deleted. See [Resource Removal](../../../documentation/05_backend_api/RESOURCE_REMOVAL.md).
- **Members**: active access needs `lifecycle_status=active` and `access_status=active`. Capabilities are `admin` and `teacher`; database checks enforce valid combinations.
- **Foundation**: normal admin and teacher routes return `409 FOUNDATION_REQUIRED` until Foundation completes.

## Start here

- Curriculum catalog: `backend/app/services/{room,subject,course,class}_service.py` and `frontend/src/features/catalog/data.js`.
- Members: `backend/app/services/member_service.py` and `frontend/src/features/members/data.js`.
- School configuration: `backend/app/services/{foundation,settings,grid_change}_service.py`.
- Change paths: [Repository Map](../../../documentation/00_getting_started/REPOSITORY_MAP.md#feature-change-paths).

## Pitfalls

- Class-subject links are keyed by `grade_level`. Changing a class grade level changes which links apply.
- Room names have no uniqueness constraint, but the CSV import rejects duplicates.
- Teacher progress reads the v1 curricular ledger when assignments exist, and the legacy `ProgressLedgerEntry` otherwise.

## Done when

- Domain rules are covered by unit tests on pure functions where possible.
- The domain guide states the new or changed rule in plain words.

## Documentation

- [Professional Education](../../../documentation/02_domain_model/PROFESSIONAL_EDUCATION.md)
- [Members and Access](../../../documentation/02_domain_model/MEMBERS_AND_ACCESS.md)
- [School Configuration](../../../documentation/02_domain_model/SCHOOL_CONFIGURATION.md)
- [Glossary](../../../documentation/00_getting_started/GLOSSARY.md)
