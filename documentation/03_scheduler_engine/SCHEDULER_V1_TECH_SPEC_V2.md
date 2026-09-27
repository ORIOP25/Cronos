# Especificação técnica — Cronos Scheduler v1 (Revisão 2)

Data: 25 de setembro de 2026.

Estado: as secções 2–11 e 16–17 descrevem, para W00–W09, o comportamento implementado e testado (o código e os testes são a fonte da verdade). As secções 12–15 descrevem o ciclo de vida e a API v1 implementados em W08–W09; o restante de W10–W14 é especificação por implementar. Esta revisão substitui a especificação de 23 de setembro de 2026 a partir de W06; a original permanece como referência histórica. Registo de W08–W09: [SCHEDULER_V1_W08_W09_STATUS.md](SCHEDULER_V1_W08_W09_STATUS.md).

Base: [plano de execução v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), decisões D01–D31 e fases P0–P12B.

Branch: `codex/scheduler-v1-revamp`.

Decomposição de trabalho: [WBS técnico v2](SCHEDULER_V1_WBS_V2.md).

## 1. Objetivo, autoridade e âmbito

Substituir o gerador, os seus contratos e os consumidores incompatíveis por uma nova baseline.
O resultado obrigatório é um horário completo, verificável e publicável mediante aprovação.
Uma proposta parcial nunca representa sucesso.

As decisões do plano prevalecem sobre os documentos da implementação anterior.
Esta especificação concretiza essas decisões. Não introduz compatibilidade com o solver antigo.
Os parâmetros experimentais têm critérios de seleção explícitos. Não constituem valores de produção aprovados.

| Pergunta | Resposta técnica |
| :--- | :--- |
| O quê? | Domínio curricular, geração, recuperação, persistência, fila, APIs e consumidores coerentes com a nova v1. |
| Porquê? | Produzir horários completos com boas datas de conclusão, estabilidade controlada e contabilização correta. |
| Quem? | Implementação por quem executar este plano; validação funcional e aceitação pelo proprietário. |
| Onde? | Docker local até P11; Railway e Cloudflare apenas em P12A, após o gate local. |
| Quando? | W00–W09 concluídos; W10–W14 pela ordem das dependências, sem prazos de desempenho inventados. |

Notas normativas desta revisão:

1. Os ganhos históricos de aproximadamente 90 para 22 segundos pertencem às medições anteriores (registos de campanha de 24–25 de setembro de 2026, Docker local, um worker). Esta revisão não os apresenta como nova comparação controlada nem como garantia universal.
2. A antecipação das conclusões resulta da política aprovada (D10–D12). Distribuir procura ao longo do ano exige decisão explícita de produto. Não introduzir limites semanais ou penalizações de antecipação para obter uma aparência mais uniforme.
3. O agrupamento de salas equivalentes e a calibração 1/2/4/8 workers continuam dependentes de medições em W11.

Manter FastAPI, SQLAlchemy, PostgreSQL, Celery, Redis, React e OR-Tools já presentes.
Não adicionar microserviços, outro broker, framework de otimização ou modelo de aprendizagem automática.
As versões verificadas incluem Python 3.14.7 e OR-Tools 9.15.6755; os lockfiles prevalecem.

## 2. Fronteiras e estrutura de código

Estrutura implementada em `backend/app/scheduler/`:

```text
backend/app/scheduler/
  composition.py             # Raiz de composição: injeta a pesquisa no caso de uso
  application/
    contracts.py             # Portas (pesquisa, dispatch, avaliação) e contratos de resultado
    generation.py            # CompleteGeneration, avaliação de recuperabilidade e relatório
  domain/
    candidate.py             # Snapshot, candidato, identidades estáveis e estratégias
    candidate_validation.py  # Validador independente (v3, 20 códigos tipados)
    calendar.py              # Períodos, grelha e fronteira de estabilidade
    capacity.py              # Elegibilidade conjunta e pré-verificação agregada
    demand.py                # Ledger de execução append-only com reversões
    debt.py                  # Dívida, reservas, liquidações e reconciliação
    projection.py            # Projeção modular exata
    quality.py               # Vetores de qualidade, evidência de pesquisa e comparadores
    eligibility.py           # Motivos para geração manual
    oracle.py                # Oráculo enumerativo para instâncias mínimas
    results.py               # Resultados tipados do motor
    constraints.py           # Política de restrições da fronteira legada (sai em W12)
    validation.py            # Validadores da fronteira de blocos legada (sai em W12)
    contracts.py             # Contratos da fronteira legada (sai em W12)
  infrastructure/
    models.py                # Modelos SQLAlchemy v1 (13 tabelas)
    progress.py              # Transações de execução/dívida/recuperação sob lock de estado
    annual_model.py          # Master anual CP-SAT (quotas, hint, no-goods, poda)
    placement_model.py       # Detalhe por janelas, salas, orçamento e cache
    search.py                # Coordenação master/detalhe com realimentação de cortes
    cp_sat_quality.py        # Adaptador CP-SAT do avaliador legado (sai em W12)
    task_dispatcher.py        # Transporte Celery existente
  lab/
    fixtures.py              # Fixtures mínimas com testemunhos e 13 mutações
    scale.py                 # Fixtures de semana única por seed (10–60 turmas)
    annual.py                # Fixtures anuais com testemunhos construídos
    manifest.py              # Manifests, digests SHA-256 e serialização de snapshots
    campaign.py              # CLI de campanhas com retoma por proveniência
    reports.py               # Relatórios e comparação de regressões
    revalidate.py            # Revalidação independente de candidatos armazenados
    payload.py               # Serialização de validação/qualidade/evidência
```

Dependências permitidas:

```text
API/Celery -> composição de dependências -> aplicação -> domínio
infraestrutura -------------------------------> domínio
```

O domínio recebe datas e instantes explicitamente. Nunca consulta relógio, base de dados ou variáveis de ambiente.
Usar dataclasses imutáveis, enums próprios, inteiros e coleções ordenadas.
Não transportar modelos ORM, `Any`, objetos CP-SAT ou sessões SQLAlchemy nos contratos de domínio.
O validador verifica blocos materializados. Não consulta variáveis ou restrições construídas pelo solver.
O oráculo enumerativo é implementação de teste; nunca é fallback de produção.
Produção ainda executa o motor legado em `app/services/`; o cablage é da W08 e a remoção da W12.

## 3. Vocabulário e contratos imutáveis (implementado)

| Conceito | Campos essenciais e semântica |
| :--- | :--- |
| `Assignment` | `class_id`, `subject_id`, professor atribuído, salas elegíveis e restrições obrigatórias. |
| `ModuleRequirement` | Identificador, ordem estável e minutos positivos. |
| `Period` | Data escolar, início/fim local, instante UTC e duração física positiva. |
| `ScheduledLesson` | Identidade estável, atribuição, período, sala e minutos curriculares previstos. |
| `ModuleSlice` | Aula, módulo, offset curricular inicial e minutos; várias parcelas por aula. |
| `ExecutionEntry` | Facto executado ou acerto, minutos assinados, origem, revisão, autor e motivo. |
| `DebtClaim` | Origem de minutos em falta; não constitui procura adicional. |
| `RecoveryAllocation` | Reserva de minutos de uma aula futura para uma dívida. |
| `PlanningSnapshot` | Estratégia, datas de origem/preferencial/absoluta, timezone, grelha, atribuições, execução, bloqueios, indisponibilidades, aulas protegidas, reservas e dívida aberta. |
| `CandidateSchedule` | Conjunto completo de aulas futuras, identidades preservadas e salas atribuídas. |
| `ValidationReport` | Validade, violações estruturadas e totais recalculados. |
| `QualityVector` | Componentes ordenadas, métricas auxiliares e versão da política. |
| `SearchEvidence` | Objetivo, âmbito, incumbente, limite, tolerância, etapas provadas/reutilizadas e motivo de fim. |

