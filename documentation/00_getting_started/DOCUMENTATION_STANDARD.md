# Documentation Standard (ASD-STE100)

## Purpose
This document defines the writing standards, structural templates, and quality requirements for Cronos technical documentation.

## Intended Reader
This document targets technical authors, software engineers, and documentation reviewers.

## ASD-STE100 Writing Rules
All documentation in this repository must comply with Simplified Technical English (ASD-STE100) standards:

1. **Controlled Language**: Use clear, direct, and unambiguous English.
2. **Active Voice**: Write in active voice ("FastAPI validates tokens" not "Tokens are validated by FastAPI").
3. **Imperative Form**: Use imperative form for procedural steps ("Run `pytest tests/`").
4. **Sentence Length**:
   - Limit procedural sentences to a maximum of 20 words.
   - Limit descriptive sentences to a maximum of 25 words.
5. **Paragraph Limit**: Limit paragraphs to a maximum of six sentences.
6. **Noun Groups**: Limit noun groups to a maximum of three nouns (e.g., use "overhead panel" instead of "overhead panel battery section").
7. **Approved Terminology**: Use a single approved term for each concept. Consult [GLOSSARY.md](GLOSSARY.md).
8. **Portuguese Domain Terms**: Preserve exact Portuguese terms (*Ensino Profissional*, *Sumários*, *Faltas*, *Substituições*, *Turmas*) when referencing UI labels or legal domain definitions.
9. **No Unplanned Features**: Write in present tense for observed behavior (`does`, `calculates`). Do not use `will` for planned features. Do not use unresolved decision markers.

## Standard Section Template for Technical Guides
Every technical guide under `01_system_architecture/` through `09_ops_observability/` must use this exact structure:

```markdown
# [Document Title]

## Purpose
[Short statement of purpose]

## Intended Reader
[Target developer profile]

## Prerequisites
[Required reading or technical background]

## What the System Does
[Factual explanation of component behavior]

## Why the Behavior Exists
[Business rationale or architectural justification]

## Components and Ownership
[Table listing files, classes, and responsibilities]

## Data or Request Flow
[Diagram or numbered step list]

## Contracts and Invariants
[Enforced rules and structural constraints]

## States and Transitions
[State machine tables or diagrams]

## Failure Modes
[List of error scenarios and system responses]

## Verification Procedure
[Commands or steps to verify functionality]

## Source Map
[Paths to implementation files and unit tests]

## Related Documents
[Links to related documentation files]
```

## Review Checklist
Before merging documentation changes:
- [ ] Validate sentence length (max 20 words for procedures, max 25 words for descriptions).
- [ ] Confirm active voice usage.
- [ ] Confirm all relative file links resolve correctly.
- [ ] Verify that source paths match current codebase files.

## Related Documents
- [Glossary](GLOSSARY.md)
- [Contributing Guidelines](CONTRIBUTING.md)
