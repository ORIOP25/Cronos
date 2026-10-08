# WBS técnico — Parte 3: Operação histórica e restantes percursos

Revisão: 2026-10-07. Versão: 2.0. Baseline: `91a9d28bcb9c9a829a8578872156a6b90fa04bcf`.

## Objetivo

Comprovar a operação histórica e os restantes percursos.
W07 exige W05, W06 e calendário real elegível.
Avançar W08 e tarefas independentes da parte 4 enquanto o histórico amadurece.
G4 e G5 exigem minutos, histórico e cobertura completa.

Este plano contém 15 tarefas, com os IDs originais.

## Leitor e pré-requisitos

Destina-se a quem implementa esta parte.
Ler o [índice](REAL_BROWSER_TESTING_WBS.md), o [PRD](REAL_BROWSER_TESTING_PLAN.md) e os guias relevantes.

Aplicar as [regras comuns](REAL_BROWSER_TESTING_WBS.md#contratos-e-invariantes) em todas as tarefas.
Usar Clean Architecture, Clean Code, TDD e Ponytail full.
Preservar os IDs e verificar dependências entre partes.
Um comportamento já correto exige reutilização dos seus testes, sem criar uma falha artificial.
Escrever RED antes de alterar um comportamento não trivial.

## Comportamento atual e motivo da revisão

| Evidência atual | Consequência |
| :--- | :--- |
| Ocorrência pendente não cria dívida nem execução. | Provar os saldos antes da decisão administrativa. |
| Substituição planeada não credita horas. | Provar reserva agora e crédito apenas após conclusão real. |
| Fecho semanal bloqueia decisões e reversões. | Reabrir os professores afetados antes da alteração. |
| Linhagem e reserva da história persistem entre versões. | Comparar identidade física, créditos e reservas após reparação. |
| Há `Reconciliar dívida` para resíduos históricos. | Preservar a regressão no núcleo; não fabricar resíduos antigos em produção. |

As correções de produto já existentes não comprovam a aceitação em produção.
Reutilizar essas correções e acrescentar as provas em falta.

## Componentes e tarefas

### W07 — Estado persistente, minutos e semanas reais

Ficheiros: Specs operacionais, `LessonLogModal.jsx`, `Occurrences.jsx`, `Timesheets.jsx`, serviços e consumidores v1.

| ID | Dependências | RED / prova inicial | Implementação mínima e DONE |
| :--- | :--- | :--- | :--- |
| W07.1 | W05, W06 | Escola sem proveniência UI não é elegível. | Preparar escolas persistentes completas e registar IDs, hashes e execução de criação. |
| W07.2 | W07.1 e tempo real | COMPLETED/GIVEN e submissão prematuros devem ser bloqueados. | Selecionar aulas terminadas e semanas elegíveis. Distinguir GAP futuro legítimo de execução antecipada. |
| W07.3 | W07.2 | Crédito incorreto ou repetição com crédito duplicado deve falhar. | Registar sumário pela UI. Conferir saldo inicial, delta e saldo final; repetir apenas ações permitidas. |
| W07.4 | W07.2–3 | Ocorrência pendente ou substituição planeada não pode antecipar crédito. | Executar decisões e reversões na UI. Conferir crédito, dívida, reservas, diagnóstico e idempotência por transição. |
| W07.5 | W07.3–4 | Semana incompleta ou fechada não pode aceitar alterações operacionais. | Concluir originais e substituições; submeter, aprovar e reabrir pela UI. Conferir bloqueios dos professores afetados. |
| W07.6 | W07.3–5, W06 | Reparação não pode sobrepor história futura nem duplicar crédito ou reservas. | Alterar uma condição futura pela UI e reparar. Conferir identidade de origem, fronteira protegida, cobertura residual e histórico. |
| W07.7 | W07.1–6 | Segunda campanha sem estado elegível deve expor a dependência. | Definir ciclos suportados e reservas de aulas reais. Executar duas campanhas consecutivas, sem resets ou backdating. |

### W08 — Recursos, isolamento e percursos restantes

Ficheiros: Specs de catálogo, professor, permissões, público, tutorial e ano escolar; rotas e componentes atuais.

| ID | Dependências | RED / prova inicial | Implementação mínima e DONE |
| :--- | :--- | :--- | :--- |
| W08.1 | W05 | CRUD não persistido ou relações perdidas devem falhar. | Criar, editar, arquivar/restaurar e eliminar pela UI. Provar a turma inicial preenchida sem clicar Adicionar turma. |
| W08.2 | W05, W06 | Horário, progresso ou disponibilidade não persistidos devem falhar. | Consultar como professor e guardar disponibilidade. Voltar a entrar e comparar valores; provar acesso administrativo permitido à disponibilidade. |
| W08.3 | W05 | Duas escolas com dados iguais não comprovam isolamento. | Criar diferenças pela UI. Alternar organizações e conferir dados, cache, toasts e contexto. |
| W08.4 | W08.3 | Professor com acesso administrativo ou efeitos indevidos deve falhar. | Tentar rotas e ações pela UI. Conferir recusa e ausência de alterações. |
| W08.5 | W02, W03 | Contacto apenas com HTTP 200 ou agradecimento deixa entrega por provar. | Submeter com Turnstile real. Observar mensagem entregue numa caixa autorizada, sem alterar o destinatário global. |
| W08.6 | W05 | Guia sem progresso ou tutorial com efeitos na escola deve falhar. | Concluir e retomar passos; conferir estado local e isolamento do tutorial. |
| W08.7 | W05, W06 | Mudança de ano que recria onboarding ou perde história protegida deve falhar. | Executar mudança e eliminação apenas numa escola descartável. Comparar estados, referências e história. |
| W08.8 | W04 | Headers locais ou imagem correta sem navegação real não certificam o site. | Provar routing, 404 público/autenticado, datas, teclado, foco e anúncios. Conferir feedback e persistência nos percursos existentes. |

## Contratos e ordem de execução

### Decisões e contabilidade

| Transição | Prova independente |
| :--- | :--- |
| Criar ocorrência pendente | Zero dívida e zero execução novas. |
| Decidir `GIVEN` | Apenas após o fim real; um crédito original. |
| Decidir `GAP` | Uma dívida original; nenhum crédito. |
| Planear `SUBSTITUTED` | Dívida original e reservas; zero execução antecipada. |
| Concluir substituição | Crédito no docente/disciplina substitutos; dívida original não desaparece por esse crédito. |
| Reverter substituição concluída | Confirmação explícita e compensações exatas. |
| Repetir decisão/reversão | Não duplicar movimentos. |
| Alterar numa semana fechada | Recusa sem efeitos; permitir após reabrir. |

Respeitar versões e `409 OCCURRENCE_STALE_VERSION`.
Uma edição de texto de sumário não altera a decisão ativa.
Não permitir que o sumário normal contorne `occurrence_active`.
Conferir os dois professores quando a substituição afetar ambos.
Manter reservas de aulas reais elegíveis para campanhas consecutivas.
Quando faltarem aulas ou semanas, declarar `incomplete`.

### História e reparação

Comparar identidade estável, origem, turma, atribuição e intervalo físico.
IDs de linhas podem mudar entre versões; não interpretar isso como desaparecimento da aula.
Conferir reservas de história futura, substituições e recuperação.
Dívida fechada não pode criar nova reserva; a história anterior permanece.

Planeamento de recuperação não liquida dívida. Execução real produz a liquidação.
Conferir coerência entre dashboard, lista de dívida e saldo restante por claim.

Usar testes isolados para resíduos legados e dados prematuros.
Não fabricar histórico antigo, decisões prematuras ou resíduos num tenant de produção.
Não tocar em resíduos QA ou escolas de clientes durante esta iniciativa.
Consultar o [procedimento de reconciliação](../09_ops_observability/OCCURRENCE_RECONCILIATION.md) quando houver um caso autorizado separado.

### Feedback e interação

Exercitar submit real, mensagens de campo, banners de bloqueio e toasts pertinentes.
Conferir foco e anúncios acessíveis.
Provar turma inicial, download efetivo dos cinco modelos e relatório de importação.
Os modelos descarregados do produto não substituem os moldes completos do proprietário.
Conferir 404 e retorno ao destino correto com e sem sessão.
Manter Chrome desktop; retirar verificações móveis da aceitação acordada.

A entrega do contacto exige observação em `contacto@cronos.pt` ou encaminhamento autorizado.
Não mudar o destinatário global para facilitar o teste.

## Estados, falhas e verificação

Registar tarefa, commit, ficheiros, RED, GREEN e referências das provas.
Usar `PENDENTE`, `EM_CURSO`, `CONCLUÍDO` ou `DEPENDÊNCIA`.
Concluir apenas quando DONE estiver comprovado.

Uma falha de fornecedor ou falta de histórico não é RED de uma regra do produto.
Não reduzir critérios nem usar retries para apagar uma falha.
Aplicar os [comandos comuns](REAL_BROWSER_TESTING_WBS_PART_4_CLEANUP_AND_CI.md#comandos-e-checks-comuns).
Conferir as [condições globais](REAL_BROWSER_TESTING_WBS.md#condições-de-passagem) antes de avançar.

## Fontes e documentos relacionados

- [Ocorrências UI](../../frontend/src/pages/Occurrences.jsx)
- [Consumidor v1](../../backend/app/scheduler/infrastructure/occurrences.py)
- [Operações v1](../../backend/app/scheduler/infrastructure/operations.py)
- [Regressões atuais](../../backend/tests/integration/committed/test_scheduler_v1_occurrences.py)
- [Guia atual de testes](TESTING_AND_CI.md)
- [Padrão de documentação](../00_getting_started/DOCUMENTATION_STANDARD.md)
- [Parte seguinte](REAL_BROWSER_TESTING_WBS_PART_4_CLEANUP_AND_CI.md)
