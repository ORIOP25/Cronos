# Data and Seed

Esta secao trata a base de dados para validacao controlada.

## Conteudo principal
- SEED_SCENARIOS.md: perfis baseline/operacional/stress, regras tenant-scoped e exemplos de validacao.
- seed_data.py: entrypoint canonico de seed com perfis (`baseline`, `operational`, `large-scale`, `stress`) e modo seguro sem reset por omissao.

## Comandos canonicos
- seed nao destrutivo (preserva dados existentes): `python seed_data.py`
- carga deterministica com reset: `python seed_data.py --profile large-scale --reset`
- perfil baseline: `python seed_data.py --profile baseline --reset`
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
- evolucao funcional de seed deve ocorrer no ficheiro canonico `seed_data.py`.

## Compromisso
- seeds reproduziveis e alinhadas com invariantes do dominio.