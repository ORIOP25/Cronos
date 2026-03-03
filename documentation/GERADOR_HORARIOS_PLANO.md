# Horário Zen — Plano de Implementação do Gerador de Horários
**Documento de Arquitetura e Contexto de Negócio**
*Versão 1.5 — Atualizado em Março de 2026 com decisões Q15-Q21: Página de Configurações existente, archival de Turmas Antigas (5 anos), imutabilidade total do passado, estado vazio com call-to-action, OrganizationSettings por (org_id, academic_year)*

---

## PARTE 1 — CONTEXTO DE NEGÓCIO (O "Porquê")

### 1.1 A Diferença Fundamental: Ensino Regular vs. Ensino Profissional

No **Ensino Regular**, o horário é essencialmente estático:
- O Ministério define que o ano começa a X e acaba a Y.
- "Matemática é sempre à segunda às 9h" — o mesmo bloco, todas as semanas, durante todo o ano.
- O professor não tem módulos para completar; tem um programa que segue ao seu ritmo.

No **Ensino Profissional**, o paradigma é radicalmente diferente:
- O ano letivo **não tem data de fim fixa**. As aulas terminam quando todas as horas de todos os módulos forem dadas. Pode acabar em Maio, pode acabar em Agosto.
- Uma Disciplina é composta por **Módulos (UFCDs)**, cada um com um número fixo de horas (ex: M1 = 25h, M2 = 50h).
- O aluno é avaliado **por Módulo**, não por Disciplina. Sem M1 aprovado, não avança para M2.
- Os Módulos são **sequenciais dentro de uma Disciplina**: M1 tem de estar 100% terminado antes de M2 começar.
- Uma Turma pode ter, por exemplo, 8 Disciplinas a decorrer em simultâneo. O horário é uma grelha que distribui os blocos dessas 8 disciplinas ao longo das semanas.

### 1.2 O Ciclo de Vida de um Horário

O horário **nunca é final**. É sempre uma projeção do presente até ao fim do ano:

```
Início do Ano         Hoje                   Fim Projetado
     |                  |                         |
     |--[horas dadas]----|--[horário a gerar]------|
     |     (passado)     |        (futuro)          |
     |                  |                         |
                   ClassProgress              Data de Fim
                   (o que já foi dado)        (objetivo a minimizar)
```

**Fluxo real:**
1. Diretor preenche toda a informação no início do ano (Turmas, Professores, Salas, Cursos, Datas de pausas letivas).
2. O sistema gera um **horário completo para o ano todo**.
3. À medida que as aulas decorrem, o `ClassProgress` vai sendo atualizado (horas dadas por módulo).
4. Um professor falta. O sistema regista a substituição (ou o furo).
5. O sistema **regenera o horário do zero**, mas agora só para o período que falta. As horas já dadas estão no `ClassProgress` e não precisam de ser reagendadas.
6. A nova geração produz uma nova **data de fim projetada** para cada turma.
7. Processo repete-se dezenas ou centenas de vezes ao longo do ano.

### 1.3 O Problema das Faltas e Substituições

**Caso 1 — Furo Simples:**
O professor de Matemática falta. Não há substituto. A turma fica com um furo. As horas ficam em atraso. A data de fim de Matemática empurra-se para a frente.

**Caso 2 — Substituição Interna:**
O professor de Marketing tem disponibilidade. Vai à turma e dá horas de **Marketing** (não de Matemática). A turma não fica com um furo, mas:
- Marketing avança mais rápido do que o planeado.
- Matemática continua em atraso.
- O `ClassProgress` de Marketing avança; o de Matemática não.
- O desequilíbrio entre disciplinas aumenta.

> **Regra de Negócio Crítica:** Uma turma **só pode ter aulas com um professor que esteja assignado a essa turma**. Não existe um "professor substituto externo". A substituição é sempre interna — outro professor da mesma turma cobre com horas da sua própria disciplina.

**Consequência do desequilíbrio:**
- Sem correção ativa, Marketing pode acabar em Abril e Matemática em Setembro.
- Isto é mau: o professor de Marketing fica sem turma durante meses; os alunos têm uma carga horária absurda no final do ano.
- **Objetivo do gerador:** minimizar o desvio entre as datas de fim de todas as disciplinas de todas as turmas. Idealmente todas acabariam no mesmo dia; na prática, 1 mês de diferença entre a primeira e a última disciplina é expectável e aceitável dada a natureza do Ensino Profissional. A minimização do makespan é uma **consequência natural** de minimizar o desvio — quando todas as disciplinas avançam uniformemente, o ano acaba o mais cedo possível.

### 1.4 Princípio da Geração Escolar Completa

> **Regra Operacional Crítica:** O horário é sempre gerado para **a escola como um todo**, nunca para uma turma isolada.

A razão é matemática: modificar a turma A obriga o solver a realocar professores e salas, o que cria um efeito cascata que afeta as turmas B, C e D que partilham os mesmos recursos. Gerar apenas para a turma A produziria um horário local ótimo mas globalmente inválido ou sub-ótimo. O solver recebe todas as turmas de todas as organizações ativas e encontra o equilíbrio global.

---

## PARTE 2 — O PROBLEMA DE OTIMIZAÇÃO (O "Quê")

### 2.1 Formulação do Problema

Este é um problema clássico de **Scheduling com Múltiplos Recursos e Minimização de Makespan**. Na literatura académica é chamado de **RCPSP (Resource-Constrained Project Scheduling Problem)** com variante multi-projeto.

**Recursos:**
- Salas (capacidade, tipo: informática, laboratório, sala normal)
- Professores (disponibilidade, horas contrato)
- Turmas (não podem estar em dois sítios ao mesmo tempo)
- Tempo (grelha de timeslots: dias × horas)

**Tarefas (Jobs):**
- Cada Módulo de cada Disciplina de cada Turma é uma tarefa com duração fixa (ex: M1 de Matemática da Turma A = 25h = ~12 blocos de 2h).
- As tarefas têm **precedência**: M2 só pode começar depois de M1 estar 100% completo.
- No momento da regeneração, uma tarefa pode estar **parcialmente completa** (ex: M1 tem 15h dadas, faltam 10h).

**Variável de Decisão:**
Para cada (Turma, Disciplina, Módulo, Timeslot) → `está agendado? [0/1]`

**Restrições Rígidas (Hard Constraints):**
1. Nenhuma sala tem mais de uma turma ao mesmo tempo.
2. Nenhum professor está em dois sítios ao mesmo tempo.
3. Nenhuma turma está em dois sítios ao mesmo tempo.
4. Os módulos são sequenciais — M2 não pode ter nenhum bloco agendado antes de M1 atingir `hours_total`.
5. As pausas letivas (feriados, férias, exames) são blocos proibidos.
6. Cada professor só pode dar aulas nos dias e horas em que tem disponibilidade (já registada em `TeacherAvailability`).
7. **Um professor não pode dar mais de 15 horas por semana a uma turma específica.** Esta é uma hard constraint — o solver nunca viola este limite, mesmo em modo de reparação com muitas faltas acumuladas. O raciocínio é que quando o Professor B substitui A regularmente, o `ClassProgress` de B avança aceleradamente. O solver, na próxima regeneração, vai naturalmente "frear" B e tentar recuperar A para reequilibrar. Com o limite de 15h/semana, este reequilíbrio tem margem operacional: B não pode ter 30h numa semana para compensar, e A não pode ter 0h indefinidamente.

