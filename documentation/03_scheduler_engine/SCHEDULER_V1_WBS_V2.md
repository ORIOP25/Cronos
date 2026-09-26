# WBS técnico — implementação e validação do Scheduler v1 (Revisão 2)

Data: 25 de setembro de 2026.

Estado: W00–W12 concluídos; resíduos do audit (R55.00–R55.10, B01–B05) fechados. W13–W14 por iniciar. Esta revisão substitui o WBS de 23 de setembro de 2026 a partir de W06; o original permanece como referência histórica. Registos: [W08–W09](SCHEDULER_V1_W08_W09_STATUS.md), [W10–W11](SCHEDULER_V1_W10_W11_STATUS.md), [W12](SCHEDULER_V1_W12_STATUS.md).

Documentos de referência: [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md) e [especificação técnica v2](SCHEDULER_V1_TECH_SPEC_V2.md).
Branch de execução: `codex/scheduler-v1-revamp`.

## 1. Objetivo e utilização

Este WBS transforma a especificação em pacotes de trabalho verificáveis.
Os pacotes W00–W05 são registo as-built do trabalho executado. Os pacotes W06–W14 são plano revisto com as nove otimizações consolidadas do gerador.
As campanhas C01–C20 continuam obrigatórias; os casos T01–T30 do plano continuam obrigatórios.

O objetivo é demonstrar correção, qualidade e recuperação operacional em ambientes diversos.
Nenhuma quantidade finita de testes prova fiabilidade em todos os ambientes possíveis.
A confiança resulta de invariantes, oráculos independentes, diversidade, testes longitudinais e evidência reproduzível.

### Responsabilidades

| Papel | Responsabilidade |
| :--- | :--- |
| Implementador | Código, testes, análise, correções, relatórios e documentação. |
| Proprietário | Validar exemplos escolares, compromissos de qualidade e gates local/remoto. |
| Automação local/CI | Executar verificações e preservar evidência; não substitui a interpretação dos resultados. |

Estados de trabalho: `por iniciar → em execução → em validação → concluído`.
Uma regressão reabre o pacote responsável e regista os pacotes afetados.
"Concluído" exige artefacto, teste ou ensaio e resultado analisado.

### Notas normativas desta revisão

1. Os ganhos históricos de aproximadamente 90 para 22 segundos pertencem às medições anteriores (registos de campanha de 24–25 de setembro de 2026, Docker local, um worker). Esta revisão não os apresenta como nova comparação controlada nem como garantia universal.
2. A antecipação das conclusões resulta da política aprovada (D10–D12). Distribuir procura ao longo do ano exige decisão explícita de produto. Não introduzir limites semanais ou penalizações de antecipação para obter uma aparência mais uniforme.
3. O agrupamento de salas equivalentes e a calibração 1/2/4/8 workers continuam dependentes de medições em W11.

## 2. Regras transversais

- Clean Code: funções pequenas, unidades explícitas, comportamento visível e nomes do domínio.
- Clean Architecture: domínio sem ORM, HTTP, Celery, CP-SAT ou relógio global.
- TDD: reproduzir a falha antes da correção; implementar o mínimo e refatorar depois.
- Ponytail full: reutilizar runner, bibliotecas e containers; evitar framework genérico de experiências.
- Manter um único job global e medir paralelismo interno 1/2/4/8 em W11.
- Não criar metas fixas de p95 ou timeouts de qualidade.
- Não modificar dados, fixtures ou expectativas para esconder um erro.
- Não enfraquecer estabilidade, integridade, autorização ou cobertura curricular para obter um resultado.
- Não executar ensaios Railway/Cloudflare antes do gate local.
- Não exigir migração ou compatibilidade com dados antigos de teste.

### Condições de correção das nove otimizações (vinculativas em W06–W14)

| Nº | Otimização | Condição de correção |
| :--- | :--- | :--- |
| 1 | Master anual e detalhe reabrível | Cortes descrevem integralmente o subproblema excluído. |
| 2 | Hint greedy earliest-week | É um arranque de pesquisa; não prova viabilidade detalhada. |
| 3 | Conclusões por contagens de limiar | Abranger todas as turmas e verificar equivalência com o vetor ordenado. |
| 4 | Congelar prioridades superiores | Distinguir valores provados de valores conservados heuristicamente. |
| 5 | Orçamento por janela e pré-solve | Contar construção e finalização; evitar starvation e certificados de etapas omitidas. |
| 6 | Poda pela semana do incumbente | Permitir a mesma semana, para melhorar os restantes componentes. |
| 7 | Matching global de salas após posições | Considerar sobreposições físicas e reconhecer que as posições continuam fixas. |
| 8 | Elegibilidade conjunta e proteção | Testar turma, docente, salas, passado, datas protegidas e timezone. |
| 9 | Cache de janelas provadas | Nunca reutilizar uma janela interrompida como ótima. |

Qualquer pacote W06+ que toque no motor tem de manter as nove condições verdes. As regressões existentes (`test_scheduler_w05_audit`, `test_scheduler_w04_w05_regressions`, `test_scheduler_search_v1`, `test_scheduler_generation_v1`) fazem parte dos checks obrigatórios desses pacotes.

Na implementação, o ciclo de cada tarefa é:

```text
exemplo/requisito → teste que falha → implementação mínima
→ teste verde → refatoração → regressões relacionadas → evidência
```

Nas experiências, alterar uma variável de cada vez para explicar causas.
Depois combinar variáveis para testar interações e comportamento realista.
Uma alteração de fixture é uma nova versão; não apaga o resultado anterior.

## 3. Árvore de entregas e dependências

| Pacote | Entrega | Fase | Depende de | Estado |
| :--- | :--- | :--- | :--- | :--- |
| W00 | Ambiente, inventário e controlo de execução | P0 | Plano e tech spec | Concluído |
| W01 | Domínio curricular e temporal | P1 | W00 | Concluído |
| W02 | Baseline de dados e transações | P2 | W01 | Concluído (consolidação Alembic em W12) |
| W03 | Oráculos, validador e laboratório | P3 | W01; W02 para integração | Concluído |
| W04 | CompleteGeneration correto | P4 | W01, W03 | Concluído |
| W05 | Qualidade inicial e datas coletivas | P5 | W04 | Concluído |
| W06 | AdaptiveRecovery e reconciliação | P6 | W02, W05 | Concluído ([registo](SCHEDULER_V1_W06_W07_STATUS.md)) |
| W07 | Paragem e diagnóstico sustentados | P7 | W03–W06 | Concluído ([registo](SCHEDULER_V1_W06_W07_STATUS.md)) |
| W08 | Fila, snapshots e publicação | P8 | W02, W04; integração final com W06–W07 | Concluído ([registo](SCHEDULER_V1_W08_W09_STATUS.md)) |
| W09 | API e aplicação escolar | P9 | W01, W02, W08 | Concluído ([registo](SCHEDULER_V1_W08_W09_STATUS.md)) |
| W10 | Campanhas combinadas e anuais | P6–P10 | W06; completar com W07–W09 | Concluído ([registo](SCHEDULER_V1_W10_W11_STATUS.md)) |
| W11 | Calibração e recursos | P10 | W07, W10 | Concluído ([registo](SCHEDULER_V1_W10_W11_STATUS.md)) |
| W12 | Remoção de legado e candidate local | P11 | W00–W11 | Concluído ([registo](SCHEDULER_V1_W12_STATUS.md)) |
| W13 | Validação remota | P12A | W12 aceite | Por iniciar |
| W14 | Corte final e entrega | P12B | W13 aceite | Por iniciar |