Identificadores mantêm o tipo nativo do projeto. O solver utiliza índices densos internos e conserva um mapa explícito para os identificadores originais.
Identidades novas nunca reutilizam identificadores de aulas publicadas.

Unidades obrigatórias:

- Minutos curriculares e durações: inteiros; nunca `float` em conservação de horas.
- Datas escolares: `date` na timezone da escola.
- Instantes de auditoria: UTC com timezone.
- Durações de pesquisa: relógio monotónico.
- Intervalos físicos: semiabertos `[início, fim)`; aulas adjacentes não colidem.

Horários ambíguos ou inexistentes numa transição de timezone falham na normalização.
Não corrigir silenciosamente períodos inválidos.

## 4. Procura, execução, dívida e módulos (implementado)

### 4.1 Conservação curricular

Para cada atribuição `a = (turma, disciplina)`:

```text
Q[a] = soma dos minutos obrigatórios dos módulos
E[a] = soma efetiva dos créditos executados e acertos auditados
R[a] = Q[a] - E[a]

0 <= E[a] <= Q[a]
soma(credit_minutes das aulas futuras de a) = R[a]
0 < credit_minutes[aula] <= duração física[aula]
```

Rejeitar um acerto que viole os limites. Não esconder o erro com `max(0, R)`.
Executar uma aula substitui previsão por execução, uma única vez.
Uma proposta pendente não altera `E`, nem reduz a dívida efetiva.
O mesmo evento repetido não pode acrescentar créditos.
A fórmula `procura = Q - E + dívida` fica proibida. A dívida identifica parte dos minutos já incluídos em `R`.

### 4.2 Projeção modular

Representar os módulos como intervalos consecutivos de minutos curriculares.
Depois de considerar créditos efetivos, percorrer as aulas futuras por data, início e identidade estável.
Distribuir cada crédito pelos intervalos curriculares ainda abertos.
Não criar variáveis de posição por módulo no solver temporal.

Exemplo obrigatório:

```text
M1 = 75 minutos; M2 = 75 minutos; períodos = 50 minutos
Aula 1: M1 50
Aula 2: M1 25 + M2 25
Aula 3: M2 50
```

Cancelar terça e repor quinta pode alterar o módulo previsto de quarta, sem mover quarta.
Essa alteração é permitida dentro da janela de estabilidade.
O diff distingue alteração física de atualização curricular.
Os factos executados conservam a evidência original; sumários atrasados ou correções retroativas nunca a sobrescrevem.

### 4.3 Crédito parcial e duração variável

Uma aula de 30 minutos curriculares num período de 50 ocupa os 50 minutos físicos.
Não atribuir os 20 minutos restantes a outra disciplina, turma ou professor.
Não arredondar módulos individualmente.
Na geração inicial, preencher os períodos selecionados e permitir apenas a última aula parcial por atribuição.
Na reparação, preservar os créditos das aulas protegidas; conservar uma aula parcial publicada apenas quando a estabilidade o exige.
Se créditos protegidos excederem `R`, reportar conflito; não apagar execução nem alterar a janela silenciosamente.
Não assumir períodos universais de 50 minutos. Os modelos agregados distinguem durações; o detalhe verifica a soma exata.

### 4.4 Reconciliação de dívida

Por dívida:

```text
aberta = criada + revisões - liquidada_por_execução - liquidada_por_acerto
0 <= reservada_em_horário_ativo <= aberta
soma(dívida aberta da atribuição) <= R[atribuição]
```

Uma aula pode liquidar várias dívidas. Uma dívida pode ser repartida por várias aulas.
As parcelas de recuperação não podem exceder o crédito curricular da aula.
Reservas pertencem à versão ativa; propostas têm reservas separadas até aprovação.
Ao cancelar uma recuperação, libertar a reserva existente.
Não recriar como dívida nova os minutos que já estavam em dívida.
Acertos positivos reconciliam dívida aberta por data de origem e identificador (mais antiga primeiro), salvo origem explicitamente indicada.
Acertos negativos revertem liquidações associadas quando existir essa relação.
Uma substituição por outra disciplina credita apenas a disciplina realmente lecionada.
Proibir crédito duplicado por sumário, substituição e recuperação sobre a mesma execução.

## 5. Calendário e estabilidade (implementado)

Validar `start_date <= preferred_end_date <= hard_end_date`.
CompleteGeneration usa `preferred_end_date` como limite obrigatório.
AdaptiveRecovery usa `hard_end_date` e penaliza o excesso sobre a preferência. O validador já aplica o ramo por estratégia.

`grid_dates` são as datas cujo dia da semana existe na grelha escolar.
Feriados impedem colocação, mas a contagem da janela segue os dias da grelha.

```text
protected_dates = primeiras N grid_dates a partir de school_today, inclusive
editable_from = primeira grid_date depois dessas N datas
```

Com `N=0`, permitir apenas períodos ainda não iniciados.
Preservar sempre aulas executadas e passado, independentemente de `N`.
Proteger inserção, remoção, mudança de data, período, professor, sala, disciplina e crédito físico/curricular confirmado.
A projeção modular futura constitui a exceção explícita.
Uma ocorrência pode registar que uma aula protegida não aconteceu; isso não autoriza o solver a reescrever esse passado.
A aprovação recalcula a fronteira com a data atual.
Uma proposta antes editável pode tornar-se inválida enquanto aguarda aprovação.

## 6. Modelo de dados da nova baseline (implementado; consolidação em W12)

Migração provisória `0011_scheduler_v1_curricular`. Consolidação numa baseline Alembic nova é da W12.

| Entidade | Campos ou relações essenciais |
| :--- | :--- |
| Estado escolar do planeamento | Organização/ano únicos; revisões `input/planning`; versão ativa; última geração válida; motivos pendentes. |
| Configuração anual | Início, preferência, limite, timezone, grelha e tamanho da janela. |
| Atribuição curricular | Turma/disciplina únicas; professor explícito; requisitos e restrições normalizadas. |
| Ledger de progresso | Origem/revisão idempotentes; minutos assinados; referência de reversão; auditoria. |
| Parcelas de execução | Crédito por módulo, offsets, execução e revisão efetiva. |
| Dívida e liquidações | Origem, revisões e parcelas liquidadas; sem duplicar procura. |
| Versão de horário | Organização/ano, origem, estado, datas de aprovação e versão anterior. |
| Aula de versão | Identidade estável, atribuição, intervalo, sala, crédito e referência à origem. |
| Parcelas curriculares | Aula, módulo, offset e minutos; projeção versionada. |
| Reservas de recuperação | Versão/aula/dívida/minutos; relação muitos-para-muitos. |
| Job | Pedido, snapshot, estados, tentativa, heartbeat, cancelamento e resultado. |
| Proposta | Job único, baseline, validade, política, métricas, diff e aprovação/rejeição. |

