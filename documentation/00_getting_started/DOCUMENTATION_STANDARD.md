# Documentation Standard (ASD-STE100)

## Purpose

This document defines the writing, structure, and verification rules for Cronos documentation.

## Intended Reader

This document targets technical authors, engineers, and documentation reviewers.

## Prerequisites

Read the [Glossary](GLOSSARY.md) before changing controlled terms.

## What the System Does

Cronos documentation describes observed repository behavior.

Source code, tests, configuration, and migrations have priority over existing text.

Documentation does not claim that external provider dashboards are configured.

## Why the Behavior Exists

Short, controlled sentences reduce ambiguity during development, release, and incident recovery.

## Components and Ownership

| Area | Location | Rule |
| :--- | :--- | :--- |
| Application guides | `documentation/00_getting_started/` through `documentation/09_ops_observability/` | Describe current behavior. |
| Cronos agent guidance | `.agents/skills/cronos-*/` | Describe current engineering contracts. |
| Imported skills | `.agents/skills/clerk*`, `grill-me`, `ponytail`, and others | Do not modify. |

The `.agents/` directory is git-ignored. It is available in local development environments and is absent from a clean repository clone.

## Data or Request Flow

1. Inspect the implementation and tests.
2. Check paths, commands, routes, and configuration names.
3. Update the smallest complete set of documents.
4. Validate relative links and source paths.
5. Run relevant application verification commands.

## Contracts and Invariants

- Use active voice.
- Use imperative mood for procedures.
- Use present tense for observed behavior.
- Keep descriptive sentences to 25 words or fewer.
- Keep procedural sentences to 20 words or fewer.
- Keep paragraphs to six sentences or fewer.
- Use one approved term for each concept.
- Preserve exact Portuguese UI and domain terms.
- Link only to existing repository files.
- Mark unverified external state as an operational prerequisite.
- Index files named `README.md` may use a short document list.
- Technical guides use the full section structure in this standard.

## States and Transitions

Documentation changes follow this review state:

`inspect` -> `edit` -> `link-check` -> `verification` -> `review`.

## Failure Modes

- A stale source path makes the document non-actionable.
- A copied legacy status can mislead operations.
- An unverified provider claim can create a false release signal.
- A broken relative link fails navigation.

## Verification Procedure

1. Search changed documents for obsolete paths and feature names.
2. Resolve every relative Markdown link.
3. Compare commands with package scripts, Compose services, and CI steps.
4. Run the relevant backend or frontend checks.
5. Review `git diff --check` and `git status --short`.

## Source Map

- [Glossary](GLOSSARY.md)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Repository Map](REPOSITORY_MAP.md)
- [CI Workflow](../../.github/workflows/ci.yml)

## Related Documents

- [Project Overview](PROJECT_OVERVIEW.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