Os pacotes descrevem dependências, não obrigam a PRs gigantes.
Entregar fatias verticais pequenas quando as suas dependências estiverem prontas.
Executar campanhas progressivamente; não adiar a descoberta de problemas para W10.

## 4. Pacotes

### W00 — Ambiente e inventário (as-built, concluído)

| ID | Pedido | Entregue | Evidência |
| :--- | :--- | :--- | :--- |
| W00.1 | Mapear chamadas do gerador, ledger, módulos, mapas, UI, scripts e migrations. | Inventário com consumidor, contrato atual e destino novo. | [W00 status](SCHEDULER_V1_W00_STATUS.md) |
| W00.2 | Confirmar branch, imagens, volumes e serviços locais. | Imagem `cronos-backend-test:local` manifestada: Python 3.14.7, OR-Tools 9.15.6755, Docker local. | idem |
| W00.3 | Impedir deployments automáticos da branch. | Branch sem pushes durante P0–P11; nenhum deployment remoto provocado. | idem |
| W00.4 | Executar setup/doctor e checks atuais. | Runner reparado; suites de backend de 399 para 444 testes; falhas pré-existentes registadas à parte. | idem |
| W00.5 | Diretórios de artefactos e limites de segurança de laboratório. | `.test-artifacts/` com execuções nomeadas por campanha; limites de laboratório documentados. | idem |

### W01 — Domínio curricular e temporal (as-built, concluído)

| ID | Pedido | Entregue | Evidência |
| :--- | :--- | :--- | :--- |
| W01.1 | Valores imutáveis, minutos inteiros e intervalos semiabertos. | `domain/calendar` e `domain/candidate`; intervalos adjacentes permitidos; negativos e durações inválidas rejeitados; horários ambíguos em transição de timezone falham na normalização. | T01–T03, T08–T09 verdes; [W01 status](SCHEDULER_V1_W01_STATUS.md) |
| W01.2 | Procura `Q-E`, crédito parcial e módulos cronológicos. | `domain/demand` e `domain/projection`; nenhum arredondamento por módulo; 75+75 em períodos de 50 com parcelas 50; 25+25; 50. | T01–T03 verdes |
| W01.3 | Execução, reversões e acertos auditados. | Ledger append-only com reversões idempotentes; execução repetida não credita duas vezes. | T04–T07, T29–T30 verdes |
| W01.4 | Dívida, reservas e liquidação muitos-para-muitos. | `domain/debt`; cancelar recuperação não duplica dívida; reconciliação mais antiga primeiro com associação auditável. | T05 verde |
| W01.5 | Calendário, timezone e janela por dias de grelha. | `grid_dates`, `protected_grid_dates`, proteção física com instantes passados; N=0; relógio injetável. | T08–T09 verdes |
| W01.6 | Definições de qualidade e elegibilidade. | `domain/quality` (vetores e comparadores puros) e `domain/eligibility` (FIRST_GENERATION, PLANNING_CHANGE, RETRY_INCOMPLETE, PERIODIC_RENEWAL, ACTIVE_JOB). | T15–T19 (comparador), T21–T22 verdes |

### W02 — Baseline de dados (as-built, concluído; consolidação Alembic em W12)

| ID | Pedido | Entregue | Evidência |
| :--- | :--- | :--- | :--- |
| W02.1 | Schema de atribuições, ledger, parcelas e dívida. | Migração provisória `0011_scheduler_v1_curricular`: 13 tabelas com constraints e RLS forçada; equações verificadas após comandos e reversões. | `test_scheduler_v1_baseline`; [W02 status](SCHEDULER_V1_W02_STATUS.md) |
| W02.2 | Versões, aulas, propostas, jobs e revisões. | `scheduler_version_v1` (uma ativa), `scheduler_lesson_v1` (identidade estável), `scheduler_job_v1` (um ativo por ano), `scheduler_proposal_v1` (uma pendente por ano); revisões `input/planning` no estado. | idem |
| W02.3 | Baseline Alembic, grants, RLS e índices. | Instalação vazia em bases de teste temporárias; FKs com organização; auditorias de RLS. Consolidação em baseline nova é da W12. | [Consolidação Alembic](SCHEDULER_V1_ALEMBIC_CONSOLIDATION_PLAN.md) |
| W02.4 | Transações de progresso e mudanças de configuração. | `infrastructure/progress` sob lock de estado: execução, dívida, recuperação e configuração; escritas concorrentes não perdem revisão nem duplicam crédito. | `test_scheduler_v1_progress`, `test_scheduler_v1_configuration` |
| W02.5 | Procedimento local de reset com alvos explícitos. | Reset repetível apenas em dados de teste; autenticação externa não atingida. | Registado no ciclo RC; scripts de reset/erasure |

### W03 — Validação independente e laboratório (as-built, concluído)

| ID | Pedido | Entregue | Evidência |
| :--- | :--- | :--- | :--- |
| W03.1 | Validador de cobertura, recursos, datas e estabilidade. | `candidate_validation` versão 3 com 20 códigos tipados; candidatos adulterados rejeitados pelo motivo correto. | `test_scheduler_candidate_validation` (26 testes) |
| W03.2 | Oráculo enumerativo para instâncias mínimas. | `domain/oracle`: enumeração até 50 000 combinações; viabilidade e ótimo sem reutilizar restrições CP-SAT; objetivo pelo vetor de conclusões. | `test_scheduler_lab_fixtures` |
| W03.3 | Gerador de fixtures com testemunhos e variantes. | `lab/fixtures` (13 mutações rastreáveis), `lab/scale` (semana única por seed), `lab/annual` (testemunhos construídos por construção, oráculo nunca chamado para gerar). | `test_scheduler_lab_scale`, `test_scheduler_lab_annual_v1` |
| W03.4 | Manifests, seeds separadas e reprodução de casos. | `lab/manifest`: schema `scheduler-lab-v3`, digests SHA-256 de inputs e candidatos; seeds de fixture, eventos e solver separadas. | `test_scheduler_lab_manifest` |
| W03.5 | Modo de campanhas no runner existente. | `node scripts/test.mjs campaign` → CLI `app.scheduler.lab.campaign` com seleção por ID, escritas atómicas e retoma por provenância. | `test_scheduler_lab_campaign` |
| W03.6 | Comparador de relatórios e cobertura de cenários. | `lab/reports`: regressões por família, casos omitidos, inconclusivos e mudanças de política. | `test_scheduler_lab_reports` |

### W04 — CompleteGeneration correto (as-built, concluído)

