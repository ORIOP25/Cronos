# WBS técnico — Índice dos quatro planos

Revisão: 2026-10-07. Versão: 2.0.
Main revista: `91a9d28bcb9c9a829a8578872156a6b90fa04bcf`.
A main remota e o checkout tinham a mesma revisão durante a inspeção.

## Objetivo e leitor

Coordenar a implementação do [PRD](REAL_BROWSER_TESTING_PLAN.md) em quatro partes menores.
Destina-se ao proprietário e aos implementadores.
Manter o âmbito aceite e os 80 IDs originais.
Os IDs W00–W12 pertencem à iniciativa de testes, não ao WBS entregue do scheduler.

## Pré-requisitos e recuperação dos documentos

Os seis documentos anteriores não estavam no checkout nem no histórico Git consultado.
Esta revisão repõe o PRD, o índice e as quatro partes a partir das decisões desta conversa.
A revisão atualiza contratos e fontes; não certifica percursos ainda não executados.
Preservar alterações externas, incluindo o relatório de revalidação já existente em outputs.

## Quatro partes

| Parte | Pacotes | Tarefas |
| :--- | :--- | ---: |
| [1 — Base técnica, Gmail e evidências](REAL_BROWSER_TESTING_WBS_PART_1_FOUNDATION.md) | W00–W03 | 22 |
| [2 — Deployments, escola e geração](REAL_BROWSER_TESTING_WBS_PART_2_SCHOOL_AND_SCHEDULING.md) | W04–W06 | 19 |
| [3 — Operação histórica e restantes percursos](REAL_BROWSER_TESTING_WBS_PART_3_REAL_JOURNEYS.md) | W07–W08 | 15 |
| [4 — Limpeza dos testes, CI e verificação final](REAL_BROWSER_TESTING_WBS_PART_4_CLEANUP_AND_CI.md) | W09–W12 | 24 |

## Comportamento atual e motivo da revisão

| Alteração observada na main | Evidência | Ajuste neste WBS |
| :--- | :--- | :--- |
| Feedback, submit real e contexto assíncrono | b07c488, c245862, 27f4ffc, d753988 | W08.1/3/8 e W09.5 preservam interação, contexto e anúncios. |
| Preferências semanais e recuperação adaptativa | 13faa17, 8e3699f | W06.2 e W07.6 usam o motor atual e distinguem preferências de regras obrigatórias. |
| Decisões de ocorrência, reservas e fecho semanal | 7550fac, d962e65 | W07.4–6 e W09.3 preservam as novas transições e reservas. |
| Calendário atómico e QA de contabilidade | 4f30bc4, 5efba01 | W05.8 e W09.2/3 conferem datas e saldos coerentes. |
| Linhagem e dívida residual histórica | 95406f2 | W07.6 e W09.3 conferem origem e compensações entre versões. |
| Proteção incompleta de erros de aprovação/rejeição | `Schedules.jsx`, handlers atuais | W09.5 exige prova do chamador antes de remover testes. |
| Data preferencial na Fundação | fd91719 | W05.8 prova draft, limites, resumo e persistência. |
| Ícones de calendário dentro do campo | 8e94c0b | W08.8 prova calendário, teclado, foco e ajuda acessível. |
| Atribuições retiradas da página Cursos | 91a9d28 | W05.4 entra em /imports; não procura o botão removido. |
| Sessão Clerk e origem local corrigidas | 6190498, c01f95e | Reutilizar esperas; auth e preparação artificiais continuam por substituir. |
| Telemetria externa ignorada | c9ad291 | W03.7 não pode ignorar backend ou autenticação fora da origem frontend. |
| Relatório de capacity-smoke publicado em falha | 1415ecd, 4d493e7 | Reutilizar diagnóstico; não o contar como aceitação humana. |

Funcionalidades implementadas não significam tarefas de aceitação concluídas.
O runner ainda usa Compose, chaves de teste, `clerk.signIn` e estado preparado.
Gmail, revisão frontend, proteção de binários e limpeza por execução continuam por implementar/verificar.

