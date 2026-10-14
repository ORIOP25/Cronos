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
Cada modelo usa ponto e vírgula, CRLF, BOM e uma linha de exemplo.
Substitua ou apague a linha de exemplo antes de importar.

Um conjunto completo de exemplo, com 48 turmas e 16 cursos, está em [`sample_import_48_classes/`](sample_import_48_classes/).
Use-o para testar a importação num ambiente descartável.

| Secção | Ficheiro | Cabeçalhos exatos |
| --- | --- | --- |
| Salas | `Cronos_Salas_Template.csv` | `Nome da sala;Tipo de sala;Capacidade` |
| Disciplinas e módulos | `Cronos_DisciplinasEModulos_Template.csv` | `Nome da disciplina;Tipo de sala;Nome do módulo;Código do módulo;Horas do módulo;Ordem do módulo` |
| Cursos e turmas | `Cronos_CursosETurmas_Template.csv` | `Sigla do curso;Nome do curso;Nome da turma;Ano escolar;Ano de início;Ano de fim;Número de alunos` |
| Professores e competências | `Cronos_ProfessoresECompetencias_Template.csv` | `Nome do professor;Email do professor;Nome da disciplina` |
| Atribuições | `Cronos_Atribuicoes_Template.csv` | `Sigla do curso;Nome da turma;Nome da disciplina;Email do professor` |

Os cabeçalhos devem manter nomes, ordem e quantidade.
Os modelos antigos, com cabeçalhos em inglês, deixam de ser aceites.
Valores entre aspas podem conter vírgulas ou ponto e vírgula.

## Tipos de sala

Salas e disciplinas aceitam estes valores, sem distinguir maiúsculas ou acentos:

| Valor aceite | Valor guardado |
| --- | --- |
| `Normal` | `normal` |
| `Laboratório` ou `Laboratorio` | `lab` |
| `Ginásio` ou `Ginasio` | `gym` |
| `Artes` | `art` |

Os códigos internos `lab`, `gym` e `art` não são aceites no ficheiro.

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
