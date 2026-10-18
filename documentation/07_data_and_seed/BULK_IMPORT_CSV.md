# Importação administrativa CSV

## Objetivo

`/imports` permite a um administrador adicionar dados em várias secções.
O sistema verifica todos os ficheiros antes de gravar.

Pode utilizar Excel ou Google Sheets.
O sistema aceita vírgula ou ponto e vírgula como separador.
O sistema aceita UTF-8 com ou sem BOM.
Cada ficheiro pode ter até 1 MB.

## Modelos oficiais

Os modelos estão disponíveis em `/api/v1/imports/templates/{resource}`.
Cada modelo fixo usa ponto e vírgula, CRLF, BOM e uma linha de exemplo.
Substitua ou apague a linha de exemplo antes de importar.
Os dois modelos de disponibilidade são a exceção: são gerados a partir dos dados da escola e não têm linha de exemplo; sem dados trazem só o cabeçalho.

Um conjunto completo de exemplo, com 48 turmas e 16 cursos, está em [`sample_import_48_classes/`](sample_import_48_classes/).
Use-o para testar a importação num ambiente descartável.

| Secção | Ficheiro | Cabeçalhos exatos |
| --- | --- | --- |
| Salas | `Cronos_Salas_Template.csv` | `Nome da sala;Tipo de sala;Capacidade` |
| Disciplinas e módulos | `Cronos_DisciplinasEModulos_Template.csv` | `Nome da disciplina;Tipo de sala;Nome do módulo;Código do módulo;Horas do módulo;Ordem do módulo` |
| Cursos e turmas | `Cronos_CursosETurmas_Template.csv` | `Sigla do curso;Nome do curso;Nome da turma;Ano escolar;Ano de início;Ano de fim;Número de alunos;Sala da turma` |
| Professores e competências | `Cronos_ProfessoresECompetencias_Template.csv` | `Nome do professor;Email do professor;Nome da disciplina` |
| Atribuições | `Cronos_Atribuicoes_Template.csv` | `Sigla do curso;Nome da turma;Nome da disciplina;Email do professor` |
| Disponibilidade das turmas | `Cronos_DisponibilidadeTurmas_Template.csv` | `Sigla do curso;Nome da turma;Dia` e uma coluna por hora de início |
| Disponibilidade dos professores | `Cronos_DisponibilidadeProfessores_Template.csv` | `Nome do professor;Email do professor;Dia` e uma coluna por hora de início |
| Presença dos professores | `Cronos_PresencaProfessores_Template.csv` | `Nome do professor;Email do professor;Hora de almoço;Mínimo de horas por presença;Furo máximo (horas)` |

Os cabeçalhos devem manter nomes, ordem e quantidade.
Os modelos antigos, com cabeçalhos em inglês, deixam de ser aceites.
Valores entre aspas podem conter vírgulas ou ponto e vírgula.

Uma linha de Atribuições cria a ligação turma–disciplina e marca todos os módulos da disciplina (D03).
O CSV não escolhe módulos por turma.
Depois da importação, ajuste a seleção em `/courses/:courseId/classes/:classId/subjects`.

## Tipos de sala

A coluna `Tipo de sala` escreve o **nome** de um tipo de sala da escola, igual ao nome que aparece em `/api/v1/room-types`: `Normal`, `Laboratório`, `Ginásio`, `Artes` ou um tipo criado pela escola. O nome é comparado sem distinguir maiúsculas ou acentos.

- Um nome que a escola já usa liga a sala ou a disciplina a esse tipo.
- Um nome que a escola ainda não tem cria um tipo novo. O mesmo nome nas salas e nas disciplinas cria um só tipo, mesmo com grafias diferentes.
- Um nome arquivado restaura esse tipo, com o mesmo identificador.
- Um nome igual ao de um tipo de outra escola cria um tipo novo nesta escola. Nunca usa o tipo de outra escola.
- Uma célula vazia devolve `room_type_invalid`, com a mensagem «Escreva o tipo de sala.».
- Um nome com mais de 60 caracteres devolve `room_type_invalid`, com a mensagem «Escreva um nome de tipo com até 60 caracteres.».

Os tipos novos são criados antes das salas e das disciplinas. Salas e disciplinas ficam ligadas ao tipo pelo identificador; o resto da secção não muda.

## Sala da turma

