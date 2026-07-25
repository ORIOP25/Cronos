# Seed scenarios

## Objetivo

O seed operacional fornece dados sintéticos determinísticos para validar a
geração, aprovação e operação diária sem violar o isolamento por tenant.

## Cenários incluídos

1. `multi_eligible_substitution`: ocorrência com, pelo menos, dois candidatos elegíveis.
2. `no_eligible_fallback_gap`: ocorrência sem candidato elegível e fallback GAP explícito.
3. `tenant_isolation_check`: duas organizações com dados próprios e sem cruzamento de dados.

## Execução e validação

Depois de `alembic upgrade head`, execute `python seed_data.py` no diretório
`backend`. O único seed operacional é idempotente e publica um horário gerado
para cada tenant.

`pytest tests/test_operational_seed.py -q` executa o seed duas vezes e confirma
que o resultado permanece idempotente.

## Regras

1. Todos os dados são separados por `organization_id`.
2. Nenhum cenário mistura registos entre tenants.
3. Os cenários mantêm eventos de falta/substituição rastreáveis.
