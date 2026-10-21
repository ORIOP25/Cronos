# Registo de engenharia — Gerador com prioridades

## Purpose

Este registo conta como o gerador com prioridades foi construído, calibrado e corrigido entre 19 e 21 de outubro de 2026.
Regista as decisões boas e as más, as medições de cada versão e o processo de teste.
Serve para trabalhar sobre o gerador sem repetir os mesmos erros.

O comportamento atual vive no [spec](SCHEDULE_PRIORITIES_TECH_SPEC.md) e no código. Este registo explica o caminho até lá.

## Intended Reader

Engenheiros e agentes que alteram `backend/app/scheduler/`, e o responsável de produto.

## Prerequisites

- Leia o [Tech Spec — Prioridades do horário](SCHEDULE_PRIORITIES_TECH_SPEC.md), sobretudo T06–T15, D16 e as invariantes I02, I03 e I05.
- Leia o [Scheduler Engine](README.md).
- Os comandos vivem na [Command Reference](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type), incluindo o "Priority benchmark".

## What the System Does

### O gerador hoje

1. A construção percorre o ano período a período (`constructive.py` `_construct_pass`).
2. Em cada período, cada opção recebe um valor inteiro calculado com os níveis da escola (T06).
3. O modelo CP-SAT `_select_period` escolhe as opções pela ordem: horas necessárias, urgência (T09), preenchimento (T11) e valor.
4. A primeira passagem é estrita: recusa um Evitar enquanto o recurso ainda tem horas livres (T08).
5. Se falha, corre a passagem relaxada. Se também falha, corre a passagem de preenchimento (T11). Por fim, a construção sem pesos.
6. Numa atualização, a reparação local (`recovery_construction.py`) e a reconstrução competem. Ganha o menor custo da T13 (T12).

### Escola de referência

A calibração usa só a escola piloto realista: [`lab/realistic_pilot.py`](../../backend/app/scheduler/lab/realistic_pilot.py), cenário `pilot-real`.
A fixture é a fonte dos números (turmas, professores, salas, disponibilidades). Não os copie para documentos.
O responsável de produto descreveu-a a 20 de outubro de 2026 e abandonou o ficheiro piloto original a 21 de outubro ("não são minimamente realistas").

## Why the Behavior Exists

### Como a versão de 21 de outubro melhorou todas as métricas