**Restrições Suaves (Soft Constraints — com peso/penalidade):**
| Prioridade | Restrição | Penalidade |
|---|---|---|
| P1 | Professor preferiu não dar aulas neste horário | Baixa |
| P2 | Turma tem "furo" (bloco vazio entre aulas) | Média |
| P3 | Disciplinas terminam em datas muito diferentes | Alta |
| P4 | Aulas da mesma disciplina estão distribuídas irregularmente na semana | Baixa |

**Função Objetivo:**
```
Minimizar:
  α × Desvio entre datas de fim das disciplinas (dentro de cada turma e entre turmas)
  + β × Penalidade/Recompensa face à data-alvo (school_target_end_date)
  + γ × Soma das penalidades das soft constraints
```

Onde `α >> β >> γ`.

**Formulação do desvio:**
Para cada turma, calculamos o desvio entre a data de fim de cada disciplina e a média das datas de fim de todas as disciplinas dessa turma:
```
Desvio(turma) = sum(|end_date(disciplina_i) - mean_end_date(turma)|)
Desvio_total = sum(Desvio(turma) for all turmas)
```

**Formulação da penalidade/recompensa face à data-alvo:**
O `school_target_end_date` é definido pelo diretor nas configurações da escola (ex: 15 de junho). O solver calcula:
```
δ = makespan_index - target_day_index  (ambos em índice de dias desde o início do ano)

Se δ < 0 (acabou ANTES do alvo): recompensa (contribuição negativa para o objetivo)
Se δ > 0 (acabou DEPOIS do alvo): penalidade (contribuição positiva para o objetivo)
Se δ = 0 (acabou exatamente no alvo): neutro

O CP-SAT trata isto nativamente em aritmética inteira:
  β × δ  (negativo = bom, positivo = mau)
```
Esta formulação incentiva acabar antes do alvo e penaliza cada dia extra após o alvo, mas NUNCA torna o problema insolúvel — o solver sempre encontra solução (ver secção INFEASIBLE abaixo).

**Impossibilidade de INFEASIBLE neste domínio:**
Ao contrário de scheduling clássico, este sistema **nunca pode ser verdadeiramente infeasible**. Se um professor só tem 8h de disponibilidade por semana e a turma precisa de 20h dele, as restantes 12h vão para a semana seguinte. O ano letivo simplesmente acaba mais tarde. A única causa real de INFEASIBLE seria um erro de dados (ex: professor com 0h de disponibilidade para o ano todo). Esses casos são apanhados pela **pré-validação** antes de o solver correr (ver 3.5), nunca durante.

### 2.2 Por Que CP-SAT e Não Outro Algoritmo

| Abordagem | Prós | Contras | Veredicto |
|---|---|---|---|
| Heurísticas (greedy) | Rápido | Não garante ótimo; difícil de adicionar constraints | Rejeitado |
| Algoritmos Genéticos | Flexível | Lento; difícil de garantir hard constraints | Rejeitado |
| ILP (CPLEX, Gurobi) | Ótimo garantido | Licença paga; mais lento que CP-SAT em scheduling | Rejeitado |
| **OR-Tools CP-SAT** | Ótimo garantido; gratuito; nativo em Python; excelente em scheduling; já em `requirements.txt`; suporta repair scheduling nativamente com variáveis fixadas | Pode demorar em instâncias muito grandes | **Escolhido** |

**CP-SAT é ideal porque:**
- Softwares como Google Maps, DPDHL, e Air France usam CP-SAT para scheduling real.
- Suporta nativamente a fixação de variáveis (`solver.Add(var == 1)`) — essencial para Repair Scheduling.
- O modelo matemático é declarativo: adicionamos constraints sem reescrever o algoritmo.
- Obj. de minimização de makespan é trivial de expressar: `solver.Minimize(makespan_var)`.

---

## PARTE 3 — ARQUITETURA TÉCNICA (O "Como")

### 3.1 Stack e Componentes Existentes

```
Backend (já existe)                    Frontend (já existe)
├── FastAPI                            ├── React 19 + Vite
├── SQLAlchemy Async                   ├── CoreUI
├── PostgreSQL                         ├── React Query (TanStack v5)
├── Celery + Redis (wired)             ├── Zustand (auth store)
└── OR-Tools CP-SAT (em requirements)  └── Axios (apiClient.js)
```

### 3.2 Modelo de Dados — Estado Real (Após Auditoria ao Código)

> **⚠️ A nomenclatura do modelo atual é enganosa.** Após auditoria ao `models.py`, o modelo real é:

```
MODELOS EXISTENTES (estado atual)
├── Organization         → Tenant isolation
├── Course               → Plano curricular do curso
├── Subject              → Disciplina (tem required_room_type)
├── Module               → Módulo/UFCD (tem hours_total, order)
├── Class (Turma)        → Instância de um curso (tem start_year, end_year)
├── ClassSubjectLink     → Professor assignado a uma Disciplina de uma Turma
├── ClassProgress        → Horas completadas por Módulo por Turma
├── Teacher              → Professor (tem TeacherAvailability)
├── TeacherAvailability  → Dias/horas de disponibilidade do professor
├── Room                 → Sala (tem capacity, room_type)
├── Timeslot             → Padrão semanal (day_of_week, start_time, end_time) — SEM data absoluta
│
├── Lesson               → ⚠️ NÃO é um bloco agendado. É uma DEFINIÇÃO ABSTRATA:
│                           (Class + Subject + Teacher). Sem data, sem timeslot, sem sala.
├── ScheduleOutput       → O horário gerado. Liga: Lesson + Timeslot + Room + generation_id.
│                           ⚠️ Também SEM data absoluta — apenas padrão semanal.
└── Substitution         → Registo de substituição/furo. TEM date (Date). Liga:
                            Lesson + Timeslot + date + original_teacher + substitute_teacher.
                            ⚠️ Não tem substitute_subject_id — não rastreia qual disciplina foi dada.
```

**Problema crítico identificado:** Nem `Lesson` nem `ScheduleOutput` têm uma data absoluta. Só existe o padrão semanal (`Timeslot.day_of_week`). Isto impossibilita:
- Saber se uma aula "já foi dada" (não há data para comparar com hoje)
- A visualização navegável semanal (←→)
- O sistema automático de confirmação de aulas (Opção B)
- O cálculo de "dívida de horas" (esperado vs. dado até hoje)

