# Relatório da otimização da baseline de testes

## Revisão e escopo

- Branch de implementação: `codex/test-performance`.
- Base intocada: `codex/test-baseline` em `8368b1b098f204522f49f03a4a24b9176dd4f8bf`.
- `main`: não alterada.
- Máquina de referência: Windows, i7-1165G7, 32 GB RAM, Docker Desktop Linux.

## Comparação formal do `fast --scope all`

| Amostra | Antes (ms) | Depois (ms) |
| :--- | ---: | ---: |
| 1 | 119089 | 31592 |
| 2 | 109608 | 30704 |
| 3 | 109642 | 31283 |
| 4 | 109414 | 31197 |
| 5 | 108266 | 31120 |
| Mediana | **109608** | **31197** |
| Mínimo / máximo | 108266 / 119089 | 30704 / 31592 |

Resultado: redução de **71,54%**, de 109,6 s para 31,2 s. Todas as cinco amostras posteriores foram processos Node novos, com aquecimento separado, e tiveram 654/654 testes aprovados.

## Suites e gates posteriores

| Área | Resultado |
| :--- | :--- |
| Backend unit | 300 passed |
| Backend integration | 264 passed in full `all`; latest Clerk-prep focus 265 passed with xdist 4 |
| Backend contracts | 43 passed; serial; 26,60 s na execução `all` |
| Integração + contratos | 105,59 s incluindo preparação e limpeza; meta <125 s |
| Frontend fast | 62 ficheiros, 354 passed |
| Frontend coverage | 68,04% statements; 59,36% branches; 63,70% functions; 70,81% lines |
| Frontend quality | ESLint, Knip, scripts, assets, build e audit verdes |
| Scheduler Clerk prep | 265 integration + 43 contracts passed |

## Alterações aplicadas

1. Runner único com relatórios `run.json`, JUnit, relógio monotónico, contagens por suite, workers efetivos e limpeza ownership-safe.
2. Vitest DOM em `vmThreads`, 4 workers, limite VM de 512 MB, optimizer client CoreUI e streams nativos antes do DOM/MSW.
3. Remoção da repetição SchoolConfig de dez execuções, mantendo os testes normais.
4. PostgreSQL 16 em `tmpfs` de 1 GB, Redis real e quatro bases xdist (`cronos_test_gw0..gw3`); contratos continuam seriais.
5. Os testes de volume mantêm 55/70 requests e ativam o limiter real, isolados por grupo e IP de teste.
6. Stack E2E local descartável em `localhost:5174`, frontend compilado, worker/beat, validação de chaves Clerk e Playwright no host com 2 workers globais e zero retries; a cadeia que muta o mesmo tenant fica serializada.
7. CI instala dependências/Chromium explicitamente, executa o runner host e deixou de usar `network_mode: host`/volume de `node_modules` no Compose E2E.
8. Esperas E2E passaram a marcadores visíveis e `expect.poll`; a matriz pública tornou-se 24 casos parametrizados e os seis testes isolados de `h1` foram removidos.

## Limitações e estado

- A validação E2E autenticada local não foi executada: este ambiente não possui `VITE_CLERK_PUBLISHABLE_KEY` (`pk_test_`), `CLERK_SECRET_KEY` (`sk_test_`) nem identidades reservadas. O `doctor --profile e2e` falha explicitamente e nenhum mock foi introduzido.
- O CI deve fornecer as credenciais Clerk reservadas para validar os cenários autenticados e acompanhar a mediana E2E no mesmo runner.
- A baseline “antes” foi recolhida antes das edições na branch de implementação e os artefactos estruturados “depois” ficam em `.test-artifacts/` (ignorado pelo Git).
