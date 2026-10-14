---
name: cronos-base
description: Base rules shared by all Cronos skills. Load it for every task in the Cronos repository, together with ponytail and the specialist Cronos skill for the area.
---

# Cronos Base

[AGENTS.md](../../../AGENTS.md) is the authority. This skill is the short checklist that every specialist skill extends.

## Every task

1. Apply the four mandatory practices: clean code, Clean Architecture, TDD, and Ponytail (`full`). They apply to every task type, including documentation and reviews.
2. Load `.agents/skills/ponytail/SKILL.md`.
3. Find the change path in the [Repository Map](../../../documentation/00_getting_started/REPOSITORY_MAP.md#feature-change-paths) before you search the code.
4. Use only commands from the [Command Reference](../../../documentation/00_getting_started/COMMAND_REFERENCE.md).
5. Deliver through the pull request workflow in [AGENTS.md](../../../AGENTS.md#git-ci-and-delivery).

## Safety rules

- **Zero masking**: never swallow exceptions, hide errors, or return dummy fallbacks.
- **Tenant isolation**: every tenant query carries `organization_id`; forced RLS protects the tables. Never bypass it.
- **Explicit verification**: name the exact command or CI job behind every "passed" claim.
- **Production**: provider settings, secrets, DNS, and production data need explicit owner approval.
- Do not modify imported third-party skills (`.agents/skills/clerk*`, `ponytail`, `grill-me`, `design-taste-frontend`).

## Documentation

- Code, tests, migrations, and configuration are the source of truth. Update the guide in the same pull request.
- Link to the file that owns a list, count, or state. Do not copy it.
- Follow the [Documentation Standard](../../../documentation/00_getting_started/DOCUMENTATION_STANDARD.md): active voice, short sentences, approved terms.
