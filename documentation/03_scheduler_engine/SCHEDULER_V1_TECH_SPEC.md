# Especificação técnica — Cronos Scheduler v1

Data: 23 de setembro de 2026.

Estado: especificação da implementação futura. Este documento não descreve funcionalidades já implementadas.

Base: [plano de execução aprovado](SCHEDULER_V1_REVAMP_PLAN.md), decisões D01–D31 e fases P0–P12B.

Revisão analisada: `facd1d93bead7fc6ed481de6761644afd2e0be81`.
Branch: `codex/scheduler-v1-revamp`.

Execução detalhada: [WBS técnico e campanhas iterativas](SCHEDULER_V1_WBS.md).

## 1. Objetivo, autoridade e âmbito

Substituir o gerador, os seus contratos e os consumidores incompatíveis por uma nova baseline.
O resultado obrigatório é um horário completo, verificável e publicável mediante aprovação.
Uma proposta parcial nunca representa sucesso.

As decisões do plano prevalecem sobre os documentos da implementação anterior.
Esta especificação concretiza essas decisões. Não introduz compatibilidade com o solver antigo.
Os parâmetros experimentais têm critérios de seleção explícitos. Não constituem valores de produção já aprovados.

| Pergunta | Resposta técnica |
| :--- | :--- |
| O quê? | Domínio curricular, geração, recuperação, persistência, fila, APIs e consumidores coerentes com a nova v1. |
| Porquê? | Produzir horários completos com boas datas de conclusão, estabilidade controlada e contabilização correta. |
| Quem? | Implementação por quem executar este plano; validação funcional e aceitação pelo proprietário da aplicação. |
| Onde? | Docker local até P11; Railway e Cloudflare apenas em P12A, após o gate local. |
| Quando? | Pela ordem das dependências e evidências descritas na secção 19; sem prazos de desempenho inventados. |

Manter FastAPI, SQLAlchemy, PostgreSQL, Celery, Redis, React e OR-Tools já presentes.
Não adicionar microserviços, outro broker, framework de otimização ou modelo de aprendizagem automática.
As versões instaladas verificadas incluem Python 3.14.7, Celery 5.6.3 e OR-Tools 9.15.6755.
Os lockfiles e imagens fixadas prevalecem sobre versões exemplificadas em skills.

## 2. Fronteiras e estrutura de código

Reutilizar o pacote `backend/app/scheduler/`. Os nomes seguintes indicam responsabilidades concretas, não scaffolding obrigatório.

```text
backend/app/scheduler/
  domain/
    contracts.py         # Valores imutáveis e resultados tipados
    calendar.py          # Datas, períodos e fronteira de estabilidade
    demand.py            # Minutos residuais e reconciliação curricular
    projection.py        # Distribuição cronológica pelos módulos
    quality.py           # Comparador e métricas de produto
    validation.py        # Verificação independente de propostas
    eligibility.py       # Motivos para geração manual
  application/
    generation.py        # Coordenar um pedido autorizado
    approval.py          # Revalidar e publicar
    contracts.py         # Entradas/saídas dos casos de uso
  infrastructure/
    snapshot.py          # Leitura consistente e normalização
    persistence.py       # Transações, revisões e idempotência
    task_dispatcher.py   # Transporte Celery existente
    search.py            # Coordenação dos modelos e bairros
    annual_model.py      # Distribuição anual agregada
    placement_model.py   # Colocação temporal CP-SAT
    room_assignment.py   # Salas concretas e conflitos
    search_control.py    # Progresso, limites e paragem
```

Criar cada ficheiro apenas quando existir código que justifique a separação.
Não dividir módulos pequenos por convenção. Não criar repositórios genéricos ou factories para um único solver.

Dependências permitidas:

```text
API/Celery -> composição de dependências -> aplicação -> domínio
infraestrutura -------------------------------> domínio
```

O domínio recebe datas e instantes explicitamente. Nunca consulta relógio, base de dados ou variáveis de ambiente.
Usar dataclasses imutáveis, enums próprios, inteiros e coleções ordenadas.
Não transportar modelos ORM, `Any`, objetos CP-SAT ou sessões SQLAlchemy nos contratos de domínio.
A aplicação recebe funções/adaptadores concretos. Introduzir `Protocol` apenas numa fronteira com substituição real em testes ou execução.
O módulo de composição conhece a infraestrutura. A API não importa o solver.

O avaliador e o modelo partilham definições, mas não a implementação da validação.
O validador verifica blocos materializados. Não consulta variáveis ou restrições construídas pelo solver.

## 3. Vocabulário e contratos imutáveis

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
| `PlanningSnapshot` | Revisões, calendário, procura, execução, aulas publicadas, dívida e política fixada. |
| `CandidateSchedule` | Conjunto completo de aulas futuras, identidades preservadas e atribuições de salas. |
| `ValidationReport` | Validade, violações estruturadas e totais recalculados. |
| `QualityVector` | Componentes ordenadas, métricas auxiliares e versão da política. |
| `SearchEvidence` | Objetivo, âmbito, incumbente, limite, tolerância, tempo e motivo de fim. |

Identificadores mantêm o tipo nativo do projeto. Não converter IDs de negócio em índices CP-SAT fora do adaptador.
O solver utiliza índices densos internos e conserva um mapa explícito para os identificadores originais.

Unidades obrigatórias:

- Minutos curriculares e durações: inteiros; nunca `float` em conservação de horas.
- Datas escolares: `date` na timezone da escola.
- Instantes de auditoria: UTC com timezone.
- Durações de pesquisa: relógio monotónico.
- Intervalos físicos: semiabertos `[início, fim)`; aulas adjacentes não colidem.

Horários ambíguos ou inexistentes numa transição de timezone devem falhar na normalização.
Não corrigir silenciosamente períodos inválidos.

## 4. Procura, execução, dívida e módulos

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

