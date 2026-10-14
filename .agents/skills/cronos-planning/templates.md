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
| ID | Perigo | Cenário (teste que falha primeiro) | Ficheiro de teste |
| R01 | Escrita múltipla | Importar 2 dias mantém o primeiro | <path> |

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

## Estado
| PR | Slices | Estado | Ligação |
| PR 1 | S1–S3 | por iniciar | — |

## Slices
| ID | PR | Comportamento | Write set | Teste primeiro | Prova | Depende | Tamanho |
| S1 | PR 1 | <comportamento observável> | <ficheiros> | R01, R03 em <test file> | `integration -- -k <area>` | — | M |

## Lanes
| Lane | Slices | Ficheiros quentes |
| A | S1 → S2 | `models.py` |
| B | S4 | — |
Os slices de lanes diferentes correm em paralelo, cada um na sua worktree.

## Pull requests
| PR | Merge sozinho porque | Prova local antes do PR |
| PR 1 | <ex.: sem UI, campo novo com valor por omissão> | <profile> |

## Rastreabilidade
| Decisão ou risco | Slices |
| D01 | S1 |
| R01 | S2 |

## Related Documents
```