```
MODELOS A CRIAR (novas migrações)
│
├── OrganizationSettings (NOVA)   → Configurações gerais da escola (por org, por ano letivo):
│   ├── org_id
│   ├── academic_year             →   Ex: "2025/2026"
│   ├── school_start_date: Date   →   Ex: 2025-09-15 (primeiro dia de aulas)
│   ├── school_target_end_date: Date → Ex: 2026-06-15 (data-alvo para as aulas acabarem)
│   └── region_code: str          →   Código de região para feriados (ex: "11" = Lisboa)
│                                     Necessário para feriados municipais via API
│
├── SchoolCalendarEvent (NOVA)    → Pausas letivas (hard constraint para o solver):
│   ├── org_id
│   ├── name                      →   Ex: "Natal", "Páscoa", "Feriado Municipal"
│   ├── start_date
│   ├── end_date
│   ├── type: NATIONAL_HOLIDAY | SCHOOL_BREAK | EXAM_PERIOD | OTHER
│   └── source: AUTO | MANUAL     →   AUTO = importado via API; MANUAL = adicionado pelo diretor
│
├── ScheduleOutput.date (Date)    → Migração: adicionar data absoluta ao ScheduleOutput.
│   ScheduleOutput.is_draft (Bool)→   True = aguarda aprovação; False = geração ativa
│   ScheduleOutput.generation_id  →   Já existe — mantido para auditoria histórica
│
├── LessonOccurrence (NOVA)       → O que realmente aconteceu numa data específica:
│   ├── schedule_output_id        →   FK → ScheduleOutput (ON DELETE SET NULL, não CASCADE)
│   │                                 ⚠️ Nunca deletar LessonOccurrence — é histórico permanente
│   ├── date                      →   Data em que deveria ter ocorrido
│   ├── status                    →   GIVEN | GAP | SUBSTITUTED
│   ├── substitute_teacher_id     →   Professor que substituiu (se SUBSTITUTED)
│   ├── substitute_subject_id     →   Disciplina que foi dada pelo substituto
│   └── hours_given               →   Horas efetivamente dadas (duração do timeslot em horas)
│
└── Substitution (EXISTENTE)      → Refactor: adicionar substitute_subject_id
```

### 3.3 Ficheiros do Solver Já Existentes (Esqueletos)

- `backend/app/core/solver_engine.py` — Onde vai viver o modelo CP-SAT
- `backend/app/solver_tasks.py` — Tarefas Celery que invocam o engine

### 3.4 Fluxo de Dados do Solver

```
HTTP POST /api/v1/schedule/generate
     │
     ▼
FastAPI endpoint (síncrono, valida payload)
     │
     ▼
Celery Task: solve_schedule.delay(params)
     │  (retorna task_id imediatamente ao frontend)
     ▼
[Worker Celery — sem time limit artificial]
     │
     ├── 1. Carregar dados do DB:
     │      - Todas as Turmas ativas da org
     │      - ClassProgress (horas já completadas por módulo — "o passado")
     │      - TeacherAvailability (disponibilidade dos professores)
     │      - Rooms (salas disponíveis com tipo e capacidade)
     │      - Timeslots (padrões semanais: day_of_week + start_time + end_time)
     │      - SchoolCalendarEvents (feriados, períodos de exame — dias bloqueados)
     │      - [Repair Mode] LessonOccurrence com status=GIVEN (aulas já dadas — imutáveis)
     │
     ├── 2. Expandir Timeslots → Datas Absolutas:
     │      Para cada semana do ano letivo (início → fim projetado):
     │        Para cada Timeslot (ex: Monday 09:00-11:00):
     │          gerar data absoluta (ex: 2026-03-09 09:00)
     │          excluir se data está em SchoolCalendarEvent
     │      Resultado: lista de "slots disponíveis" com datas concretas
     │
     ├── 3. Construir modelo CP-SAT:
     │      - Variáveis binárias por (Turma, Módulo, Slot com data absoluta)
     │      - Hard constraints (sem conflitos, módulos sequenciais, 15h/semana, etc.)
     │      - Soft constraints (preferências, furos)
     │      - Objective: minimizar desvio entre datas de fim das disciplinas
     │
     ├── 4. Resolver (CP-SAT — sem time limit)
     │
     ├── 5. Escrever resultados no DB:
     │      - DELETE ScheduleOutput futuro (onde date > hoje e sem LessonOccurrence GIVEN)
     │      - INSERT novos ScheduleOutput com datas absolutas
     │      - Calcular e guardar projected_end_date por Turma
     │
     └── 6. Marcar task como DONE (Celery result backend)

HTTP GET /api/v1/schedule/status/{task_id}
     │
     └── Retorna: status (PENDING/RUNNING/SUCCESS/FAILURE)
                  + projected_end_dates por turma (quando SUCCESS)
                  + quality_score: % de soft constraints satisfeitas
```

### 3.4 Endpoint de Geração — Payload

```json
POST /api/v1/schedule/generate
{
  "mode": "full",         // "full" = gerar tudo | "repair" = mínimas alterações
  // Nota: class_ids removido — a geração é SEMPRE para a escola inteira.
  // Isolar turmas produziria um ótimo local mas inválido globalmente.
  "locked_lesson_ids": [], // Repair mode: estes Lesson.id ficam fixados (não mudam)
  "teacher_unavailabilities": [
    // Overrides temporários além do TeacherAvailability padrão
    { "teacher_id": 5, "date": "2026-03-15" }
  ]
  // Sem time_limit_seconds — o solver corre até encontrar a melhor solução possível.
  // Existe apenas um timeout de infra (ex: 30min) para troubleshooting, não para limitar qualidade.
}
```

**Racional da ausência de time limit:**
Despender 5 minutos para gerar um horário perfeito é infinitamente melhor do que gerar um em 30 segundos que requer horas de edição manual. A qualidade do output é o KPI, não a velocidade. O timeout de infra existe apenas para evitar processos zumbis — não para comprometer o resultado.

### 3.5 Pré-Validação (Preflight Check) — Antes de Correr o Solver

Antes de submeter a tarefa Celery, o endpoint `/generate` corre uma pré-validação síncrona e rápida. Se falhar, retorna imediatamente com `400 Bad Request` e uma lista de problemas — sem desperdiçar recursos de CPU no solver.

**Verificações obrigatórias:**
1. `OrganizationSettings.school_start_date` está configurado
2. `OrganizationSettings.school_target_end_date` está configurado
3. `SchoolCalendarEvent` tem pelo menos os feriados nacionais do ano letivo atual importados
4. Todas as turmas ativas têm pelo menos uma Disciplina associada
5. Todas as Disciplinas ativas de cada turma têm pelo menos um Professor atribuído (`ClassSubjectLink`)
6. Nenhum Professor assignado tem 0 horas de disponibilidade semanal (`TeacherAvailability`)
7. Existem salas do tipo necessário para cada Disciplina (`required_room_type`)
8. Todos os Módulos de todas as Disciplinas ativas têm `hours_total > 0`