A melhoria veio de um erro na regra de presença dos professores, não de uma nova calibração ([#180](https://github.com/ORIOP25/Cronos/pull/180)).

- Antes: em cada período, a escolha das opções acontecia antes da verificação da presença.
- Uma aula de um professor com mínimo de presença era escolhida e depois descartada, porque a presença não fechava nesse dia.
- A turma dessa aula ficava sem aula nesse período, apesar de ter outra disciplina disponível.
- Esses buracos viravam tempos livres e dias com uma só aula. Também empurravam horas para mais tarde no ano.
- Agora, uma opção cuja presença não pode fechar sai antes da escolha. A turma e o professor ficam livres para outra disciplina.

O mesmo erro impedia a construção sem pesos de acabar a escola realista: ficavam 5 horas por dar.
A paragem antecipada ([#178](https://github.com/ORIOP25/Cronos/pull/178)) não muda o horário: só poupa tempo.
A janela da passagem estrita ([#179](https://github.com/ORIOP25/Cronos/pull/179)) só muda as atualizações. Na geração, `eligible_periods` em `domain/capacity.py` já corta na data preferida.

## Components and Ownership

| Peça | Onde | O que decide |
| :--- | :--- | :--- |
| Níveis, multiplicadores e custos unitários | `domain/priorities.py` | Quanto vale cada critério face aos outros. |
| Valor de uma opção | `domain/priority_value.py`, `constructive.py` `_option_measures` | Usado na geração e nas atualizações (T06). |
| Métricas e custo de um horário | `domain/priority_metrics.py` | Resumo da proposta e escolha da atualização (T12, T13). |
| Urgência e Evitar necessário | `domain/availability_priority.py` | Quem é servido primeiro e quando um Evitar é inevitável. |
| Passagens de construção | `infrastructure/constructive.py`, `recovery_construction.py` | Estrita, relaxada, preenchimento. |
| Escolha da atualização | `infrastructure/search.py` `search_adaptive_schedule` | Reparação local ou reconstrução. |
| Banco de ensaio | `lab/priority_bench.py`, `lab/realistic_pilot.py` | Medição repetível das 11 métricas. |

## Data or Request Flow

### Processo de trabalho usado

1. Descrever o pedido como comportamento observável e confirmar com o responsável de produto só as decisões de produto.
2. Criar uma worktree por correção a partir de `origin/main` e copiar os `.env` do checkout principal.
3. Escrever primeiro o teste que falha. Registar o vermelho e o verde no corpo do commit.
4. Correr os testes focados, depois `fast --scope backend -- -k scheduler`, depois `integration -- -k scheduler`.
5. Medir a escola realista localmente, no contentor de testes do backend, nunca na Railway.
6. Abrir o pull request com o comportamento, a prova, as limitações e as perguntas abertas.
7. Fazer merge só com `backend`, `frontend`, `e2e-runtime` e `e2e-browser` verdes.

Os agentes Haiku 5.5 (esforço alto) implementaram cada correção com instruções fechadas: ficheiros, testes, provas e limites.
O coordenador reviu cada diff antes do pull request. Essa revisão apanhou dois erros (ver [Más decisões](#más-decisões)).

### Como medir

- Geração: o comando "Priority benchmark" da [Command Reference](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type) com `--scenario pilot-real --profile recommended`.
- Atualização: ainda não existe cenário de atualização no banco de ensaio. Os ensaios usaram um script local que:
  1. carrega um horário gerado e publicado (`candidate_from_dict`);
  2. acrescenta blocos Impossível a um professor sem mínimo de presença;
  3. chama `search_adaptive_schedule` com `ADAPTIVE_RECOVERY` e `stop_at_first_complete=True`;
  4. mede as aulas alteradas com `measure_disruption` e as 11 métricas com `measure_priority_metrics`.
- Para ver os dois candidatos da atualização, envolva `priority_cost` em `search.py` e escreva o custo e as métricas de cada candidato.

### Como ler as medições

- As métricas são deterministas (I03). Pode compará-las mesmo com a máquina ocupada.
- O tempo não é determinista. Outros contentores do solver a correr ao mesmo tempo multiplicam-no por cerca de 1,7.
- Compare tempos só entre corridas com a mesma carga, ou com a máquina parada.
- Apresente os resultados ao responsável de produto em totais e por pessoa (por professor, por turma, por semana), sempre ao lado da versão anterior.

## Contracts and Invariants

Estas regras saíram de erros reais e devem continuar a valer:

- **I02:** sem pesos, a construção é a de antes, exceto correções de erros declaradas. Os resumos fixados em `test_scheduler_typology_v1.py` provam-no.
- **I03:** a mesma entrada dá o mesmo horário. Os orçamentos de reparação com pesos são determinísticos (`PERIOD_REPAIR_DETERMINISTIC_TIME`).
- **I05:** um critério em Ignorar não tem efeito. Nenhuma regra de escolha pode dar prioridade absoluta a um critério.
- Os custos unitários de `UNIT_COSTS` também entram no valor das opções da geração. Mudar um custo para corrigir a escolha da atualização muda a geração.
- Uma escolha entre candidatos precisa de todas as grandezas na mesma moeda. Minutos, dias e aulas não se comparam sem um custo unitário pensado.

## States and Transitions

### Medições da geração (escola realista, níveis recomendados)

Valores totais da escola. Tempo medido localmente.

| Versão | Última aula | Tempos livres prof. | Tempos livres turmas | Dias de 1 aula prof. | Dias de 1 aula turmas | Evitar prof. | Evitar turmas | Mudanças de sala | Mudanças semanais | Ritmo (dias) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fa32df4d` (#175) | 14 jun | 1 466 h | 973 h | 88 | 42 | 3 770 h | 893 h | 6 622 | 13 929 | 1 054 |
| `307baf00` (#178) | igual | igual | igual | igual | igual | igual | igual | igual | igual | igual |
| `d91eed5b` (#180) | 9 jun | 1 400 h | 901 h | 79 | 35 | 3 768 h | 914 h | 6 292 | 12 904 | 1 031 |
| `e4874e40` (#180 + #179) | igual | igual | igual | igual | igual | igual | igual | igual | igual | igual |

As linhas iguais provam a origem da melhoria: só o #180 mudou o horário gerado.
Tempo: cerca de 14 minutos com a máquina parada. O #178 baixou uma corrida com carga de 1 475 s para 1 310 s.

### Medições da atualização

Cenário A: um professor fica Impossível de 1 a 12 de março de 2027 (63 aulas afetadas).

| Versão | Escolhido | Última aula | Aulas mudadas | Mudanças de sala |
| :--- | :--- | :--- | :--- | :--- |
| Sem pesos | reparação local | 14 jun | 63 | 51 |
| Com pesos, `fa32df4d` | reconstrução | 30 jul | 34 992 | 3 028 |
| Com pesos, #179 | reparação local | 14 jun | 63 | 46 |

Cenário B: um professor fica Impossível todas as quartas-feiras, de março ao fim do ano (77 aulas afetadas).
Foi escolhido para que a escolha fique equilibrada: a reparação local atrasa o fim, a reconstrução não.

| Candidato | Última aula | Aulas alteradas | Escolhido com a data primeiro | Escolhido com o atraso no custo (#179) |
| :--- | :--- | :--- | :--- | :--- |
| Reparação local | 22 jun | 250 | não | sim |
| Reconstrução | 9 jun | 37 791 | sim | não |

### Taxas de troca da atualização

O responsável de produto delegou esta decisão a 21 de outubro de 2026. Os valores vivem em `domain/priorities.py`.

- Uma aula mudada vale uma hora de Evitar de um professor, a níveis iguais (`UNIT_COSTS["update_stability"]`).
- Um dia de atraso depois da data preferida vale 600 aulas mudadas a níveis iguais, e 1 200 com os níveis recomendados (`LATE_DAY_COST`).
- Com os níveis recomendados, a reconstrução só ganha quando a reparação local atrasaria o fim cerca de um mês.
- O atraso entra só na escolha da atualização. `UNIT_COSTS["finish_early"]` não mudou, porque também pesa na geração.

## Failure Modes

### Boas decisões

| Decisão | Porque resultou |
| :--- | :--- |
| Construir uma escola realista fixa e repetível a partir da descrição do responsável de produto. | Revelou erros que a fixture de 48 turmas e o ficheiro piloto escondiam: almoço, presença, salas, horas por dar. |
| Medir as 11 métricas em cada versão e mostrá-las por pessoa. | O responsável de produto decidiu com números que entende. As percentagens soltas não ajudavam. |
| Contar os dias com uma só aula por dia inteiro (T10). | Corresponde ao que a escola sente: vir à escola para uma aula. |
| Não contar o almoço como tempo livre e tratar 10 minutos de intervalo como aulas seguidas. | Os tempos livres medidos deixaram de ser inflacionados pela grelha. |
| Comparar a estabilidade semanal com a semana anterior, como a métrica. | Menos 45% de mudanças semanais. |
| Passagem de preenchimento (T11) antes da construção sem pesos. | A escola realista não se constrói sem pesos; o preenchimento salva a geração com pesos. |
| Testar as atualizações na escola realista, não só a geração. | Revelou que uma atualização mudava o ano inteiro. |
| Testar a regra de escolha com um segundo cenário, equilibrado. | Revelou que a primeira correção dava prioridade absoluta à data. |
| Ordem de merge: motor primeiro, ecrã depois do deploy do motor. | O ecrã nunca grava níveis que o servidor ainda não usa. |

### Más decisões

| Decisão | O que correu mal | Lição |
| :--- | :--- | :--- |
| Calibrar primeiro com o ficheiro piloto original. | O responsável de produto rejeitou-o como irrealista; a calibração foi refeita. | Confirmar os dados de referência antes de calibrar. |
| Medir memória com `tracemalloc` no banco de ensaio. | Cada corrida demorou várias vezes mais; o responsável de produto esperou 45 minutos. | Medir memória pelo RSS do processo. |
| Custos da T13 em unidades diferentes (minutos de Evitar × 20, aulas × 1, dias × 1). | Uma atualização de duas semanas escolheu uma reconstrução com 34 992 aulas mudadas e fim a 30 de julho. | Pôr todas as grandezas na mesma moeda: 1 aula mudada = 1 hora de Evitar, a níveis iguais. |
| Passagem estrita com pesos podia usar o verão até à data limite. | Fugia ao Evitar empurrando aulas para julho. | Limitar a passagem estrita à data preferida; a relaxada usa o resto. |
| Primeira correção da escolha: a data de fim decide sempre primeiro. | Com uma semana de atraso, reconstruía o horário de todos (37 791 aulas). Violava a I05. | Pôr o atraso no custo, por dia, multiplicado pelo nível do critério 1. |
| Perguntas ao responsável de produto com rótulos internos (R07, D5). | Duas perguntas não foram percebidas. | Explicar com tabelas simples, por pessoa, sem rótulos internos. |
| Merge de um pull request enquanto a sessão ainda empurrava commits. | Um commit de limpeza ficou fora do `main`. | Avisar a sessão antes do merge e confirmar o commit final. |

### Erros de ambiente que custaram tempo

- Um processo lançado com `&` num shell em primeiro plano morre com o shell. Use a execução em segundo plano da ferramenta.
- Uma stack E2E órfã segura a porta 5174. Desligue-a com `docker compose -p <projeto> down --volumes`.
- `npm update` reescreve o lockfile inteiro. Para um aviso de segurança, altere só a entrada afetada.
- `pip-compile` precisa de `HOME` e de uma pasta de cache com permissão de escrita dentro do contentor.

## Verification Procedure

Antes de mudar o gerador:

1. Gere a escola realista com o código atual e guarde as 11 métricas e o tempo.
2. Faça a mudança com TDD e os testes focados.
3. Corra `fast --scope backend -- -k scheduler` e confirme que os resumos sem pesos não mudaram (I02).
4. Gere outra vez e compare as 11 métricas com o passo 1.
5. Se a mudança toca atualizações, corra os cenários A e B e compare o candidato escolhido.
6. Corra o R24 da escola realista (`-m slow_solver -k realistic`); demora cerca de 20 minutos.
7. Escreva a tabela antes/depois no pull request, em totais e por pessoa.

## Source Map

- [`domain/priorities.py`](../../backend/app/scheduler/domain/priorities.py), [`domain/priority_metrics.py`](../../backend/app/scheduler/domain/priority_metrics.py), [`domain/availability_priority.py`](../../backend/app/scheduler/domain/availability_priority.py)
- [`infrastructure/constructive.py`](../../backend/app/scheduler/infrastructure/constructive.py), [`infrastructure/recovery_construction.py`](../../backend/app/scheduler/infrastructure/recovery_construction.py), [`infrastructure/search.py`](../../backend/app/scheduler/infrastructure/search.py)
- [`lab/priority_bench.py`](../../backend/app/scheduler/lab/priority_bench.py), [`lab/realistic_pilot.py`](../../backend/app/scheduler/lab/realistic_pilot.py)
- Testes: `backend/tests/unit/test_scheduler_weighted_construction_v1.py`, `test_scheduler_recovery_construction_v1.py`, `test_scheduler_search_fallback_v1.py`, `test_scheduler_realistic_pilot_v1.py`, `test_scheduler_typology_v1.py`

## Related Documents

- [Tech Spec — Prioridades do horário](SCHEDULE_PRIORITIES_TECH_SPEC.md)
- [WBS — Prioridades do horário](SCHEDULE_PRIORITIES_WBS.md)
- [Scheduler Engine](README.md)
- [Tech Spec — Prioridade a quem tem pouca disponibilidade](AVAILABILITY_PRIORITY_TECH_SPEC.md)
