# Planning Templates

Copy these skeletons. Replace every `<...>` value. Delete a section only when it does not apply, and say why in one line.

## Tech spec skeleton

```markdown
# Tech Spec — <Funcionalidade>

## Purpose
<Uma frase: o que muda para o utilizador.>
**Estado:** pronto para implementação. **Base:** `main` em `<commit>`, Alembic `<revision>`.

## Intended Reader
Agentes que implementam e o responsável de produto.

## Prerequisites
<Specs ou PRs que têm de estar em `main` antes. "Nenhum" se não houver.>

## What the System Does
### Decisões de produto
| ID | Decisão |
| D01 | <decisão fechada> |
### Âmbito e fora de âmbito
<Listas curtas.>

## Why the Behavior Exists
<O problema da escola, em poucas frases.>

## Components and Ownership
### Inventário de leitores e escritores
| Ficheiro | Lê ou escreve | Slice |
| <path> | <função ou endpoint> | <S2> |

## Data or Request Flow
<Modelo de dados, migração, contrato HTTP, fluxo da interface. Só o que muda.>

## Contracts and Invariants
### Identificadores
| Campo | Aponta para |
| `class_id` | `classes.id` |
<Invariantes numerados I01...>

## States and Transitions
<Só se a funcionalidade tem estados.>

## Failure Modes
<Erros devolvidos, com código e mensagem visível.>

## Cenários de risco
| ID | Perigo | Cenário (teste que falha primeiro) | Resultado exato esperado | Ficheiro de teste |
| R01 | Escrita múltipla | Importar 2 dias | Os 2 dias ficam gravados | <path> |

## Coexistência
<Branches e specs abertas nos mesmos ficheiros, ordem de merge, número da migração.>

## Verification Procedure
<Prova por PR, com links para a Command Reference.>

## Source Map
## Related Documents
```

## WBS skeleton

```markdown
# WBS — <Funcionalidade>

## Purpose
Decompõe o tech spec `<FEATURE>_TECH_SPEC.md` (com link) em slices verticais. As regras vivem no spec.

## Slices
| ID | PR | Comportamento | Write set | Teste primeiro | Prova | Depende | Tamanho |
| S1 | PR 1 | Contratos partilhados: alterações aos ficheiros quentes | `schemas.py`, `models.py`, migração | R01 em <test file> | `fast --scope backend -- -k <area>` | — | M |
| S2 | PR 1 | <comportamento observável> | <ficheiros> | R02, R03 em <test file> | `integration -- -k <area>` | S1 | M |

## Lanes
| Lane | Slices | Ficheiros quentes |
| 0 | S1 | `schemas.py`, `models.py` |
| A | S2 → S3 | — |
| B | S4 | — |
A lane 0 corre primeiro e sozinha. As outras lanes partem do seu commit e correm em paralelo, cada uma na sua worktree.

## Pull requests
| PR | Merge sozinho porque | Prova local antes do PR | Cenários E2E |
| PR 1 | <ex.: sem UI, campo novo com valor por omissão> | <profile> | <título do teste ou "nenhum"> |

## Rastreabilidade
| Decisão ou risco | Slices |
| D01 | S1 |
| R01 | S2 |

## Related Documents
```
