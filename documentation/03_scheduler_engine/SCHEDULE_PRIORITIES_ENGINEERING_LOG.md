# Registo de engenharia — Gerador com prioridades

## Purpose

Este registo conta como o gerador com prioridades foi construído, calibrado e corrigido entre 19 e 22 de outubro de 2026.
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
   Uma hora só fica vazia quando o valor, somado ao custo de escassez do calendário, não é positivo (T07).
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
| #182 (sliders) | 8 jun | 1 459 h | 1 026 h | 68 | 30 | 3 535 h | 884 h | 6 712 | 12 244 | 991 |

As linhas iguais provam a origem da melhoria: só o #180 mudou o horário gerado.
O #182 troca 0,8 h de tempos livres por professor e 2,6 h por turma por menos Evitar, menos dias de uma só aula e menos mudanças semanais.
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

### Campanha dos sliders (21 e 22 de outubro de 2026)

O objetivo do item 8 é que cada escola equilibre os critérios com os seus níveis, sem que nenhum ganhe sempre.
A campanha mediu esse objetivo na escola realista.
Cada critério da geração correu em Ignorar e em Prioridade máxima, com os outros nos valores recomendados.
Correram também "tudo Importante" e o caso de verificação do spec ("Acabar cedo" em Ignorar com "Tempos livres das turmas" no máximo).
O critério 11 correu nos cenários de atualização A e B.

Critério próprio de cada slider (Ignorar / recomendado / máximo), antes e depois do #182:

| Slider | Antes (`fd932b01`) | Depois |
| :--- | :--- | :--- |
| Acabar cedo (última aula) | sem horário em 1 h / 9 jun / — | 15 jun / 8 jun / — |
| Tempos livres dos professores (h por professor) | 95,4 / 20,3 / 17,0 | 95,5 / 21,1 / 16,5 |
| Tempos livres das turmas (h por turma) | 27,7 / 18,8 / 10,8 | 31,2 / 21,4 / 12,2 |
| Dias de uma só aula dos professores | 760 / 79 / 71 | 719 / 68 / 76 |
| Dias de uma só aula das turmas | 136 / 35 / 28 | 106 / 30 / 25 |
| Evitar dos professores (h por professor) | 68,8 / 54,6 / 54,6 | 69,7 / 51,2 / 51,2 |
| Evitar das turmas (h por turma) | 22,1 / 19,0 / 20,2 | 22,2 / 18,4 / 18,0 |
| Mesma sala (mudanças) | 17 510 / 6 292 / 6 407 | 17 995 / 6 712 / 6 532 |
| Estabilidade semanal (mudanças) | 43 371 / 12 904 / 6 251 | 43 520 / 12 244 / 5 677 |
| Ritmo (dias por turma) | 91,4 / 21,5 / 16,0 | 95,7 / 20,6 / 14,1 |
| Poucas mudanças nas atualizações (cenário B) | reconstrução / reparação / reparação | reconstrução / reparação / reparação |

"Acabar cedo" em Importante, antes: fim a 15 jun, mas 31,2 h de tempos livres por turma e 65,8 h de Evitar por professor. Tudo piorava.
Depois: fim a 11 jun, 19,6 h de tempos livres por professor e 53,6 h de Evitar por professor.
Em Ignorar, depois: fim a 15 jun (D14), 18,7 h de tempos livres por professor, em cerca de 15 minutos.
O caso de verificação do spec dá 12,7 h de tempos livres por turma, contra 21,4 h no recomendado.

#### Causas encontradas

1. **Hora vazia tratada como grátis (T07).** Uma opção com valor ≤ 0 deixava a hora vazia. Numa escola apertada a aula tem de entrar mais tarde, quase sempre pior. Só o "Acabar cedo" empurrava para dar a aula. Ao baixá-lo, os tempos livres das turmas duplicavam em todos os meses, não só no fim do ano.
2. **Medida semanal diferente da métrica (T06).** A métrica compara com o dia letivo anterior e conta uma posição vazia como mudança. A medida comparava com a última semana que tinha aula na posição e só penalizava uma disciplina diferente. Por isso preferia deixar horas vazias.
3. **Custos unitários (T15).** Depois das duas correções, os níveis recomendados ficavam a acabar a 4 jun com mais tempos livres. Os custos unitários foram reescalados para manter os níveis do ecrã e cumprir os alvos do responsável de produto.

#### Experiências rejeitadas

| Experiência | Resultado | Lição |
| :--- | :--- | :--- |
| Necessidade com um período de antecedência | Quase sem efeito; o recomendado piorou um pouco. | A hipótese "aperto no fim do ano" estava errada; os dados mês a mês mostraram o problema todo o ano. |
| Admitir sempre a aula que continua um bloco | Tempos livres dos professores subiram para 47–49 h. | Continuar o bloco da turma abria buracos ao professor. |
| Continuar o bloco só sem criar buracos | Resultados mistos. | Não resolvia a causa. |
| Evitar no limiar da passagem relaxada | A passagem relaxada falhou; o preenchimento deu 46 h de tempos livres por professor. | Uma regra que deixa horas vazias tem de saber quando há folga. |
| Escassez em "Acabar cedo" Ignorar só acima de 9/10 de ocupação | As turmas da escola realista estão a cerca de 8/10; fim a 3 jun e 48,6 h de tempos livres por professor (passagem de preenchimento). | A escassez em Ignorar tem de crescer de forma contínua: zero até meia ocupação, completa com o calendário cheio. |
| Escassez em "Acabar cedo" Ignorar com a mesma regra de ritmo da necessidade | Um recurso novo fica atrás do ritmo depois de qualquer hora vazia; o teste de D14 falhava. | O ritmo linear não mede folga; a ocupação mede. |
| Relaxar só quem falha na passagem estrita | Não implementada: no dia 3 jun, 47 de 48 turmas e 50 professores ainda tinham horas. | Numa escola apertada, recusar todo o Evitar atrasa a escola inteira. |