A coluna `Sala da turma` do ficheiro Cursos e turmas é opcional e é a última. Uma célula vazia deixa a turma em Automática (o Cronos escolhe).

- O valor é o nome de uma sala ativa da escola ou de uma sala do ficheiro de salas do mesmo lote. Não distingue maiúsculas nem acentos.
- A sala tem de ter lugares para os alunos da turma, indicados em `Número de alunos`.
- Um nome sem sala devolve `home_room_not_found`, com a mensagem «Sala não encontrada. Escreva o nome de uma sala existente ou do ficheiro de salas.».
- Uma sala sem lugares devolve `home_room_capacity`, com a mensagem «A sala {nome} não tem lugares para os {n} alunos da turma.». Se o nome já começa por «Sala», a mensagem usa «A {nome}», como no ecrã da turma.
- Os dois erros indicam a linha e a coluna `Sala da turma`.
- Preencher a sala sem os outros campos da turma devolve `class_partial`.
- A coluna só se aplica a turmas novas. As turmas existentes não mudam; altere-as na página da turma.
- O `commit` define a sala da turma depois de criar as salas e as turmas.

## Disponibilidade das turmas

A secção `Disponibilidade das turmas` atualiza a disponibilidade semanal das turmas.
O modelo é dinâmico: a função pura `render_availability_template` monta-o a partir da grelha visível, das turmas não arquivadas e dos níveis guardados.

- As colunas fixas são `Sigla do curso`, `Nome da turma` e `Dia`.
- Cada coluna seguinte é uma hora de início distinta da grelha visível, por ordem.
- Há uma linha por turma e por dia com blocos, ordenadas por sigla, turma e dia.
- Uma hora sem bloco nesse dia fica com a célula vazia.

A grelha visível tem de existir. Sem blocos, o pedido do modelo devolve `400` com `A escola ainda não configurou blocos.`

As células aceitam `Impossível`, `Evitar`, `Neutro` ou `Preferencial`, sem distinguir maiúsculas ou acentos.
Uma célula vazia, um dia sem linha ou uma hora sem bloco contam como Neutro.
Um dia aceita o nome com ou sem `-feira`, acentos e maiúsculas.
As horas aceitam `H:MM`, `HH:MM` e `HH:MM:SS`.

A validação recusa cada situação com a sua mensagem.
As mensagens exatas e as regras de cabeçalho estão em `backend/app/services/bulk_import_policy.py` (`_validate_availability` e `_parse_availability_file`).
O campo do erro numa célula é o título da coluna, por exemplo `08:30`.
Uma turma pode existir ou vir no mesmo lote, no ficheiro de Cursos e turmas.

Cada turma do ficheiro fica com a grelha inteira do ficheiro. As turmas ausentes ficam iguais.
O `commit` aplica as grelhas depois de criar cursos, turmas e atribuições.
`created_counts["class_availability"]` conta as turmas atualizadas.

## Disponibilidade dos professores

A secção `Disponibilidade dos professores` atualiza a disponibilidade semanal dos professores.
O modelo é dinâmico: a função pura `render_availability_template` monta-o a partir da grelha visível, dos professores ativos e dos níveis guardados.

- As colunas fixas são `Nome do professor`, `Email do professor` e `Dia`.
- Cada coluna seguinte é uma hora de início distinta da grelha visível, por ordem.
- Há uma linha por professor ativo e por dia com blocos, ordenadas por nome sem distinguir maiúsculas, email e dia.
- Cada célula traz o nível atual; uma linha em falta conta como Neutro.
- Uma hora sem bloco nesse dia fica com a célula vazia.

O email identifica o professor, sem distinguir maiúsculas; o nome só serve para ler o ficheiro e não é validado.
Um professor arquivado ou sem a capacidade de professor dá erro; retire a linha ou reative-o na Equipa.
Um professor novo pode vir no mesmo lote, no ficheiro de Professores e competências.

Cada professor do ficheiro fica com a grelha inteira do ficheiro. Os professores ausentes ficam iguais.
O `commit` aplica as grelhas dos professores depois das grelhas das turmas, pela função `teacher_service.set_teacher_availability`.
`created_counts["teacher_availability"]` conta os professores atualizados.

## Presença dos professores