## Baseline e componentes

| Medida local | Valor |
| :--- | ---: |
| Backend: ficheiros test_*.py | 162 |
| Backend: unit / integration / contracts | 95 / 55 / 12 |
| Backend: definições estáticas test_* | 1192 |
| Frontend: ficheiros src/test/*.test.* | 87 |
| E2E: ficheiros *.spec.* | 27 |

Não confundir definições estáticas com casos recolhidos pelo pytest.
Não confundir contagem de ficheiros com redução efetiva de testes.

Reutilizar runner, Playwright, sanitizador, serviços de domínio, solver e CLI de privacidade.
A parte 1 define adaptadores e contratos do registo.
A parte 2 define revisão e helpers UI.
A parte 3 define expectativas operacionais.
A parte 4 define limpeza, núcleo e CI.

## Contratos e invariantes

- Usar Clean Architecture: domínio e políticas puros, efeitos nos adaptadores e composição no ponto de entrada.
- Passar dados e funções explícitos. Não criar interfaces com uma implementação ou frameworks internos.
- Aplicar Ponytail full: reutilizar código e biblioteca padrão antes de adicionar dependências.
- Usar nomes claros e unidades pequenas. Extrair helpers apenas perante repetição concreta.
- Escrever RED antes de uma alteração não trivial; implementar o mínimo, confirmar GREEN e refatorar.
- Reutilizar testes de comportamentos já corretos. Não criar RED artificial nem reimplementar correções existentes.
- Manter testes essenciais determinísticos, focados em comportamento.
- Testes de políticas/adaptadores podem controlar entradas; essa prova não substitui E2E real.
- E2E usa ações humanas na UI, sem auth programática, respostas falsas ou seeds de negócio.
- Preservar RLS, transações, segurança, acessibilidade, histórico e integridade.
- Registar IDs de caso concretos, revisão, organizações, RED/GREEN e referências de provas.
- Preservar erro primário; falhas auxiliares e dependências não podem produzir verde.

## Ordem e dependências

| Pacote | Dependências principais |
| :--- | :--- |
| W00 | Nenhuma |
| W01 | W00 |
| W02 | W01; acessos W00.4 |
| W03 | W00 e W01 |
| W04 | W01; acessos W00.4 |
| W05 | W02, W03 e W04 |
| W06 | W05 |
| W07 | W05, W06 e tempo real |
| W08 | W05; W06 quando depender de horários |
| W09 | W00 e prova substituta de cada grupo |
| W10 | W03/W04; W05 para limpeza; matriz completa para ativação final |
| W11 | W00 e núcleo de jobs |
| W12 | W01–W11 |

Executar W00 e a base da parte 1.
Avançar W04 quando os acessos estiverem disponíveis.
Preparar W10.1 após W01/W03/W04.
Verificar cedo o canal administrativo; concluir W10.4–6 depois de W05.
Passar G1 antes dos percursos de negócio.

Preparar W07.1 cedo para formar história real.
Avançar tarefas independentes enquanto o calendário amadurece.
Ativar W10.7 só depois da matriz completa.

## Mapeamento ao PRD

| Requisito | Tarefas |
| :--- | :--- |
| E2E-01 | W05.1, W05.8 |
| E2E-02 | W05.2 |
| E2E-03 | W05.3 |
| E2E-04 | W05.6–7 |
| E2E-05 | W01.1–3, W05.4–5 |
| E2E-06 | W08.1–2 |
| E2E-07 | W05.8 |
| E2E-08 | W06.1–4 |
| E2E-09 | W06.4–5, W08.2 |
| E2E-10 | W07.2–3 |
| E2E-11 | W07.4 |
| E2E-12 | W07.5 |
| E2E-13 | W07.6 |
| E2E-14 | W08.3 |
| E2E-15 | W08.4, W09.1 |
| E2E-16 | W08.5, W08.8 |
| E2E-17 | W08.6 |
| E2E-18 | W08.7 |
| NFR-01 | W01.4–5, W10.1 |
| NFR-02 | W10.1–2 |
| NFR-03 | W05.1–8, W10.8 |
| NFR-04 | W04.1–6 |
| NFR-05 | W07.1–2, W07.7 |
| NFR-06 | W08.3–4, W10.4–6 |
| NFR-07 | W03.1–2, W03.6–7, W10.7 |
| NFR-08 | W02.4–6, W04.6, W06.3 |
| NFR-09 | W03.3–6 |
| NFR-10 | W07.7, W10.3, W10.6 |
| NFR-11 | W09.1–4, W11.1–3 |
| NFR-12 | W09.5–8, W10.8, W12.4 |

## Condições de passagem

| Condição | Prova exigida |
| :--- | :--- |
| G1 | W01–W04: dados completos, Gmail, evidências protegidas e revisão. |
| G2 | W05: contas, convite e escola pela interface. |
| G3 | W06: candidato completo, aprovação, restrições e persistência. |
| G4 | W07: aulas reais, semanas, minutos e história. |
| G5 | W08 e matriz E2E-01–18 completa. |
| G6 | W09–W10: núcleo essencial, CI obrigatória e limpeza limitada. |
| G7 | W11–W12: recuperação isolada, campanha e documentação reconciliadas. |

Uma condição parcial não certifica produção.
A suite antiga é apenas baseline durante a migração.
Retirar o grafo antigo no cutover.
Não manter duas suites permanentes de aceitação.
Não reduzir critérios para cumprir uma data de entrada de clientes.

## Estados, falhas e riscos

Implementação e aceitação permanecem pendentes.
Esta revisão regista inspeção de código e uma seleção de testes locais.
Não marca Gmail, fornecedores ou histórico como configurados.
Classificar bloqueios de autenticação, email, calendário, deployments, artefactos e limpeza explicitamente.
Falhas reais dos fornecedores impedem aceitação verde.

## Verificação realizada nesta revisão

- `git ls-remote origin refs/heads/main`: mesma revisão que o checkout.
- `node --test scripts/test.test.mjs`: 18 testes passaram.
- Frontend selecionado: 60 testes passaram em cinco ficheiros.
- Seleção: `foundationModel`, `useAttemptScope`, `AppToaster`, `apiErrors` e `PortugueseDateInput`.

Comando frontend:

```powershell
node scripts/test.mjs fast --scope frontend -- src/test/foundationModel.test.js src/test/useAttemptScope.test.jsx src/test/AppToaster.test.jsx src/test/apiErrors.test.js src/test/PortugueseDateInput.test.jsx
```

Não foram executados testes backend de dados, campanhas completas ou E2E em produção nesta revisão.
Os [comandos comuns](REAL_BROWSER_TESTING_WBS_PART_4_CLEANUP_AND_CI.md#comandos-e-checks-comuns) definem a verificação durante a implementação.

## Fontes e documentos relacionados

- [Registo da implementação e provas observadas](REAL_BROWSER_TESTING_IMPLEMENTATION.md)
- [Guia atual de testes](TESTING_AND_CI.md)
- [Configuração escolar](../02_domain_model/SCHOOL_CONFIGURATION.md)
- [Scheduler atual](../03_scheduler_engine/README.md)
- [Ocorrências](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md)
- [Fecho semanal](../04_operational_features/TIMESHEETS_AND_PROGRESS.md)
- [Feedback](../06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md)
- [Rotas atuais](../06_frontend_ux/ROUTES_AND_PERMISSIONS.md)
- [Importação CSV](../07_data_and_seed/BULK_IMPORT_CSV.md)
- [Privacidade](../09_ops_observability/PRIVACY_OPERATIONS.md)
- [Padrão de documentação](../00_getting_started/DOCUMENTATION_STANDARD.md)
