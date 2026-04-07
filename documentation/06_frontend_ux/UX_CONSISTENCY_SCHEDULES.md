# UX consistency schedules

## Objetivo
Garantir experiencia premium e consistente na operacao diaria da escola.

## 5 Ws da UX

### What
Interface para consulta e operacao de horarios conforme role.

### Who
- admin: experiencia de controlo operacional completo da organizacao.
- professor: experiencia simples e focada em duas tarefas.

### Where
Uso em contexto escolar profissional privado, com foco administrativo.

### When
Uso diario na preparacao, consulta e ajuste de operacao.

### Why
Produto premium exige clareza, confiabilidade percebida e baixa friccao.

## Escopo funcional por role na interface

### Admin
- acesso a fluxos de governanca operacional;
- visao global da organizacao para horarios e ocorrencias.

### Professor
- registar disponibilidade;
- consultar apenas o proprio horario.

A interface nao deve sugerir capacidades alem do role autenticado.

## Regras de consistencia de estado

1. Loading: estado explicito e previsivel.
2. Erro: mensagem clara com acao de recuperacao quando aplicavel.
3. Empty state: texto explicativo sem ambiguidade.
4. Troca de contexto (ex.: semana/filtro): sem ghost state nem dados stale invisiveis.

## Regras tecnicas de implementacao (confirmadas)

- usar elementos semanticos nativos quando aplicavel;
- evitar nested ternaries;
- usar compare function explicita em ordenacao;
- manter comportamento consistente de selecao/troca de contexto.

## Direcao visual premium (confirmada no posicionamento)

Principios:
- visual profissional e intencional;
- clareza de hierarquia informativa;
- comunicacao de confiabilidade para perfil administrativo.

Nota:
este documento define direcao, nao congela um tema grafico unico.

## Exemplo pratico

Caso: professor entra para atualizar disponibilidade.

Experiencia esperada:
- ve apenas as funcoes permitidas;
- conclui acao em poucos passos;
- recebe feedback claro de sucesso/erro.

Caso: admin consulta operacao diaria.

Experiencia esperada:
- ve contexto global da organizacao;
- identifica rapidamente situacoes que exigem decisao.

## Impacto por layer

### Interface
- principal camada responsavel por usabilidade e percecao de produto premium.

### Regras de negocio
- UX deve refletir regras reais, nao criar atalho que viole autorizacao.

### Base de dados
- estados de interface dependem de respostas consistentes e tenant-scoped.