Constraints implementadas:

- Chaves estrangeiras incluem organização quando necessário para impedir referências entre escolas.
- RLS forçada em todas as tabelas escolares; sessão com organização explícita e role sem bypass.
- Índice único de idempotência por organização, origem e revisão.
- Um job não terminal por organização/ano; uma proposta corrente por organização/ano.
- Versão ativa única; aulas únicas por identidade dentro da versão.
- Durações positivas, créditos positivos e crédito não superior à ocupação física.
- Sem sobreposição física para turma, professor ou sala na versão publicada.

O deployment deve detetar schema antigo e falhar com orientação de reset após a consolidação.
Inventariar identidades, autenticação e integrações externas antes do reset final.

## 7. Snapshot, revisões e consistência (domínio implementado; cablage na W08)

Duas revisões com finalidades distintas:

- `input_revision`: qualquer alteração que afete a validade de um snapshot, incluindo execução normal.
- `planning_revision`: alteração relevante que pode justificar uma nova geração manual.

Cada comando escolar bloqueia primeiro a linha de estado, altera dados e incrementa as revisões aplicáveis na mesma transação (implementado em `infrastructure/progress`).
Atualizações sem efeito semântico não incrementam `planning_revision`.
Executar normalmente uma aula incrementa `input_revision`, mas não cria motivo de regeneração.

O snapshot é imutável, com representação canónica serializável e digest SHA-256 (implementado em `lab/manifest`).
Coleções ordenadas; configuração, restrições, progresso, dívida, aulas e políticas relevantes incluídos.
Nomes de apresentação sem impacto matemático são excluídos.
O pedido grava as revisões e a versão ativa observadas; a verificação de atualidade na fila é da W08 (T24).

## 8. Modelo matemático de colocação (implementado com as nove otimizações)

### 8.1 Conjuntos e elegibilidade conjunta

```text
A = atribuições turma/disciplina/professor
P = períodos concretos do calendário
R = salas concretas
K[a,p] = salas elegíveis para a em p
d[p] = duração física do período
x[a,p] ∈ {0,1} = atribuição colocada no período
```

`capacity.eligible_periods` é a interseção única usada pela pré-verificação, pelo master anual, pelo detalhe e pelo oráculo:

- Mesma timezone que o snapshot; datas dentro de origem..limite (preferencial em COMPLETE_GENERATION, absoluto em ADAPTIVE_RECOVERY);
- Datas não bloqueadas e não fisicamente protegidas (datas protegidas e instantes passados via `now_utc`);
- Dia da semana presente na grelha;
- Turma e docente disponíveis (indisponibilidade obrigatória exclui; preferência desfavorável mantém elegibilidade e acrescenta custo);
- Pelo menos uma sala elegível livre;
- Sem sobreposição com períodos fixados por aulas protegidas da mesma turma/docente;
- Novas aulas não começam antes de a última aula protegida terminar.

O validador e o oráculo recompõem esta interseção de forma independente. Não criar o produto cartesiano anual atribuição × período × sala.
Não copiar limites de quatro aulas diárias, três consecutivas ou duas recuperações. Manter almoço e exclusões realmente configuradas.

Para cada recurso e conjunto de períodos fisicamente sobrepostos:

```text
soma(ocupações selecionadas e fixas) <= 1
```

### 8.2 Créditos sem arredondamento

Para a parte editável de cada atribuição, descontar primeiro créditos protegidos.
Se o residual editável for positivo, selecionar uma última colocação `l[a,p]`:

```text
l[a,p] ∈ {0,1}; l[a,p] <= x[a,p]; soma_p l[a,p] = 1
u[a,p] ∈ [0, d[p]-1]; u[a,p] <= (d[p]-1) * l[a,p]
credit[a,p] = d[p] * x[a,p] - u[a,p]
soma_p credit[a,p] = residual_editável[a]
```

Nenhuma colocação selecionada depois de `l`. Quando o residual é zero, todas estas variáveis são zero.
Créditos de aulas protegidas ficam constantes; a projeção modular é calculada após materialização.
A verificação de materialização confirma que o detalhe coincide exatamente com a distribuição anual.

### 8.3 Master anual com hint greedy e poda pelo incumbente

Definir `q[a,w,d]` como número de períodos de duração `d` atribuídos à semana `w`.
Definir `f[a,w,d]` para o grupo que contém a última colocação e o desperdício `u`.

```text
q >= f; soma f = 1; 0 <= u[a,w,d] <= (d-1)*f[a,w,d]
soma(w,d)(d*q[a,w,d] - u[a,w,d]) = residual_editável[a]
nenhuma quota positiva depois da semana final selecionada
```

Capacidades semanais por turma, docente e conjuntos de salas, descontando ocupações fixas.
Uma soma semanal suficiente não prova que as aulas cabem nos mesmos períodos disponíveis; o detalhe certifica cada distribuição.

Hint greedy earliest-week: construção gulosa a partir da semana mais precoce, respeitando capacidade por turma, docente e sala; injetada por `AddHint`. É um arranque de pesquisa; não prova viabilidade detalhada.

Objetivo do master: minimizar a semana de conclusão mais tardia; depois, com essa fixada, minimizar o desperdício.
Poda: `latest <= semana_do_incumbente`, com a mesma semana permitida para melhorar os restantes componentes. O limite relaxado é conservado separadamente do incumbente.

### 8.4 Realimentação correta

Quando uma janela é demonstradamente impossível para uma distribuição, devolver um no-good que exclui integralmente essa combinação: contagens positivas, contagens nulas condicionadas, grupo final e desperdício.
Nunca produzir cortes a partir de timeout, solução parcial ou matching heurístico falhado.
Não excluir uma quota porque uma escolha anterior arbitrária ocupou o recurso necessário; reabrir essa escolha ou incluir explicitamente a condição no corte.
Ao mudar o snapshot, descartar cortes que não sejam válidos para os novos dados.
Janelas são reabertas, não congeladas; o número de rondas de realimentação é finito e registado.
Para instâncias pequenas, o oráculo enumerativo mantém-se como referência exata nos testes.

### 8.5 Salas: matching global após posições

Agrupar apenas salas com elegibilidade realmente equivalente para o contexto. Lotação, equipamento, reservas e restrições específicas participam na equivalência. O agrupamento adicional de salas equivalentes como otimização de simetria continua dependente de medições em W11.

Após escolher posições, resolver o matching aula–sala como modelo global:

```text
choice[(aula, sala)] ∈ {0,1}
soma_sala choice = 1 por aula com múltiplas salas elegíveis
soma(ocupações por sala em períodos sobrepostos, incluindo fixas e protegidas) <= 1
```

As posições continuam fixas durante o matching.
Etapas lexicográficas: custo de preferências de sala; depois excesso de continuidade por (turma, disciplina).
Proveniência: o estágio de salas só é provado quando o valor final de mudanças é zero.
Se não existir matching completo, devolver conflito ao modelo temporal.
Refinamento: reabrir posições da mesma semana apenas quando o vetor de qualidade completo melhora estritamente.
Em modo de janela única, a continuidade é otimizada dentro da própria janela.
Validar salas concretas antes de reconhecer uma solução completa.