A fórmula errada `procura = Q - E + dívida` fica proibida.
A dívida identifica parte dos minutos já incluídos em `R`.

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
Total físico = 150; total curricular = 150
```

Cancelar terça e repor quinta pode alterar o módulo previsto de quarta, sem mover quarta.
Essa alteração é permitida dentro da janela de estabilidade.
O diff distingue alteração física de atualização curricular.

Os factos executados conservam a evidência original e as parcelas confirmadas.
Um sumário atrasado ou uma correção retroativa nunca sobrescreve essa evidência.
Quando exigir redistribuição de créditos confirmados, produzir revisões compensatórias auditáveis na mesma transação.
A projeção efetiva usa a última revisão válida; relatórios históricos permitem recuperar as anteriores.
Não usar a previsão modular antiga como prova de execução.

### 4.3 Crédito parcial e duração variável

Uma aula de 30 minutos curriculares num período de 50 ocupa os 50 minutos físicos.
Não atribuir os 20 minutos restantes a outra disciplina, turma ou professor.
Não arredondar módulos individualmente.

Na geração inicial, preencher os períodos selecionados e permitir apenas a última aula parcial por atribuição.
Na reparação, preservar os créditos das aulas protegidas.
Para o restante, aplicar o mesmo preenchimento cronológico; conservar uma aula parcial publicada apenas quando a estabilidade o exige.
Se créditos protegidos excederem `R`, reportar conflito; não apagar execução ou alterar a janela silenciosamente.
Uma alteração administrativa incompatível deve expor o conflito antes de confirmar, sempre que já seja detetável.

Não assumir períodos universais de 50 minutos.
Os modelos agregados distinguem durações; o detalhe verifica a soma exata.

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
Criar dívida adicional apenas para crédito cancelado ainda não representado por uma dívida aberta.

Acertos positivos reconciliam dívida aberta por data de origem e identificador, salvo origem explicitamente indicada.
Acertos negativos revertem liquidações associadas quando existir essa relação.
Sem relação, aumentam procura residual sem inventar uma ocorrência histórica.
Guardar sempre as parcelas reconciliadas e o motivo.

Uma substituição por outra disciplina credita apenas a disciplina realmente lecionada.
Recalcular a cobertura futura de ambas as disciplinas.
Proibir crédito duplicado por sumário, substituição e recuperação sobre a mesma execução.

## 5. Calendário e estabilidade

Validar `start_date <= preferred_end_date <= hard_end_date`.
CompleteGeneration usa `preferred_end_date` como limite obrigatório.
AdaptiveRecovery usa `hard_end_date` e penaliza o excesso sobre a preferência.

Definir `grid_dates` como datas cujo dia da semana existe na grelha escolar.
Feriados impedem colocação, mas a contagem da janela segue os dias da grelha, conforme o plano.

```text
protected_dates = primeiras N grid_dates a partir de school_today, inclusive
editable_from = primeira grid_date depois dessas N datas
```

Com `N=0`, permitir apenas períodos ainda não iniciados.
Preservar sempre aulas executadas e passado, independentemente de `N`.
Uma data atual presente na grelha conta como primeiro dia protegido.

Proteger inserção, remoção, mudança de data, período, professor, sala, disciplina e crédito físico/curricular confirmado da aula.
A projeção modular futura constitui a exceção explícita, porque não altera a posição física.
Uma ocorrência pode registar que uma aula protegida não aconteceu; isso não autoriza o solver a reescrever esse passado.

A aprovação recalcula a fronteira com a data atual.
Uma proposta antes editável pode tornar-se inválida enquanto aguarda aprovação.
Não deslocar automaticamente alterações para outra data durante a aprovação.

## 6. Modelo de dados da nova baseline

Aplicar os nomes finais às convenções existentes. As relações e invariantes seguintes são obrigatórias.

| Entidade | Campos ou relações essenciais |
| :--- | :--- |
| Estado escolar do planeamento | Organização/ano únicos; revisões; versão ativa; última geração válida; motivos pendentes. |
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

Usar colunas relacionais para referências e valores sujeitos a integridade.
JSONB serve para snapshots imutáveis, relatórios e evidência de pesquisa.
Não esconder todas as regras num documento JSON mutável.

Constraints e índices mínimos:

- Chaves estrangeiras incluem organização quando necessário para impedir referências entre escolas.
- RLS em todas as tabelas escolares; sessão com organização explícita e role sem bypass.
- Índice único de idempotência por organização, origem e revisão.
- Um job não terminal por organização/ano; uma proposta corrente por organização/ano.
- Versão ativa única; aulas únicas por identidade dentro da versão.
- Índices de leitura por organização, ano, turma/data e professor/data.
- Durações positivas, créditos positivos e crédito não superior à ocupação física.
- Sem sobreposição física para turma, professor ou sala na versão publicada.

Com uma grelha global comprovadamente disjunta, a unicidade recurso/data/período é suficiente.
Se períodos diferentes puderem sobrepor-se, usar exclusão por intervalo ou mecanismo transacional equivalente testado.
Uma simples unicidade por `timeslot_id` não cobre esse caso.

Invariantes entre várias linhas são validadas pelo domínio dentro de transações serializadas pelo estado escolar.
Acrescentar constraints de base de dados onde expressáveis. Não duplicar o solver em triggers.

Criar uma baseline Alembic nova para instalação vazia.
Reconstruir RLS, grants, índices e triggers ainda necessários.
Não migrar dados de teste ou conservar colunas apenas para leitura pelo frontend antigo.
Inventariar identidades, autenticação e integrações externas antes do reset; não fazem parte de uma limpeza indiscriminada.

## 7. Snapshot, revisões e consistência

Manter duas revisões com finalidades distintas:

- `input_revision`: qualquer alteração que afete a validade de um snapshot, incluindo execução normal.
- `planning_revision`: alteração relevante que pode justificar uma nova geração manual.

Cada comando escolar bloqueia primeiro a linha de estado, altera dados e incrementa as revisões aplicáveis na mesma transação.
Atualizações sem efeito semântico não incrementam `planning_revision`.
Executar normalmente uma aula incrementa `input_revision`, mas não cria automaticamente motivo de regeneração.

O pedido grava as revisões e a versão ativa observadas.
Ao sair da fila, comparar esses valores antes de construir o snapshot.
Se diferirem, terminar como `STALE`; não iniciar um novo pedido automaticamente.

Construir o snapshot numa leitura consistente curta.
Guardar representação canónica com esquema versionado e digest SHA-256.
Ordenar coleções; incluir configuração, restrições, progresso, dívida, aulas e políticas relevantes.
Excluir nomes de apresentação sem impacto matemático.
Usar o digest para integridade/reprodução, não como substituto de transações e revisões.

Terminar a transação antes do solve.
Persistir a proposta apenas se revisões, versão ativa e token da tentativa continuarem válidos.
Uma escrita posterior ao snapshot permanece pendente e nunca é consumida pela geração antiga.

## 8. Modelo matemático de colocação

### 8.1 Conjuntos e elegibilidade

```text
A = atribuições turma/disciplina/professor
P = períodos concretos do calendário
R = salas concretas
K[a,p] = salas elegíveis para a em p
d[p] = duração física do período
x[a,p] ∈ {0,1} = atribuição colocada no período
```

Criar `x` apenas para combinações elegíveis.
Intersetar calendário, professor atribuído, turma, disponibilidade obrigatória e regras específicas.
Não criar o produto cartesiano anual atribuição × período × sala.
Preferências desfavoráveis mantêm a combinação elegível e acrescentam custo.
Não copiar limites de quatro aulas diárias, três consecutivas ou duas recuperações.
Manter intervalos de almoço e exclusões realmente configuradas.

Para cada recurso e conjunto de períodos fisicamente sobrepostos:

```text
soma(ocupações selecionadas e fixas) <= 1
```

Usar restrições por período quando a grelha é disjunta.
Usar intervalos ou cliques de sobreposição quando essa propriedade não existe.

### 8.2 Créditos sem arredondamento

Para a parte editável de cada atribuição, descontar primeiro créditos protegidos.
Se o residual editável for positivo, selecionar uma última colocação `l[a,p]`:

```text
l[a,p] ∈ {0,1}; l[a,p] <= x[a,p]
soma_p l[a,p] = 1
u[a,p] ∈ [0, d[p]-1]
u[a,p] <= (d[p]-1) * l[a,p]
credit[a,p] = d[p] * x[a,p] - u[a,p]
soma_p credit[a,p] = residual_editável[a]
```

Impor que nenhuma colocação selecionada ocorre depois de `l`.
Quando o residual for zero, todas essas variáveis são zero e não existe última colocação.
Identidades de aulas móveis são mapeadas depois, preservando correspondências físicas e curriculares possíveis.
Fixar primeiro correspondências exatas com a versão publicada.
Nas restantes, obter uma correspondência de custo mínimo dentro da mesma atribuição.
Usar esse custo no objetivo de reparação, diretamente ou numa avaliação externa consistente.
Não avaliar movimentos antes dessa correspondência, nem fabricar identidades novas para esconder perturbações.
Créditos de aulas protegidas ficam constantes; a projeção modular é calculada após materialização.

### 8.3 Planeador anual

Definir `q[a,w,d]` como número de períodos de duração `d` atribuídos à semana `w`.
Definir `f[a,w,d]` para o grupo que contém a última colocação e o respetivo desperdício `u`.

```text
q >= f; soma f = 1; 0 <= u[a,w,d] <= (d-1)*f[a,w,d]
soma(w,d)(d*q[a,w,d] - u[a,w,d]) = residual_editável[a]
nenhuma quota positiva depois da semana final selecionada
```

No detalhe, vincular quotas, grupo final, crédito parcial e ordem cronológica.
Usar capacidades necessárias por turma, professor e conjuntos de salas.
Descontar ocupações fixas e considerar interseções de disponibilidade.
Uma soma semanal suficiente não prova que as aulas cabem nos mesmos períodos disponíveis.

O planeador anual fornece distribuições candidatas e limites de relaxação.
O detalhe temporal certifica a realização de cada distribuição.
Guardar os resultados por semana e reabrir semanas afetadas por novas quotas.
Não congelar irrevogavelmente semanas anteriores.

### 8.4 Realimentação correta

Quando uma semana é demonstradamente impossível para uma quota, devolver um corte que exclua essa combinação.
O corte inclui todos os parâmetros dos quais depende: quotas, ocupações fixas, restrições e crédito final.
Começar por um no-good sobre a combinação inteira. Reduzir o conflito apenas com evidência suficiente.

Nunca produzir cortes a partir de timeout, solução parcial ou matching heurístico falhado.
Não excluir uma quota porque uma escolha anterior arbitrária ocupou o recurso necessário.
Reabrir essa escolha ou incluir explicitamente a condição no corte.
Ao mudar o snapshot, descartar cortes que não sejam válidos para os novos dados.

Para instâncias pequenas, manter um modelo exato de referência nos testes.
Comparar o resultado da decomposição com esse oráculo.
Esse modelo é uma implementação de teste, não um fallback legado em produção.

### 8.5 Salas

Agrupar apenas salas com elegibilidade realmente equivalente para o contexto.
Lotação, equipamento, reservas e restrições específicas participam na equivalência.
Não tratar duas salas como iguais apenas porque têm o mesmo tipo.

Após escolher posições, resolver o matching aula–sala por períodos disjuntos.
Para intervalos sobrepostos, resolver conjuntamente o componente temporal afetado.
Preservar salas publicadas e continuidade como objetivos subordinados.
Se não existir matching completo, devolver conflito ao modelo temporal.
Validar salas concretas antes de reconhecer uma solução completa.

## 9. Política de qualidade executável

### 9.1 Métricas comuns

`C[c]` é a última data necessária para concluir toda a procura da turma.
Incluir conclusão executada quando relevante; uma turma incompleta não recebe uma data fictícia.
Ordenar `C` por ordem decrescente: `C↓`.
Usar dias desde uma origem comum do snapshot; não números de semana com mudanças de ano.

Furos representam minutos escolares desocupados entre a primeira e última aula do recurso no dia.
Excluir almoço e períodos inexistentes na grelha.
Contar furos de professores antes dos das turmas.
Não tratar indisponibilidade obrigatória como uma violação de preferência; especificar no relatório a decomposição dos intervalos contados.

### 9.2 Geração inicial

Minimizar lexicograficamente:

```text
(C↓, minutos_de_furos_professores, minutos_de_furos_turmas,
 custo_preferências, custo_mudanças_de_sala)