**Resposta em caso de falha:**
```json
{
  "error": "preflight_failed",
  "issues": [
    "Professor 'Ana Silva' não tem disponibilidade configurada.",
    "Não existem salas do tipo 'Informática' na escola.",
    "Feriados nacionais de 2025/2026 não foram importados."
  ]
}
```

### 3.6 Integração com API de Feriados (Automático)

**Problema:** Os feriados nacionais portugueses mudam de data a cada ano (ex: Páscoa cai em dias diferentes). Não podem ser inseridos manualmente. Portugal tem também feriados municipais que variam por região.

**Solução:** Usar o package Python `holidays` (já está ou pode ser adicionado a `requirements.txt`):
```python
import holidays

# Feriados nacionais
pt_holidays = holidays.Portugal(years=2026)

# Feriados com subdivisão regional (município)
pt_holidays_lisbon = holidays.Portugal(years=2026, subdiv="Lisboa")
# subdiv aceita: "Lisboa", "Porto", "Aveiro", "Braga", "Faro", etc.
```

**Fluxo de importação:**
1. O diretor configura `OrganizationSettings.region_code` (ex: "Lisboa") uma vez.
2. No início de cada ano letivo (trigger manual ou no primeiro acesso), o sistema chama:
   - `holidays.Portugal(years=[start_year, end_year], subdiv=region_code)`
   - Cria `SchoolCalendarEvent` com `source=AUTO` para cada feriado
3. O diretor pode depois adicionar manualmente as pausas escolares (Natal, Páscoa, férias de verão) com `source=MANUAL`
4. O diretor pode também eliminar um feriado AUTO se a escola decidir ter aulas nesse dia (raro mas possível)
5. A importação pode ser re-corrida a qualquer momento via botão "Sincronizar Feriados" nas configurações

**Garantia:** `SchoolCalendarEvent.type = NATIONAL_HOLIDAY` e `source = AUTO` são sempre substituídos, não duplicados, quando a importação corre novamente.

### 3.7 O Fluxo Completo de Gestão de uma Falta (Decisão Q7)

**O que acontece quando um professor avisa que falta amanhã:**

```
Professor avisa que falta → Diretor vai ao horário da turma
     │
     ▼
[Diretor clica nos blocos afetados → botão "Encontrar Substituto"]
     │
     ├── Sistema filtra automaticamente:
     │     - Professores assignados à ESTA turma (ClassSubjectLink)
     │     - Que não têm outro bloco nesse timeslot (sem conflito)
     │     - Que têm disponibilidade nesse horário (TeacherAvailability)
     │     - São de OUTRA disciplina (o sub dá a SUA disciplina, não a do ausente)
     │
     ├── Diretor escolhe substituto → cria LessonOccurrence:
     │     status = SUBSTITUTED
     │     substitute_teacher_id = professor escolhido
     │     substitute_subject_id = disciplina DO professor substituto ← atualiza ClassProgress de B
     │     (ClassProgress do ausente NÃO avança — a hora fica em dívida)
     │
     └── Sem substituto disponível → diretor marca como GAP:
           LessonOccurrence.status = GAP
           ClassProgress do ausente NÃO avança
           Alerta criado: "Prof. X ficou a dever 2h à Turma Y em [data]"

[Horário NÃO é alterado — base do plano permanece intacta]
     │
     ▼
[Quando o diretor decide resolver as dívidas acumuladas]
     │
     └── Clica em "Resolver Dívidas / Regenerar Horário"
           → mode: "repair" (solver corre para a escola inteira)
           → ClassProgress atual já reflete todas as faltas e substituições
           → Solver naturalmente "recupera" as disciplinas em atraso
             porque vê que têm mais horas remaining do que o previsto
           → O resultado é um novo ScheduleOutput com datas ajustadas
```

**Porquê "Resolver Dívidas" = modo repair do solver:**
A dívida já está implícita no `ClassProgress`. O solver vê que Matemática devia ter 40h dadas mas só tem 34h → nas semanas seguintes atribui mais blocos a Matemática. Não é necessário um mecanismo separado — o CP-SAT resolve isto automaticamente ao recalcular a distribuição ótima com base no estado atual.

**O sistema de alertas ("Dívidas"):**
- Alert = qualquer disciplina onde `ClassProgress.hours_completed` < soma dos `ScheduleOutput.hours` com `date <= hoje` e `LessonOccurrence.status != GIVEN`
- Mostrado num painel de avisos para o diretor, com filtro por turma e por professor
- Quando o solver gera novo horário, os alertas são recalculados automaticamente

### 3.8 Confirmação Automática de Aulas (Opção B)

**O mecanismo:**
- Um job periódico (cron via Celery Beat) corre **diariamente ao fim do dia** (ex: às 23:59)
- Para cada `ScheduleOutput` onde `date = hoje` e não existe `LessonOccurrence`:
  → Cria automaticamente `LessonOccurrence` com `status = GIVEN`
  → Incrementa `ClassProgress.hours_completed` pelo valor de `timeslot.duration`
- **Override manual:** O diretor pode criar manualmente uma `LessonOccurrence` com `status = GAP` ou `SUBSTITUTED` ANTES do cron correr — o cron ignora os dias que já têm ocorrência registada

**Garantia de consistência:**
- `ClassProgress.hours_completed` é a fonte de verdade — nunca decresce
- O solver só lê `ClassProgress` — não calcula horas a partir de LessonOccurrences
- Isto mantém o CP-SAT simples e sem dependência de lógica de negócio complexa

### 3.9 Repair Scheduling — O Detalhe Técnico

Modo repair = regeneração com perturbação mínima:

1. Solver distingue passado de futuro via data:
   - Passado: `LessonOccurrence.status = GIVEN` → não pode ser movido
   - Futuro: `ScheduleOutput.date > hoje` → pode ser reotimizado
2. Hard constraint no modelo: para cada slot já dado → `solver.Add(x[slot] == 1)` — variável fixada
3. Soft constraint adicional (repair): minimizar `sum(novo_plano[i] != plano_anterior[i])` — número de mudanças face ao horário em uso
4. O ClassProgress atual (que já inclui dívidas) é a entrada — o solver distribui as horas restantes de forma ótima
5. A constraint de 15h/semana **mantém-se aplicada** mesmo em modo repair

**Porquê sempre escola inteira:**
Uma falta do Professor de Matemática da Turma A pode libertar a Sala 3 às terças-feiras às 10h. A solver descobriria que a Turma B (que precisava de uma sala de informática nesse slot) pode agora usar a Sala 3 e deixar a Sala Informática 1 disponível para outra turma. Estes ganhos de cascata são invisíveis num repair isolado por turma.

### 3.10 Modelo CP-SAT — Pseudo-código

