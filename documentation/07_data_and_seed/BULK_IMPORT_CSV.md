# Importação administrativa CSV

## Objetivo

`/imports` permite a um administrador importar dados de forma aditiva. A validação é feita em memória; a confirmação reenvia exatamente os mesmos ficheiros, revalida dentro da transação e só grava no fim.

Não existe atualização/substituição, undo automático, histórico de lotes, Excel, multipart ou processamento assíncrono.

## Templates oficiais

Todos os templates são descarregados autenticadamente em `/api/v1/imports/templates/{resource}` e usam UTF-8 com BOM, `;`, CRLF e uma linha oficial de exemplo. A linha de exemplo tem de ser substituída.

| Recurso | Ficheiro | Cabeçalho exato |
| --- | --- | --- |
| `rooms` | `salas.csv` | `name;type;capacity` |
| `subjects` | `disciplinas.csv` | `name;required_room_type;module_name;module_code;module_hours;module_order` |
| `courses` | `cursos.csv` | `abbreviation;name;class_name;grade_level;start_year;end_year;size` |
| `teachers` | `professores.csv` | `name;email;competency_subject` |
| `assignments` | `atribuicoes.csv` | `course_abbreviation;class_name;subject_name;teacher_email` |

Os cabeçalhos podem estar em qualquer ordem, mas não podem faltar, repetir-se ou conter colunas extra. Os módulos usam ordens `1..n` no CSV e são convertidos para o índice interno.

## Pedido e respostas

```json
{
  "files": {
    "rooms": {
      "filename": "salas.csv",
      "content_base64": "..."
    }
  }
}
```

`POST /api/v1/imports/validate` devolve `200` mesmo com erros de dados:

- `can_commit`: false quando existe pelo menos um erro;
- `preview.counts` e `preview.items`;
- `issues`, com severidade, recurso, linha física, campo, código e mensagem.

`POST /api/v1/imports/commit` devolve `201` quando grava tudo. Se a revalidação encontrar erros, devolve `422` no envelope de erro existente, com a prévia e as issues no `context`. Warnings permitem confirmar.

## Regras de segurança e integridade

- Todos os endpoints exigem `AdminActor` e usam o tenant da sessão.
- Cada ficheiro tem no máximo 1 MiB, o lote descodificado no máximo 5 MiB e cada ficheiro no máximo 5.000 linhas.
- Base64 inválido, BOM ausente, UTF-8 inválido, NUL, separador diferente e estrutura CSV diferente são rejeitados.
- Salas, disciplinas, cursos e professores são novos; duplicados existentes bloqueiam.
- Cursos, turmas e disciplinas podem ser referenciados nas atribuições, mas professores existentes não podem ser usados.
- Professores importados ficam com `teacher` + `scheduler_only`; não há convite nem chamada Clerk.
- As queries do snapshot filtram sempre `organization_id`. `validate` não faz `flush`, `commit` nem chamadas externas.
- O commit cria salas, disciplinas/módulos, professores, cursos/turmas e atribuições numa única transação. Uma exceção tardia provoca rollback integral.

## Correção de falhas

1. Descarregue o template atualizado.
2. Substitua a linha de exemplo e mantenha os cabeçalhos sem alterar nomes.
3. Corrija todas as issues; referências de atribuições devem usar a sigla, turma e disciplina corretas.
4. Inclua cada professor referenciado no mesmo lote e use um email ainda não existente.
5. Valide novamente e confirme apenas quando `can_commit` for verdadeiro.

O relatório descarregado pela interface é CSV seguro para Excel: inclui BOM, `;`, escaping de aspas e prefixo textual para valores iniciados por `=`, `+`, `-` ou `@`.

## Capacidade

O fluxo permanece síncrono e é limitado pelos limites acima. A aceitação esperada cobre aproximadamente 10 cursos, 30 turmas, 100 disciplinas, 300 módulos, 80 professores e 300 atribuições, sem impor um tempo de execução instável.

## Source map

- Política pura: `backend/app/services/bulk_import_policy.py`
- Serviço transacional: `backend/app/services/bulk_import_service.py`
- API: `backend/app/api/v1/endpoints/imports.py`
- Cliente e relatório: `frontend/src/features/imports/data.js`
- Interface: `frontend/src/pages/BulkImport.jsx`