| ID | Pedido | Entregue | Evidência |
| :--- | :--- | :--- | :--- |
| W04.1 | Compilar atribuições e disponibilidade conjunta. | `capacity.eligible_periods`: interseção única (timezone, datas, bloqueios, proteção, grelha, turma, docente, salas livres, períodos fixados por protegidas); preferência soft mantém elegibilidade. | T13–T14 verdes; [W04/W05 status](SCHEDULER_V1_W04_W05_STATUS.md) |
| W04.2 | Quotas anuais por duração e crédito final. | `annual_model.plan_annual_quotas`: equações exatas com grupos finais e desperdício; capacidades semanais por recurso; hint greedy earliest-week; no-goods completos. | T10 verde |
| W04.3 | Colocação detalhada e realimentação de conflitos. | `search` + `placement_model`: janelas reabríveis; pré-solve; cortes apenas de inviabilidade provada; timeout não produz corte falso; verificação de materialização exata. | T11 verde; `test_scheduler_search_v1` |
| W04.4 | Salas elegíveis e matching completo. | `placement_model._optimize_rooms`: matching global após posições com sobreposições físicas incluindo fixas/protegidas; refinamento de continuidade. | T12 verde |
| W04.5 | Materializar, projetar módulos e validar ano completo. | `_build_candidate` com projeção modular; validador independente antes de aceitar; campanhas de escala e anuais com candidatos completos e revalidação de digests. | Campanha `w04-generation` {válido 20, inviável 6}; campanha `w04-annual` {válido 12}; T30 verde. Persistência atómica de propostas é da W08 (T27 parcial). |

### W05 — Qualidade da geração inicial (as-built, concluído)

| ID | Pedido | Entregue | Evidência |
| :--- | :--- | :--- | :--- |
| W05.1 | Vetor de conclusões ordenado da mais tardia para a mais precoce. | Conclusões por contagens de limiar do valor mais alto para o mais baixo; equivalência ao vetor ordenado verificada contra o oráculo com seeds aleatorizadas; o contraexemplo da soma de datas é coberto pelo oráculo. | `test_scheduler_generation_quality_v1`; `test_scheduler_w05_audit` (vetor completo = ótimo enumerado) |
| W05.2 | Furos docentes, depois turmas, preferências e salas. | `InitialQualityVector` e `measure_initial_quality` recalculados fora do solver; prioridade independente da ordem das variáveis (invariância à permutação testada). | T19 verde |
| W05.3 | Incumbente anual e limites com âmbito explícito. | Incumbente conservado pelo vetor completo; melhorias locais não degradam prioridades globais; limite relaxado separado do incumbente; poda pela semana do incumbente com mesma semana permitida. | `test_scheduler_w05_audit` |
| W05.4 | Relatório de conclusão, margem e recuperabilidade. | Relatório de conclusão com margem, excessos e avaliação de recuperabilidade de um cenário (cancelamento da última aula planeada e nova resolução). | C10–C11 no que não requer reparação; comparadores T15–T18 verdes; solver de recuperação na W06 |

Propriedades do motor entregues e fechadas em W05 (as nove otimizações consolidadas): master/detalhe reabrível, hint greedy, limiares, congelamento provado/conservado, orçamento por janela e pré-solve, poda pela semana do incumbente, matching global de salas com refinamento, elegibilidade conjunta e cache de janelas provadas. Regressões: `test_scheduler_w05_audit` (28), `test_scheduler_w04_w05_regressions` (F01–F09), `test_scheduler_search_v1`, `test_scheduler_generation_v1`.

Percurso de validação de W04–W05: revisão independente rejeitou o primeiro fecho (falhas F01–F11); correções R45.00–R45.09; audit A01–A12 fixado com 16 regressões vermelho-primeiro e validador v2→v3; G2 aceite no âmbito corrigido; resíduos R55/B01–B05 fechados. Registos: [revisão](SCHEDULER_V1_W04_W05_REVIEW.md), [correções](SCHEDULER_V1_W04_W05_CORRECTION_WBS.md), [status](SCHEDULER_V1_W04_W05_STATUS.md), [G2](SCHEDULER_V1_W04_W05_G2_REVIEW.md), [audit](SCHEDULER_V1_W00_W05_AUDIT_PLAN.md).

### W06 — AdaptiveRecovery (concluído; revisto nesta revisão)

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W06.1 | Identificar falta, excesso e aulas inválidas. Baseline inválido não é aceite por ter sido publicado anteriormente; o ramo do validador até `hard_end` já existe. | T20 verde; o validador rejeita baseline invalidado por mudança de professor ou sala. |
| W06.2 | Inserção, movimentos e expansão por conflitos, sobre o master/detalhe reabrível: movimentos reabrem janelas afetadas; cache de janelas invalidado por mudanças de protegidos, baseline ou fronteira editável; poda pela semana do incumbente de reparação, com a mesma semana permitida. | C02–C04, C08; escapar de bairro local inviável quando há testemunho global; cache nunca reutiliza janela interrompida como ótima. |
| W06.3 | Correspondência de identidades e custo de perturbação. Salas voltam a matching global após os movimentos; posições fixas; refinamento só melhora o vetor completo. | Trocar IDs não esconde movimentos; modular não conta como movimento físico. |
| W06.4 | Proteção progressiva da margem e excesso prioritário. | T15–T18 no solver; comparações C10–C12 aceites. |
| W06.5 | Reconciliar propostas, dívida e currículo após reparação. | C13–C14; nada é liquidado apenas porque existe uma proposta. |
| W06.6 | Preservar as nove propriedades do gerador sob reparação: cortes integrais, hint como arranque, limiares com todas as turmas e equivalência ao vetor, congelamento provado/conservado, orçamento com construção e finalização, poda com mesma semana, salas com sobreposições físicas e posições fixas, elegibilidade conjunta, cache sem janelas interrompidas. | As nove condições de correção verdes em cenários de reparação (C02–C04, C08, C13–C14); oráculo confirma equivalência do vetor também na reparação; regressões permanentes atualizadas. |

Fecho: reparar não significa apenas encontrar a primeira cobertura completa.
Guardar melhores resultados e evidência de alternativas exploradas.

### W07 — Paragem e diagnóstico (concluído; revisto nesta revisão)

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W07.1 | Resultados e certificados tipados. O prefixo certificado é a sequência contígua de etapas provadas; `SAFETY` des-certifica; ótimo local não vira ótimo anual; unknown não vira impossible. | T26; motivações de fim por âmbito. |
| W07.2 | Pré-verificações e explicações de conflitos. | C08, C15; valores mínimos apenas quando demonstrados; estimativas identificadas como estimativas. |
| W07.3 | Controlador de exploração e retorno adicional, com regras de honestidade de orçamento: contar construção e finalização; sem starvation; etapa omitida nunca certificada; execução fora do orçamento nunca reportada como dentro. | Replay de trajetórias C19 com ganhos perdidos e esforço poupado. |
| W07.4 | Segurança, finalização e cancelamento. | C16; limite cobre construção, solve e persistência. |

Fecho: política explicável e mensurada, sem p95 como comando de paragem.

### W08 — Execução e publicação (concluído; registo em [SCHEDULER_V1_W08_W09_STATUS.md](SCHEDULER_V1_W08_W09_STATUS.md))