```python
from ortools.sat.python import cp_model

def build_model(data: SchedulerInput) -> cp_model.CpModel:
    model = cp_model.CpModel()

    # ── VARIÁVEIS ──────────────────────────────────────────────────
    # x[class_id, module_id, timeslot_id] = 1 se este timeslot serve este módulo
    x = {}
    for cls in data.classes:
        for subject_link in cls.active_subject_links:
            for module in subject_link.remaining_modules:  # ignora módulos completos
                for ts in data.timeslots:
                    x[cls.id, module.id, ts.id] = model.NewBoolVar(
                        f"x_c{cls.id}_m{module.id}_t{ts.id}"
                    )

    # ── HARD CONSTRAINTS ───────────────────────────────────────────

    # 1. Cada timeslot tem no máximo 1 turma por sala
    for room in data.rooms:
        for ts in data.timeslots:
            model.AddAtMostOne(
                x[cls.id, mod.id, ts.id]
                for cls, mod in data.class_module_pairs
                if needs_room_type(mod, room)
            )

    # 2. Cada professor no máximo 1 aula por timeslot
    for teacher in data.teachers:
        for ts in data.timeslots:
            model.AddAtMostOne(
                x[cls.id, mod.id, ts.id]
                for cls, mod in teacher.assigned_class_modules
            )

    # 3. Cada turma no máximo 1 aula por timeslot
    for cls in data.classes:
        for ts in data.timeslots:
            model.AddAtMostOne(
                x[cls.id, mod.id, ts.id]
                for mod in cls.all_active_modules
            )

    # 4. Horas necessárias por módulo (ajustadas pelo ClassProgress)
    for cls in data.classes:
        for mod in cls.active_modules:
            hours_remaining = mod.hours_total - data.progress[cls.id, mod.id]
            blocks_needed = ceil(hours_remaining / BLOCK_DURATION_HOURS)
            model.Add(
                sum(x[cls.id, mod.id, ts.id] for ts in data.timeslots) == blocks_needed
            )

    # 5. Precedência de módulos (M2 só depois de M1 acabar)
    # Implementado via IntervalVar e sequência temporal

    # 6. Professor indisponível em certas horas/dias
    for teacher in data.teachers:
        for unavail in teacher.unavailabilities:
            for mod in teacher.assigned_modules:
                model.Add(x[teacher.class_id, mod.id, unavail.timeslot_id] == 0)

    # ── SOFT CONSTRAINTS (penalidades) ─────────────────────────────
    penalties = []

    # Furos na turma (bloco vazio entre aulas)
    # ... (variáveis auxiliares + penalidade)

    # Preferências dos professores
    for teacher in data.teachers:
        for pref in teacher.preferences:
            for mod in teacher.assigned_modules:
                penalty_var = model.NewBoolVar(f"pref_viol_{teacher.id}_{pref.id}")
                model.Add(x[teacher.class_id, mod.id, pref.timeslot_id] == 1).OnlyEnforceIf(penalty_var)
                penalties.append(WEIGHT_PREFERENCE * penalty_var)

    # ── OBJECTIVE ──────────────────────────────────────────────────
    # Makespan: minimizar o timeslot mais tardio usado
    makespan = model.NewIntVar(0, len(data.timeslots), "makespan")
    for key, var in x.items():
        _, _, ts_id = key
        ts_index = data.timeslot_index[ts_id]
        model.Add(makespan >= ts_index * var)

    model.Minimize(makespan + sum(penalties))

    return model
```

---

## PARTE 4 — PLANO DE IMPLEMENTAÇÃO (Os Sprints)

### Sprint 1 — Gerador Básico (Hard Constraints Only)

**Objetivo:** Um endpoint funcional que gera um horário válido (sem conflitos) com desvio mínimo entre datas de fim das disciplinas.

**Ficheiros a criar/modificar:**
- `backend/app/core/solver_engine.py` — Modelo CP-SAT completo (hard constraints + objetivo de desvio)
- `backend/app/solver_tasks.py` — Tarefa Celery que invoca o engine + escreve no DB
- `backend/app/api/v1/endpoints/schedule.py` — Endpoints `/generate` e `/status/{task_id}`
- `backend/app/schemas.py` — `ScheduleGenerateRequest`, `ScheduleStatusResponse`
- Migração Alembic — campo `projected_end_date` em `Class` (Turma)
- Migração Alembic — tabela `school_calendar_events` (pausas letivas)

**Hard constraints do Sprint 1:**
1. Sem conflitos de sala
2. Sem conflitos de professor
3. Sem sobreposição de turmas
4. Módulos sequenciais (M2 só após M1 completo)
5. Blocos proibidos (feriados, férias — via `school_calendar_events`)
6. Respeito pela `TeacherAvailability` (já em DB)
7. **Máximo 15h/semana por professor por turma** (hard)

**Critério de aceitação:**
- `POST /schedule/generate` retorna `{ "task_id": "..." }` imediatamente
- `GET /schedule/status/{task_id}` retorna `PENDING | RUNNING | SUCCESS | FAILURE`
- O solver corre sem time limit artificial (apenas timeout de infra)
- Quando `SUCCESS`: zero violações de hard constraints
- Desvio entre datas de fim das disciplinas é minimizado
- Data de fim projetada é calculada e guardada por turma

---

### Sprint 2 — Soft Constraints + Confirmação Automática + UI de Faltas

**Objetivo:** Sistema de confirmação automática de aulas + fluxo de gestão de faltas.

**Backend:**
- Celery Beat cron job (fim do dia) → cria `LessonOccurrence` GIVEN automático
- Endpoint `PATCH /schedule/occurrences/{id}` → diretor marca GAP ou SUBSTITUTED
- Endpoint `GET /schedule/debts?class_id=X` → lista dívidas de horas (ClassProgress vs. esperado até hoje)
- Endpoint `GET /teachers/{id}/available?date=X&timeslot_id=Y` → "encontrar substituto"
- Soft constraints no solver: penalidades por furos, por preferências dos professores

**Frontend:**
- UI "Registar Falta": o diretor clica num bloco → modal com lista de substitutos disponíveis
- Painel "Dívidas de Horas": lista de alertas com Professor / Turma / Horas em dívida
- Botão "Resolver Dívidas / Regenerar Horário" (trigger do repair mode)

---

### Sprint 3 — Repair Mode + Diff View + Calendário Escolar

**Objetivo:** Regeneração completa em modo repair + UI de confirmação do diff.

**O que adicionar:**
- `mode: "repair"` no solver: lê `LessonOccurrence.status = GIVEN` como slots fixados
- UI: Resultado da geração mostra diff ("X aulas de Y disciplinas foram movidas")
- O diretor revê o diff e **aceita ou rejeita** antes de se tornar ativo
- Se rejeitar: `ScheduleOutput` anterior é restaurado (guardar snapshot antes de apagar)
- Interface de gestão do `SchoolCalendarEvent` (feriados, períodos de exame) — bloqueante para o Sprint 1