A secção `Presença dos professores` atualiza a regra de presença opcional de cada professor.
O modelo é dinâmico: a função pura `render_teacher_presence_template` monta-o a partir dos professores ativos e da regra atual.

- Os cabeçalhos são `Nome do professor`, `Email do professor`, `Hora de almoço`, `Mínimo de horas por presença` e `Furo máximo (horas)`.
- Há uma linha por professor ativo, por ordem de nome, com a regra guardada.
- Nomes e emails dos professores são só de leitura.

O email identifica o professor, com a mesma procura da secção Professores.
Pode já existir ou vir no mesmo lote, no ficheiro de Professores.
Um email desconhecido ou de outra organização é recusado com a linha e a coluna.

`Hora de almoço` aceita `Sim` ou `Não`, sem distinguir maiúsculas ou acentos. Uma célula vazia vale `Sim`.
O mínimo vazio quer dizer sem regra. O furo vazio com um mínimo vale 1 hora.
O mínimo aceita inteiros de 1 a 12; o furo aceita inteiros de 0 a 12. Um furo sem mínimo é recusado.
Cada linha substitui os três valores desse professor. Os professores ausentes ficam iguais.

As mensagens exatas estão em `backend/app/services/bulk_import_policy.py` (`_validate_teacher_presence`).
O campo do erro é `email`, `lunch`, `minimum_hours` ou `max_gap_hours`.

O `commit` aplica a presença depois de criar os professores.
Cada professor alterado regista uma alteração do motor.
`created_counts["teacher_presence"]` conta os professores alterados.

## Comparação e pré-visualização

Os tipos de sala novos aparecem na lista `Tipos de sala novos` e no contador `room_types`. Um tipo arquivado que volta também conta como novo.
As linhas de disponibilidade ficam fora do limite de 100 itens da pré-visualização.
Cada item traz `changed_blocks`: o número de blocos da versão visível em que o nível novo difere do guardado.
Um nível em falta conta como Neutro nos dois lados.
As turmas aparecem por `changed_blocks` decrescente, depois sigla e turma.
Os professores aparecem por `changed_blocks` decrescente, depois nome sem distinguir maiúsculas e email.
Uma grelha toda em `Impossível` dá o aviso `all_blocks_impossible`; a importação continua.

## Pedido e respostas

```json
{
  "files": {
    "rooms": {
      "filename": "Cronos_Salas_Template.csv",
      "content_base64": "..."
    }
  }
}
```

`POST /api/v1/imports/validate` devolve `200`, mesmo com problemas de dados.
A resposta mantém `can_commit`, `preview.counts` e `issues`.
A interface apresenta apenas os resumos, problemas e avisos.

`POST /api/v1/imports/commit` devolve `201` quando grava tudo.
O pedido volta a ser verificado antes de gravar.
Uma falha impede qualquer gravação parcial.

## Segurança e integridade

- Todos os endpoints exigem `AdminActor` e usam a organização da sessão.
- O conjunto descodificado pode ter até 5 MB.
- Cada ficheiro pode ter até 5.000 linhas.
- Ficheiros inválidos recebem uma mensagem de leitura comum.
- Salas, disciplinas, cursos e professores novos não podem repetir dados existentes.
- Nomes de disciplinas e siglas de cursos arquivados podem ser reutilizados; o histórico mantém os registos originais.
- Cursos, turmas e disciplinas podem ser usados nas atribuições.
- Uma linha de Atribuições marca todos os módulos da disciplina na turma.
- Um professor existente não pode ser usado numa atribuição.
- Um professor indicado numa atribuição deve estar no mesmo pedido.
- O professor importado recebe acesso `scheduler_only`.
- A validação não grava nem chama serviços externos.

## Relatório

O relatório da interface chama-se `Cronos_Relatorio_Importacao.csv`.
Usa ponto e vírgula e BOM para compatibilidade com Excel.
Os cabeçalhos são `Tipo`, `Secção`, `Linha`, `Campo` e `Mensagem`.
Os valores de tipo são `Erro` e `Aviso`.

## Source map

- Política e parser: `backend/app/services/bulk_import_policy.py`
- Serviço transacional: `backend/app/services/bulk_import_service.py`
- API: `backend/app/api/v1/endpoints/imports.py`
- Cliente e relatório: `frontend/src/features/imports/data.js`
- Interface: `frontend/src/pages/BulkImport.jsx`
