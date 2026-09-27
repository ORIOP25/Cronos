# Scheduler v1 — WBS para a falha da CI #509

Data: 27 de setembro de 2026. Branch: `codex/scheduler-v1-revamp`. Commit analisado: `fa86e41`.

Estado: **por executar**. Este documento regista trabalho necessário; não altera a implementação nem declara W12 aceite. A [CI #509](https://github.com/ORIOP25/Cronos/actions/runs/36311106347) terminou com backend e frontend verdes, mas o job E2E falhou: **3 testes falhados, 74 aprovados**. Não houve alterações na `main` nem validação remota W13.

Referências: [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md), [especificação v2](SCHEDULER_V1_TECH_SPEC_V2.md), [revisão do gate W12](SCHEDULER_V1_W10_W12_REVIEW_CORRECTION_STATUS.md) e [log do job E2E](https://github.com/ORIOP25/Cronos/actions/runs/36311106347/job/108597079698).

## 1. Falhas observadas e diagnóstico inicial

| ID | Falha observada na CI | Evidência no código; hipótese a confirmar |
| :--- | :--- | :--- |
| F1 | Depois de aprovar a primeira proposta v1, `/dashboard` devolve `PREPARATION` em vez de `OPERATIONAL` (`first-schedule-approval-dashboard.spec.js:133`). | `dashboard_service.py` escolhe o modo por `Organization.first_real_schedule_approved_at`; `approve_proposal` em `scheduler/infrastructure/proposals.py` ativa a versão e atualiza o estado do ano, mas não atualiza esse marco na organização. |
| F2 | Após aprovação, a semana consultada contém **0** aulas com `scheduler_lesson_id`, quando o teste exige pelo menos 2 (`generation.spec.js:494`). | O teste consulta `FIXTURE.schoolStartDate`, definido duas semanas antes da execução. O motor impede novas aulas em períodos já iniciados. Confirmar no artefacto de execução se as aulas foram publicadas noutras semanas antes de concluir que a publicação falhou. |
| F3 | Depois de criar uma regra `teacher_unavailable`, `/scheduler/status` não inclui `PLANNING_CHANGE` durante 30 s (`generation.spec.js:647`). | A criação da regra chama `record_scheduler_change`, que incrementa `scheduler_state_version`; a elegibilidade v1 compara `planning_revision` com `last_completed_planning_revision`. Confirmar a revisão e os eventos na mesma organização e ano antes de fechar o diagnóstico. |

Os três testes chegaram à geração e aprovação. F1–F3 são falhas de integração ou de cenário E2E; a causa exata de F2 ainda requer inspeção dos dados da versão publicada. Não enfraquecer as asserções nem excluir os testes para obter uma CI verde.

## 2. Pacotes de trabalho

| ID | Dependência | Trabalho e entrega | Critério de aceitação |
| :--- | :--- | :--- | :--- |
| CI509.1 | — | Reproduzir F1–F3 na stack Docker isolada e guardar respostas de aprovação, estado, semanas publicadas, revisão de planeamento e artefactos Playwright. Distinguir defeito do produto de pressuposto inválido do teste. | Causa documentada para cada falha, com organização, ano, versão e datas correlacionados; nenhuma alteração especulativa ao motor. |
| CI509.2 | CI509.1 | Integrar a aprovação da primeira proposta v1 com o marco de entrada no modo operacional. Cobrir aprovação repetida, nova versão, organização diferente e transação revertida. | Teste de integração vermelho antes da correção e verde depois; o marco é definido uma vez, na mesma transação da aprovação; dashboard muda para `OPERATIONAL` apenas após publicação real. F1 passa em E2E. |
| CI509.3 | CI509.1 | Corrigir o cenário de publicação e registo de aulas: usar uma semana que contenha aulas realmente publicadas, ou controlar explicitamente o relógio e as datas do ensaio, conforme a causa confirmada. Preservar a verificação de aula concluída, ocorrência, identidade da aula e crédito/dívida. Se não existir nenhuma aula publicada apesar da aprovação, corrigir a publicação ou projeção em vez de mudar apenas a data do teste. | Teste determinístico com pelo menos duas aulas v1 visíveis em `/schedule/week`; os dois registos referem aulas da versão ativa e os estados/ledger são coerentes. F2 passa sem reduzir cobertura. |
| CI509.4 | CI509.1 | Ligar as mutações de regras relevantes à revisão de planeamento v1, mantendo o evento de auditoria e a transação coerentes. Cobrir criação, remoção, ausência de efeito e mudança apenas no passado; verificar invalidação de proposta pendente quando aplicável. | Teste de integração vermelho antes da correção e verde depois; uma indisponibilidade futura produz `PLANNING_CHANGE` e a geração seguinte escolhe `ADAPTIVE_RECOVERY`; alterações irrelevantes não geram revisão espúria. F3 passa em E2E. |
| CI509.5 | CI509.2–CI509.4 | Executar os testes de integração afetados e os três E2E, depois a matriz obrigatória do projeto em Docker. Reconstruir o container frontend se houver alteração no frontend. Publicar apenas na branch de trabalho e acompanhar a CI desse novo commit até terminar. | Backend, frontend e E2E verdes no mesmo commit; execução identificada por URL e SHA. Nenhum merge ou push para `main`. |

Aplicar TDD às correções não triviais: teste que reproduz a falha, menor correção válida, refatoração e regressões focadas. Investigar chamadas existentes antes de escolher o ponto de integração.

## 3. Gate W12 antes de W13

Mesmo com CI509.5 concluído, a CI verde **não equivale à aceitação de W12**. O E2E atual prepara `preferred_end_date`, `CurricularAssignment` e `CurricularRequirement` através do script de teste `backend/scripts/seed_scheduler_e2e.py`; isso demonstra o percurso com projeção semeada, mas não demonstra que um administrador consegue configurar esses dados pelos fluxos do produto. A revisão de W12 também mantém abertas a avaliação online da política de paragem e a aceitação de horários concretos pelo proprietário.

| ID | Dependência | Trabalho e entrega | Critério de aceitação |
| :--- | :--- | :--- | :--- |
| W12.R1 | CI509.5 | Verificar o percurso real de configuração da data preferencial e da projeção curricular a partir de Foundation e das atribuições escolares. Se faltar uma ligação de produto, implementá-la com testes de domínio/integração e repetir o E2E sem depender do seed para esse comportamento. | Administrador configura → gera → aprova → regista → repara numa instalação limpa; dados curriculares, isolamento por organização e validação `início ≤ preferida ≤ limite absoluto` demonstrados. |
| W12.R2 | CI509.5 | Concluir a avaliação reservada da política de paragem nos termos do registo de revisão W10–W12, sem ativar uma política não confirmada. | Evidência comparável de qualidade, duração e paragem; decisão explícita sobre ativação ou manutenção da política conservadora. |
| W12.R3 | W12.R1–W12.R2 | Atualizar o dossier do gate local e submeter horários concretos e compromisso qualidade/tempo/custo ao proprietário. | Condições 2, 7 e 10 do plano §17.1 fechadas com evidência e aceitação explícita. Só então iniciar W13 (Railway/Cloudflare). |

Esta sequência preserva a fronteira do plano: corrigir e validar no Docker local, fechar W12, e apenas depois realizar a validação remota W13.