### 8.6 Conclusões por contagens de limiar

Por turma concluinte, uma variável `dia[turma]`. Por valor distinto `v`, uma contagem:

```text
count_ge[v] = número de turmas cujo dia de conclusão >= v
```

Minimizar os limiares sequencialmente, do valor mais alto para o mais baixo.
Esta minimização é equivalente a minimizar o vetor ordenado `C↓` (mais tardia primeiro).

Condições vinculativas:

- Abranger todas as turmas; turma sem cobertura não recebe data fictícia.
- A equivalência com o vetor ordenado é verificada contra o oráculo enumerativo, incluindo seeds aleatorizadas; é regressão permanente.
- Não substituir a semântica de `C↓` (D12) por somas de datas nem por médias.

### 8.7 Congelamento de prioridades e orçamento por janela

Congelamento: após cada etapa, fixar o valor atingido antes da etapa seguinte.
Uma etapa é provada quando termina `OPTIMAL`. Valor conservado heuristicamente (viável, não provado) fica congelado mas sem certificado.
O prefixo certificado é a sequência contígua de etapas provadas. `SAFETY` des-certifica todas as etapas da janela.

Orçamento por janela:

- As janelas são resolvidas da mais tardia para a mais precoce.
- Reserva de finalização de salas (fração do orçamento, com teto fixo de laboratório).
- Divisão igual do restante pelas janelas pendentes; prazos monótonos verificados em regressão.
- Pré-solve de viabilidade antes das etapas de qualidade, com limite próprio; inviabilidade provada no pré-solve devolve corte ao master sem gastar as etapas.
- Verificações de orçamento entre etapas, com tempo mínimo de etapa.
- Construção e finalização contam no orçamento. Etapa omitida por orçamento nunca é certificada.

### 8.8 Cache de janelas provadas

A chave da cache inclui tudo o que condiciona a janela: âmbitos de atribuição, turmas concluintes, dias protegidos e modo de continuidade.
Uma janela entra na cache apenas quando terminou `OPTIMAL` em todas as etapas.
Uma janela reutilizada tem as etapas marcadas como reutilizadas.
Uma janela interrompida nunca é cacheada nem reutilizada como ótima.
Mudança de protegidos, baseline ou fronteira editável invalida a chave.

## 9. Política de qualidade executável

### 9.1 Métricas comuns (implementado)

`C[c]` é a última data necessária para concluir toda a procura da turma.
Incluir conclusão executada quando relevante; uma turma incompleta não recebe uma data fictícia.
Ordenar `C` por ordem decrescente: `C↓`.
Usar dias desde uma origem comum do snapshot; não números de semana com mudanças de ano.
Furos representam minutos escolares desocupados entre a primeira e última aula do recurso no dia.
Excluir almoço e períodos inexistentes na grelha.
Contar furos de professores antes dos das turmas.
Indisponibilidade obrigatória não é violação de preferência; o relatório decompõe os intervalos contados.
`measure_initial_quality` recalcula todas as componentes a partir de snapshot e candidato, sem consultar o solver.

### 9.2 Geração inicial (implementado)

Minimizar lexicograficamente:

```text
(C↓, minutos_de_furos_professores, minutos_de_furos_turmas,
 custo_preferências, custo_mudanças_de_sala)
```

Implementação: etapas de limiar (secção 8.6) seguidas de furos de professores, furos de turmas, preferências e salas, com congelamento entre etapas (secção 8.7).
Datas nunca ultrapassam a preferência na geração inicial.
Uma melhoria da conclusão mais tardia prevalece sobre estética ou soma das restantes datas.
Não atrasar uma turma apenas para igualar datas.
Não usar pesos gigantes: a lexicografia é implementada por etapas e congelamento, com equivalência ao oráculo verificada.
Fixar um prefixo como ótimo apenas quando houver prova; um prefixo conservado heuristicamente limita a pesquisa, não certifica optimalidade global.

### 9.3 Recuperação: datas e perturbação (especificação W06)

Definir `O[c] = max(0, C[c] - preferred_end_date)` e ordenar `O↓`.
Minimizar primeiro `O↓`, antes de qualquer perturbação do futuro editável.
Assim, reduzir excesso prevalece sobre conservar aulas móveis.
Nenhum objetivo permite atravessar o limite absoluto.

Dentro do mesmo vetor de excessos, usar uma função crescente convexa `g` até à preferência.
Definir perturbação `D` por diferenças reais em relação à versão publicada:

```text
D = soma_por_aula(custo_tipo_alteração * urgência * reincidência)
```

Inserções, remoções, movimentos e mudanças de sala têm custos explícitos.
Contar cada transformação uma vez. Urgência aumenta junto da fronteira editável; reincidência depende de alterações anteriores auditadas.
Alteração apenas modular não aumenta perturbação física.

Formulação proposta:

```text
B[i] = g(min(C↓[i], preferred_end_date)) + lambda * D
QualityAdaptive = (O↓, B[1], ..., B[n], C↓, D,
                   furos_professores, furos_turmas, preferências, salas)
```

Minimizar lexicograficamente. `lambda` é positivo; `g` usa coeficientes inteiros e declives estritamente positivos.
O comparador `adaptive_quality_vector` já existe como política experimental com T15–T18 verdes ao nível do comparador.
Esta fórmula é uma decisão técnica sujeita à calibração P6–P10, não uma escala universal de qualidade.
Guardar `quality_policy_version`, coeficientes e exemplos de ordenação junto de cada benchmark.
Não escolher coeficientes numéricos antes desses ensaios.
Uma alteração da fórmula ou das prioridades exige atualizar especificação, oráculos e baseline.

Medir impacto incremental contra a versão anterior e acumulado contra a primeira aprovação.
O comparador usa a referência publicada do snapshot, nunca uma proposta intermédia da própria pesquisa.

## 10. Algoritmos de geração e recuperação

### 10.1 CompleteGeneration (implementado)

```text
normalizar snapshot e compilar procura
pré-verificação agregada com défices mínimos provados (INFEASIBLE com evidência)
master anual: hint greedy, poda pela semana do incumbente, no-goods de rondas anteriores
detalhe por janelas: pré-solve, limiares, congelamento, orçamento, cache
verificação de materialização contra a distribuição
salas: matching global e refinamento da mesma semana
incumbente pelo vetor completo; cortes apenas de inviabilidade provada
validação independente e métricas recalculadas fora do solver
avaliação de recuperabilidade de um cenário (cancelamento da última aula planeada)
evidência por etapa: âmbito, incumbente, limite, etapas provadas/reutilizadas, motivo de fim
```

A primeira solução completa é um marco de pesquisa, não o critério automático de paragem.
Guardar o incumbente fora do objeto solver para sobreviver ao encerramento de uma fase.
O número de rondas de realimentação é finito e registado; limites honestos de fim: distribuições esgotadas, limite de segurança, limite de rondas.

### 10.2 AdaptiveRecovery (especificação W06)

Compilar residual contra execução efetiva e horário publicado.
Detetar falta de cobertura, excesso, recursos inválidos e alterações relevantes.
Começar por inserção e movimentos nos recursos afetados.
Expandir o bairro por conflitos entre professor, turma, sala e períodos.
Permitir cadeias entre semanas afastadas e cedência de capacidade entre turmas.