### Sprint 4 — Visualização do Horário (Página de Detalhe)

**Objetivo:** Interface rica para visualizar o horário gerado, navegável no tempo.

**Visão da página:**
- Seletor no topo: **Turma** ou **Professor** (dois modos de visualização)
- Grelha semanal no centro, com blocos coloridos por Disciplina
- Navegação esquerda/direita por semana: passado mostra o que **aconteceu** (aulas dadas); futuro mostra o que está **planeado** (solver output)
- KPIs laterais:
  - Progresso de cada Disciplina (barra: horas dadas / horas totais)
  - Data de fim projetada por Disciplina
  - Desvio médio entre disciplinas (métrica de equilíbrio)
  - Horas dadas esta semana vs. média semanal esperada
  - Número de furos acumulados
- Tooltip nos blocos: Módulo ativo, horas dadas neste bloco, professor, sala
- Indicador visual: blocos passados (cinzento/verde = dado, vermelho = furo); blocos futuros (cor da disciplina, semitransparente)

**Semelhança com a página de Cursos:** Rica em detalhe, com vários painéis de informação, não apenas a grelha.

---

## PARTE 5 — QUESTÕES ABERTAS / DECISÕES PENDENTES

### Q1 — Duração dos Timeslots — DECISÃO TOMADA ✅
Usar `end_time - start_time` de cada `Timeslot` já existente na DB. Não existe um valor fixo hardcoded. O solver calcula `blocks_needed` com base na duração real de cada slot.

### Q2 — Pausas Letivas — DECISÃO TOMADA ✅
Tabela `SchoolCalendarEvent` com `(org_id, start_date, end_date, type: HOLIDAY | EXAM_PERIOD | OTHER)`. Hard constraint — o solver não agenda nada nesses dias.

### Q3 — Geração Escolar Completa — DECISÃO TOMADA ✅
Sempre todas as turmas. Nunca isolada. Ver 1.4.

### Q4 — Datas Absolutas — DECISÃO TOMADA ✅
O solver expande padrões semanais (`Timeslot`) em datas absolutas ao longo do ano letivo, excluindo dias da `SchoolCalendarEvent`.

### Q5 — Transição de Módulo a meio da semana — DECISÃO TOMADA ✅
Sim, é visível ao diretor. A grelha semanal mostra segunda/terça com "M1" e quinta/sexta com "M2" se a transição ocorreu na quarta. O CP-SAT com datas absolutas resolve isto sem barreira de semana.

### Q6 — Visualização — DECISÃO TOMADA ✅
Grelha semanal navegável (← →), colorida por Disciplina, com KPIs laterais. Sprint 4.

### Q7 — Atualização do ClassProgress — DECISÃO TOMADA ✅
Opção B: automático. Cron job (Celery Beat) ao fim de cada dia cria `LessonOccurrence` com `status=GIVEN` para todos os slots do dia sem ocorrência manual. O diretor pode criar manualmente ocorrências `GAP` ou `SUBSTITUTED` antes do cron. Ver 3.6.

### Q8 — Lesson vs LessonOccurrence — DECISÃO TOMADA ✅
- `Lesson` = definição abstrata (Class + Subject + Teacher). Permanece como está.
- `ScheduleOutput` = slot planeado (Lesson + Timeslot + Room + **date absoluta** — migração necessária).
- `LessonOccurrence` = o que aconteceu numa data (GIVEN / GAP / SUBSTITUTED) — nova tabela.

---

### Q9 — Snapshot do Horário antes de Repair — DECISÃO TOMADA ✅
O solver não apaga o horário oficial. Escreve o novo com `is_draft=True`. O diretor tem o horário oficial X ativo e o draft Y pendente de aprovação. Pode:
- **Aprovar:** Y torna-se oficial (is_draft=False), X é apagado (apenas os `ScheduleOutput` FUTUROS — os passados com `LessonOccurrence` ficam)
- **Descartar:** Y é apagado, X continua ativo
Nunca existe mais de 1 draft ativo em simultâneo.

### Q10/Q11 — INFEASIBLE é impossível neste domínio — DECISÃO TOMADA ✅
Este sistema **nunca pode ser verdadeiramente insolúvel**. Se um professor só tem 8h disponíveis por semana e a turma precisa de 20h, as 12h restantes vão para a semana seguinte. O ano acaba mais tarde. A constraint de 15h/semana mantém-se hard em todos os modos — as dívidas diluem-se ao longo do tempo e a `projected_end_date` reflete isso honestamente.

Os únicos casos de impossibilidade real são **erros de dados** (professor com 0h de disponibilidade, sem salas do tipo necessário) — apanhados pela **pré-validação** (ver 3.5) antes de o solver correr. O solver em si nunca deve atingir INFEASIBLE em operação normal.

### Q12 — Feriados via API Externa — DECISÃO TOMADA ✅
Feriados nacionais importados automaticamente via package Python `holidays` (Portugal + subdivisão regional). O diretor configura o `region_code` uma vez. As pausas escolares (Natal, Páscoa, etc.) são adicionadas manualmente. O diretor pode re-sincronizar a qualquer momento. Ver 3.6.

### Q13 — Datas do Ano Letivo em OrganizationSettings — DECISÃO TOMADA ✅
As datas (`school_start_date`, `school_target_end_date`) são **configurações ao nível da organização/escola**, não por turma. Vivem no novo modelo `OrganizationSettings`. A `school_target_end_date` funciona como benchmark com recompensa/penalidade no objetivo do solver (ver função objetivo na Parte 2). Não há `start_date` no modelo `Class` — todas as turmas ativas partilham o mesmo início de ano letivo.

### Q14 — Histórico de Gerações — DECISÃO TOMADA ✅
- Manter as últimas **5 gerações aprovadas** + o draft mais recente (se existir)
- `LessonOccurrence` é **imutável e eterno** — nunca deletado, independentemente da política de retenção de gerações
- A navegação `←→` por semanas passadas baseia-se em `LessonOccurrence`, não em `ScheduleOutput` histórico
- Quando a 6ª geração é aprovada, a 1ª é eliminada (apenas `ScheduleOutput` com `date > hoje` — os passados com `LessonOccurrence` ficam com `schedule_output_id = NULL`)
- `generation_id` é um UUID gerado no momento da geração — serve para agrupar todos os `ScheduleOutput` de uma geração

---

### Q15 — OrganizationSettings: a página de configurações já existe — DECISÃO TOMADA ✅
A página de "Definições" / "Configurações" da aplicação já existe e já permite configurar o horário de funcionamento da escola e as horas de geração de horários. Esta página deve ser **expandida** (não criada de raiz) para incluir os novos campos do modelo `OrganizationSettings`:
- Data de início das aulas (`school_start_date`)
- Data-alvo de fim das aulas (`school_target_end_date`)
- Região/município para feriados (`region_code` — dropdown)
- Botão "Sincronizar Feriados Nacionais"
- Campo `academic_year` (ex: "2025/2026" — preenchido automaticamente ou pelo diretor)

