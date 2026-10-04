# Cronos — Correções da revalidação QA

**Data:** 4 de outubro de 2026. **Baseline:** `1d99169`; integração com `6526fea`. **Estado:** correções locais verificadas; dados de produção sem alterações manuais.

## Findings e correções

| Finding | Causa confirmada | Correção e verificação |
| :--- | :--- | :--- |
| F02 | O horário aprovado inclui seis turmas arquivadas; o catálogo apresenta 48 turmas ativas. | O dashboard explica as populações. A API expõe `classes_archived`; o teste preserva o denominador e a média anual. |
| F06 | A coluna da ação tinha largura insuficiente. | A ação ocupa uma linha própria no tablet e usa largura automática no desktop. |
| F08 | O aviso global ficava longe do botão usado. | Cada modelo indica preparação. O toast de sucesso ou falha permanece visível no viewport. A transferência mantém o helper existente. |
| F09 | A decisão futura continuava selecionável. O crédito histórico não aparecia nas ocorrências. | A UI bloqueia `GIVEN` antes do fim. O histórico expõe créditos antecipados e permite reversão auditada. |
| F15 | A projeção semanal enviava `REVOKED` para um campo que só aceita `PENDING`, `COMPLETED` e `OCCURRENCE`. | A grelha projeta `PENDING`, preserva o estado de ocorrência `REVOKED` e permite um novo ciclo. |
| F17 | O link QA usava o ID do membro como ID do professor. | A equipa abre o perfil correto. A edição usa a grelha válida na data da ocorrência e preserva outras versões. |
| F19 | A tabela exigia scroll horizontal em 451 px. | A dívida usa cartões no mobile e mantém a tabela no desktop. |
| F20 | A submissão só enviava turmas adicionadas explicitamente à lista. | A criação inclui a turma preenchida. Um rascunho inválido impede a submissão e conserva os campos. |

A reversão segue a cadeia `source_lesson_id` entre versões publicadas.
O ledger conserva o ID original; procurar apenas a aula atual deixava os 50 minutos creditados.
O teste reproduz duas republicações e confirma saldo zero após duas chamadas de reversão.
Uma aula concluída normalmente continua fora da lista de ocorrências.

## Evidência de produção, apenas leitura

As consultas usaram transações `READ ONLY` e filtros da organização.
Nenhum dado de produção foi alterado.

| Elemento | Evidência |
| :--- | :--- |
| Organização e horário | Organização `27`; versão aprovada `22`. |
| Turmas arquivadas | `743` TGPSI 10; `744` TGPSI 11; `745` TGPSI 12; `746` TDES 10; `747` TDES 11; `748` TDES 12. |
| Professor QA | Membro `684`; professor `657`; 45 disponibilidades na grelha `27`; sem acesso à plataforma. |
| Crédito QA | Log `1`, revisão `4`; aula atual `279321`; aula de origem `230239`; execução `9`, origem `lesson-log:230239`, +50 minutos. |
| Natureza do registo | A razão da execução identifica explicitamente um ensaio QA sem dados reais. |
| Erro semanal | Logs do período mostram a validação da resposta a rejeitar `REVOKED`. As referências curtas não tiveram correspondência textual direta. |

## Verificação local

- Backend: 868 testes unitários, 429 integrações e 61 contratos aprovados.
- Reversão histórica: teste final aprovado após a confirmação de ausência de decisão histórica explícita.
- Frontend: 558 testes aprovados após integração da main. `npm run verify` e `npm run audit:production` aprovados.
- Runner: 18 contratos aprovados. Ruff e verificação de formatação aprovados.
- Alembic: sem drift. Auditorias de triggers e integridade aprovadas.
- Stack local reconstruída e atualizada; backend e frontend respondem `200`.
- Browser: 25 testes Playwright aprovados, incluindo os três novos cenários QA.
- Downloads: os cinco modelos produzem ficheiros CSV reais com nome esperado, BOM UTF-8, separador e feedback visível.
- Layout: calendário validado em 768, 1024 e 1440 px; dívida validada em 451 px sem overflow.
- Acessibilidade: axe não encontra violações WCAG 2 A/AA nos cartões de dívida verificados.
- Curso: a turma preenchida fica persistida sem clicar em “Adicionar turma”.

O teste de capacidade de 48 turmas falhou nas primeiras execuções e passou na suite final sem alteração do solver.
Esta validação não certifica todos os 154 casos do plano original.

O `409 conflict` do calendário resultava de uma gravação intermédia que violava `ck_scheduler_school_year_preferred_order`.
O backend gravava os limites novos antes de atualizar a data preferencial.
A correção aplica as três datas antes dos eventos de auditoria.
Os testes reproduzem a mudança para anos anteriores e posteriores, preservam as revisões e confirmam repetição sem efeitos adicionais.
O cenário E2E volta a substituir as datas do calendário.

O runner isolado usa `127.0.0.1`, conforme o binding IPv4 do Docker.
Esta escolha evita colisões com servidores locais que escutam a mesma porta em IPv6.
Clerk e a URL do frontend usam a mesma origem.

## Entrega e operação

| WBS | Ação | Critério de fecho |
| :--- | :--- | :--- |
| QA-E2 | Publicar o patch na main, conforme autorização recebida. | Commit revisto, CI aprovada e serviços atualizados em produção. |
| QA-E3 | Reverter o registo QA, quando autorizado. | Uma compensação de −50 minutos referente à execução `9`; repetição sem novo crédito. |
| QA-E4 | Revalidar produção. | Semana 19–23/10 carregada, perfil `657` identificado e progresso QA sem os 50 minutos. |
| QA-E5 | Concluído: correção do conflito de calendário. | Testes de substituição do calendário e cenário E2E aprovados. |

Não elimine execuções, decisões ou turmas arquivadas para corrigir os resultados.
Use o procedimento de [reconciliação](../../documentation/09_ops_observability/OCCURRENCE_RECONCILIATION.md) para aplicar e verificar a compensação.
