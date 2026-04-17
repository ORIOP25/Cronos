# Substituicoes

## Objetivo
Definir substituicoes seguras para manter continuidade letiva sem quebrar regras hard do sistema.

## 5 Ws

### What
Processo de trocar o docente previsto por docente elegivel de outra disciplina da mesma turma afetada.

### Who
admin aprova e executa decisao operacional.
professor permanece com escopo de disponibilidade e consulta do proprio horario.

### Where
Sempre no mesmo tenant (organizacao).

### When
Durante operacao diaria, apos identificacao de falta ou necessidade de ajuste imediato.

### Why
Manter execucao curricular e reduzir impacto operacional sem perder rastreabilidade.

## Validacoes de elegibilidade (confirmadas)

1. Mesmo tenant (same organization).
2. Docente substituto deve lecionar disciplina que a turma afetada ja tenha.
3. Docente substituto deve ser de disciplina diferente da aula faltante.
4. Docente da mesma disciplina, mas de outra turma, nao e elegivel para esta substituicao.
5. Sem conflito no slot de substituicao.
6. Atualizacao consistente de progresso/accounting apos decisao.

## Modelo de decisao (abordagem 3 com criterios da abordagem 1)

1. O sistema filtra todos os elegiveis validos da turma afetada.
2. O sistema calcula ranking automatico com ordem deterministica:
	- menor numero de substituicoes acumuladas na turma no periodo;
	- menor carga letiva ja alocada ao docente no dia;
	- maior tempo desde a ultima substituicao do docente nessa turma;
	- desempate final por identificador estavel do docente.

Regra de periodo (decisao fechada):
- o "periodo" da contagem acumulada usa a janela configurada em repair_stability_window_days da escola.
- em seed de testes, esta janela esta em 14 dias.
3. O sistema apresenta recomendacao simplificada ao admin (top opcoes e justificativa).
4. A decisao final da troca e sempre humana (admin), com selecao de um elegivel.
5. Se nao existir elegivel valido, a ocorrencia nao vira SUBSTITUTED e segue fluxo alternativo (ex.: GAP).

## Estados de ocorrencia associados
- GAP
- GIVEN
- SUBSTITUTED

## Fluxo pratico minimo

1. Aula planeada sofre indisponibilidade do docente previsto.
2. Sistema valida elegibilidade e conflitos.
3. Sistema gera recomendacao ordenada para o admin.
4. admin escolhe o docente substituto entre elegiveis.
5. Sistema regista substituicao com estado explicito.
6. Se nao elegivel, regista alternativa operacional sem mascarar historico.

## Workflow integrado com criacao de ocorrencia (alvo Alpha)

Objetivo do fluxo integrado:
- manter a pagina de faltas como centro de triagem (escala real com muitas faltas),
- sem perder entrada rapida no ponto operacional real (bloco da grelha semanal).

Passos alvo:
1. Professor comunica falta ao admin.
2. Admin clica no bloco da aula na grelha semanal.
3. Admin usa "Criar Ocorrencia" no contexto desse bloco.
4. Ocorrencia passa a constar imediatamente na pagina de faltas.
5. Admin escolhe "Substituicao" na pagina de faltas.
6. Sistema mostra ate 3 opcoes de substituicao (top ranking) com justificativa curta.
7. Admin escolhe 1 opcao e confirma.
8. Sistema revalida elegibilidade no backend e persiste a decisao.
9. Horario reflete novo professor/disciplina para admin, professores e turmas envolvidas.

Nota de escopo:
- passo 6 usa top 3 para reduzir ruido operacional;
- acesso a lista completa permanece opcional para casos limite (a definir no detalhe de UX).

## Exemplo pratico

Cenario:
- turma X tem aula de Portugues com professora A.
- professora A falta.
- admin analisa professor B (Educacao Fisica da turma X) como substituto.

Verificacoes:
- professor B pertence a mesma organizacao;
- professor B leciona disciplina da propria turma X;
- professor B nao leciona a mesma disciplina faltante;
- professor B nao esta ocupado no mesmo slot;
- professora C (Portugues da turma Y) nao e elegivel neste caso.

Decisao assistida:
- sistema apresenta ranking dos elegiveis da turma X com justificativas objetivas;
- admin confirma a escolha final do substituto.

Resultado:
- ocorrencia registada como SUBSTITUTED quando validacoes passam;
- historico preserva quem estava previsto e quem executou.

## Decisao fechada para Alpha V1 (sem pendencias)

Formato minimo obrigatorio da recomendacao no frontend:
- lista ordenada de elegiveis com posicao no ranking;
- destacar ate 3 candidatos no topo para decisao rapida;
- explicacao curta por candidato com os 4 criterios deterministas;
- acao explicita de confirmacao pelo admin;
- revalidacao obrigatoria no backend no instante da confirmacao.

Nota:
- este formato fecha o escopo funcional da Alpha V1;
- melhorias esteticas/UX adicionais ficam para iteracoes posteriores, sem alterar regra de negocio.

## Contrato operacional implementado (Alpha V1 - Passo 2)

Fluxo HTTP aplicado:
1. admin consulta ranking por ocorrencia em `GET /api/v1/occurrences/{occurrence_id}/substitutes/recommendations`.
2. frontend apresenta candidatos ordenados e justificativa objetiva.
3. admin confirma decisao final em `PATCH /api/v1/occurrences/{occurrence_id}` com `status=SUBSTITUTED` e par `substitute_teacher_id` + `substitute_subject_id`.

Compatibilidade legacy (Alpha, ponto 12):
- `POST /api/v1/substitutions/` permanece ativo para clientes existentes;
- internamente, o endpoint legacy usa adaptador para criar/reusar ocorrencia e aplicar decisao canónica `SUBSTITUTED`;
- objetivo: coexistencia sem quebra enquanto a fonte de verdade funcional permanece em `LessonOccurrence`.

Descontinuacao legado (decisao 2026-04-12):
- `GET /api/v1/substitutions/suggestions` esta descontinuado e devolve `410 Gone`;
- motivo: evitar recomendacao fora do fluxo canónico por ocorrencia;
- caminho oficial: `GET /api/v1/occurrences/{occurrence_id}/substitutes/recommendations`.

Revalidacao obrigatoria no instante de confirmacao:
- backend executa novamente todos os checks de elegibilidade antes de persistir SUBSTITUTED;
- se candidato perder elegibilidade entre sugestao e confirmacao (ex.: conflito superveniente no slot), pedido falha sem persistencia parcial.

Detalhe do ranking deterministico implementado:
1. menor `substitutions_in_period` (periodo = `repair_stability_window_days` da escola);
2. menor `daily_load_hours` no dia da ocorrencia;
3. maior `days_since_last_substitution` na mesma turma;
4. desempate final por `teacher_id` ascendente.

Campos de transparencia devolvidos por candidato:
- `rank`;
- `teacher_id` e `teacher_name`;
- `subject_id` e `subject_name`;
- `substitutions_in_period`;
- `daily_load_hours`;
- `days_since_last_substitution`;
- `justification` textual com os 4 criterios.

Seguranca e autorizacao:
- recomendacao e confirmacao de substituicao sao operacoes exclusivas de admin;
- professor nao pode confirmar SUBSTITUTED nem alterar estado de ocorrencia.

## Impacto por layer

### Interface
- admin precisa de validacoes visiveis antes de confirmar substituicao.

### Regras de negocio
- substituicao so ocorre apos checks de elegibilidade e conflito.

### Base de dados
- ocorrencia e decisoes devem ficar auditaveis e imutaveis.