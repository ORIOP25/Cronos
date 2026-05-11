# Objetivo final do produto

## Posicionamento
Apérius e um SaaS premium para escolas profissionais privadas em Portugal.
O foco comercial nao e ser a opcao mais barata, mas ser a opcao mais confiavel para resolver a dor operacional de horarios.
Modelo de adocao: self-service, com utilizacao autonoma da plataforma e contacto humano apenas em suporte ao cliente quando necessario.

## 5 Ws do produto

### What
Plataforma de gestao e geracao de horarios com operacao continua.
Inclui:
- planeamento inicial;
- replaneamento seguro do futuro;
- controlo de progresso modular por turma;
- historico imutavel do que foi realmente executado;
- suporte operacional para faltas e substituicoes.

### Who
Perfis confirmados na aplicacao:
- admin: acesso total na organizacao (planeia, valida, publica, aprova).
- professor: apenas define disponibilidade e consulta os seus horarios.

Nao existe perfil de aluno dentro do escopo funcional.

### Where
Mercado alvo:
- escolas profissionais privadas portuguesas.

Escopo tecnico:
- multi-tenant por organizacao;
- isolamento por organization_id em queries e mutacoes.

### When
Estado atual do produto:
- motor de geracao com baseline estavel e iterativa;
- fim hard obrigatorio por data definida pela escola;
- fim target como objetivo de qualidade;
- faltas/substituicoes como frente critica seguinte.

### Why
Problema resolvido:
- complexidade operacional e burocratica da gestao de horarios no ensino profissional.

Valor entregue:
- previsibilidade para direcao/administracao;
- menos friccao operacional para professores;
- controlo real de execucao curricular por modulos.

## Operacao diaria da escola (ponta a ponta)

### 1) Preparacao e governo operacional
Ator principal: admin.

Pratica:
- define regras e parametros da organizacao;
- acompanha disponibilidade dos professores;
- decide quando gerar ou regenerar horarios futuros.

Resultado esperado:
- base valida para geracao sem conflitos hard.

### 2) Contribuicao dos professores
Ator principal: professor.

Pratica:
- regista disponibilidade;
- consulta apenas o proprio horario.

Resultado esperado:
- dados de disponibilidade atualizados para o motor;
- menor risco de conflito operacional.

### 3) Geracao e publicacao de horario
Ator principal: admin.

Pratica:
- executa geracao global da organizacao;
- valida consistencia operacional;
- aprova e publica plano resultante.

Resultado esperado:
- horario viavel sem violar hard constraints.

### 4) Execucao real e rastreabilidade
Ator principal: admin (com suporte de eventos operacionais).

Pratica:
- distingue plano previsto de ocorrencia real;
- preserva historico imutavel do executado;
- prepara acao para faltas/substituicoes quando necessario.
- em substituicoes, aplica regra de elegibilidade por turma (docente de outra disciplina da mesma turma afetada).
- em substituicoes com multiplos elegiveis, sistema recomenda candidatos e admin toma a decisao final.

Resultado esperado:
- confianca nos dados de execucao;
- progresso modular consistente ao longo do tempo.

### 5) Regeneracao controlada do futuro
Ator principal: admin.

Pratica:
- replaneia apenas futuro quando contexto muda;
- respeita janela fixa de estabilidade configurada por escola;
- nunca altera historico passado para "corrigir" metricas.

Resultado esperado:
- continuidade operacional sem perder rastreabilidade.

## Criterios minimos para considerar a fase atual valida

Estes criterios derivam de regras ja confirmadas.

### Criterios hard (obrigatorios)
- zero conflito de professor, turma e sala;
- respeito de tipo de sala exigido pela disciplina;
- bloqueio de slots impossiveis;
- respeito de regras de almoco quando configuradas;
- nenhuma aula apos school_hard_end_date;
- isolamento por organization_id em toda operacao.

### Criterios de controlo operacional
- capacidade de distinguir planeado vs executado;
- historico de execucao tratado como imutavel;
- formula deterministica de progresso/divida por estado (GIVEN, GAP, SUBSTITUTED);
- para faltas/substituicoes: caminho operacional sem quebrar consistencia.

## Limites de escopo explicitamente assumidos
- sem gestao individual de alunos no produto;
- sem flexibilizacao de hard constraints para melhorar "aparencia" do horario.

## Impacto por layer

### Interface
- admin com poderes de aprovacao e publicacao;
- professor com escopo minimo (disponibilidade e consulta do proprio horario).

### Regras de negocio
- motor sujeito a hard constraints inegociaveis;
- soft objectives guiam qualidade sem violar viabilidade.

### Base de dados
- isolamento por tenant e historico imutavel sao obrigatorios.