Manter blocos exteriores ao bairro como ocupações fixas, sem esquecer o seu custo global.
Recalcular conclusões e furos dos dias afetados com o contexto exterior incluído.
Comparar sempre candidatos pelo avaliador global do snapshot.
Não usar número do bairro, distância de expansão ou ordem de tentativa como prioridade de produto.

Integração com as nove otimizações consolidadas:

- Movimentos reabrem as janelas afetadas; cortes continuam a descrever integralmente o subproblema excluído.
- O hint pode partir do baseline publicado; nunca prova viabilidade detalhada.
- As conclusões por limiar abrangem todas as turmas também na reparação; a equivalência ao vetor ordenado mantém-se como regressão.
- O congelamento distingue provado de conservado em todos os estágios de reparação.
- O orçamento por janela conta construção e finalização da reparação; sem starvation; etapas omitidas não são certificadas.
- A poda usa a semana do incumbente de reparação; a mesma semana é permitida.
- As salas voltam a matching global após os movimentos; posições fixas; refinamento só com melhoria estrita do vetor completo.
- A elegibilidade conjunta é a mesma interseção única, incluindo passado, datas protegidas e timezone.
- O cache de janelas provadas invalida quando protegidos, baseline ou fronteira editável mudam; janela interrompida nunca é ótima.

Se houver solução com excesso, procurar alternativas sem excesso antes de aceitar baixo retorno.
O controlador regista se essa exploração foi local ou global.
Impossibilidade num bairro apenas justifica expansão ou diagnóstico local.
Só uma prova válida para todo o espaço autorizado permite declarar impossibilidade do pedido.

## 11. Paragem, certificados e diagnóstico

### 11.1 Resultado tipado (implementado no motor; CANCELLED/STALE completam-se na W08)

| Resultado | Proposta | Significado | Estado |
| :--- | :--- | :--- | :--- |
| `COMPLETE` | Sim | Solução completa, validada e atual. | Implementado. |
| `INFEASIBLE` | Não | Impossibilidade demonstrada no âmbito integral aplicável. | Implementado (pré-verificação e detalhe provado). |
| `INCONCLUSIVE` | Não | Não existe solução completa nem prova de impossibilidade. | Implementado. |
| `CANCELLED` | Não | Cancelamento administrativo ganhou a corrida de finalização. | W08. |
| `STALE` | Não | Dados ou fronteira já não permitem finalizar aquela proposta. | W08. |
| `FAILED` | Não | Erro de execução, infraestrutura ou validação interna. | Implementado. |

Input inválido (residual negativo, configuração inconsistente) é rejeitado na fronteira com `INVALID_INPUT`, sem entrar no solver.
Uma solução completa pode ter `stop_reason=SAFETY_LIMIT`; nesse caso, mostrar que a melhoria foi interrompida; não atribuir certificado inexistente.
Um erro do validador nunca é convertido em sucesso degradado.

### 11.2 Evidência matemática (implementada por etapa)

Guardar objetivo exato, sentido, incumbente, limite, tolerância e âmbito por etapa; marcar cada etapa como provada ou conservada, e as reutilizadas da cache como reutilizadas.
Não transformar `OPTIMAL` de uma janela em prova do ano.
Não somar gaps locais para fabricar um gap global.
Para um vetor lexicográfico, indicar o prefixo certificado (sequência contígua de etapas provadas).
O limite relaxado do master é conservado separadamente do incumbente; nunca substitui um candidato materializado.
Tolerâncias nativas requerem registar os valores, além do status retornado.
Os estados CP-SAT e os campos de limites pertencem ao contrato do solver; verificar o comportamento na versão fixada antes de expor certificados.

### 11.3 Controlo por retorno adicional (especificação W07)

Entradas: trajetória de incumbentes, limites, esforço, bairros explorados e família de dificuldade.
Saídas: continuar, mudar bairro/fase ou finalizar com motivo explícito.

Começar com regras determinísticas, calibradas em trajetórias prolongadas:

1. Exigir solução completa antes de parar por qualidade suficiente.
2. Verificar exploração mínima dos objetivos superiores e recursos críticos.
3. Medir frequência e dimensão das melhorias numa janela de esforço.
4. Consultar ganhos posteriores observados em casos comparáveis do corpus de calibração.
5. Continuar quando existirem sinais úteis; terminar quando o ganho adicional esperado for pequeno.

Usar dias, alterações e furos para interpretar ganho; não uma percentagem inventada de perfeição.
Guardar a incerteza da estimativa empírica.
Instâncias fora das famílias calibradas recebem exploração conservadora até certificado ou limite de segurança documentado.
Nenhum p95, global ou por bloco, entra na regra de paragem.
Os limites de segurança são finitos, configurados por ambiente e versionados nos ensaios.
Cobrem construção, solve, memória e finalização; não apenas o tempo dentro de CP-SAT.

### 11.4 Diagnóstico

Pré-verificações (implementadas) provam défices necessários de capacidade por recurso, com classes afetadas e minutos mínimos em falta.
Conflitos CP-SAT podem identificar grupos incompatíveis, sem garantir um conjunto mínimo.
Marcar sempre o âmbito e a natureza da evidência.
Um cálculo relaxado fornece um limite inferior de défice; não o apresentar como défice exato.

```json
{
  "code": "INSUFFICIENT_TEACHER_CAPACITY",
  "evidence_kind": "PROVEN_LOWER_BOUND",
  "minimum_missing_minutes": 100,
  "affected_class_ids": [17, 18],
  "suggestions": ["REVIEW_AVAILABILITY", "REVIEW_END_DATE", "REVIEW_RECORDED_PROGRESS"]
}
```

Quantidades só aparecem quando suportadas pelo cálculo.
"Rever horas registadas" significa corrigir execução real ou trabalho reconhecido pela escola.
Nunca recomendar inventar horas para satisfazer o solver.
Não prometer que aumentar a data resolve um conflito de professor ou sala sem validar essa hipótese.
Explicações completas por conflito identificado são da W07 (C15).

## 12. Fila global e execução operacional (especificação W08)

Uma réplica do serviço solver; Celery com concorrência um e prefetch um.
Um job pode configurar `num_search_workers` com vários workers CP-SAT.
Não executar várias janelas simultâneas na v1; primeiro medir o paralelismo interno do solver.

Pedidos têm ordem FIFO persistida na base de dados.
A mensagem Celery acorda o executor; a base de dados decide o próximo pedido elegível.
O acesso global à fila limita-se aos metadados operacionais necessários para escolher o pedido.
Carregar dados escolares apenas depois de estabelecer a organização desse pedido e a respetiva sessão RLS.
Não desativar RLS globalmente. Uma entrega duplicada não cria nova execução.

Usar advisory lock global numa ligação PostgreSQL dedicada durante a execução.
Não manter uma transação de escrita aberta durante o solve.
Cada claim incrementa `attempt_token`; todas as escritas de resultado verificam esse token.
Heartbeat e cancelamento usam uma ligação distinta e continuam durante o solve.
O controlador chama a interrupção suportada pelo solver quando necessário.
Um supervisor do processo cobre bloqueios na construção e finalização, fora dos callbacks CP-SAT.
O limite extremo pode terminar o processo; a recuperação não depende de esse processo escrever o estado final.

