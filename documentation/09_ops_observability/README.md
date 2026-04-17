# Ops and Observability

Esta secao define sinais minimos de saude operacional.

## Conteudo principal
- METRICS_AND_ALERTS.md

## Arranque deterministico local (Docker)
- backend aplica migracoes antes de expor healthcheck de prontidao;
- worker, beat e frontend aguardam backend healthy para evitar corrida contra schema ainda incompleto;
- endpoint de health (`/api/v1/health`) e isento de rate limit para suportar probes frequentes de infraestrutura;
- bootstrap idempotente de admin local pode ser ativado por variaveis de ambiente no compose:
	- `BOOTSTRAP_DEFAULT_ADMIN=0` (default recomendado para evitar criacao de utilizador em cada arranque)
	- `BOOTSTRAP_DEFAULT_ADMIN=1` (apenas quando necessario em ambiente local vazio)
	- `BOOTSTRAP_ADMIN_EMAIL`
	- `BOOTSTRAP_ADMIN_PASSWORD`
	- `BOOTSTRAP_ADMIN_NAME`
	- `BOOTSTRAP_ORG_NAME`
- quando o email configurado ja existe, nao ha recriacao nem sobrescrita (idempotencia).
- para consistencia de dados entre sessoes, usar seed canonico uma vez e preservar volume Postgres:
	- `python seed_data.py --profile large-scale --reset`
	- em execucoes seguintes, usar `python seed_data.py` (nao destrutivo).

## Compromisso
- visibilidade de violacoes hard, riscos de isolamento e eventos operacionais criticos.
- suporte operacional ao modelo self-service sem exigir acompanhamento privado continuo.
- alarmes tecnicos internos da plataforma, sem notificacao global a todos os utilizadores.