**Nota:** Uma organização pode ter múltiplos `OrganizationSettings` simultaneamente, um por `academic_year`, porque os cursos duram 3 anos. A turma "TGPSI 25/28" está em simultâneo com configurações de 2025/2026, 2026/2027 e 2027/2028. O solver seleciona o `OrganizationSettings` correto com base nas datas das turmas ativas.

A chave primária lógica é `(org_id, academic_year)`. Na UI de Configurações, o diretor vê uma lista dos anos letivos ativos e pode criar/editar cada um independentemente — por exemplo, em 2027 poderá ter "2025/2026", "2026/2027" e "2027/2028" todos configurados em simultâneo. Ver D26.

### Q16 — Região para Feriados Municipais — DECISÃO TOMADA ✅
Dropdown com os distritos / municípios portugueses suportados pelo package `holidays`. A lista é derivada programaticamente de `holidays.Portugal.subdivisions` — não é hardcoded. O diretor seleciona uma vez e o sistema usa para importação automática.

### Q17 — Página de Configurações — DECISÃO TOMADA ✅
A página já existe (confirmado na Q15). É uma expansão, não uma criação nova. Sprint 0 inclui apenas a adição dos novos campos ao formulário existente.

### Q18 — Gestão de Turmas Antigas (Arquivo) — DECISÃO TOMADA ✅
**Contexto:** Os cursos são trienais. A "Turma TGPSI 25/28" está ativa de 2025 a 2028. Quando encerrarem todas as suas atividades (todos os módulos completos e `end_year < current_year`), a turma torna-se "antiga". Não existem turmas por ano letivo — existem turmas por triénio.

**Mecanismo de arquivo:**
- Uma `Class` com `end_year < current_year` E todos os módulos completos é automaticamente marcada como `is_archived = True`
- Turmas arquivadas **não aparecem** nas listagens normais (horários, selects, dashboards)
- Existem num grupo separado "Turmas Antigas" na UI — **só carregadas quando o diretor clica explicitamente** (lazy loading, não incluídas no bundle principal)
- Os dados são **mantidos por 5 anos após o `end_year`**. Ao fim de 5 anos, o sistema notifica o diretor antes de eliminar (soft delete).
- `LessonOccurrence` de turmas arquivadas **nunca são eliminadas** — apenas os `ScheduleOutput` futuros (inexistentes numa turma fechada) poderiam ser eliminados.

**Nova coluna necessária:** `Class.is_archived: Boolean` (default `False`) — ver migração 9.

### Q19 — Imutabilidade Total do Passado — DECISÃO TOMADA ✅
**Regra absoluta:** Tudo o que tem `date < hoje` é **sagrado e imutável**.
- `ScheduleOutput` com `date < hoje` → **nunca eliminado**, independentemente de qualquer política de retenção
- `LessonOccurrence` → **nunca eliminada**, em nenhuma circunstância
- O solver ao correr em modo `full` ou `repair` **ignora completamente** qualquer slot com `date <= hoje` — só trabalha com o futuro
- A política de "5 gerações" aplica-se exclusivamente a `ScheduleOutput` com `date > hoje` sem `LessonOccurrence` associadas
- **Consequência:** A FK `LessonOccurrence.schedule_output_id ON DELETE SET NULL` é um mecanismo de segurança, mas na prática nunca deve disparar para datas passadas — a validação de negócio proíbe eliminar esses registos.

### Q20 — Estado Vazio Antes da Primeira Geração — DECISÃO TOMADA ✅
Antes de o solver correr pela primeira vez, a página de visualização mostra um **estado vazio com call-to-action**:
- Mensagem: *"Ainda não foi gerado nenhum horário para este ano letivo."*
- Botão de ação primária: *"Gerar Horário"* (leva ao fluxo de geração)
- A navegação `←→` por semanas está **desativada** até existir pelo menos uma geração ativa
- Se as pré-condições (preflight check) não estiverem satisfeitas, o botão "Gerar Horário" está desativado com tooltip explicativo dos problemas pendentes

---

## PARTE 6 — GLOSSÁRIO DE TERMOS

| Termo PT | Termo EN (código) | Definição |
|---|---|---|
| Turma | Class | Instância de um curso para um grupo de alunos |
| Disciplina | Subject | Matéria/cadeira (ex: Matemática) |
| Módulo / UFCD | Module | Unidade atómica com horas fixas (ex: M1 = 25h) |
| Furo | Gap | Bloco no horário onde não houve aula sem substituto |
| Progressão | ClassProgress | Horas completadas de um módulo numa turma (fonte de verdade) |
| Substituição | Substitution | Professor B cobre com a SUA disciplina por ausência de A |
| Disponibilidade | TeacherAvailability | Dias/horas em que um professor pode dar aulas |
| Dívida de Horas | Hour Debt | Horas planeadas mas não dadas (visíveis no painel de alertas) |
| Makespan | Makespan | Data de fim da última aula de qualquer turma |
| Data-Alvo | Target End Date | Data ideal definida pelo diretor — benchmark para o solver |
| Modo Reparação | Repair Mode | Regeneração que minimiza mudanças face ao horário anterior |
| Horário Planeado | ScheduleOutput | Output do solver — slots com datas absolutas (pode ser draft) |
| Ocorrência | LessonOccurrence | Registo do que aconteceu numa data: GIVEN / GAP / SUBSTITUTED |
| Calendário Escolar | SchoolCalendarEvent | Feriados e pausas — dias bloqueados para o solver |
| Configurações da Escola | OrganizationSettings | Datas do ano letivo, região, data-alvo — ao nível da org |
| Draft | Draft | Geração pendente de aprovação do diretor |
| Geração Ativa | Active Generation | O horário atualmente em uso pela escola |
| Pré-Validação | Preflight Check | Verificação de dados antes de correr o solver |

---

## PARTE 7 — DIAGRAMA DE FLUXO DO ANO LETIVO

```
INÍCIO DO ANO
     │
     ▼
[Diretor preenche dados]
     Cursos, Turmas, Professores, Salas, Calendário, Disponibilidades
     │
     ▼
[Geração Inicial — Modo Full]
     CP-SAT gera horário completo para o ano
     → Projeta data de fim para cada turma (ex: Turma A: 2 Jun, Turma B: 5 Jun)
     │
     ▼
[Ano letivo em curso]
     │
     ├──→ Semana normal: Aulas dadas → ClassProgress atualizado automaticamente
     │
     ├──→ Professor falta:
     │         │
     │         ├──→ Há substituto interno? → Regista Substituição → ClassProgress ajustado
     │         │
     │         └──→ Não há substituto → Regista Furo → ClassProgress não avança
     │
     └──→ Trigger de Regeneração (automático ou manual):
               │
               ▼
          [Geração — Modo Repair]
               CP-SAT lê ClassProgress atual
               Fixa todas as Lesson já dadas (locked)
               Gera horário apenas para horas em falta
               Minimiza alterações face ao horário anterior
               → Atualiza data de fim projetada para cada turma
               │
               ▼
          [Diretor vê diff: "3 aulas de Matemática movidas"]
               Aceita ou rejeita
               │
               ▼
          Volta a "Ano letivo em curso"
     │
     ▼
TODOS OS MÓDULOS DE TODAS AS TURMAS COMPLETOS
     → Ano letivo termina (data variável, minimizada pelo solver)
```

