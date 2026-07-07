# Algoritmo do Gerador de Horários (Ensino Profissional)

> Historical note: this document describes the legacy weekly-pattern scheduler and
> is not authoritative for the current beta scheduler. Use
> `documentation/03_scheduler_engine/PRD_SCHEDULE_GENERATOR_NEW_BASELINE.md` and
> `documentation/03_scheduler_engine/TECH_SPEC_SCHEDULE_GENERATOR_NEW_BASELINE.md`
> for current generation behavior. In particular, current generation is
> draft-first, school-year scoped, and schedules subject-level remaining demand;
> module/UFCD metadata is sequential accounting, not a placement driver.

## Objetivo de Negócio
Gerar um padrão semanal viável para Ensino Profissional, respeitando progressão por módulos (UFCD/Módulos), disponibilidade docente, tipo de sala e regras operacionais da escola.

## Pipeline Técnico
1. Fetch: carrega turmas ativas, lições, módulos, progresso, salas, timeslots, disponibilidade e calendário.
2. Solve: CP-SAT encontra padrão semanal (lição x timeslot x sala).
3. Expand: converte padrão semanal para datas reais até ao alvo do ano letivo.
4. Save: grava ScheduleOutput e atualiza projected_end_date das turmas.

## Princípios do Ensino Profissional
- O planeamento é dinâmico (semanal/quinzenal), não fixo anual.
- O progresso é por módulo, não só por disciplina.
- O solver agenda apenas lições com minutos remanescentes.
- A expansão para datas para quando os minutos remanescentes chegarem a zero.

## Hard Constraints (Obrigatórias)
- HC1: Uma sala não pode ter duas lições no mesmo timeslot.
- HC2: Um professor não pode estar em dois sítios no mesmo timeslot.
- HC3: Uma turma não pode ter sobreposição de aulas.
- HC4: A lição só pode usar sala do tipo exigido pela disciplina.
- HC5: Timeslots com disponibilidade IMPOSSIBLE (-1) são proibidos.
- HC6: Limite máximo semanal por lição = 900 min (15 horas).
- HC7: Lição ativa tem pelo menos 1 sessão e cumpre minutos mínimos semanais.
- HC8: Janela de almoço é bloqueada como restrição dura (sem aulas nesse intervalo).

## Soft Constraints (Objetivo)
- Penaliza slots EVITAR (score=0).
- Penaliza ausência em slots PREFERIDOS (score=2).
- Em modo repair, penaliza alterações ao padrão ativo anterior.
- Penaliza dispersão por muitos dias para cada turma.
- Penaliza furos internos de turma (slots vazios entre aulas do mesmo dia).
- Penaliza furos internos de professor (slots vazios entre aulas do mesmo dia).
- Recompensa sessões agendadas para aumentar preenchimento viável.

## Configuração de Janela de Almoço
Campos em OrganizationSettings por ano letivo:
- lunch_window_start
- lunch_window_end
- lunch_min_duration_minutes

Comportamento:
- Se start/end não estiverem definidos, aplica default 12:00-14:00.
- A validação garante que fim > início e coerência da janela.
- O solver bloqueia qualquer timeslot que sobreponha a janela ativa.

## Escalonamento e Robustez
- Seleção de OrganizationSettings por organização e ano letivo.
- Isolamento por org_id em todo o fluxo.
- Minutos semanais mínimos calculados por horizonte real (planning weeks).
- Preflight valida dados críticos antes de arrancar o Celery task.

## Métricas Operacionais Recomendadas
- Taxa de preenchimento semanal por turma.
- Minutos remanescentes por lição após cada geração.
- Número médio de furos por turma/professor.
- Percentagem de uso de slots EVITAR.
- Duração média de execução do solver.