A produção ainda executa o motor legado. Este pacote liga o motor v1 à fila, à persistência e à publicação.

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W08.1 | Revisões, snapshots e verificação de atualidade. | T24; alteração em fila, solve e aprovação invalida corretamente. |
| W08.2 | FIFO global, lock e token de tentativa. | T23; várias escolas e entrega duplicada mantêm um único cálculo. |
| W08.3 | Heartbeat, supervisor e recuperação de processo. | C16; terminação anterior confirmada antes de takeover. |
| W08.4 | Proposta e relógio de 28 dias atómicos. | T21–T22 no percurso persistido; falha/rejeição/aprovação não reiniciam indevidamente. |
| W08.5 | Aprovação e reconciliação numa transação. | Rollback a meio mantém integralmente a versão anterior; T27 completo. |

Fecho: C16–C17 em containers reais, incluindo falhas induzidas.

### W09 — API e aplicação escolar (concluído; registo em [SCHEDULER_V1_W08_W09_STATUS.md](SCHEDULER_V1_W08_W09_STATUS.md))

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W09.1 | Contratos, autorização e geração idempotente. | GET não escreve; organização deriva do utilizador; duplo clique não duplica job. |
| W09.2 | Estado, fila, cancelamento e motivos de elegibilidade. | UI concorda com servidor; não existe geração automática por ocorrência. |
| W09.3 | Proposta, diferenças, alertas e aprovação. | Diferença modular separada da física; alerta além da preferência persiste. |
| W09.4 | Turmas, sumários, ocorrências, mapas e acertos. | Consumidores aceitam várias parcelas por aula e conservação de minutos. |
| W09.5 | Acessibilidade e percurso escolar completo. | C20; linguagem escolar, teclado, erros e frontend Docker atualizado. |

Fecho: percurso manual do proprietário sobre dados locais e E2E reproduzível.

### W10 — Campanhas integradas (por iniciar)

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W10.1 | Matriz de fatores e combinações por pares. | Relatório lista pares válidos cobertos e exclusões justificadas. |
| W10.2 | Interações críticas de três ou mais fatores. | C08–C14 em topologias distintas, não só seeds diferentes. |
| W10.3 | Replays anuais com eventos acumulados. | C14; validação após cada passo e aprovação. |
| W10.4 | Fronteiras de viabilidade e reversão de pressão. | C02–C08, C15; transição explicada, não inferida pelo timeout. |
| W10.5 | Redução de falhas a casos mínimos. | Cada falha corrigida origina regressão determinística persistente. |

Fecho: matriz obrigatória concluída, resultados analisados e defeitos resolvidos ou explicitamente bloqueantes.

### W11 — Desempenho e calibração (por iniciar)

O agrupamento de salas equivalentes e a calibração 1/2/4/8 workers continuam dependentes das medições deste pacote.

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W11.1 | Comparar workers 1/2/4/8 no hardware local. | C18; CPU, RAM, qualidade e tempo, incluindo falhas. |
| W11.2 | Perfilar construção, procura, solver e persistência. | Otimizar o custo dominante observado; evitar otimização especulativa. |
| W11.3 | Calibrar política adaptativa e paragem. | C11, C19; treino separado de avaliação reservada. |
| W11.4 | Fixar baseline e parâmetros candidatos, incluindo decisão sobre agrupamento de salas equivalentes. | Manifesto versionado e relatório por família; nenhum p95 alvo inventado. |

Após otimização, repetir a falha, vizinhos da matriz e regressões relevantes.
Repetir campanha ampla quando o algoritmo, política, schema ou fronteira de concorrência mudar.

### W12 — Candidate e gate local (por iniciar)

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W12.1 | Remover implementação, campos e contratos antigos, incluindo a fronteira legada de domínio e o adaptador CP-SAT do avaliador antigo. | Pesquisa de consumidores sem referências funcionais ao legado. |
| W12.2 | Consolidar a migração provisória `0011` na baseline Alembic nova. | Instalação vazia e reset reproduzíveis; auditorias de RLS/constraints. |
| W12.3 | Instalação limpa e checks completos. | Suites, contratos, segurança, integridade e E2E verdes em Docker. |
| W12.4 | Avaliação reservada da candidate congelada. | Mesmo commit e política; casos não utilizados na calibração. |
| W12.5 | Dossier local e aceitação. | Proprietário revê resultados, limitações e runbooks concretos. |

Bloquear o gate por violações de integridade, isolamento, cobertura ou publicação incorreta.
Não compensar um erro crítico com uma média de qualidade alta.

### W13 — Validação remota, apenas após W12 (por iniciar)

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W13.1 | Publicar candidate identificada em Railway/Cloudflare. | Verificar commit, imagens, configuração e ausência de réplicas solver sobrepostas. |
| W13.2 | Repetir subconjunto representativo e casos extremos locais. | Validar integrações reais, latência, memória, filas e publicação. |
| W13.3 | Repetir configurações finalistas de workers. | Baseline remota separada; vencedor local não assumido como vencedor remoto. |
| W13.4 | Corrigir divergências através do ciclo local. | Falha remota reproduzida quando possível; regressões locais e remotas relevantes repetidas. |

Usar o ambiente de produção autorizado, ainda sem escolas reais, apenas nesta fase.
Validar os modos de falha próprios do deployment e o procedimento de recuperação.

### W14 — Corte e entrega (por iniciar)

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W14.1 | Preparar release, merge e acompanhar CI. | CI associada a cada push passa; revisão candidata identificada. |
| W14.2 | Parar entrada de jobs, limpar dados de ensaio e instalar baseline final. | Alvos verificados; nenhum job antigo ativo; instalação íntegra. |
| W14.3 | Smoke final de geração, aprovação e execução. | API, worker e frontend servem a mesma release compatível. |
| W14.4 | Entregar runbook, relatórios e limitações conhecidas. | Aceitação final e procedimento de recuperação da nova v1 ensaiado. |

## 5. Protocolo obrigatório de cada loop experimental

Cada campanha executa o seguinte ciclo, mesmo quando o primeiro cenário passa:

```text
X: baseline conhecida → executar → validar → analisar
Y: mutação controlada de X → executar → validar → comparar X/Y
Z: aumentar pressão ou introduzir interação → executar → validar → comparar
R: remover a pressão ou aplicar ação administrativa → executar → validar recuperação
```

Se ocorrer uma falha:

```text
congelar inputs e outputs → classificar → reduzir caso → escrever teste vermelho
→ corrigir causa → teste verde → repetir X/Y/Z/R e vizinhos afetados
→ atualizar relatório → avançar para outra topologia/escala
```

Não confundir três mudanças distintas:

| Mudança | Finalidade | Regra |
| :--- | :--- | :--- |
| Mudar cenário | Explorar ambiente diferente. | Preservar versão anterior e declarar o delta. |
| Mudar configuração | Comparar workers/política/limites. | Fixar inputs e commit para isolar o efeito. |
| Mudar código | Corrigir ou otimizar. | TDD e repetição da comparação anterior. |

Para comparar causas, derivar X/Y/Z da mesma baseline restaurada.
Para simular operação real, encadear eventos sobre o estado aprovado anterior.
Registar `execution_mode=isolated` ou `execution_mode=longitudinal`.
Nunca comparar uma cadeia acumulada com um cenário limpo como se só uma variável tivesse mudado.