```

Datas nunca ultrapassam a preferência na geração inicial.
Uma melhoria da conclusão mais tardia prevalece sobre estética ou soma das restantes datas.
Não atrasar uma turma apenas para igualar datas.

Usar objetivos sequenciais ou uma formulação equivalente verificada.
Não usar pesos gigantes sem prova de equivalência e limites de overflow.
Fixar um prefixo como ótimo apenas quando houver prova.
Um prefixo conservado heuristicamente limita a pesquisa, não certifica optimalidade global.

### 9.3 Recuperação: datas e perturbação

Definir `O[c] = max(0, C[c] - preferred_end_date)` e ordenar `O↓`.
Minimizar primeiro `O↓`, antes de qualquer perturbação do futuro editável.
Assim, reduzir excesso prevalece sobre conservar aulas móveis.
Nenhum objetivo permite atravessar o limite absoluto.

Dentro do mesmo vetor de excessos, usar uma função crescente convexa `g` até à preferência.
Os seus declives aumentam à medida que a margem desaparece.
Definir perturbação `D` por diferenças reais em relação à versão publicada:

```text
D = soma_por_aula(custo_tipo_alteração * urgência * reincidência)
```

Inserções, remoções, movimentos e mudanças de sala têm custos explícitos.
Contar cada transformação uma vez. Uma aula movida não é simultaneamente remoção e inserção.
Urgência aumenta junto da fronteira editável; reincidência depende de alterações anteriores auditadas.
Alteração apenas modular não aumenta perturbação física.

Formulação proposta para concretizar o compromisso do plano:

```text
B[i] = g(min(C↓[i], preferred_end_date)) + lambda * D
QualityAdaptive = (O↓, B[1], ..., B[n], C↓, D,
                   furos_professores, furos_turmas, preferências, salas)