Perder a ligação do lock exige parar o processo de cálculo.
Um token impede escrita antiga, mas não prova que o CPU antigo parou.
Na v1, usar recuperação conservadora: confirmar terminação do processo anterior antes de iniciar outro solver.
Deployments usam stop-before-start; não permitir sobreposição de réplicas de cálculo.

No arranque, reconciliar jobs abandonados antes de consumir novos pedidos.
Falhas de dispatch deixam o pedido recuperável.
Reenviar o mesmo pedido autorizado é permitido; criar uma nova geração sem ação administrativa não é.

## 13. Elegibilidade e máquina de estados (domínio implementado; fila na W08)

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
   |          |           |
   +----------+-----------+-> CANCELLED / STALE / FAILED
              +-------------> INFEASIBLE / INCONCLUSIVE

Proposta: PENDING -> APPROVED / REJECTED / STALE / SUPERSEDED
```

Estados terminais não regressam a `RUNNING`.
Uma repetição administrativa cria nova tentativa identificável e conserva a anterior para diagnóstico.
Uma reentrega do transporte referencia a mesma tentativa e é idempotente.

Elegibilidade exige ausência de job ativo e pelo menos uma condição (implementado em `domain/eligibility`, testado T21–T22):

- Primeira geração ainda sem proposta completa para o mesmo estado.
- Alteração relevante não coberta pela última proposta completa.
- Tentativa anterior sem resultado completo.
- Passaram 28 dias corridos desde `last_successful_generation_at`.

Contar os 28 dias pela data local da escola, mantendo o instante UTC auditável.
Persistir proposta completa e atualizar o relógio na mesma transação (W08).
Aprovação e rejeição não reiniciam o relógio.
Uma rejeição sem mudança de dados não cria motivo novo.
Revalidar motivos ao submeter; o frontend não é a autoridade de elegibilidade.

## 14. Transações de proposta e aprovação (especificação W08)

### 14.1 Finalização

1. Validar o candidato fora da transação de escrita.
2. Bloquear estado escolar e job, nesta ordem em todos os comandos.
3. Verificar revisões, versão base, tentativa e cancelamento.
4. Revalidar a fronteira temporal atual e os invariantes afetados.
5. Persistir proposta, aulas, parcelas, reservas, diff e evidência.
6. Consumir apenas motivos cobertos pelo snapshot.
7. Atualizar relógio e terminar o job na mesma transação.

O cancelamento antes do ponto de commit impede nova proposta.
Após sucesso confirmado, cancelar o job é operação sem efeito; rejeitar a proposta é uma ação distinta.

### 14.2 Aprovação

1. Validar administrador e organização.
2. Bloquear estado escolar e proposta.
3. Verificar proposta pendente, versão base e revisões atuais.
4. Recalcular procura, dívida, calendário e estabilidade.
5. Executar validador independente sobre o resultado completo.
6. Ativar a versão e reconciliar reservas de recuperação.
7. Registar auditoria e concluir atomicamente.

Não executar o solver dentro da transação de aprovação.
Qualquer conflito causa rollback integral e resposta estruturada.
Pedidos repetidos de aprovação devolvem o mesmo resultado quando já aprovados pelo mesmo comando idempotente.
Leitores nunca observam meio horário antigo e meio horário novo.

## 15. API e adaptação do frontend (especificação W09)

Reutilizar a área `/api/v1/scheduler`, atualizando schemas sem adaptadores de payload legado.
O servidor escolhe CompleteGeneration ou AdaptiveRecovery conforme exista baseline publicada.

| Operação | Contrato |
| :--- | :--- |
| `GET /status` | Estado, elegibilidade, motivos, proposta corrente e datas; sem escritas. |
| `POST /generate` | Pedido manual idempotente; devolve job e posição aproximada na fila. |
| `GET /jobs/{id}` | Fase, resultado e resumo; sem percentagem fictícia do solve. |
| `POST /jobs/{id}/cancel` | Regista cancelamento idempotente. |
| `GET /drafts/current` | Proposta corrente, métricas de produto e avisos. |
| `GET /drafts/{id}/diff` | Alterações físicas e projeções modulares separadas. |
| `POST /drafts/{id}/approve` | Aprovação atómica com revisão esperada. |
| `POST /drafts/{id}/reject` | Rejeição auditada; não desbloqueia reroll arbitrário. |

Usar os endpoints existentes de turma, sumários e ocorrências para comandos desses domínios.
Adaptá-los ao novo ledger; não criar caminhos paralelos de contabilização.

`POST /generate` recebe chave idempotente e revisão esperada.
Não recebe organização confiada ao cliente, número de workers ou escolha livre de estratégia.
Responder `202` para pedido aceite; `409` para estado/revisão incompatível; `422` para configuração inválida.
Manter o envelope de erro existente com `code`, `message`, `reference`, `retryable`, `fields` e `context`.
Não expor traceback, snapshot completo ou dados de outras escolas.

O frontend traduz códigos estáveis; não interpreta texto para decidir comportamento.
Mostrar fila, preparação, organização, melhoria e revisão como fases compreensíveis.
Mostrar alerta persistente enquanto houver conclusão depois da preferência.
Separar dívida aberta, recuperação planeada e horas efetivamente cumpridas.
Atualizar detalhe de turma, calendário, mapas, sumários e relatórios para múltiplas parcelas modulares.
Preservar acessibilidade, navegação por teclado e erros junto dos campos.

## 16. Validador independente e estratégia TDD

### 16.1 Verificações obrigatórias (implementado, versão 3)

O validador recebe snapshot e candidato, sem acesso à construção do modelo.
Recalcula:

1. Cobertura exata por atribuição e conservação de minutos.
2. Unicidade de identidade e integridade das referências.
3. Colisões físicas de turma, professor e sala.
4. Elegibilidade, disponibilidade, calendário e limites de datas (ramo por estratégia).
5. Preservação histórica e janela de estabilidade.
6. Parcelas modulares sem lacunas ou sobreposição curricular.
7. Reservas de dívida sem dupla liquidação.
8. Cronologia das aulas protegidas e prestação de contas do crédito protegido.
9. Métricas de conclusão, perturbação e furos (via `measure_initial_quality`).

Indexar por recurso/data e ordenar intervalos; evitar comparação quadrática.
Guardar versão do validador e digest do candidato.
Métricas declaradas pelo solver nunca substituem métricas recalculadas.
Cada um dos 20 códigos de violação tem teste próprio; candidatos deliberadamente adulterados são rejeitados pelo motivo correto.

### 16.2 Ciclo TDD por fatia (aplicado em W01–W05; mantém-se para W06+)

Escrever primeiro um exemplo observável que falha.
Implementar a menor regra correta e refatorar após verde.
Testes de domínio usam apenas valores; não precisam de mocks ORM ou solver.
Testes de transação usam PostgreSQL real no Docker local, não SQLite.
Testes CP-SAT verificam validade e qualidade, não sequências exatas de callbacks.

| Grupo | Estado | Oráculo |
| :--- | :--- | :--- |
| Currículo | Verde | 75+75/50; aula cruza três módulos; minutos parciais; durações heterogéneas. |
| Progresso | Verde | Crédito único, reversão, sumário atrasado, acerto positivo/negativo e limites. |
| Dívida | Verde | Uma dívida em várias aulas; várias dívidas numa aula; cancelar recuperação sem duplicação. |
| Estabilidade | Verde | Grelhas de 3/5/7 dias; N=0; feriado; data atual; aprovação posterior. |
| Recursos | Verde | Mesmo professor em turmas distintas; salas específicas; intervalos sobrepostos; preferência soft. |
| Capacidade | Verde | Semana agregada suficiente com períodos conjuntos insuficientes (T10). |
| Qualidade inicial | Verde | Oráculo enumerado com vetor de conclusões, não soma de datas; limiares equivalentes ao vetor com seeds. |
| Qualidade adaptativa | Comparador verde; solver na W06 | Ceder recursos à turma atrasada; estabilidade versus margem; excesso domina perturbação (T15–T18). |
| Diagnóstico | Parcial | Impossível conhecido; bairro impossível mas global viável; timeout sem prova (T26 na W07). |
| Ciclo de vida | Pendente (W08) | Duplo clique, entrega duplicada, dados alterados em fila/solve/aprovação (T23–T25, T27–T28). |
| Recuperação operacional | Pendente (W08) | Processo morto, lock perdido, dispatch falhado, cancelamento durante validação. |
| Isolamento | RLS verde em W02; restante na W08–W09 | Consultas e FKs entre escolas; role RLS real; org do cliente ignorada (T28). |
| UI/E2E | Pendente (W09) | Configurar → gerar → aprovar → ocorrência → reparar → executar → acertar → renovar. |

Propriedades metamórficas verificadas: renomear entidades não altera qualidade; permutar entradas não altera o comparador; mais disponibilidade não destrói testemunho válido; o vetor completo iguala o ótimo enumerado em instâncias mínimas (40 casos comparados, zero divergências no audit).

### 16.3 Loops experimentais obrigatórios

Executar as campanhas C01–C20 do [WBS v2](SCHEDULER_V1_WBS_V2.md) durante a implementação, não apenas antes do lançamento.
Cada campanha encadeia baseline, mutação controlada, aumento de pressão e recuperação.
Uma falha exige reprodução, redução do caso, teste vermelho, correção e repetição dos cenários afetados.
Cada caso declara expectativa: viável com testemunho, impossível demonstrado, input inválido ou exploratório sem viabilidade conhecida.
Testar o validador com candidatos deliberadamente adulterados.
Um timeout num caso viável conhecido é insuficiência de pesquisa, não prova de impossibilidade.

## 17. Corpus, benchmarks e seleção de parâmetros

### 17.1 Artefactos reproduzíveis (estado e plano)

Implementado: fixtures canónicas no repositório; manifests `scheduler-lab-v3` com digests SHA-256; seeds de fixture, eventos e solver separadas; corpora:

- `manifest.json`: 3 casos witness (campanha `w03-minimal`).
- `generation_manifest.json`: 26 casos de geração (campanha `w04-generation`; famílias C01–C10, contraexemplos T10–T14/T19, escala 10/30/45/60).
- `annual_manifest.json`: 12 casos anuais (campanha `w04-annual`; 10/30/45/60 turmas × perfis `loose`/`shared-teacher`/`scarce-rooms`).

Pendente: corpus de reparações (W06), sequências anuais com eventos (W10), conjunto reservado final (W12).
Cobertura continua a exigir 10/30/45/60 turmas, partilha docente, salas escassas, calendários restritos, reparações de 1h/10h/50h com distribuições de conflito diferentes e replays anuais (tranquilo, irregular, crises, saturação).

Explorar pouca/muita procura com pouco/muito espaço efetivamente elegível, capacidade exata, um minuto além, conflitos de interseção e abundância de alternativas equivalentes.
Medir disponibilidade conjunta de turma, professor atribuído, sala, período e fronteira editável.
Professores adicionais sem atribuições não aumentam capacidade curricular automaticamente.
Cobertura por níveis isolados, pares válidos e interações críticas de três ou mais fatores, com exclusões declaradas no manifesto.

### 17.2 Medições por execução

```text
commit, image_digest, fixture_digest, seed, policy_version
CPU/modelo/quota, RAM/limite, sistema, versões, workers
queue_wait, snapshot_time, build_time, first_complete_time
search_time, validation_time, persistence_time, total_processing_time
peak_RSS, CPU_seconds, candidate_count, model_variables, model_constraints
complete_valid, outcome, stop_reason, objective_vector
bounds_with_scope, trajectory, certified_stages, reused_stages
changed_lessons, class_completion_dates
```

Separar espera na fila de processamento.
Guardar falhas, OOM e censura; não excluir execuções difíceis para melhorar o p95.
Publicar tamanho da amostra e incerteza.
Não misturar Docker local e Railway na mesma baseline.

O modo `campaign` do runner existe:

```text
node scripts/test.mjs campaign --manifest <manifest> --mode generator [--case <id>]... [--time-limit <s>] [--workers <n>] [--resume]
```

Revalidação independente de candidatos armazenados:

```text
python -m app.scheduler.lab.revalidate <case.json>
```

### 17.3 Protocolo de comparação

Fixar fixture, hardware, política, versões e limites de segurança.
Intercalar ordem das configurações para reduzir efeito de aquecimento.
Executar várias seeds do solver; uma seed não elimina não determinismo multithread.

Comparar primeiro validade e taxa de conclusão.
Depois comparar o vetor de qualidade, a trajetória e recursos consumidos.
Evitar uma média única que esconda regressões nas escolas mais difíceis.
Traçar a fronteira qualidade/tempo/CPU/RAM e identificar configurações dominadas.

Executar 1, 2, 4 e 8 workers internos em W11, respeitando os limites do host.
Não confundir oito workers com oito cores garantidos.
Selecionar a configuração com ganhos sustentados e custo aceitável, não apenas menor wall time.

### 17.4 Calibração da paragem

Executar trajetórias prolongadas apenas no laboratório com limites finitos.
Reproduzir offline as decisões de paragem candidatas.
Medir tempo poupado e melhorias relevantes perdidas depois da paragem simulada.
Avaliar no conjunto reservado antes de fixar a política.

Parâmetros a fechar por evidência: declives de `g`, `lambda`, custos de perturbação, exploração mínima e limiar de retorno.
Também fechar workers, limites de segurança e reserva de finalização.
Nenhum destes campos recebe um default silencioso de produção.
O manifesto de ensaio exige valores explícitos e identifica-os como experimentais até aceitação.

### 17.5 Evidência e prevenção de sobreajuste

Guardar IDs de campanha/caso, versão, cenário pai, mutação e seeds separadas.
Associar cada resultado ao commit, política, hardware, limites e digest dos inputs.
Preservar sequência de eventos, validação independente e análise da próxima ação.
Reutilizar o runner e `.test-artifacts/`.

Registar falhas de pesquisa separadamente de erros de domínio, fixtures incorretas e impossibilidades reais.
Após correção, repetir o caso mínimo, a família de origem e as famílias afetadas pela mesma regra.
Uma alteração arquitetural ou de política exige nova comparação ampla antes do gate.

Se resultados reservados influenciarem alterações, promovê-los a regressões conhecidas.
Criar avaliação reservada nova para a candidate seguinte.

## 18. Observabilidade e critérios de aceitação

Logs estruturados incluem `job_id`, tentativa, organização, fase e código de resultado.
Não registar dados pessoais ou conteúdo integral dos snapshots nos logs.
Métricas agregadas evitam labels de cardinalidade ilimitada.
Evidência detalhada permanece associada ao job, com acesso administrativo autorizado.

Alertas operacionais: fila sem consumo, heartbeat parado, falhas repetidas, memória e persistência inconsistente.
Alertas escolares: proposta desatualizada, impossibilidade demonstrada e conclusão além da preferência.
Um heartbeat parado é suspeita operacional; não prova inviabilidade do horário.

Critérios objetivos para aceitar a candidate local:

- Zero violações no validador em todos os resultados apresentados como completos.
- Zero perda/duplicação de minutos, execução ou dívida nos testes sequenciais.
- Zero alterações físicas protegidas e zero aprovações de snapshots desatualizados.
- Um único cálculo global nos testes concorrentes e de recuperação.
- Corpus de 60 turmas e recuperações representativas concluído conforme o gate do plano.
- Qualidade confirmada por oráculos pequenos e evidência comparativa nos grandes.
- As nove condições de correção das otimizações verdes em geração e reparação.
- Política de paragem avaliada em casos reservados e parâmetros documentados.
- Campanhas C01–C20 concluídas nos casos obrigatórios, com análise entre mutações e replays anuais completos ou corretamente diagnosticados.
- Matriz de cobertura, regressões reduzidas e resultados inconclusivos incluídos no dossier; nenhum caso omitido silenciosamente.
- Instalação vazia, reset e recuperação de falhas ensaiados localmente.
- Frontend e consumidores sem dependência dos contratos antigos.
- Aceitação funcional do proprietário com resultados concretos.

## 19. Sequência de implementação e remoção

| Fase do plano | Entrega técnica | Estado | Condição para avançar |
| :--- | :--- | :--- | :--- |
| P0 | Inventário, serviços, manifests locais. | Concluída (W00) | Nenhum ensaio aciona cloud automaticamente. |
| P1 | Contratos, calendário, ledger, procura, projeção e comparador. | Concluída (W01) | Testes de domínio e contraexemplos verdes. |
| P2 | Schema novo, migração provisória, RLS e constraints. | Concluída (W02) | Instalação vazia e invariantes transacionais demonstradas. |
| P3 | Validador, oráculos, fixtures e medição. | Concluída (W03) | Distingue soluções inválidas e mede métricas independentemente. |
| P4 | Master anual, detalhe reabrível e salas. | Concluída (W04) | Soluções completas corretas em todo o corpus obrigatório de geração. |
| P5 | Conclusões coletivas e objetivos subordinados. | Concluída (W05) | Comparação com ótimos pequenos e baseline mensurada registada. |
| P6 | Reparação, bairros, dívida e estabilidade. | Por iniciar (W06) | Sequências anuais e política progressiva validadas; nove propriedades preservadas (W06.6). |
| P7 | Paragem, bounds e diagnósticos. | Por iniciar (W07) | Sem confusão entre local/global ou unknown/infeasible. |
| P8 | Fila, snapshots, cancelamento e publicação. | Concluída (W08) | Falhas e concorrência testadas com PostgreSQL real; ensaios de container completos em W10. |
| P9 | APIs e todos os consumidores escolares. | Concluída (W09) | Contratos e interface revistos; E2E executável pelo proprietário com a pilha local. |
| P10 | Corpus amplo, replays anuais, calibração, otimizações e workers. | Por iniciar (W10–W11) | Relatório reproduzível de qualidade versus recursos; decisão sobre agrupamento de salas e workers. |
| P11 | Remoção final do legado e release candidate. | Por iniciar (W12) | Gate local integral aprovado. |
| P12A | Validação Railway/Cloudflare. | Por iniciar (W13) | Baseline remota separada, integrações e recursos reais confirmados. |
| P12B | Merge, CI, limpeza de ensaio e ativação. | Por iniciar (W14) | Revisão publicada verificada e aceitação final. |

Remover chamadas e implementações antigas por fatia em W12, com consumidores e testes correspondentes.
Não manter duas implementações selecionáveis em produção.
Código antigo pode existir temporariamente na branch durante a construção, mas não integra a candidate W12.
Pesquisar referências em backend, frontend, migrations, testes, scripts e documentação antes de concluir a remoção.

Verificações a reutilizar, dentro do fluxo Docker local:

```text
node scripts/test.mjs setup --scope all
node scripts/test.mjs doctor --profile all
node scripts/test.mjs fast --scope all
node scripts/test.mjs integration
node scripts/test.mjs e2e --project app
node scripts/test.mjs all --scope all
node scripts/test.mjs campaign --manifest backend/tests/scheduler_lab/generation_manifest.json --mode generator
```

Manter Ruff, checks frontend, contratos, segurança, integridade e verificações Alembic aplicáveis.
Atualizar testes de contratos antigos; não preservá-los contrariando a nova baseline.
Recriar a imagem frontend após mudanças para que o teste manual use o código recente.

P0–P11 não executam testes, resets ou deployments Railway/Cloudflare.
CI GitHub pode verificar código sem deployment. Após cada push, acompanhar CI até passar.
W13 usa uma candidate identificada por commit e imagens; repetir configurações finalistas no hardware remoto.
Não transportar automaticamente a configuração vencedora do computador local para Railway.

Antes do corte final, impedir novos pedidos e terminar ou cancelar o job ativo.
Instalar a baseline limpa e verificar API, fila, geração, aprovação e frontend publicados.
Recuperar uma release apenas com artefactos compatíveis com a nova baseline.
Não definir rollback para o solver antigo como estratégia de recuperação da v1.

## 20. Rastreabilidade e entrega completa

| Decisões | Secções desta especificação | Evidência principal | Estado |
| :--- | :--- | :--- | :--- |
| D01–D02 | 1, 6, 19 | Instalação vazia, inventário e remoção de consumidores antigos. | Parcial; remoção na W12. |
| D03–D04 | 12, 17 | Exclusão global e comparação 1/2/4/8 workers. | Especificação W08/W11. |
| D05–D08 | 11, 17 | Trajetórias, limites, censura e paragem calibrada. | Etapas/certificados implementados; controlador na W07. |
| D09–D13 | 5, 8–10 | Oráculos de conclusão e cedência de capacidade. | Geração implementada; cedência na reparação W06. |
| D14–D18 | 4–5, 14 | Estabilidade, projeção e preservação de execução. | Implementado. |
| D19–D22 | 8–9 | Disponibilidade, carga densa, docente fixo e prioridade de furos. | Implementado. |
| D23–D26 | 7, 12–15 | Pedidos manuais, elegibilidade, 28 dias e snapshots. | Domínio implementado; fila W08. |
| D27–D28 | 4, 11, 16 | Diagnósticos sustentados e acertos conservativos. | Pré-verificação implementada; explicações W07. |
| D29–D30 | 14–15 | Aprovação atómica, E2E e revisão de linguagem. | Especificação W08–W09. |
| D31 | 17–19 | Gate local e relatório remoto separado. | Em vigor. |

A entrega inclui código, testes, corpus, manifests, relatórios e runbook de operação.
Inclui ainda parâmetros selecionados, limitações conhecidas e documentação atualizada dos contratos públicos.
Uma implementação que apenas encontra horários não satisfaz esta especificação.
A v1 só fica concluída quando contabilização, qualidade, operação e publicação estiverem demonstradas em conjunto.