### Análise obrigatória após cada passo

| Pergunta | Evidência |
| :--- | :--- |
| Cobriu a procura toda? | Minutos por atribuição, crédito executado, previsto e residual. |
| Respeitou recursos e datas? | Validador independente, colisões, estabilidade e limites. |
| Liquidou dívida corretamente? | Reconciliação por origem; reservas separadas de execução. |
| Que qualidade produziu? | Vetor completo, conclusões por turma, excesso, movimentos e furos. |
| Que esforço consumiu? | Tempos por fase, CPU, pico RAM, workers e trajetória. |
| Porque terminou? | Motivo, prova/estimativa e âmbito global ou local. |
| Certificados honestos? | Etapas certificadas foram executadas e provadas; orçamento contou construção e finalização; nenhuma etapa omitida certificada; cache sem janelas interrompidas. |
| O que mudou face ao controlo? | Diff de inputs, outputs e métricas; hipótese explicativa. |
| O próximo passo está justificado? | Manter, corrigir, alargar pesquisa, refinar fixture ou aumentar pressão. |

Mesmo um resultado válido pode ser uma regressão de qualidade ou rendimento.
Mesmo uma instância impossível pode representar um teste passado, se diagnosticada corretamente.
Um caso viável conhecido sem solução encontrada é uma falha de rendimento, não uma prova de impossibilidade.

## 6. Classificação dos cenários e oráculos

Cada caso declara uma expectativa antes da execução:

| Categoria | Construção e aceitação |
| :--- | :--- |
| `FEASIBLE_WITH_WITNESS` | Existe horário testemunho validado. O gerador deve encontrar proposta completa nos casos obrigatórios. |
| `INFEASIBLE_PROVEN` | Prova independente, enumeração ou défice necessário documentado. Não aceitar solução nem diagnóstico contraditório. |
| `INVALID_INPUT` | Falta configuração obrigatória ou existem dados inconsistentes. Rejeitar na fronteira adequada. |
| `EXPLORATORY_UNKNOWN` | Viabilidade ainda desconhecida. Registar resultado; não usar como prova de sucesso ou impossibilidade sem evidência. |

Começar fixtures viáveis por calendários testemunho e derivar os requisitos.
Acrescentar também topologias desenhadas independentemente para não favorecer apenas horários fáceis de construir.
Criar impossibilidades mínimas retirando um recurso indispensável e demonstrando o conflito.
Conservar casos grandes exploratórios, mas não substituir o corpus obrigatório por casos sem oráculo.

"Espaço disponível" significa interseção efetiva de turma, professor atribuído, período, sala e janela editável.
Registar capacidade por recurso e gargalo, incluindo disponibilidade simultânea.
Não usar uma razão agregada procura/capacidade como certificado de viabilidade.

## 7. Catálogo de campanhas iterativas

Estado do corpus executado até W05 (modo gerador): 3 casos witness, 26 casos de geração (famílias C01–C10, contraexemplos T10–T14/T19, escala 10/30/45/60) e 12 casos anuais (10/30/45/60 turmas × perfis `loose`/`shared-teacher`/`scarce-rooms`). Os passos que exigem reparação, fila ou API executam-se em W06+.

Todas as sequências seguintes incluem executar, validar e analisar entre cada seta.
Nas campanhas de reparação, começar sempre por uma versão publicada e execução coerente com a data simulada.

### C01 — Geração limpa e currículo

**Pacotes:** W01, W03–W05. **Estado:** base executada em modo gerador (pequenas, escala e anuais); repetição anual contínua na W10. **Regressões:** T01, T13–T14, T27, T30.

X: escola pequena, períodos uniformes, recursos suficientes e nenhuma ocorrência.
→ Y: módulos que atravessam aulas, incluindo 75+75 minutos em períodos de 50.
→ Z: períodos mistos, crédito parcial final e três módulos numa aula.
→ R: procura toda cumprida; confirmar resultado vazio útil, sem aulas inventadas.

Repetir com 10/30/45/60 turmas e grelhas diferentes.
Analisar conservação, duração física, datas de conclusão e custo de construção.

### C02 — Poucas horas em muito espaço

**Pacotes:** W04, W06. **Estado:** passos de geração executados; reparação na W06. **Regressões:** T04, T17.

X: inserir 1h residual num calendário com muitas interseções elegíveis.
→ Y: distribuir essa hora por duas atribuições e períodos de durações diferentes.
→ Z: manter a quantidade, mas concentrar disponibilidade num único professor.
→ R: repor disponibilidade e comparar movimentos e conclusão.

Verificar se a reparação usa espaço livre antes de perturbar desnecessariamente o horário.
Não exigir zero movimentos quando isso contrariar prioridades superiores.

### C03 — Muitas horas em pouco espaço

**Pacotes:** W04, W06, W10. **Estado:** passos de geração executados; reparação na W06. **Regressões:** T11, T15, T18.

X: 10h residuais com solução testemunho apertada.
→ Y: 50h, repartidas entre turmas com professores partilhados.
→ Z: retirar capacidade elegível até ultrapassar uma fronteira demonstrada.
→ R: devolver capacidade mínima ou aumentar explicitamente o limite autorizado.

Analisar expansão do bairro, cedência entre turmas, uso da margem e diagnóstico de défice.
Não aceitar solução parcial nem extensão silenciosa da data limite.

### C04 — Poucas horas em pouco espaço

**Pacotes:** W04, W06, W07. **Estado:** passos de geração executados; reparação na W06. **Regressões:** T10–T12, T26.

X: uma aula e uma posição conjunta elegível.
→ Y: a posição exige mover uma aula de outra turma.
→ Z: a cadeia atravessa várias semanas e uma sala específica.
→ R: retirar o último recurso indispensável e depois restaurá-lo.

Testar também residual de um minuto ocupando um período inteiro.
Distinguir inviabilidade local, inviabilidade global e dificuldade da pesquisa.

### C05 — Muitas horas em muito espaço

**Pacotes:** W04–W05, W11. **Estado:** executado em escala; simetria e alternativas redundantes revisitadas na W11. **Regressões:** T27.

X: procura elevada com muitas colocações equivalentes.
→ Y: adicionar salas realmente equivalentes.
→ Z: ampliar grelha e horizonte sem aumentar procura.
→ R: retirar alternativas redundantes, mantendo o testemunho.

Analisar simetria, memória e crescimento das variáveis.
Mais alternativas não devem alterar validade, mas podem dificultar uma pesquisa limitada.
Não confundir regressão de runtime com violação de monotonicidade matemática.

### C06 — Escassez e abundância de professores

**Pacotes:** W04, W06, W09. **Estado:** variantes de geração executadas; reparação e baixa prolongada na W06. **Regressões:** T14–T15, T20.

X: atribuições válidas com docentes suficientes.
→ Y: escola reatribui explicitamente disciplinas a menos docentes, aumentando partilha.
→ Z: baixa de dois meses de um professor crítico e retorno com procura acumulada.
→ R: escola atribui explicitamente um substituto ou restaura disponibilidade.