#### Como avaliar

- Compare o critério próprio de cada slider em Ignorar, recomendado e máximo, e os efeitos nos outros.
- O custo da T13 não serve sozinho para avaliar a geração. Conta mudanças semanais, dias de uma só aula e mudanças de sala em unidades, e a T06 conta-os em minutos de aula.
- Verificar se o horário de um perfil é o melhor de todos pelos seus próprios pesos também falha como critério. A construção é gulosa e não otimiza o custo global.

#### Limitações que ficam

- "Evitar dos professores" em Muito importante e em Prioridade máxima dá o mesmo horário. A passagem estrita falha sempre nesta escola e a relaxada só ordena por Evitar.
- "Ritmo das disciplinas" em Ignorar piora os outros critérios. O ritmo ajuda a construção a espalhar as disciplinas pelo ano.
- "Dias de uma só aula dos professores" em Prioridade máxima fica ligeiramente pior do que no recomendado (76 contra 68).
- Os tempos livres dos professores no recomendado subiram 0,8 h por professor por ano, acima do alvo de 0,5 h.

### "Acabar cedo" deixa de ser configurável (22 de outubro de 2026)

A campanha mostrou que baixar "Acabar cedo" só comprava cerca de 2 h de tempos livres por professor por ano.
Em troca, as turmas ganhavam 8 h de tempos livres, os professores 2 h de Evitar, e perdia-se uma semana de margem antes da data de fim.
O responsável de produto decidiu acabar com o slider (D19, [#183](https://github.com/ORIOP25/Cronos/pull/183)): o gerador acaba sempre o mais cedo possível, para deixar margem para recuperar faltas e ocorrências.
A escola escolhe os outros 10 critérios. O motor continua a medir a data da última aula.

### Velocidade

Perfil da escola realista com os níveis recomendados, com cProfile. O perfil torna a corrida cerca de 2 vezes mais lenta.

| Parte | Tempo | Peso |
| :--- | :--- | :--- |
| Passagem estrita (falha a 3 jun) | 1 366 s | 56% |
| Passagem relaxada (dá o horário) | 1 030 s | 42% |
| `_select_period` (as duas passagens) | 726 s | 30%, dos quais 174 s a resolver e o resto a montar o modelo em Python |
| `option_value` | 328 s | calculado uma vez por sala, quando só a sala da turma depende da sala |
| `open_rooms` | 321 s | salas livres e indisponibilidades |
| `presence_run` | 270 s | o filtro antes da escolha e a colocação planeiam a mesma presença |

Sinal da passagem estrita, medido no início de cada semana. "Atrasados" são os recursos atrás do ritmo linear; "atraso" é a soma das horas em falta face a esse ritmo.

| Escola | Passagem estrita | Início de outubro | Depois |
| :--- | :--- | :--- | :--- |
| Realista (horas × 1,0) | falha a 3 jun | 19 atrasados, 24 h | 68 h em novembro, até 174 h |
| Horas × 0,85 | tem sucesso | 3 atrasados, 2 h | ≤ 2 h |
| Horas × 0,70 | tem sucesso | 1 atrasado, 1 h | ≤ 1 h |
| Horas × 0,55 | tem sucesso | 0 | 0 h |

Com a data preferida 2 ou 4 semanas mais tarde, a passagem estrita da escola realista continua a falhar.

O modelo de cada período devolveu a escolha rápida em 2 553 de 2 645 chamadas (99%). Essas chamadas gastaram quase todo o tempo do modelo.

Plano aprovado pelo responsável de produto: desistir cedo da passagem estrita condenada; cortar trabalho repetido sem mudar nenhuma aula; usar o modelo só quando pode melhorar.
Cada passo entra com os horários provados iguais (impressão digital de todas as aulas em seis casos) ou com a qualidade medida.

#### Passo 1: desistir cedo da passagem estrita

A passagem estrita com pesos desiste quando duas verificações semanais seguidas mostram pelo menos 10% dos recursos atrás do ritmo e 10 h de atraso (limiares em `availability_priority.py`). A relaxada vem a seguir.
Na escola realista desiste a 28 de setembro de 2026, em vez de 3 de junho de 2027. Nas escolas com 85% e 70% das horas não desiste.

Prova de horários iguais (impressão digital de todas as aulas):

| Caso | `main` | Com o passo 1 |
| :--- | :--- | :--- |
| Recomendado | `61fc5fb0ee3f99f3` | igual |
| Tempos livres dos professores no máximo | `53dca1005caaeef6` | igual |
| Recomendado com 70% das horas | `34aa991e603aa9c7` | igual |
| Atualização às quartas, critério 11 em Ignorar | reconstrução, 35 520 aulas mudadas, fim a 16 jun | igual |
| Atualização de março | reparação, 63 aulas mudadas, 41 mudanças de sala | igual |

Tempo da reconstrução numa atualização, nas mesmas condições: 919 s → 511 s.

#### Passo 2: cortar trabalho repetido

Três mudanças, sem mudar nenhuma aula.
- O valor de cada opção sem a medida da sala de origem calcula-se uma vez por opção. Cada sala só soma a sua parte. A mesma regra vale na reconstrução de atualizações.
- O modelo de reparação de cada período usa a API `snake_case` do OR-Tools e uma só expressão `weighted_sum` para o objetivo. Um período vazio mantém o objetivo constante de antes.
- A medição de presença não foi guardada em cache. Só a colocação repetia as chamadas das opções escolhidas, uma pequena parte das chamadas do filtro. O ganho estimado era menor que 1%.

Prova de horários iguais (impressão digital de todas as aulas, `digest.py` no `main` e no ramo):

| Caso | `main` | Com o passo 2 |
| :--- | :--- | :--- |
| Recomendado | `61fc5fb0ee3f99f3` | igual |
| Tempos livres dos professores no máximo | `53dca1005caaeef6` | igual |
| Estabilidade semanal no máximo | `004684d7388854c6` | igual |
| Salas próprias e tempos livres das turmas | `c87552c238903b36` | igual |
| Recomendado com 70% das horas | `34aa991e603aa9c7` | igual |
| Ritmo das disciplinas em Ignorar | `abf8fa425fc9c2b8` | igual |

Tempo no mesmo instante, recomendado, duas corridas em paralelo: `main` 388 s, ramo 350 s (cerca de 10% mais rápido). Ambas as corridas partilham a máquina, por isso o número é relativo. Uma corrida isolada do ramo levou 266 s, mas não há medição isolada do `main` sem outras corridas.
Os testes `-k "scheduler or priorities"` passaram: 858 testes.

#### Limpeza (22 de outubro de 2026)

Limpeza do que sobrou de "Acabar cedo", sem mudar nenhuma aula.
- Saiu o caminho de espalhar aulas (D14, T07). A escassez usa sempre `t`. `_scarcity` deixou de receber `spread`, e os dois chamadores (`constructive.py` e `recovery_construction.py`) deixaram de o passar.
- Testes removidos, porque só pinavam o caminho que saiu: `test_all_zero_priorities_spread_one_lesson_every_other_week` (D14, tudo em zero) e `test_at_half_booked_an_empty_hour_stays_empty_at_finish_early_zero` (meio ocupado). O teste de três quartos deu lugar a `test_scarcity_is_the_tightness_times_the_unit_cost_with_no_spread`, que falhou antes da mudança (`TypeError`, o argumento `spread` já não existe) e passa depois. O teste de turma lotada passou a usar o nível por defeito, porque deixou de depender de `finish_early` zero.
- Saiu o perfil `finish-early-ignore` de `lab/priority_bench.py`.
- Saiu código sem uso: `assignment_physical_minutes` (`annual_model.py`), `gap_and_availability_cost_minutes` (`quality.py`) e o parâmetro `lessons` de `_choose_rooms` (`room_assignment.py`).
- Especificação: T07 e T15 perdem as frases sobre Ignorar, e sai a linha R05 ("Ignorar tudo"), que descrevia o teste removido.
- A passagem de Acabar cedo em Ignorar fica só no histórico desta secção. Não há mais caminho em produção.

Prova de horários iguais (`digest.py` no ramo, seis casos):

| Caso | `main` | Ramo |
| :--- | :--- | :--- |
| Recomendado | `61fc5fb0ee3f99f3` | igual |
| Tempos livres dos professores no máximo | `53dca1005caaeef6` | igual |
| Estabilidade semanal no máximo | `004684d7388854c6` | igual |
| Salas próprias e tempos livres das turmas | `c87552c238903b36` | igual |
| Recomendado com 70% das horas | `34aa991e603aa9c7` | igual |
| Ritmo das disciplinas em Ignorar | `abf8fa425fc9c2b8` | igual |

Tempo e memória, recomendado, uma corrida de cada vez, na mesma máquina:
- `main`: 358 s, pico de RSS 242 852 KB.
- Ramo: 340 s, pico de RSS 242 844 KB.

A diferença fica dentro do ruído de uma corrida. Esta limpeza não é uma otimização medida. Uma corrida anterior do `main`, feita com outro contentor a correr, levou 516 s, por isso não é comparável.

Coleta de lixo: depois da corrida, `gc.collect()` devolveu 0 objetos inalcançáveis. Por isso o worker não ganha nada com `gc.collect()` depois de cada tarefa, e nada foi acrescentado. O worker já recicla o processo filho (ver [o relatório de memória](../09_ops_observability/SERVER_MEMORY_AUDIT_2026-10-18.md)).

Não foi feito (cada item com o motivo):
- Complexidade cognitiva de `_construct_pass`: refatoração grande, fora do âmbito de uma limpeza.
- `PriorityWeights` ainda aceita `finish_early` zero, quando construído diretamente. Apertar a validação mudaria testes de domínio; a escola já não consegue escolher esse valor, porque `school_priority_weights` fixa 4.
- Perfil `class-gaps-maximum` do laboratório ainda usa `finish_early` 1, um nível que a escola já não escolhe. Fica para não mudar a referência do laboratório.
- Avisos ARG restantes: a assinatura do ouvinte do SQLAlchemy (`models.py`) e a porta do despachante (`task_dispatcher.py`) têm argumentos fixos. Não são código morto.
- Auxiliares usados só por testes (`build_recovery_case`, `candidate_digest`, `total_physical_minutes` e outros) ficam, porque os testes os usam para fixar digests e contratos.
- Passo 3 da velocidade (usar o modelo por período só quando melhora a escolha; estimativa de 5,2 para cerca de 4 min) fica como opção futura. O responsável de produto parou-o a 22 de outubro de 2026 em 5,2 min.
#### Unidades do custo da atualização (22 de outubro de 2026)

Problema. A T13 contava dias, trocas de sala e posições alteradas para os quatro critérios de aulas (professor e turma com uma só aula, sala da turma e padrão semanal). A T06 mede os mesmos critérios em minutos de aula. Na atualização, os quatro pesavam cerca de 60 vezes menos do que na geração, para aulas de 60 minutos.

Mudança. `priority_cost` recebe `lesson_minutes` e multiplica esses quatro critérios por ele. Os minutos vêm da duração mais comum da grelha (`typical_lesson_minutes`). Na escola de referência todas as horas da grelha duram 60 minutos. `update_stability` não muda, porque já conta aulas alteradas. `finish_early` e `LATE_DAY_COST` também não mudam.

Medição. Cada cenário correu uma vez com o código novo. A construção não depende do nível de `update_stability` nem da fórmula da T13, por isso o custo de cada nível e de cada fórmula sai das métricas impressas de cada candidato. A fórmula antiga é a mesma com minutos de aula iguais a 1. Verificação: no nível 3, o custo recalculado é igual ao custo impresso pelo código (março: 99 319 784 e 799 373 984; quarta-feira: 401 726 936 e 821 570 360). Em março, no nível 3, a escolha antiga é a reparação com 63 aulas movidas e 41 trocas de sala, como na base.

| Cenário | Nível | Antes | Depois | Aulas alteradas | Fim | Evitar de professor (h) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Março | 0 | reconstrução | reconstrução | 38 291 | 9 jun 2027 | 2 254 |
| Março | 1 | reparação | reparação | 104 | 14 jun 2027 | 3 779 |
| Março | 2 | reparação | reparação | 104 | 14 jun 2027 | 3 779 |
| Março | 3 | reparação | reparação | 104 | 14 jun 2027 | 3 779 |
| Março | 4 | reparação | reparação | 104 | 14 jun 2027 | 3 779 |
| Quartas | 0 | reconstrução | reconstrução | 38 253 | 16 jun 2027 | 2 224 |
| Quartas | 1 | reconstrução | reconstrução | 38 253 | 16 jun 2027 | 2 224 |
| Quartas | 2 | reparação | reparação | 247 | 28 jun 2027 | 3 779 |
| Quartas | 3 | reparação | reparação | 247 | 28 jun 2027 | 3 779 |
| Quartas | 4 | reparação | reparação | 247 | 28 jun 2027 | 3 779 |

Resultado. Nenhuma escolha mudou nos dez pares de cenário e nível. Em cada um, a fórmula antiga e a nova escolhem o mesmo candidato. Aulas alteradas conta movidas e trocas de sala. A reparação de março tem 63 movidas e 41 trocas de sala. A reparação das quartas tem 77 movidas e 170 trocas de sala. A reconstrução das quartas tem 38 253 alteradas, sem a divisão entre movidas e trocas.

Limitações. A reconstrução das quartas não tem a divisão entre movidas e trocas nos registos, por isso não se pode confirmar o total de 35 520 movidas da base. As horas de Evitar são a soma de `teacher_preferences` dividida por 60.

#### Furos das turmas por dia (23 de outubro de 2026)

O responsável de produto viu no horário publicado dias de turma com furos a mais, por exemplo TAS 12 à sexta (9h, três furos e duas aulas à tarde) e TDES 10 à segunda (9h, dois furos, almoço e tarde cheia). A regra de `class_gaps` já define o furo; faltava uma regra que o motor cumprisse.

Primeira tentativa: compactação só depois da construção, sem termo na construção. Movia uma aula de extremidade para uma hora vazia da mesma turma, na mesma data. Dias com dois ou mais furos passaram de 163 para 139 (-15%). Quase todas as recusas eram de professor ocupado noutra turma na hora vazia (528 em 1 000 tentativas) e de almoço do professor (157). Trocar a ordem dos dias não mudou o resultado. A compactação sozinha não chega.

Experiências com o termo de furos (B = 192 por minuto) e com a compactação, que só aceita um movimento quando o professor não ganha furos nem Evitar. Medição: escola realista, níveis recomendados (exceto onde indicado), uma geração por corrida, em série.

| Medida | main | A (48) | B (192) | B1 (furos prof. 2) | B2 (Evitar prof. 2) | B3 (ambos 2) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dias de turma com 0 furos | 6 941 | 7 015 | 7 057 | 7 161 | 7 053 | 7 212 |
| Dias com 1 furo (1 h) | 671 | 743 | 704 | 551 | 739 | 525 |
| Dias com 2 furos (2 h) | 138 | 33 | 1 | 1 | 2 | 1 |
| Dias com 3 ou mais furos | 25 | 1 | 0 | 1 | 0 | 0 |
| Dias de turma com uma só aula | 30 | 36 | 43 | 40 | 46 | 51 |
| Dias de professor com uma só aula | 68 | 76 | 88 | 69 | 72 | 74 |
| Furos dos professores, total (h) | 1 459 | 1 425 | 1 489 | 2 156 | 1 367 | 2 174 |
| Furos dos professores, média por professor (h) | 21,1 | 20,7 | 21,6 | 31,3 | 19,8 | 31,5 |
| Furos dos professores, maior subida num professor (h) | - | +24 | +31 | +52 | +45 | +51 |
| Evitar dos professores, total (h) | 3 535 | 3 639 | 3 605 | 3 433 | 3 557 | 3 439 |
| Evitar dos professores, média por professor (h) | 51,2 | 52,7 | 52,3 | 49,8 | 51,6 | 49,8 |
| Evitar dos professores, maior subida num professor (h) | - | +43 | +55 | +36 | +43 | +49 |
| Furos das turmas, total (h) | 1 026 | 812 | 706 | 556 | 743 | 527 |
| Mudanças de estabilidade semanal | 12 244 | 12 224 | 12 209 | 11 694 | 12 543 | 11 691 |
| Data de fim | 8 jun 2027 | 11 jun 2027 | 11 jun 2027 | 8 jun 2027 | 11 jun 2027 | 4 jun 2027 |
| Segundos | 303 | 307 | 313 | 314 | 317 | 318 |

A escolha. O responsável de produto escolheu a B1: "Sim, avança com a B1: regra dos 2+ furos e furos dos professores em Importante no valor recomendado." A B1 deixa 2 dias de turma com dois ou mais furos, contra 163 no main. O custo aceite é o do professor: a média sobe cerca de 10 horas de furo por professor, e um professor sobe 52 horas. As turmas perdem dias com uma só aula (30 para 40), e os dias de professor com uma só aula ficam em 69, perto dos 68 de main.

Porque é que o termo funciona. A construção percorre as horas por ordem. O termo muda só a admissão de uma opção. Numa turma com aulas às 9h e às 15h, uma aula às 14h em vez das 13h fecha o furo de duas horas. O mesmo gesto pode abrir um furo noutra turma: no dia medido, a turma 1 passou de 2 para 3 horas de furo. A regra vale por turma; por isso o teste de construção só verifica a turma que melhora.

Limitações. A recuperação e a atualização ainda não aplicam o termo nem a compactação. A compactação não move uma aula para uma hora ocupada por outra turma do mesmo professor; isso exige trocas em cadeia, que não entraram.


#### Furos das turmas nas atualizações (23 de outubro de 2026)

A regra da geração passa às atualizações. A reparação local e a reconstrução recebem o termo de furos; a compactação corre sobre as duas antes da escolha e só move aulas futuras editáveis. Cada aula movida paga o preço de uma mudança de `update_stability`, por isso uma mudança só é aceite se ganhar mais do que esse preço. As aulas anteriores a 1 de março de 2027 ficam protegidas, como a janela de estabilidade em produção.

Medição: escola realista (`pilot-real`), horário publicado com os níveis recomendados (`main` 21dae55a, 346 s, data de fim 8 de junho de 2027). Três atualizações: março (um professor Impossível de 1 a 12 de março de 2027), e quartas (um professor Impossível todas as quartas de março a julho) com `update_stability` 3 e 0. Os números só contam o futuro editável, a partir de 1 de março de 2027.

| Medida | Março (main / branch) | Quarta, nível 3 (main / branch) | Quarta, nível 0 (main / branch) |
| :--- | ---: | ---: | ---: |
| Dias de turma com 2 ou mais furos | 23 / 15 | 0 / 0 | 0 / 0 |
| Dias de turma com 0 / 1 / 2 / 3+ furos | 2 395 / 210 / 15 / 8 → 2 398 / 216 / 11 / 4 | 2 379 / 243 / 0 / 0 (igual) | 2 379 / 243 / 0 / 0 → 2 384 / 238 / 0 / 0 |
| Aulas alteradas | 126 / 122 | 10 329 / 10 329 | 10 329 / 10 330 |
| Mudanças de sala | 61 / 55 | 1 076 / 1 076 | 1 076 / 1 076 |
| Furos dos professores, total (h) | 447,0 / 443,0 | 397,0 / 397,0 | 397,0 / 395,0 |
| Furos dos professores, média por professor face a main (h) | - / -0,06 | - / 0,00 | - / -0,03 |
| Dias de professor com uma só aula | 46 / 46 | 34 / 34 | 34 / 34 |
| Evitar dos professores, total (h) | 706,0 / 698,0 | 709,0 / 709,0 | 709,0 / 709,0 |
| Evitar, média por professor face a main (h) | - / -0,12 | - / 0,00 | - / 0,00 |
| Data de fim | 8 jun 2027 / 8 jun 2027 | 7 jun 2027 / 7 jun 2027 | 7 jun 2027 / 7 jun 2027 |
| Fonte escolhida | reparação / reparação | reconstrução / reconstrução | reconstrução / reconstrução |
| Segundos | 244 / 268 | 245 / 260 | 250 / 266 |

Leitura. Nas quartas a regra já estava cumprida em main, porque a reconstrução com pesos recebe o termo desde a geração. Em março, a reparação fica com 15 dias com dois ou mais furos, contra 23 em main, e não chega à redução de 90% que o critério pedia. O motivo é a compactação: só move uma aula de extremidade para uma hora vazia da mesma turma, sem que o professor ganhe furo ou Evitar. Em muitos desses dias a hora vazia é de um professor ocupado noutra turma, ou o movimento aumentaria o Evitar do professor.

Achado. Pela contagem por horário feita pela coordenação, 13 dos 19 dias ruins restantes caem nas semanas de falta (1 a 12 de março de 2027). São buracos deixados pelo professor ausente, e não furos que a atualização cria em turmas normais. As substituições tratam esses buracos. A contagem por dia de turma desta tabela (15) é outra medida e não se soma com a contagem por horário.

Decisão. O responsável de produto aceitou o resultado como está: "Sim, faz o merge como está. Os buracos da falta resolvem-se com substituições."

Limitações. A compactação não move uma aula para uma hora ocupada por outra turma do mesmo professor; isso exige trocas em cadeia, que não entraram. As quartas não mudam porque o caminho escolhido já era a reconstrução com o termo.

#### Lições

- Um script chamado `profile.py` esconde o módulo `profile` do Python e parte o cProfile. Use outro nome.
- `python -I` ignora o `PYTHONPATH` e não encontra o pacote `app`.
- O cProfile mede onde está o tempo, mas não quanto dura uma corrida normal.

### Dias curtos e modelo semanal (26–27 de outubro de 2026)

As medições são locais, no contentor de testes do backend. A escola real é a entrada de produção do piloto, lida só em leitura e gerada localmente. Os números são totais da escola. Os comandos estão na [Command Reference](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type).

#### Regras do responsável de produto (26 de outubro de 2026)

- Um dia de turma tem 0 aulas ou pelo menos 3. Duas aulas cedo e uma às 17h não podem existir.
- A grelha de produção não tem a aula das 17h00–18h00. Os intervalos de 10 minutos empurram a aula 8 para as 17h10–18h10, depois do fecho às 18h00.
- O responsável quer um intervalo de 0 minutos depois da aula das 12h30. A grelha aceita 0 minutos ([`timetable.py`](../../backend/app/scheduler/domain/timetable.py)).
- A mensagem de erro ao regenerar a grelha foi corrigida em [#199](https://github.com/ORIOP25/Cronos/pull/199).

#### Primeira semana mais fraca

Na escola real, o `main` dá dias de turma com 1 ou 2 aulas: 92 na primeira semana, 41 na segunda, depois 26 e 22.
Na primeira semana há cerca de 2,8 aulas por dia de turma. Depois há cerca de 4,5. Ao longo do ano, 500 dias de turma têm 1 ou 2 aulas.

#### Tentativas que falharam

- **Tentativa 1: penalização na construção para dias com 1 ou 2 aulas.** Escola real: dias de 1–2 aulas de 500 para 1 380; dias de professor com uma só aula de 31 para 495; fim de 29 de março para 9 de julho.
  Lição: a construção cronológica não vê que um dia vai acabar curto. Furos e dias com uma só aula nascem de decisões que a construção vê. Um dia com 2 aulas nasce de aulas que nunca chegam a ser colocadas.
- **Tentativa 2: compactação semanal depois da construção.** Dias de 1–2 aulas. Escola real: 500 para 450 (−10%). Piloto ×1.0: 197 para 192. Mais de 30 000 recusas, porque o professor ou a turma estava ocupado.
  Lição: o pós-processamento não reorganiza dias num horário cheio.

#### Modelo semanal (ramo de ensaio)

O ramo `spike/weekly-template-mvp` existe no remoto e não foi fundido no `main`.
O desenho tem duas fases. Primeiro, um modelo CP-SAT de contagem por semana: aulas por unidade por dia da semana. Depois, um modelo de posições por dia da semana, com regras duras de dia. O padrão repete-se pelo calendário e respeita os feriados.

- **Ronda 1, escola real:** dias de 1–2 aulas de 500 para 12; furos dos professores de 490 para 1 721 h; 10 unidades por acabar; 24 minutos. A escola grande (48 turmas) não resolveu dentro do limite de tempo.
- **Ronda 2:** dois estágios, metas semanais rígidas, regra da cauda e feriados. Um dia curto só existe para acabar as últimas aulas de uma unidade.
  - Escola real: válida e completa. Dias fora da cauda com 1–2 aulas: 0. Furos dos professores: 130 h. Dias de turma com 1 furo: 807 (`main`: 485). Dias de professor com uma só aula: 101 (`main`: 31). Tempo: 40 min.
  - Piloto ×1.0: 939 violações; 82 unidades por acabar.
- **Ronda 3:** solves paralelos por dia da semana, custo exato de dias de professor com uma só aula com regra de junção, e regra exata de presença.

| Escola real | `main` | Ronda 3 |
| :--- | ---: | ---: |
| Válido | sim | sim |
| Dias fora da cauda com 1–2 aulas | 439 | 0 |
| Furos dos professores (h) | 490 | 47 |
| Dias de professor com uma só aula | 31 | 2 |
| Dias de turma com 1 furo | 485 | 1 064 |
| Última aula | 29 de março | 2 de abril |
| Tempo | 159 s | 2 158 s |
| Pico de RSS | 216 MB | 227 MB |

Piloto ×1.0, Ronda 3: 113 unidades por acabar; 12 violações de presença; 75 min. A fase de contagem ocupa 85–88% do tempo.

- **Ronda 4 (28 de outubro de 2026), só tempo.** Fasquia do responsável de produto: no máximo +50% do tempo do `main`.
  - A fase de contagem parte de um plano guloso determinístico. O plano enche primeiro cada dia de turma e de professor até 3 aulas, depois equilibra e repara.
  - O CP-SAT recebe esse plano como dica, com orçamento curto. Se o CP-SAT não devolve solução, fica o plano.
  - Commit `2335383b` no ramo de ensaio.

| Escola real, mesmo dia e mesma máquina | `main` | Ronda 3 | Ronda 4 |
| :--- | ---: | ---: | ---: |
| Válido e completo | sim | sim | sim |
| Dias fora da cauda com 1–2 aulas | 439 | 0 | 0 |
| Dias de turma com 2+ furos | 0 | 0 | 0 |
| Dias de turma com 1 furo | 485 | 1 064 | 1 062 |
| Furos dos professores (h) | 490 | 47 | 43 |
| Dias de professor com uma só aula | 31 | 2 | 21 |
| Última aula | 29 de março | 2 de abril | 2 de abril |
| Tempo | 176 s | 2 158 s | 176 s |
| Pico de RSS | 216 MB | 227 MB | 221 MB |

A medição do `main` foi repetida no mesmo dia (176 s; 159 s noutro dia). A Ronda 4 dá o mesmo resumo em duas corridas (determinística).
O plano guloso sozinho demora 14 s, mas a última aula passa para 12 de abril. O piloto não foi medido nesta ronda.

O tempo de produção mede-se em `scheduler_job_v1`, do arranque ao fim do trabalho. As gerações completas de 26–27 de outubro correram 103–134 s no worker, com cerca de 1 s de fila. A proposta foi criada no mesmo segundo.

- **Ronda 5 (28 de outubro de 2026): furos das turmas e fim do ano.** Pedido do responsável de produto: reduzir os dias de turma com 1 furo e a data da última aula.
  - O custo de furo de turma no modelo por dia passou a pesar 20 vezes mais.
  - As metas semanais apontam para uma semana mais cedo.
  - Commit `06571981` no ramo de ensaio.

| Escola real, mesmo dia e mesma máquina | `main` | Ronda 5 |
| :--- | ---: | ---: |
| Válido e completo | sim | sim |
| Dias fora da cauda com 1–2 aulas | 439 | 0 |
| Dias de turma com 2+ furos | 0 | 0 |
| Dias de turma com 1 furo | 485 | 677 |
| Horas de furo das turmas | 879 | 677 |
| Furos dos professores (h) | 490 | 29 |
| Dias de professor com uma só aula | 31 | 21 |
| Última aula | 29 de março | 25 de março |
| Tempo | 151 s | 182 s |
| Pico de RSS | 215 MB | 223 MB |

Por turma, 41 das 48 acabam as suas aulas mais tarde (8 dias em média), embora a escola acabe mais cedo. As turmas saem 36 minutos mais tarde em média.
Uma variante com feriados arredondados deu 370 dias de turma com 1 furo, com a última aula a 2 de abril. Não foi validada nem guardada.

Na escola do laboratório o modelo semanal falha. Com a carga completa não coloca nenhuma aula (o `main` termina em 316 s). Com as horas a 55% fica incompleto: 5 módulos por acabar, 10 violações e 196 dias com 2+ furos.
A causa está no avanço semana a semana: depois de um dia sem solução, o modelo reutiliza o padrão anterior e não recupera. A Ronda 4 já falhava nessa escola: 232 unidades por acabar e 482 violações.

- **Ronda 6 (28 de outubro de 2026): carga completa de cerca de 1 050 h por turma.** O responsável de produto fixou esta carga como a única que conta: uma turma de Ensino Profissional tem cerca de 1 050 h por ano letivo.
  - Causa da falha: a etapa de contagens só verificava totais por recurso. Uma unidade podia pedir mais aulas do que as vagas comuns à turma e ao professor, e o dia ficava sem solução.
  - Correções: o modelo por dia passou a aceitar aulas por colocar (falta penalizada) e deixou de falhar a semana; as rondas de corte foram retiradas; a etapa de contagens passou a verificar a presença do professor.
  - Commits `31c211f6` e `16e35aa0` no ramo de ensaio.
- **Ronda 7 (28 de outubro de 2026): aulas em falta e atualizações.** As aulas que sobram foram entregues à reconstrução do gerador atual (`construct_recovery`). O modelo semanal ganhou um caminho de atualização no laboratório. Commits `ebeab635`, `28820cd6` e `f9872ed6`.

| Escola do laboratório, `pilot@1.0`, sem faltas | `main` | Modelo semanal |
| :--- | ---: | ---: |
| Aulas colocadas | 43 152 | 42 994 (faltam 158) |
| Violações | 0 | 128 |
| Última aula | 8 de junho | 15 de junho |
| Dias de turma com 1 furo | 551 | 734 |
| Dias de turma com 2+ furos | 2 | 9 |
| Dias fora da cauda com 1–2 aulas | 134 | 0 |
| Furos dos professores (h) | 2 156 | 3 178 |
| Dias de professor com uma só aula | 69 | 305 |
| Tempo | 323 s | 422–466 s |

A reconstrução do gerador atual não completa o modelo semanal. Com as aulas semanais fixas, o modelo exato de colocação (`solve_placement`) também dá inviável. Com as aulas do `main` fixas até 1 de junho dá completo, por isso o modelo exato não está a falhar sem razão.

Atualizações com faltas na mesma escola, todas a 1 de fevereiro de 2027, com o passado protegido. Os valores contam de 1 de fevereiro em diante.

- Caso passado: três professores faltam a semana de 11 a 15 de janeiro. As aulas em falta deixam de estar protegidas e voltam a ser procura.
  - O validador exige que as aulas protegidas de cada unidade formem um prefixo do progresso do módulo. Por isso, as aulas seguintes da mesma unidade antes de 1 de fevereiro também voltam a ser procura.
  - No `main` são 88 aulas em falta mais 159 seguintes.
- Caso futuro: um professor fica Impossível de 1 a 12 de março (65 aulas).

| Atualização | `main` passado | Semanal passado | `main` futuro | Semanal futuro |
| :--- | ---: | ---: | ---: | ---: |
| Aulas por colocar | 0 | 607 | 0 | 333 |
| Violações | 0 | 394 | 0 | 238 |
| Aulas publicadas que mudam de hora | 0 (125 só de sala) | 10 815 | 67 (57 só de sala) | 10 930 |
| Dias de turma com 2+ furos (publicado → depois) | 1 → 4 | 6 → 85 | 1 → 15 | 6 → 46 |
| Furos dos professores (h, publicado → depois) | 619 → 662 | 1 497 → 2 693 | 619 → 637 | 1 497 → 2 589 |
| Tempo | 366 s | 333 s | 360 s | 270 s |

Cada atualização correu duas vezes com o mesmo resumo (determinística). O modelo semanal muda até uma semana sem alterações: guarda só 60% das aulas publicadas dessa semana. A causa provável, não verificada, são as metas semanais recalculadas a partir da procura restante.

#### Veredicto

O modelo semanal foi arquivado por decisão do responsável de produto a 28 de outubro de 2026. O ramo `spike/weekly-template-mvp` fica guardado e não é integrado no `main`.

Com cerca de 1 050 h por turma, o modelo semanal não completa o ano e desfaz o horário publicado nas atualizações. O gerador atual completa o ano e repõe as faltas sem mover aulas publicadas além das que a falta obriga.

Pontos abertos no gerador atual, medidos na escola do laboratório:

- 134 dias fora da cauda com 1–2 aulas (cerca de 3 por turma por ano);
- a atualização do caso futuro cria 14 dias de turma com 2+ furos, que a regra proíbe.

#### Lições dos ensaios

- Medir na carga anual real: cerca de 1 050 h por turma, na escola do laboratório `pilot@1.0`. Os dados atuais da escola real (420 h por turma) são um caso leve e não chegam para decidir.
- Uma aula conjunta grava-se uma linha por turma em [`scheduler_lesson_v1`](../../backend/app/scheduler/infrastructure/models.py), com o mesmo `stable_key` e o mesmo `teaching_unit_key`. Contar furos dessa tabela sem agrupar pela unidade de ensino erra os números. Foi um erro de contagem da coordenação a 26 de outubro.
- Os dados de produção leem-se a partir do contentor da API, em transação só de leitura, com o contexto do tenant definido. Sem esse contexto, o RLS esconde todas as linhas. Ver [Cloud Operations](../09_ops_observability/CLOUD_OPERATIONS.md#read-only-inspection) e [isolamento de tenant](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md).

O responsável de produto fechou os dias curtos a 28 de outubro de 2026: cerca de 3 por turma por ano é pouco relevante, e houve duas tentativas falhadas. Os 2+ furos criados pelas atualizações foram corrigidos no #212.

### Ocorrências ao longo do ano (28–29 de outubro de 2026)

Doze casos de atualização a meio do ano na escola do laboratório `pilot@1.0` (cerca de 1 050 h por turma), com o motor do `main` sem alterações. Fim previsto do horário publicado: 8 de junho. Todos os casos acabam completos, com 0 violações e 0 aulas por colocar.

| Caso | Aulas publicadas mantidas | Fim |
| :--- | ---: | :--- |
| 1–4, 6, 7: faltas curtas e baixa de um mês | 96–99% | 8 de junho (baixa de um mês: 18 de junho) |
| 5: um professor perde todas as quartas-feiras | 44% | 8 de junho |
| 8: estágio de uma turma (fluxo de estágio real) | 97% | 8 de junho |
| 9: escola fechada um dia | 42% | 9 de junho |
| 10: faltas no fim de maio | 100% | 2 de julho |
| 11: laboratório fechado | 43% | 7 de junho |
| 12: atualização mensal de outubro a maio, com os eventos acima | 97–100% por passo | 8 de junho até fevereiro; 29 de junho no fim |

- O fluxo de estágio deixa a turma sem aulas durante o fluxo. A turma parceira perde 30 aulas conjuntas e recupera-as todas. Dois defeitos encontrados foram corrigidos no #213 e no #214.
- Nos casos 5, 9 e 11 ganha a reconstrução: muda cerca de 60% das células visíveis (mediana por professor 57%), mas acaba a tempo. A reparação acaba a 20 de julho (caso 5) e a 23 de junho (caso 9), e no caso 11 não completa: um professor com regra de presença fica com 60 minutos que não formam um dia válido.
- No caso 12 a reparação ganha em todos os passos. Uma primeira corrida mostrou reconstruções sem eventos; a causa era o ensaio, que levava o `source_lesson_id` para o passo seguinte.
- Cada atualização troca 150 a 800 aulas de sala, sem mudar hora, disciplina nem professor. Segue a regra de salas de 18 de outubro: sala da turma e mesma sala no dia antes da sala publicada ([`room_assignment.py`](../../backend/app/scheduler/infrastructure/room_assignment.py)). O responsável de produto confirmou esta regra a 29 de outubro de 2026.
- No caso 10 a janela de estabilidade impede repor as faltas em horas livres das duas semanas seguintes. Com a janela aberta só para inserções, o fim passa de 2 de julho para 15 de junho, com as mesmas 91 inserções e nenhuma aula publicada movida. O responsável de produto recusou a 29 de outubro de 2026: nada muda dentro da janela, e a escola escolhe a duração da janela.

#### Reconstrução local

Ensaio de um terceiro candidato: refazer só as turmas e os professores do evento, com o resto fixo, alargando por anéis até 3. Código de laboratório, não integrado.

| Caso | Anel 0 (turmas, professores) | Resultado |
| :--- | :--- | :--- |
| 2 | 12, 3 | A reparação ganha; o anel 2 já é a escola inteira. |
| 5 | 6, 1 | O anel 1 (6 turmas, 29 professores) é válido mas acaba a 17 de junho. O anel 3 ganha com 9 074 aulas mudadas, contra 9 136 da reconstrução. |
| 9 | 48, 62 | Igual à reconstrução. |
| 11 | 26, 15 | O anel 1 já tem 44 turmas e 67 professores; 9 171 aulas mudadas contra 9 295. |

Fixar só os professores (modo turma) dá candidatos inválidos no caso 5. O resultado repete-se em duas corridas. Veredicto: não integrar. As turmas e os professores ligados a um evento grande cobrem quase toda a escola, por isso a reconstrução local não muda menos que a reconstrução completa.

#### Janela de estabilidade sem valor

Sem valor configurado, o snapshot usa uma janela de 0 dias ([`snapshot.py`](../../backend/app/scheduler/infrastructure/snapshot.py), `_stability_window`). A impressão digital de prontidão e a mudança de grelha usam 14 dias ([`task_keys.py`](../../backend/app/core/task_keys.py)). Os testes de integração não configuram a janela, por isso correm com 0 dias. Com os 14 dias por omissão, 9 testes falham: as regenerações depois de mudar a configuração, a redução manual de progresso e a remoção de módulos. Em dois casos o snapshot lança um `ValueError` ou um `TypeError`, em vez de um erro de configuração. A correção ficou por fazer.

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
| Medir cada slider em Ignorar e em Prioridade máxima na escola realista. | Mostrou que "Acabar cedo" mais baixo piorava tudo, um problema que os valores recomendados escondiam. |
| Analisar o horário mês a mês antes de corrigir. | Desmentiu a hipótese do aperto no fim do ano e apontou para os buracos de todos os dias. |
| Recalibrar pelos custos unitários e não pelos níveis recomendados. | Os níveis no ecrã, que são decisão de produto, ficaram iguais. |

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
6. Se a mudança toca valores ou o limiar da T07, repita a campanha dos sliders (cada critério em Ignorar e em Prioridade máxima) e compare com a tabela da campanha.
7. Corra o R24 da escola realista (`-m slow_solver -k realistic`); demora cerca de 20 minutos.
8. Escreva a tabela antes/depois no pull request, em totais e por pessoa.

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