---

---

## PARTE 8 — DECISÕES TOMADAS (Registo)

| # | Decisão | Escolha | Razão |
|---|---|---|---|
| D1 | Objetivo primário do solver | Minimizar desvio entre datas de fim das disciplinas | Makespan é consequência, não causa |
| D2 | Limite de horas por professor por turma | 15h/semana — hard constraint | Protege contra desequilíbrio por substituições |
| D3 | Trigger de regeneração | Manual pelo diretor | Simples; automático é Sprint futuro |
| D4 | Granularidade da regeneração | Escola inteira — sempre | Efeito cascata torna isolamento inválido |
| D5 | Time limit do solver | Sem limite artificial (apenas timeout de infra) | Qualidade > velocidade |
| D6 | Granularidade temporal | Datas absolutas no `ScheduleOutput` | Necessário para tudo: cron, visualização, debug |
| D7 | Algoritmo | OR-Tools CP-SAT | Grátis, Python nativo, já em requirements, ideal para RCPSP |
| D8 | Pausas letivas | Tabela `SchoolCalendarEvent` | Hard constraint — solver exclui esses dias |
| D9 | Confirmação automática de aulas | Celery Beat cron (fim do dia) cria `LessonOccurrence` GIVEN | Reduz trabalho burocrático do diretor |
| D10 | Lesson vs ScheduleOutput vs LessonOccurrence | 3 tabelas distintas com responsabilidades separadas | Separation of concerns — plano vs. realidade |
| D11 | Resultado da geração — aprovação | `ScheduleOutput` com `is_draft=True` até o diretor aprovar | Evita ativar um horário sem revisão |
| D12 | "Resolver Dívidas" = Repair Mode | Mesma lógica do solver, mesmo endpoint | Dívidas são implícitas no ClassProgress, não requerem lógica separada |
| D13 | Constraint 15h/semana em repair | Mantém-se hard | Horários insustentáveis são piores do que dívidas que se diluem ao longo do tempo |
| D14 | INFEASIBLE no solver | Impossível em operação normal — apanhado por pré-validação | O ano acaba mais tarde; nunca há verdadeira insolubilidade |
| D15 | Feriados | Package `holidays` Python (Portugal + região) — importação automática | Datas mudam todos os anos; erro humano inaceitável |
| D16 | Datas do ano letivo | `OrganizationSettings` ao nível da org, não por turma | Todas as turmas do mesmo ano letivo partilham as mesmas datas |
| D17 | Data-alvo de fim como benchmark | Soft constraint com recompensa/penalidade no objetivo CP-SAT | Incentiva acabar cedo sem tornar o problema insolúvel |
| D18 | Retenção de gerações | 5 aprovadas + draft mais recente; `LessonOccurrence` eterno | Auditoria histórica sem consumo excessivo de storage |
| D19 | `LessonOccurrence` FK safety | `ON DELETE SET NULL` — nunca deletar ocorrências passadas | Histórico permanente para navegação e audit trail |
| D20 | Página de Configurações | Expandir a página existente, não criar nova | Já existe suporte a horário de funcionamento e horas de geração |
| D21 | Seleção de região para feriados | Dropdown derivado de `holidays.Portugal.subdivisions` | Não hardcoded; suporta todos os municípios portugueses |
| D22 | Ciclo de vida das Turmas | Triénio (3 anos, ex: 25/28); não há turmas por ano letivo | Especificidade do Ensino Profissional (UFCD/Módulos) |
| D23 | Arquivo de Turmas Antigas | `Class.is_archived=True` quando `end_year < now` e todos módulos completos | Lazy loading on demand; mantidas por 5 anos; notificação antes de eliminar |
| D24 | Imutabilidade do passado | `ScheduleOutput.date < hoje` e `LessonOccurrence` jamais eliminados | Integridade histórica absoluta; solver só toca no futuro |
| D25 | Estado vazio na visualização | Call-to-action com botão "Gerar Horário"; navegação ←→ desativada até existir geração | UX clara para novos utilizadores; preflight check visível |
| D26 | `OrganizationSettings` — chave lógica | Um registo por `(org_id, academic_year)` — vários ativos em simultâneo por organização | Cursos duram 3 anos; escola tem sempre múltiplos anos letivos sobrepostos |

---

## PARTE 9 — MIGRAÇÕES DE BASE DE DADOS NECESSÁRIAS (Por Ordem)

| Ordem | Migração | Urgência | Notas |
|---|---|---|---|
| 1 | `organization_settings` — nova tabela | Sprint 1 (bloqueante) | `school_start_date`, `school_target_end_date`, `region_code`, `academic_year` |
| 2 | `school_calendar_event` — nova tabela | Sprint 1 (bloqueante) | `source: AUTO\|MANUAL`, `type: NATIONAL_HOLIDAY\|SCHOOL_BREAK\|EXAM_PERIOD\|OTHER` |
| 3 | `schedule_output.date: Date` — nova coluna | Sprint 1 (bloqueante) | Cada linha = 1 aula num dia específico |
| 4 | `schedule_output.is_draft: Boolean` — nova coluna | Sprint 1 | Default: False |
| 5 | `class.projected_end_date: Date` — nova coluna | Sprint 1 | Output do solver |
| 6 | `lesson_occurrence` — nova tabela | Sprint 2 | FK `schedule_output_id ON DELETE SET NULL` |
| 7 | `substitution.substitute_subject_id` — nova coluna | Sprint 2 | Nullable — só preenchido se SUBSTITUTED |
| 8 | Remover `class.start_date` do plano | — | ⚠️ `Class` usa `start_year`/`end_year` (inteiros, ex: 25, 28) — esses FICAM. A nota refere-se a hipotética coluna `start_date` (Date completa) que nunca deve existir. `OrganizationSettings.school_start_date` é o início real das aulas. |
| 9 | `class.is_archived: Boolean` — nova coluna | Sprint 0 | Default `False`; set `True` automaticamente quando `end_year < current_year` e todos os módulos completos |

---

*Documento elaborado com base nas discussões de arquitetura de Março de 2026.*
*Versão 1.5 — Q15-Q21 todas decididas (D20-D26). Plano 100% completo. Sem questões em aberto.*
*Próximo passo: Sprint 0 — Expandir página de Configurações + migrações 1-9 + iniciar Sprint 1.*