Ramo adicional: acrescentar docentes sem atribuições → confirmar que não criam capacidade fictícia.
Depois atribuir disciplinas a esses docentes → medir capacidade efetivamente utilizável.
Separar professor obrigatório em falta, que é input inválido, de professor atribuído sem capacidade suficiente.
O solver nunca distribui serviço docente por iniciativa própria.

### C07 — Escassez e abundância de salas

**Pacotes:** W04, W06, W11. **Estado:** variantes de geração executadas; reparação na W06. **Regressões:** T12, T20.

X: salas suficientes e matching conhecido.
→ Y: retirar salas gerais, uma de cada vez, até à capacidade crítica.
→ Z: retirar o único laboratório elegível ou limitar a única sala com lotação suficiente.
→ R: devolver sala elegível; depois adicionar salas redundantes.

Acrescentar salas sem equipamento necessário não resolve falta de laboratório.
Verificar reservas por data, indisponibilidade parcial e continuidade das salas publicadas.
Analisar cortes devolvidos ao detalhe e custo das alternativas redundantes.

### C08 — Capacidade aparente e interações críticas

**Pacotes:** W03–W07, W10. **Estado:** casos gen-* executados; interações completas na W06–W10. **Regressões:** T10–T12, T26.

X: totais semanais suficientes com interseções temporais válidas.
→ Y: conservar os totais, deslocando disponibilidades para períodos incompatíveis.
→ Z: combinar professor partilhado, sala específica e estabilidade longa.
→ R: restaurar uma interseção indispensável e demonstrar solução.

Executar pares e triplos: docente×sala, docente×calendário, sala×estabilidade, docente×sala×prazo.
O detalhe deve refutar falsas promessas do agregado sem eliminar quotas viáveis por escolhas locais arbitrárias.

### C09 — Curto, médio e longo prazo

**Pacotes:** W01, W06, W08. **Estado:** domínio executado (calendário e estabilidade); horizontes de reparação na W06. **Regressões:** T03, T07–T09, T24.

Definir horizontes de teste pela grelha, nunca como novos limites de produto:

- Curto: primeiros cinco dias da grelha depois da fronteira editável.
- Médio: alterações entre duas e seis semanas depois dessa fronteira.
- Longo: alterações no restante período letivo, incluindo proximidade do limite final.

X: mesma ocorrência no curto prazo.
→ Y: mesma ocorrência no médio prazo, restaurando o estado de controlo.
→ Z: ocorrência equivalente no longo prazo.
→ R: colocar o alvo dentro da estabilidade e confirmar proteção física.

Repetir com janela 0, 1, 9 dias e janela que cobre todo o futuro disponível.
Repetir grelhas de 3/5/7 dias, feriados e mudança de data entre gerar e aprovar.
Comparar perturbação, urgência e capacidade real; não esperar igual dificuldade entre horizontes.

### C10 — Preferência, limite absoluto e justiça entre turmas

**Pacotes:** W05–W07. **Estado:** geração executada; recuperação na W06. **Regressões:** T15–T18.

X: concluir todas as turmas antes da preferência.
→ Y: a turma atrasada só melhora se outra ceder capacidade.
→ Z: construir pares de alternativas que terminam na preferência, um dia depois e no limite absoluto.
→ R: ultrapassar o limite absoluto no testemunho proposto; o validador deve rejeitá-lo.

Incluir preferência igual ao limite absoluto e previsão de excesso detetada ainda em novembro.
Geração inicial não usa margem posterior à preferência.
Recuperação prioriza reduzir excesso, mesmo com muitos movimentos permitidos.

### C11 — Estabilidade versus margem

**Pacotes:** W06–W07, W11. **Estado:** comparador puro testado (T16–T19); solver de recuperação na W06; calibração na W11. **Regressões:** T16–T19.

X: conservar aulas custa um dia adicional, ainda longe da preferência.
→ Y: mesmo compromisso perto da preferência.
→ Z: mesmo compromisso implica ultrapassar a preferência.
→ R: comparar poucas/muitas alterações e alterações próximas/repetidas.

Guardar pares de resultados que o proprietário consegue comparar em linguagem escolar.
Validar monotonicidade e prioridades antes de ajustar coeficientes.
Repetir política escolhida em topologias reservadas para evitar sobreajuste aos exemplos.

### C12 — Acumular ocorrências ou reparar frequentemente

**Pacotes:** W06, W08, W10. **Estado:** fila e relógio na W08; sequências na W10. **Regressões:** T21–T22, T24.

X: reproduzir uma sequência de ocorrências e pedir reparação após cada uma.
→ Y: restaurar baseline e acumular a mesma sequência antes de pedir reparação.
→ Z: alterar a frequência administrativa, incluindo renovação aos 28 dias.
→ R: cancelar ou rejeitar propostas e verificar os motivos ainda disponíveis.

Não exigir horários idênticos: decisões anteriores e estabilidade alteram o espaço de pesquisa.
Comparar efeito acumulado, minutos, datas finais e perturbação.
Nenhuma ocorrência inicia automaticamente o solver.

### C13 — Contabilidade sob alterações sucessivas

**Pacotes:** W01–W02, W06, W09. **Estado:** domínio e integração executados; sequências de reparação na W06. **Regressões:** T02–T07, T29–T30.

X: cancelar aula, criar dívida, planear recuperação e aprovar.
→ Y: cancelar a recuperação; voltar a planear; executar; repetir o comando de execução.
→ Z: acerto +600 e depois reversão -600, com origem auditada.
→ R: substituição por outra disciplina, sumário atrasado e correção retroativa.

Validar cada transição, não apenas o saldo final.
Incluir várias dívidas numa aula, uma dívida em várias aulas e excesso de crédito protegido.
Quando uma operação é inválida, exigir rollback integral e explicação; não forçar a sequência a continuar com dados corrompidos.

### C14 — Ano letivo completo

**Pacotes:** W06, W10–W12. **Estado:** por executar (requer W06). **Regressões:** T01–T30 conforme eventos.

X: gerar, aprovar e executar semanas sem ocorrências.
→ Y: introduzir faltas dispersas, substituições e acertos reais simulados.
→ Z: baixa de dois meses de professor partilhado, encerramento de sala e turmas desigualmente atrasadas.
→ R: regressar recursos, reparar, executar até ao fim e reconciliar todo o ano.

Executar perfis tranquilo, irregular, concentrado em crises e próximo da saturação.
Avançar o relógio explicitamente; nunca editar datas fora dos comandos de teste.
Registar dezenas e centenas de eventos com seeds e sequência persistida.
Se a sequência tornar o ano impossível, exigir diagnóstico e ação administrativa explícita para retomar.
Não pedir ao solver para resolver uma impossibilidade física.

### C15 — Diagnóstico e recuperação administrativa

**Pacotes:** W07, W09. **Estado:** por executar. **Regressões:** T20, T26.

X: caso viável conhecido.
→ Y: remover capacidade indispensável e provar o défice.
→ Z: comparar mensagem de impossibilidade com interrupção de segurança sem prova.
→ R: diretor altera disponibilidade, professor atribuído, limite ou progresso efetivamente reconhecido.