```

Minimizar lexicograficamente. `lambda` é positivo; `g` usa coeficientes inteiros e declives estritamente positivos.
O mesmo `D` em cada componente permite comparar perturbação com a conclusão coletiva mais tardia primeiro.
Com perturbação igual, prevalece `C↓`. Com conclusões iguais, prevalece menor perturbação.
Perto da preferência, perder um dia custa mais do que perder esse dia com muita margem.
Depois da preferência, o vetor `O↓` impede trocar excesso por estabilidade.

Esta fórmula é uma decisão técnica sujeita à calibração P6–P10, não uma escala universal de qualidade.
Guardar `quality_policy_version`, coeficientes e exemplos de ordenação juntamente com cada benchmark.
Aceitar a fórmula apenas se passar os cenários T15–T18 do plano e simulações anuais reservadas.
Não escolher coeficientes numéricos antes desses ensaios.
Uma alteração da fórmula ou das prioridades exige atualizar especificação, oráculos e baseline.

Medir impacto incremental contra a versão anterior e acumulado contra a primeira aprovação.
O comparador usa a referência publicada do snapshot, nunca uma proposta intermédia da própria pesquisa.

## 10. Algoritmos de geração e recuperação

### 10.1 CompleteGeneration

```text
normalizar snapshot e compilar procura
verificar invariantes e condições necessárias de capacidade
construir distribuição anual candidata
resolver detalhe, salas e créditos; realimentar conflitos demonstrados
quando existir ano completo: validar e conservar incumbente
melhorar conclusão coletiva; depois objetivos subordinados
consultar controlador de pesquisa entre etapas e durante solves
validar novamente melhor resultado completo
persistir apenas com snapshot atual e tentativa autorizada
```

A primeira solução completa é um marco de pesquisa, não o critério automático de paragem.
Guardar incumbente fora do objeto solver para sobreviver ao encerramento de uma fase.
Não exportar callback com milhares de escritas na base de dados.

### 10.2 AdaptiveRecovery

Compilar residual contra execução efetiva e horário publicado.
Detetar falta de cobertura, excesso, recursos inválidos e alterações relevantes.
Começar por inserção e movimentos nos recursos afetados.
Expandir o bairro por conflitos entre professor, turma, sala e períodos.
Permitir cadeias entre semanas afastadas e cedência de capacidade entre turmas.

Manter blocos exteriores ao bairro como ocupações fixas, sem esquecer o seu custo global.
Recalcular conclusões e furos dos dias afetados com o contexto exterior incluído.
Comparar sempre candidatos pelo avaliador global do snapshot.
Não usar número do bairro, distância de expansão ou ordem de tentativa como prioridade de produto.

Se houver solução com excesso, procurar alternativas sem excesso antes de aceitar baixo retorno.
O controlador regista se essa exploração foi local ou global.
Impossibilidade num bairro apenas justifica expansão ou diagnóstico local.
Só uma prova válida para todo o espaço autorizado permite declarar impossibilidade do pedido.

## 11. Paragem, certificados e diagnóstico

### 11.1 Resultado tipado

Separar resultado, motivo de fim e existência de proposta:

| Resultado | Proposta | Significado |
| :--- | :--- | :--- |
| `COMPLETE` | Sim | Solução completa, validada e atual. |
| `INFEASIBLE` | Não | Impossibilidade demonstrada no âmbito integral aplicável. |
| `INCONCLUSIVE` | Não | Não existe solução completa nem prova de impossibilidade. |
| `CANCELLED` | Não | Cancelamento administrativo ganhou a corrida de finalização. |
| `STALE` | Não | Dados ou fronteira já não permitem finalizar aquela proposta. |
| `FAILED` | Não | Erro de execução, infraestrutura ou validação interna. |

Uma solução completa pode ter `stop_reason=SAFETY_LIMIT`.
Nesse caso, mostrar que a melhoria foi interrompida; não atribuir certificado inexistente.
Um erro do validador nunca é convertido em sucesso degradado.

### 11.2 Evidência matemática

Guardar objetivo exato, sentido, incumbente, limite, tolerância e âmbito.
Não transformar `OPTIMAL` de uma semana em prova do ano.
Não somar gaps locais para fabricar um gap global.
Para um vetor lexicográfico, indicar quais os prefixos certificados.
Tolerâncias nativas requerem registar os valores, além do status retornado.

Os estados CP-SAT e os campos de limites pertencem ao contrato do solver.
Verificar o comportamento na versão fixada antes de expor certificados. [Contrato oficial OR-Tools](https://github.com/google/or-tools/blob/stable/ortools/sat/cp_model.proto).

### 11.3 Controlo por retorno adicional

Entradas: trajetória de incumbentes, limites, esforço, bairros explorados e família de dificuldade.
Saídas: continuar, mudar bairro/fase ou finalizar com motivo explícito.

Começar com regras determinísticas, calibradas em trajetórias prolongadas:

1. Exigir solução completa antes de parar por qualidade suficiente.
2. Verificar exploração mínima dos objetivos superiores e recursos críticos.
3. Medir frequência e dimensão das melhorias numa janela de esforço.
4. Consultar ganhos posteriores observados em casos comparáveis do corpus de calibração.
5. Continuar quando existirem sinais úteis; terminar quando o ganho adicional esperado for pequeno.

Usar dias, alterações e furos para interpretar ganho; não uma percentagem inventada de perfeição.
Guardar a incerteza da estimativa empírica. Não prometer prever a próxima melhoria.
Instâncias fora das famílias calibradas não recebem confiança artificial.
Nesses casos, usar exploração conservadora até certificado ou limite de segurança documentado.

Nenhum p95, global ou por bloco, entra na regra de paragem.
Os limites de segurança são finitos, configurados por ambiente e versionados nos ensaios.
Cobrem construção, solve, memória e finalização; não apenas o tempo dentro de CP-SAT.
Reservar tempo de validação/persistência com base em medições.

### 11.4 Diagnóstico

Pré-verificações podem provar défices necessários de capacidade.
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
“Rever horas registadas” significa corrigir execução real ou trabalho reconhecido pela escola.
Nunca recomendar inventar horas para satisfazer o solver.
Não prometer que aumentar a data resolve um conflito de professor ou sala sem validar essa hipótese.

## 12. Fila global e execução operacional

Uma réplica do serviço solver; Celery com concorrência um e prefetch um.
Um job pode configurar `num_search_workers` com vários workers CP-SAT.
Não executar várias janelas simultâneas na v1; primeiro medir o paralelismo interno do solver.

Pedidos têm ordem FIFO persistida na base de dados.
A mensagem Celery acorda o executor; a base de dados decide o próximo pedido elegível.
O acesso global à fila limita-se aos metadados operacionais necessários para escolher o pedido.
Carregar dados escolares apenas depois de estabelecer a organização desse pedido e a respetiva sessão RLS.
Não desativar RLS globalmente para permitir FIFO entre escolas.
Uma entrega duplicada não cria nova execução.
Não depender da ordem acidental das mensagens Redis para garantir FIFO após retries.

Usar advisory lock global numa ligação PostgreSQL dedicada durante a execução.
Não manter uma transação de escrita aberta durante o solve.
Locks de sessão exigem libertação explícita e não desaparecem por rollback. [Documentação PostgreSQL 16](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS).

Cada claim incrementa `attempt_token`; todas as escritas de resultado verificam esse token.
Heartbeat e cancelamento usam uma ligação distinta e continuam durante o solve.
O controlador chama a interrupção suportada pelo solver quando necessário.
Um supervisor do processo cobre também bloqueios na construção e finalização, fora dos callbacks CP-SAT.
O limite extremo pode terminar o processo; a recuperação não depende de esse processo escrever o estado final.
Não colocar a única tarefa de cancelamento atrás do job que se pretende cancelar.

Perder a ligação do lock exige parar o processo de cálculo.
Um token impede escrita antiga, mas não prova que o CPU antigo parou.
Não assumir takeover seguro apenas porque expirou um heartbeat.
Na v1, usar recuperação conservadora: confirmar terminação do processo anterior antes de iniciar outro solver.
Deployments usam stop-before-start; não permitir sobreposição de réplicas de cálculo.
Testar esta propriedade com interrupções reais de processo e ligação.

No arranque, reconciliar jobs abandonados antes de consumir novos pedidos.
Falhas de dispatch deixam o pedido recuperável.
Reenviar o mesmo pedido autorizado é permitido; criar uma nova geração sem ação administrativa não é.
Usar o próprio registo de job e `dispatch_pending`; não introduzir um outbox genérico sem outra necessidade.

## 13. Elegibilidade e máquina de estados

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

Elegibilidade exige ausência de job ativo e pelo menos uma condição:

- Primeira geração ainda sem proposta completa para o mesmo estado.
- Alteração relevante não coberta pela última proposta completa.
- Tentativa anterior sem resultado completo.
- Passaram 28 dias corridos desde `last_successful_generation_at`.

Contar os 28 dias pela data local da escola, mantendo também o instante UTC auditável.
Persistir proposta completa e atualizar o relógio na mesma transação.
Aprovação e rejeição não reiniciam o relógio.
Uma rejeição sem mudança de dados não cria motivo novo.
Revalidar motivos ao submeter; o frontend não é a autoridade de elegibilidade.

## 14. Transações de proposta e aprovação

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

## 15. API e adaptação do frontend

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

Exemplo de resumo público:

```json
{
  "can_generate": false,
  "reason": "PROPOSAL_READY",
  "message": "A proposta está pronta para revisão.",
  "preferred_end_date": "2027-06-11",
  "hard_end_date": "2027-06-30",
  "classes_after_preferred_end": 2,
  "search_interrupted": false
}
```

O frontend traduz códigos estáveis; não interpreta texto para decidir comportamento.
Mostrar fila, preparação, organização, melhoria e revisão como fases compreensíveis.
Mostrar alerta persistente enquanto houver conclusão depois da preferência.
Separar dívida aberta, recuperação planeada e horas efetivamente cumpridas.
Atualizar detalhe de turma, calendário, mapas, sumários e relatórios para múltiplas parcelas modulares.
Preservar acessibilidade, navegação por teclado e erros junto dos campos.

## 16. Validador independente e estratégia TDD

### 16.1 Verificações obrigatórias

O validador recebe snapshot e candidato, sem acesso à construção do modelo.
Recalcula:

1. Cobertura exata por atribuição e conservação de minutos.
2. Unicidade de identidade e integridade das referências.
3. Colisões físicas de turma, professor e sala.
4. Elegibilidade, disponibilidade, calendário e limites de datas.
5. Preservação histórica e janela de estabilidade.
6. Parcelas modulares sem lacunas ou sobreposição curricular.
7. Reservas de dívida sem dupla liquidação.
8. Métricas de conclusão, perturbação e furos.

Indexar por recurso/data e ordenar intervalos; evitar comparação quadrática de todas as aulas anuais.
Guardar versão do validador e digest do candidato aprovado.
Métricas declaradas pelo solver nunca substituem métricas recalculadas.

### 16.2 Ciclo TDD por fatia

Escrever primeiro um exemplo observável que falha.
Implementar a menor regra correta e refatorar após verde.
Testes de domínio usam apenas valores; não precisam de mocks ORM ou solver.
Testes de transação usam PostgreSQL real no Docker local, não SQLite.
Testes CP-SAT verificam validade e qualidade, não sequências exatas de callbacks.

| Grupo | Casos mínimos e oráculo |
| :--- | :--- |
| Currículo | 75+75/50; aula cruza três módulos; minutos parciais; durações heterogéneas. |
| Progresso | Crédito único, reversão, sumário atrasado, acerto positivo/negativo e limites. |
| Dívida | Uma dívida em várias aulas; várias dívidas numa aula; cancelar recuperação sem duplicação. |
| Estabilidade | Grelhas de 3/5/7 dias; N=0; feriado; data atual; aprovação posterior. |
| Recursos | Mesmo professor em turmas distintas; salas específicas; intervalos sobrepostos; preferência soft. |
| Capacidade | Semana agregada suficiente com períodos conjuntos insuficientes. |
| Qualidade inicial | Oráculo enumerado com vetor de conclusões, não soma de datas. |
| Qualidade adaptativa | Ceder recursos à turma atrasada; estabilidade versus margem; excesso domina perturbação. |
| Diagnóstico | Impossível conhecido; bairro impossível mas global viável; timeout sem prova. |
| Ciclo de vida | Duplo clique, entrega duplicada, dados alterados em fila/solve/aprovação. |
| Recuperação operacional | Processo morto, lock perdido, dispatch falhado, cancelamento durante validação. |
| Isolamento | Consultas e FKs entre escolas; role RLS real; org do cliente ignorada. |
| UI/E2E | Configurar → gerar → aprovar → ocorrência → reparar → executar → acertar → renovar. |

Acrescentar propriedades metamórficas:

- Renomear entidades não altera viabilidade ou qualidade.
- Acrescentar disponibilidade não pode tornar inviável uma solução anteriormente válida.
- Aumentar procura não cria créditos executados.
- Repetir um comando idempotente não altera totais.
- Permutar a ordem de entrada não altera o comparador.
- Inserir perturbações durante o ano preserva as equações em cada passo.

Para casos minúsculos, enumerar soluções e obter o ótimo verdadeiro.
Para casos grandes, usar testemunhos válidos, limites e comparações, sem declarar ótimo desconhecido.
Mapear os testes aos T01–T30 do plano; nenhum caso anterior desaparece por existir esta tabela.

### 16.3 Loops experimentais obrigatórios

Executar as campanhas C01–C20 do [WBS](SCHEDULER_V1_WBS.md) durante a implementação, não apenas antes do lançamento.
Cada campanha encadeia baseline, mutação controlada, aumento de pressão e recuperação.
Executar, validar e analisar outputs entre cada alteração.
Uma falha exige reprodução, redução do caso, teste vermelho, correção e repetição dos cenários afetados.

Separar experiências isoladas de simulações longitudinais.
Nas primeiras, restaurar a baseline para comparar causas.
Nas segundas, aplicar eventos ao estado aprovado anterior e validar cada transição.
Alterar cenário, configuração de pesquisa e código em passos identificáveis.
Não substituir fixtures antigas nem eliminar resultados desfavoráveis.

Cada caso declara expectativa: viável com testemunho, impossível demonstrado, input inválido ou exploratório sem viabilidade conhecida.
Testar o validador com candidatos deliberadamente adulterados.
Um timeout num caso viável conhecido é insuficiência de pesquisa, não prova de impossibilidade.

## 17. Corpus, benchmarks e seleção de parâmetros

### 17.1 Artefactos reproduzíveis

Guardar fixtures canónicas pequenas no repositório e gerar as maiores por seeds fixas.
Cada caso inclui versão do schema, gerador, seed, características e testemunho ou prova quando disponível.
Separar treino/calibração, comparação e conjunto reservado por topologia, não apenas por seed.

Cobrir 10, 30, 45 e 60 turmas, partilha docente, salas escassas e calendários restritos.
Incluir reparações de 1h, 10h e 50h com diferentes distribuições de conflito.
Simular sequências anuais: ausências prolongadas, substituições, acertos e alterações acumuladas.
“50h” não é uma categoria de dificuldade suficiente sem número de recursos e dispersão temporal.

Explorar pouca/muita procura com pouco/muito espaço efetivamente elegível.
Incluir capacidade exata, um minuto além, conflitos de interseção e abundância de alternativas equivalentes.
Medir disponibilidade conjunta de turma, professor atribuído, sala, período e fronteira editável.
Não usar apenas buracos da turma ou somas agregadas como capacidade disponível.

Variar escassez e abundância de docentes e salas, separando recursos úteis de recursos sem elegibilidade.
Professores adicionais sem atribuições não aumentam capacidade curricular automaticamente.
Uma escola pode reatribuir disciplinas explicitamente; o solver não distribui serviço docente.
Variar curto, médio e longo prazo, estabilidade, calendário e proximidade das datas finais.

Cobrir níveis isolados, pares válidos e interações críticas de três ou mais fatores.
O manifesto declara combinações excluídas e razões; o relatório mede cobertura executada.
Não exigir o produto cartesiano integral nem considerar cobertura por pares suficiente para todas as interações.

Executar replays anuais tranquilos, irregulares, com crises concentradas e próximos da saturação.
Validar minutos, recursos, estabilidade e dívida após cada evento e aprovação.
Se o ano se tornar impossível, exigir diagnóstico e intervenção administrativa explícita para continuar.
Quantidades e protocolo inicial de repetição constam do WBS; não equivalem a metas de desempenho.

### 17.2 Medições por execução

```text
commit, image_digest, fixture_digest, seed, policy_version
CPU/modelo/quota, RAM/limite, sistema, versões, workers
queue_wait, snapshot_time, build_time, first_complete_time
search_time, validation_time, persistence_time, total_processing_time
peak_RSS, CPU_seconds, candidate_count, model_variables, model_constraints
complete_valid, outcome, stop_reason, objective_vector
bounds_with_scope, trajectory, changed_lessons, class_completion_dates
```

Separar espera na fila de processamento.
Guardar falhas, OOM e censura; não excluir execuções difíceis para melhorar o p95.
Publicar tamanho da amostra e incerteza; amostras pequenas não sustentam um p95 estável.
Não misturar Docker local e Railway na mesma baseline.

O benchmark existente em `scripts/test.mjs` mede duração de suites.
Acrescentar um modo específico para corpus do solver, reutilizando o runner e os containers.
Não tratar cinco execuções de testes como benchmark de qualidade de horários.
Documentar a sintaxe nova quando implementada; comandos futuros não são comandos já disponíveis.

### 17.3 Protocolo de comparação

Fixar fixture, hardware, política, versões e limites de segurança.
Intercalar ordem das configurações para reduzir efeito de aquecimento ou carga externa.
Executar várias seeds do solver; uma seed não elimina não determinismo multithread.
Registar warmup separado e conservar todas as execuções medidas.

Comparar primeiro validade e taxa de conclusão.
Depois comparar o vetor de qualidade, a trajetória e recursos consumidos.
Evitar uma média única que esconda regressões nas escolas mais difíceis.
Traçar a fronteira qualidade/tempo/CPU/RAM e identificar configurações dominadas.

Executar 1, 2, 4 e 8 workers internos, respeitando os limites do host.
Testar mais apenas se o hardware e os resultados justificarem.
Não confundir oito workers com oito cores garantidos.
Selecionar a configuração com ganhos sustentados e custo aceitável, não apenas menor wall time.

### 17.4 Calibração da paragem

Executar trajetórias prolongadas apenas no laboratório com limites finitos.
Reproduzir offline as decisões de paragem candidatas.
Medir tempo poupado e melhorias relevantes perdidas depois da paragem simulada.
Avaliar no conjunto reservado antes de fixar a política.
Comparar casos como 91/3min, 94/7min e 97/45min através das métricas reais, não desses números ilustrativos.

Parâmetros a fechar por evidência: declives de `g`, `lambda`, custos de perturbação, exploração mínima e limiar de retorno.
Também fechar workers, limites de segurança e reserva de finalização.
Nenhum destes campos recebe um default silencioso de produção.
O manifesto de ensaio exige valores explícitos e identifica-os como experimentais até aceitação.

### 17.5 Evidência e prevenção de sobreajuste

Guardar IDs de campanha/caso, versão, cenário pai, mutação e seeds de fixture, eventos e solver separadas.
Associar cada resultado ao commit, política, hardware, limites e digest dos inputs.
Preservar sequência de eventos, validação independente e análise da próxima ação.
Reutilizar o runner existente e `.test-artifacts/`; começar com manifests e resultados em JSON/JSONL.

Registar falhas de pesquisa separadamente de erros de domínio, fixtures incorretas e impossibilidades reais.
Após correção, repetir o caso mínimo, a família de origem e as famílias afetadas pela mesma regra.
Uma alteração arquitetural ou de política exige nova comparação ampla antes do gate.

Se resultados reservados influenciarem alterações, promovê-los a regressões conhecidas.
Criar avaliação reservada nova para a candidate seguinte.
Nenhuma repetição ou seed isolada garante determinismo multithread ou validade estatística do p95.

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
- Política de paragem avaliada em casos reservados e parâmetros documentados.
- Campanhas C01–C20 concluídas nos casos obrigatórios, com análise entre mutações e replays anuais completos ou corretamente diagnosticados.
- Matriz de cobertura, regressões reduzidas e resultados inconclusivos incluídos no dossier; nenhum caso omitido silenciosamente.
- Instalação vazia, reset e recuperação de falhas ensaiados localmente.
- Frontend e consumidores sem dependência dos contratos antigos.
- Aceitação funcional do proprietário com resultados concretos.

Os limites quantitativos de regressão de qualidade e custo são fixados após a primeira baseline mensurada.
Antes disso, exigir publicação integral das diferenças; não declarar aprovação por thresholds inventados.
Uma exceção deve nomear casos afetados, impacto e decisão. Não ocultar falhas num score médio.

## 19. Sequência de implementação e remoção

| Fase do plano | Entrega técnica | Condição para avançar |
| :--- | :--- | :--- |
| P0 | Inventário de consumidores, serviços e deployments; manifests locais. | Nenhum ensaio aciona cloud automaticamente. |
| P1 | Contratos, calendário, ledger, procura, projeção e comparador. | Testes de domínio e contraexemplos verdes. |
| P2 | Schema novo, baseline Alembic, RLS e constraints. | Instalação vazia e invariantes transacionais demonstradas. |
| P3 | Validador, oráculos, fixtures e medição. | Distingue soluções inválidas e mede métricas independentemente. |
| P4 | Planeador anual, detalhe e salas. | Produz soluções completas corretas em todo o corpus obrigatório. |
| P5 | Conclusões coletivas e objetivos subordinados. | Comparação com ótimos pequenos e baseline mensurada. |
| P6 | Reparação, bairros, dívida e estabilidade. | Sequências anuais e política progressiva validadas. |
| P7 | Paragem, bounds e diagnósticos. | Sem confusão entre local/global ou unknown/infeasible. |
| P8 | Fila, snapshots, cancelamento e publicação. | Falhas e concorrência testadas em containers reais. |
| P9 | APIs e todos os consumidores escolares. | E2E completo e linguagem de produto revista. |
| P10 | Calibração, otimizações e workers. | Relatório reproduzível de qualidade versus recursos. |
| P11 | Remoção final do legado e release candidate. | Gate local integral aprovado. |
| P12A | Validação Railway/Cloudflare. | Baseline remota separada, integrações e recursos reais confirmados. |
| P12B | Merge, CI, limpeza de ensaio e ativação. | Revisão publicada verificada e aceitação final. |

Remover chamadas e implementações antigas por fatia, com consumidores e testes correspondentes.
Não manter duas implementações selecionáveis em produção.
Código antigo pode existir temporariamente na branch durante a construção, mas não integra a candidate P11.
Remover campos de módulo singular, tetos implícitos, fallbacks, flags e documentação obsoleta.
Pesquisar referências em backend, frontend, migrations, testes, scripts e documentação antes de concluir a remoção.

Verificações existentes a reutilizar, dentro do fluxo Docker local:

```text
node scripts/test.mjs setup --scope all
node scripts/test.mjs doctor --profile all
node scripts/test.mjs fast --scope all
node scripts/test.mjs integration
node scripts/test.mjs e2e --project app
node scripts/test.mjs all --scope all
```

Acrescentar os benchmarks novos ao mesmo runner quando implementados.
Manter Ruff, checks frontend, contratos, segurança, integridade e verificações Alembic aplicáveis.
Atualizar testes de contratos antigos; não preservá-los contrariando a nova baseline.
Recriar a imagem frontend após mudanças para que o teste manual use o código recente.

P0–P11 não executam testes, resets ou deployments Railway/Cloudflare.
CI GitHub pode verificar código sem deployment. Após cada push, acompanhar CI até passar.
P12A usa uma candidate identificada por commit e imagens; repetir configurações finalistas no hardware remoto.
Não transportar automaticamente a configuração vencedora do computador local para Railway.

Antes do corte final, impedir novos pedidos e terminar ou cancelar o job ativo.
Instalar a baseline limpa e verificar API, fila, geração, aprovação e frontend publicados.
Recuperar uma release apenas com artefactos compatíveis com a nova baseline.
Não definir rollback para o solver antigo como estratégia de recuperação da v1.

## 20. Rastreabilidade e entrega completa

| Decisões | Secções desta especificação | Evidência principal |
| :--- | :--- | :--- |
| D01–D02 | 1, 6, 19 | Instalação vazia, inventário e remoção de consumidores antigos. |
| D03–D04 | 12, 17 | Exclusão global e comparação 1/2/4/8 workers. |
| D05–D08 | 11, 17 | Trajetórias, limites, censura e paragem calibrada. |
| D09–D13 | 5, 8–10 | Oráculos de conclusão e cedência de capacidade. |
| D14–D18 | 4–5, 14 | Estabilidade, projeção e preservação de execução. |
| D19–D22 | 8–9 | Disponibilidade, carga densa, docente fixo e prioridade de furos. |
| D23–D26 | 7, 12–15 | Pedidos manuais, elegibilidade, 28 dias e snapshots. |
| D27–D28 | 4, 11, 16 | Diagnósticos sustentados e acertos conservativos. |
| D29–D30 | 14–15 | Aprovação atómica, E2E e revisão de linguagem. |
| D31 | 17–19 | Gate local e relatório remoto separado. |

A entrega inclui código, testes, corpus, manifests, relatórios e runbook de operação.
Inclui ainda parâmetros selecionados, limitações conhecidas e documentação atualizada dos contratos públicos.
Uma implementação que apenas encontra horários não satisfaz esta especificação.
A v1 só fica concluída quando contabilização, qualidade, operação e publicação estiverem demonstradas em conjunto.
