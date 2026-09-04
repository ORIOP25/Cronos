# Relatório da baseline de testes

## Revisão

- Branch: `codex/test-baseline`
- Base: `91bd1bcff7c6b2e4008fc6add6369ed968892b03` (`origin/main`)
- Main: não alterada

## Antes

| Área | Resultado |
| :--- | :--- |
| Backend collection | 616 testes |
| Backend fast legado | 336 passed, 280 deselected; 45,95 s |
| Frontend Vitest legado | 62 ficheiros, 353 testes; 76,03 s |
| Scripts de marketing | 3 passed |

## Depois

| Área | Resultado |
| :--- | :--- |
| Backend unit | 300 passed; 8,34 s |
| Backend integration | 263 passed; xdist 2; 247,46 s |
| Backend contracts | 43 passed; serial; 58,35 s |
| Frontend fast | 62 ficheiros, 353 passed; 104,01 s |
| Frontend coverage | 67,31% statements; 59,30% branches; 63,63% functions; 70,35% lines |
| Frontend quality | ESLint, Knip, Knip production, scripts, assets, build e audit verdes |

Os 10 testes removidos são exclusivamente os testes do classificador automático eliminado pelo plano; os restantes foram movidos para as suites estruturais e a soma final é 606 testes.

## Correções encontradas durante a execução

1. Launcher Windows passou de wrappers `.cmd` para binários/CLI Node compatíveis com `shell:false`.
2. O fast backend permite apenas loopback, para que `asyncio` funcione sem permitir rede externa.
3. Bases xdist foram separadas por worker e o Alembic recebe a URL da base correta.
4. Clientes ASGI de webhooks/membros passaram a usar o banco temporário do worker.
5. Interações Guide usam `user-event`; erros de tutorial esperados foram declarados nos testes.

## Estado

Os gates locais disponíveis estão verdes. A validação E2E autenticada depende das credenciais Clerk de CI e será acompanhada após o push.