Após a alteração, verificar elegibilidade e nova tentativa manual.
Validar que a ação sugerida se relaciona com a causa demonstrada.
Acrescentar casos com várias causas simultâneas e quantidades mínimas apenas parcialmente conhecidas.

### C16 — Falhas e concorrência operacional

**Pacotes:** W07–W08, W12. **Estado:** por executar. **Regressões:** T23–T26.

X: duas escolas pedem geração; confirmar FIFO e um cálculo global.
→ Y: duplicar mensagem, repetir pedido HTTP e interromper dispatch.
→ Z: matar processo, perder ligação do lock e reiniciar o serviço.
→ R: reconciliar tentativa abandonada e executar pedido ainda autorizado.

Repetir falhas durante construção, solve, validação, persistência e aprovação.
Incluir cancelamento concorrente com sucesso e escrita durante fila/solve/aprovação.
Induzir limite de memória e CPU em containers de teste dedicados.
Confirmar que heartbeat e cancelamento não ficam presos atrás do solve.
Verificar CPU anterior terminado antes de começar outra geração; fencing de escrita isolado não basta.

### C17 — Isolamento, instalação e integridade

**Pacotes:** W02, W08–W09, W12. **Estado:** RLS e instalação auditadas em W02; restantes na W08–W09. **Regressões:** T28.

X: instalar base vazia e criar duas escolas.
→ Y: tentar referências, consultas e aprovações cruzadas.
→ Z: provocar falha a meio de publicação ou acerto.
→ R: verificar rollback, reinstalar localmente e repetir sem estado residual.

Usar role real sem bypass RLS.
O executor global pode escolher jobs sem ganhar acesso indiscriminado aos dados de todas as escolas.

### C18 — Escala e hardware

**Pacotes:** W11; repetição selecionada em W13. **Estado:** por executar. **Regressões:** T27.

X: mesmo caso com um worker interno.
→ Y: repetir com 2/4/8, intercalando ordem das configurações.
→ Z: reduzir quotas CPU/RAM e aumentar escala 10/30/45/60 turmas.
→ R: repetir configuração candidata nos casos fáceis, simétricos e difíceis.

Não executar solver jobs concorrentes para acelerar esta campanha.
Separar escalabilidade de infraestrutura de qualidade matemática.
Guardar configurações que falharam por OOM ou segurança; não descartá-las da comparação.

### C19 — Qualidade versus tempo

**Pacotes:** W07, W11. **Estado:** por executar. **Regressões:** nenhuma adicional.

X: trajetórias prolongadas com limites finitos de laboratório.
→ Y: simular offline diferentes critérios de paragem sobre as mesmas trajetórias.
→ Z: repetir online as políticas finalistas em casos reservados.
→ R: analisar ganhos relevantes perdidos, tempo poupado e incerteza.

Incluir melhoria precoce seguida de estagnação e melhoria tardia após uma longa fase sem incumbente novo.
Incluir famílias nunca vistas na calibração para testar comportamento conservador.
Não transformar ausência recente de melhoria em prova de proximidade do ótimo.

### C20 — Percurso escolar completo

**Pacotes:** W09, W12; smoke em W13–W14. **Estado:** por executar. **Regressões:** T21–T24.

X: configurar escola, gerar, rever e aprovar.
→ Y: professor regista aula/ocorrência; administrador acumula motivos e pede atualização.
→ Z: proposta fica desatualizada ou ultrapassa preferência; rever mensagens e ações.
→ R: corrigir configuração, gerar novamente quando elegível e aprovar versão válida.

Incluir navegação por teclado, refresh, resposta atrasada, duplo clique e sessão sem permissão.
Confirmar mapas, detalhe de turma, sumários e relatórios concordantes com o mesmo estado curricular.
Usar adaptadores locais de teste para integrações externas durante a fase local.
Autenticação e deployment reais são validados posteriormente em W13.

## 8. Matriz de variedade e cobertura

### Eixos obrigatórios

| Eixo | Níveis mínimos de exploração |
| :--- | :--- |
| Escala | Microcasos enumeráveis; 10, 30, 45 e 60 turmas. |
| Procura de reparação | 0, 1, 10 e 50h; residual parcial; fronteira exata e um minuto além. |
| Espaço efetivo | Amplo, apertado viável, capacidade exata, insuficiente, aparente sem interseção. |
| Distribuição | Uma atribuição; muitas disciplinas; uma turma; várias turmas; conflito concentrado/disperso. |
| Docentes | Independentes, partilhados, gargalo único, baixa curta/prolongada, substituto explicitamente atribuído, excedentes não atribuídos. |
| Salas | Amplas, escassas, equivalentes, específicas, lotação crítica, reservas, redundantes inúteis. |
| Horizonte | Curto, médio, longo; ano inicial, meio do ano e proximidade do fim. |
| Calendário | Grelhas 3/5/7 dias, feriados, almoço, durações mistas, mudança de hora, intervalos sobrepostos. |
| Estabilidade | 0, 1, 9 dias; fronteira exata; todo o horizonte protegido. |
| Datas finais | Antes da preferência; na preferência; depois; no limite; impossibilidade antes do limite. |
| Eventos | Falta, cancelamento, substituição, correção, alteração curricular, disponibilidade e reatribuição docente. |
| Histórico | Limpo; poucas alterações; alterações repetidas; dezenas/centenas de eventos. |
| Operação | Sucesso, cancelamento, timeout, erro, stale, crash, reentrega, aprovação concorrente. |
| Hardware | Workers 1/2/4/8; quotas reais CPU/RAM; local e remoto em baselines separadas. |

Horas são convertidas explicitamente em minutos curriculares: 1h=60min, 10h=600min, 50h=3000min.
O número de blocos depende das durações físicas; não equiparar hora curricular a um bloco.
"Espaço amplo" e "apertado" devem ter capacidades e testemunhos registados, não apenas etiquetas subjetivas.

### Seleção sem explosão cartesiana

1. Cobrir cada nível isoladamente com um caso explicável.
2. Cobrir todos os pares válidos dos eixos semânticos no manifesto aprovado.
3. Acrescentar interações críticas explícitas de três ou mais fatores.
4. Repetir topologias representativas nas quatro escalas reais.
5. Executar campanhas anuais para interações acumuladas que pares estáticos não capturam.
6. Reservar famílias novas para avaliação final.

Separar a matriz semântica da matriz de hardware.
Não multiplicar cada microteste de contabilidade por todas as configurações de workers.
Restrições entre níveis incompatíveis devem ser explícitas no manifesto.
O relatório calcula cobertura efetiva; enumerar combinações não equivale a executá-las.

Interações críticas mínimas:

- Muitas horas × pouco espaço × professor partilhado × prazo próximo.
- Poucas horas × sala única × janela longa × períodos incompatíveis.
- Crédito parcial × módulos cruzados × substituição × acerto retroativo.
- Baixa prolongada × turmas com atrasos diferentes × limite preferencial.
- Sala redundante × docentes redundantes não atribuídos × elevada simetria.
- Aprovação atrasada × mudança de data × execução entretanto registada.
- Cancelamento × perda de worker × entrega duplicada × tentativa antiga.

## 9. Repetições, orçamento e critérios de término

