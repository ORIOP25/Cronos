# Data and Seed

Esta secao trata a base de dados para validacao controlada.

## Conteudo principal
- SEED_SCENARIOS.md: perfis baseline/operacional/small-realistic/large-scale/stress, regras tenant-scoped e exemplos de validacao.
- seed_data.py: entrypoint canonico de seed com perfis (`baseline`, `operational`, `small-realistic`, `large-scale`, `stress`) e modo seguro sem reset por omissao.

## Comandos canonicos
- seed nao destrutivo (preserva dados existentes): `python seed_data.py`
- carga deterministica com reset: `python seed_data.py --profile large-scale --reset`
- perfil baseline: `python seed_data.py --profile baseline --reset`
- perfil small-realistic (manual orientado): `python seed_data.py --profile small-realistic --reset`
- perfil operacional alpha: `python seed_data.py --profile operational --reset`

## Troubleshooting rapido
- erro `UndefinedColumn` ao correr seed sem reset:
	- causa tipica: schema da BD atrasado face aos modelos atuais;
	- acao: `docker compose exec backend alembic upgrade head`;
	- depois repetir: `docker compose exec backend python seed_data.py`.
- se o schema estiver inconsistente e sem dados que precisas de preservar:
	- `docker compose exec backend python seed_data.py --profile large-scale --reset`.

Compatibilidade:
- `seed_data_large_scale.py` e `seed_data_operational.py` permanecem apenas como entrypoints legacy.
- `seed_data_small_realistic.py` e o modulo de suporte do perfil canonico `small-realistic` (com execucao direta mantida como helper legacy).
- evolucao funcional de seed deve ocorrer no ficheiro canonico `seed_data.py`.

Uso auxiliar (manual UI/UX):
- `docker compose exec backend python seed_data_small_realistic.py`

Nota:
- o perfil `small-realistic` faz parte dos perfis canonicos em `seed_data.py`, focado em navegacao manual legivel sem carga de stress.

## Compromisso
- seeds reproduziveis e alinhadas com invariantes do dominio.