Definir o manifesto e os limites de laboratório antes de lançar cada campanha.
O orçamento de ensaio controla trabalho experimental; não constitui SLA ou p95 do produto.
O orçamento de cada execução conta construção, pesquisa e finalização; execuções que excedem o orçamento são registadas como tal, nunca reportadas como dentro.

Protocolo inicial mínimo:

| Camada | Repetição inicial |
| :--- | :--- |
| Regressões determinísticas | Cada caso em cada alteração relevante; repetir identicamente se investigar instabilidade. |
| Microcasos com oráculo | Enumeração exaustiva dentro do tamanho declarado. |
| Famílias sintéticas | Pelo menos três topologias distintas por família antes de declarar cobertura da família. |
| Comparação de pesquisa | Cinco seeds de solver por par fixture/configuração finalista. |
| Replays anuais | Três sequências de eventos por perfil e escala obrigatória, sobre baseline identificada. |
| Comparação final de hardware | Várias repetições por seed quando houver variância material; número fixado no manifesto. |

Estes mínimos iniciam a investigação; não provam significância estatística.
Aumentar amostras quando houver variância, regressões inconsistentes ou conclusões ambíguas.
Não parar de recolher amostras apenas porque apareceu um resultado favorável.

Perfis anuais obrigatórios: tranquilo, irregular, crises concentradas e saturação.
Escalas anuais obrigatórias: 10/30/45/60 turmas.
Uma sequência com impossibilidade prevista termina corretamente com diagnóstico e intervenção explícita, não com sucesso artificial.

Fechar uma campanha quando:

- Todos os passos e combinações obrigatórios estão executados e analisados.
- Casos viáveis obrigatórios produzem propostas completas e válidas.
- Casos impossíveis/inputs inválidos têm classificação e explicação corretas.
- Nenhuma violação de integridade, proteção ou isolamento permanece aberta.
- Regressões de qualidade/recursos foram resolvidas ou impedem o gate até decisão explícita sustentada.
- Variância e limites da conclusão constam do relatório.

Limites de segurança que interrompem um caso não contam como cobertura bem-sucedida desse caso.
Se o computador local não suportar um ensaio obrigatório, registar o bloqueio.
Não mover silenciosamente a campanha para Railway.

## 10. Artefactos, relatórios e triagem

Reutilizar `.test-artifacts/` do runner existente.
Não versionar dumps enormes ou dados pessoais; versionar fixtures compactas e receitas de geração.

Cada execução conserva:

```text
campaign_id, case_id, case_version, parent_case_id, mutation
execution_mode, expectation, oracle_reference
commit, image_digest, schema_version, policy_version
fixture_seed, event_seed, solver_seed, workers
hardware, limits, input_digest, event_sequence
result, validation_report, objective_vector, trajectory
timings_by_phase, CPU_seconds, peak_RSS, proof_scope
analysis, defect_reference, next_action
```

O relatório de campanha contém baseline, hipótese, matriz prevista/executada, resultados, falhas e conclusão.
Mostrar piores casos e distribuições por família, além de medianas.
Separar tempo até primeira solução, tempo até proposta persistida e espera em fila.
Listar execuções censuradas e inconclusivas junto das concluídas.

| Classe de problema | Ação |
| :--- | :--- |
| Fixture/teste errado | Corrigir gerador ou oráculo com revisão rastreável; invalidar apenas conclusões afetadas. |
| Violação de domínio | Bloquear candidate; reduzir caso e corrigir com TDD. |
| Falha de pesquisa em caso viável | Preservar testemunho; analisar candidatos, cortes, bairros e recursos. |
| Qualidade pior | Comparar vetor e trajetória; localizar prioridade ou custo incorreto. |
| Runtime/RAM pior | Perfilar fase dominante; manter mesmas condições na comparação. |
| Falha operacional | Injetar novamente no ponto exato; verificar idempotência e atomicidade. |
| Expectativa escolar ambígua | Apresentar resultados concretos e alternativas; não escolher pesos ocultamente. |

Após corrigir, executar o caso mínimo, a família original e famílias que partilham a regra alterada.
Antes dos gates, executar a matriz obrigatória da candidate final.
Se ajustar código/política após observar o conjunto reservado, esses casos passam a regressão conhecida.
Criar nova amostra reservada para avaliar generalização da candidate seguinte.

## 11. Gates e rastreabilidade final

| Gate | Pacotes/campanhas | Estado | Evidência obrigatória |
| :--- | :--- | :--- | :--- |
| G1 — Domínio | W01–W03; C01, C09, C13 (casos pequenos) | Cumprido | Minutos, estabilidade, ledger e validador independentes; 20 códigos de violação; oráculo enumerativo. |
| G2 — Geração | W04–W05; C01–C08, C10 (modo gerador) | Aceite no âmbito corrigido e auditado | Cobertura completa, salas e qualidade coletiva demonstradas; A01–A12 fixados; R55/B01–B05 fechados; nove otimizações com regressões. |
| G3 — Recuperação | W06–W07; C02–C15, C19 | Pendente | Reparação, justiça, margem, diagnóstico, paragem e preservação das nove propriedades (W06.6). |
| G4 — Aplicação | W08–W09; C12–C13, C16–C17, C20 | Pendente | Ciclo manual, isolamento e publicação atómica. |
| G5 — Candidate local | W10–W12; C01–C20 | Evidência recolhida; aceitação do proprietário pendente | Matriz, replays anuais, hardware, limpeza e avaliação reservada. Registo: [W12](SCHEDULER_V1_W12_STATUS.md). |
| G6 — Remoto | W13; subconjunto declarado C14, C16, C18, C20 | Pendente | Baseline Railway/Cloudflare e integrações reais. |
| G7 — Lançamento | W14 | Pendente | CI verde, baseline final, smoke e aceitação. |

G1–G2 estão fechados. G3 é o próximo gate. G5 é a fronteira obrigatória entre Docker local e validação remota.
G6 e G7 não substituem G5.

| Regressões do plano | Campanhas principais | Estado |
| :--- | :--- | :--- |
| T01–T07 | C01, C09, C13, C14 | Verdes |
| T08–T09 | C09, C14, C20 | Verdes |
| T10–T14 | C01, C04, C06–C08 | Verdes |
| T15–T19 | C03, C06–C07, C10–C11, C14–C15 | Verdes (comparador); solver na W06 para T15–T18 |
| T20 | C06–C07, C10, C15 | Pendente: W06 |
| T21–T22 | C12, C20 | Verdes (domínio); percurso persistido na W08 |
| T23–T26 | C04, C08, C15–C16 | Pendentes: W07–W08 |
| T27 | C01, C05, C14, C18 | Parcial; completo na W08 |
| T28 | C17, C20 | RLS auditada em W02; completo na W08–W09 |
| T29–T30 | C01, C13–C14 | Verdes |

O dossier final reúne cobertura por decisão D01–D31, regressão T01–T30, pacote W00–W14 e campanha C01–C20.
Não encerrar a entrega apenas porque todos os testes unitários passaram.
Encerrar quando a candidate demonstrar comportamento correto em cenários estáticos, alterações acumuladas e falhas de operação.
