# Tech Spec — Importação CSV da Disponibilidade dos Professores

## Purpose

A escola descarrega um modelo com todos os professores, preenche o nível de cada bloco e importa a grelha de todos de uma vez.
A aplicação passa a usar só os nomes Impossível, Evitar, Neutro e Preferencial para os níveis.
A grelha chama-se sempre "Disponibilidade" e o requisito de sala da disciplina chama-se sempre "Tipo de sala".

**Estado:** pronto para implementação. **Base:** `main` em `e787aa5`, Alembic `0004_joint_lesson_groups`.
**Data:** 15 de outubro de 2026. **Origem:** item 4 dos pedidos da escola piloto, reunião de 13 de outubro de 2026.
O [WBS](TEACHER_AVAILABILITY_IMPORT_WBS.md) decompõe este documento em slices.

## Intended Reader

Agentes que implementam e o responsável de produto.

## Prerequisites

- A importação da disponibilidade das turmas está em `main` (PR #133). Esta funcionalidade reutiliza o formato dela.
- Nenhuma migração. O modelo de dados não muda.

## What the System Does

### Decisões de produto

Decisões fechadas com o responsável de produto a 15 de outubro de 2026.

| ID | Decisão | Consequência |
| :--- | :--- | :--- |
| D01 | Novo cartão "Disponibilidade dos professores" na página Importar dados. | O botão "Importar CSV" da Equipa continua a abrir a página, como hoje. |
| D02 | Mesmo formato da disponibilidade das turmas, num ficheiro separado. | Colunas fixas `Nome do professor`, `Email do professor`, `Dia`; depois uma coluna por hora de início. |
| D03 | O modelo traz todos os professores ativos e os níveis atuais. | Professor ativo: membro ativo com a capacidade de professor. |
| D04 | O email identifica o professor, sem distinguir maiúsculas. | O nome serve só para ler o ficheiro. O sistema não o valida. |
| D05 | Cada professor do ficheiro fica com a grelha do ficheiro. | Célula vazia ou dia sem linha contam como Neutro. Os professores ausentes ficam iguais. |
| D06 | Só o administrador importa. | Igual às outras secções. |
| D07 | Professor inexistente, arquivado ou sem capacidade de professor dá erro. | A linha tem de ser corrigida ou retirada. |
| D08 | Um professor novo do mesmo lote é aceite. | Pode vir no ficheiro "Professores e competências" selecionado ao mesmo tempo. |
| D09 | Uma grelha toda em Impossível dá aviso, não erro. | A importação continua. A geração já bloqueia esse caso. |
| D10 | A pré-visualização mostra uma linha por professor com "Blocos que mudam". | A comparação é com a grelha atual. O professor não é avisado. |
| D11 | A importação é tudo ou nada. | Com um erro, nada é gravado. Igual às outras secções. |
| D12 | Os níveis aceites são só Impossível, Evitar, Neutro e Preferencial. | Sem sinónimos. Maiúsculas e acentos diferentes continuam aceites, como hoje. |
| D13 | Todos os textos da aplicação usam só os quatro nomes. | O slice S1 corrige os textos que descrevem os níveis por outras palavras. |
| D14 | As duas secções de disponibilidade comportam-se igual. | As turmas também ganham "Blocos que mudam" e o aviso D09. |
| D15 | As tabelas de disponibilidade mostram todas as linhas. | O limite de 100 linhas da pré-visualização não se aplica a elas. Ordem: mais blocos alterados primeiro. |
| D16 | A grelha semanal do professor chama-se sempre "Disponibilidade", nunca "Preferências". | Página e menu do professor: `Minha Disponibilidade`, como `Meus Horários` e `Meu Progresso`. O endereço `/my-availability` não muda. |
| D17 | O requisito de sala da disciplina chama-se sempre "Tipo de sala". | O formulário (`Sala Preferencial`) e a lista (`Requisito de Sala`) passam a usar o nome da importação CSV. |

D14 e D15 seguem o pedido de uniformização (D13). Sem elas, as duas tabelas lado a lado mostrariam colunas diferentes.
D16 e D17 foram decididas pelo responsável a 15 de outubro de 2026, depois da primeira versão deste plano.

### Âmbito

- Modelo dinâmico, validação, pré-visualização e aplicação da secção `teacher_availability`.
- Partilha do parser, do modelo e do validador entre turmas e professores.
- Uniformização dos textos dos níveis (D13), do nome da grelha (D16) e do tipo de sala (D17).

### Fora de âmbito

- Um ficheiro único para turmas e professores (D02).
- Aviso ao professor (D10).
- Versões futuras da grelha. O modelo usa a versão visível, como nas turmas. Uma versão futura edita-se na janela.
- "Data preferencial de fim", a "preferência de feriados automáticos" e as "preferências funcionais" dos textos legais. São outros conceitos.
- O mapa de calor ("Disponíveis: 5 / 10"). Conta professores, não mostra níveis.

## Why the Behavior Exists

Uma escola tem dezenas de professores. Preencher a grelha de cada um no ecrã é lento e dá erros.
Sem importação, a passagem para dados reais trava.
A escola piloto também pediu uma só linguagem: o mesmo nível não pode ter dois nomes.

## Components and Ownership

### Inventário de leitores e escritores

| Ficheiro | Lê ou escreve | Slice |
| :--- | :--- | :--- |
| `backend/app/services/bulk_import_policy.py` | `IMPORT_RESOURCES`, `template_filename`, `render_class_availability_template`, `parse_resource_file`, `_parse_class_availability_file`, `_validate_class_availability`, `validate_import`, `ExistingTeacher`, `ImportSnapshot`, `ValidationResult` | S2, S3 |
| `backend/app/services/bulk_import_service.py` | Importa símbolos da política e lê `.course_abbreviation`, `.class_name`, `.scores` no `commit` (S2, S3 atualizam as chamadas); `template_bytes`, `_class_availability_template`, `load_snapshot` (S4); `commit_import` (S5) | S2–S5 |
| `backend/app/schemas.py` | `BulkImportFiles` e `require_a_file` | S4 |
| `backend/app/api/v1/endpoints/imports.py` | Rotas genéricas por `resource`. Não mudam. | — |
| `backend/app/services/teacher_service.py` | `set_teacher_availability`, reutilizada sem mudanças pelo `commit` | S5 |
| `backend/app/services/preflight_service.py` | Mensagem de `MISSING_TEACHER_AVAILABILITY` | S1 |
| `backend/app/services/school_readiness_service.py` | Mensagem de `TEACHER_AVAILABILITY` | S1 |
| `backend/app/models.py` | Comentários de `PreferenceLevel` | S1 |
| `backend/app/scheduler/infrastructure/occurrences.py` | Motivo de exclusão de um substituto com bloco Impossível | S1 |
| `frontend/src/features/imports/data.js` | `IMPORT_RESOURCES`, `IMPORT_COUNT_LABELS`, `IMPORT_INVALIDATIONS` | S6 |
| `frontend/src/pages/BulkImport.jsx` | Descrição da página e tabelas de disponibilidade | S6 |
| `frontend/src/features/marketing/content/home.js`, `workflow.js` | Texto sobre os níveis (S1) e sobre a disponibilidade do professor (S7) | S1, S7 |
| `frontend/src/features/tutorial/tutorialContent.js` | Passo `availability` | S1 |
| `frontend/src/components/AvailabilityGrid.jsx` | Texto acessível da célula sem bloco (S1) e da grelha (S7) | S1, S7 |
| `frontend/src/components/appNavigation.js` | Menu do professor | S7 |
| `frontend/src/pages/MyAvailability.jsx` | Título, estados, botão e mensagens | S7 |
| `frontend/src/components/AvailabilityEditorModal.jsx` | Estado sem blocos | S7 |
| `frontend/src/features/marketing/components/workflow/TeacherWorkflowSection.jsx` | Textos da área do professor | S7 |
| `frontend/src/components/Forms/SubjectForm.jsx`, `frontend/src/pages/Subjects.jsx` | Rótulo e coluna do tipo de sala | S7 |
| `frontend/e2e/utils/clerk-helpers.js`, `frontend/e2e/foundation/teacher-self-service-availability.spec.js` | Título da rota e nome do botão esperados | S7 |

`grid_change_service.py`, o motor e a fingerprint leem a tabela `availability`. Não mudam, porque o `commit` escreve pela mesma função da janela.

## Data or Request Flow

### Formato do ficheiro

O modelo `Cronos_DisponibilidadeProfessores_Template.csv` usa `;`, CRLF e BOM UTF-8, como os outros modelos.

| Nome do professor | Email do professor | Dia | 08:30 | 09:20 | … |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Ana Silva | ana.silva@escola.pt | Segunda | Neutro | Evitar | … |
| Ana Silva | ana.silva@escola.pt | Terça | Impossível | Neutro | … |

- As colunas de hora são as horas de início distintas da versão visível, por ordem. Igual às turmas.
- Há uma linha por professor ativo e por dia com blocos. Ordem: nome sem distinguir maiúsculas, email, dia.
- Cada célula traz o nível atual. Uma linha em falta na tabela `availability` conta como Neutro.
- Uma hora sem bloco nesse dia fica vazia.
- Sem professores ativos, o modelo traz só o cabeçalho.
- Sem blocos, o pedido devolve `400 bad_request` com `A escola ainda não configurou blocos.`, como nas turmas.

### Contrato HTTP

| Rota | Mudança |
| :--- | :--- |
| `GET /api/v1/imports/templates/teacher_availability` | Novo recurso. Devolve o modelo acima. |
| `POST /api/v1/imports/validate` | Aceita `files.teacher_availability`. |
| `POST /api/v1/imports/commit` | Aceita `files.teacher_availability`. `created_counts.teacher_availability` conta os professores atualizados. |

`preview.counts.teacher_availability` conta os professores do ficheiro.
Cada professor dá um item em `preview.items`:

| Campo | Valor |
| :--- | :--- |
| `resource` | `teacher_availability` |
| `teacher_name` | Nome guardado do professor. Para um professor do mesmo lote, o nome do ficheiro "Professores e competências". |
| `teacher_email` | Email normalizado. |
| `changed_blocks` | Número de blocos da versão visível cujo nível muda. |
| `line` | Primeira linha do professor no ficheiro. |

O item `class_availability` troca `non_neutral_blocks` por `changed_blocks` (D14).
A interface é o único leitor deste campo.

### Parser partilhado

Uma tabela de recursos de grelha semanal substitui as constantes `CLASS_AVAILABILITY_*`.
Cada entrada define o recurso, os três títulos fixos, os nomes dos campos e o nome do ficheiro.
`parse_resource_file` e o parser dinâmico usam essa tabela:

- Um ficheiro de grelha começa pelos três títulos fixos do seu recurso.
- Os títulos fixos de outro recurso, de grelha ou fixo, dão `resource_mismatch`.
  Isto inclui o ficheiro "Professores e competências", que partilha as duas primeiras colunas.
- Um ficheiro de grelha escolhido num cartão de recurso fixo também dá `resource_mismatch`.

### Validador partilhado

Um só validador de grelha semanal trata os dois recursos.
Recebe o recurso, uma função que resolve a linha numa entidade e as grelhas atuais.
As regras de horas, dias, células e repetidos de [BULK_IMPORT_CSV.md](../07_data_and_seed/BULK_IMPORT_CSV.md#disponibilidade-das-turmas) mantêm-se para os dois.

Resolução do professor (D04, D07, D08), por esta ordem. O email é normalizado com `_email` nos dois lados, no ficheiro e no snapshot.

1. O email vazio ou que não existe na organização nem no lote dá `teacher_reference_missing`.
2. O email de um professor arquivado ou sem capacidade de professor dá `teacher_inactive`.
3. O email de um professor ativo ou do lote resolve a linha.

Um membro que perde a capacidade de professor sem histórico perde o perfil (`_sync_teacher_profile`). O email dele dá `teacher_reference_missing`.

`ExistingTeacher` ganha o indicador de professor ativo e `ImportSnapshot` ganha as grelhas atuais de professores e turmas.
Os campos novos têm valores por omissão. `snapshot.teachers` continua a incluir os professores arquivados, porque as regras de email repetido da secção "Professores e competências" dependem deles.
O serviço lê o indicador do membro que `load_snapshot` já carrega (`lifecycle_status`, `can_teach`). Carrega as grelhas atuais só quando o lote traz um ficheiro de disponibilidade.

Depois de juntar os dias de cada entidade, o validador calcula:

- `changed_blocks`: blocos da versão visível em que o nível novo difere do atual. Um nível em falta conta como Neutro nos dois lados.
- O aviso `all_blocks_impossible` quando todos os blocos da versão visível ficam em Impossível (D09, D14).

A entidade do mesmo lote tem a grelha atual toda em Neutro.

### Pré-visualização

- As linhas `class_availability` e `teacher_availability` ficam fora do corte de 100 itens (D15).
- Turmas: `changed_blocks` decrescente, depois sigla, depois turma.
- Professores: `changed_blocks` decrescente, depois nome sem distinguir maiúsculas, depois email. A interface usa o email como chave da linha.

### Aplicação

O `commit` aplica as grelhas dos professores depois das grelhas das turmas.
Para cada professor do ficheiro chama `teacher_service.set_teacher_availability` com um nível por bloco da versão visível.
Os blocos sem nível no ficheiro recebem Neutro.
O identificador é o `teacher.id` do professor existente ou o do professor criado no lote.

`set_teacher_availability` já faz o necessário:

- Valida o conjunto de blocos contra a versão visível.
- Substitui a grelha inteira do professor.
- Regista a alteração `TEACHER_AVAILABILITY` com a operação `BULK_IMPORT`.
- Marca o recurso como ativo quando o professor tem aulas, o que atualiza a revisão do motor.

### Interface

Entrada nova em `IMPORT_RESOURCES`, depois de `class_availability`:

- Rótulo `Disponibilidade dos professores`. Origem `/members`. Ficheiro `Cronos_DisponibilidadeProfessores_Template.csv`.
- Campos: `teacher_name` → `Nome do professor`, `teacher_email` → `Email do professor`, `day` → `Dia`.
- Instruções:
  - `O modelo já traz os professores ativos, as horas da grelha e a disponibilidade atual.`
  - `Cada linha é um professor num dia. Cada coluna de hora é um bloco.`
  - `O email identifica o professor. O nome serve só para ler o ficheiro.`
  - `Escreva Impossível, Evitar, Neutro ou Preferencial. Uma célula vazia conta como Neutro.`
  - `Cada professor do ficheiro fica com a grelha do ficheiro. Os professores que não aparecem ficam iguais.`
  - `Não apague colunas de hora. Se a grelha mudar, descarregue um modelo novo.`

Contagem: `teacher_availability` → `Disponibilidade dos professores`.
Descrição da página: `Adicione várias salas, disciplinas, cursos, turmas e professores e atualize a disponibilidade das turmas e dos professores de uma só vez.`

Tabelas da pré-visualização, uma por recurso presente:

| Recurso | Legenda | Colunas |
| :--- | :--- | :--- |
| Turmas | `Disponibilidade das turmas por turma` | `Sigla do curso`, `Nome da turma`, `Blocos que mudam` |
| Professores | `Disponibilidade dos professores por professor` | `Nome do professor`, `Email do professor`, `Blocos que mudam` |

Um valor zero aparece como `Sem alterações`.

`IMPORT_INVALIDATIONS` acrescenta `teacher-availability`, `substitute-recommendations`, `substitute-diagnostics`, `occurrences`, `teacher-progress`, `my-availability` e `heatmap`.
As cinco primeiras são as que `useSaveTeacherAvailability` invalida. As duas últimas leem a mesma grelha.

### Uniformização dos nomes (D13)

| Ficheiro | Texto atual | Texto novo |
| :--- | :--- | :--- |
| `preflight_service.py` | `Professores sem disponibilidade configurada: {nomes}. Configure em Professores > Disponibilidade.` | `Professores com todos os blocos marcados como Impossível: {nomes}. Marque pelo menos um bloco como Neutro, Evitar ou Preferencial em Equipa > Editar disponibilidade.` |
| `school_readiness_service.py` | `Registe disponibilidade docente não impossível.` | `Marque pelo menos um bloco como Neutro, Evitar ou Preferencial na disponibilidade dos professores atribuídos.` |
| `home.js` | `Indique quando prefere, evita ou não pode lecionar.` | `Marque cada bloco como Preferencial, Neutro, Evitar ou Impossível.` |
| `workflow.js` | `Cada docente indica na grelha quando prefere, evita ou não pode lecionar.` | `Cada docente marca cada bloco da grelha como Preferencial, Neutro, Evitar ou Impossível.` |
| `tutorialContent.js` | `A grelha distingue preferências e períodos impossíveis.` | `Cada bloco fica Preferencial, Neutro, Evitar ou Impossível.` |
| `occurrences.py` | `Candidato indisponível para o período.` | `O professor marcou este bloco como Impossível.` |
| `AvailabilityGrid.jsx` | `aria-label="Bloco indisponível"` num `div` sem papel | Texto `Sem bloco` com a classe `visually-hidden`; o `—` fica `aria-hidden`. |
| `models.py` | Comentários "Quero muito", "Tanto faz", "Proibido" | Os quatro nomes da aplicação. |

A mensagem antiga do preflight estava errada: o professor tem grelha, mas está toda em Impossível.
A nova segue a mensagem das turmas, `CLASS_WITHOUT_AVAILABILITY`.
Um `aria-label` num `div` sem papel não é lido pelos leitores de ecrã, por isso o texto passa a escondido visualmente.
O [Glossário](../00_getting_started/GLOSSARY.md) ganha a entrada "Nível de disponibilidade" com os quatro nomes, no PR 1.

### Nome da grelha e do tipo de sala (D16, D17)

| Ficheiro | Texto atual | Texto novo |
| :--- | :--- | :--- |
| `appNavigation.js` | Menu `Preferências` | `Minha Disponibilidade` |
| `MyAvailability.jsx` | Título `Minhas Preferências`, nos quatro estados | `Minha Disponibilidade` |
| `MyAvailability.jsx` | `A carregar preferências` | `A carregar disponibilidade` |
| `MyAvailability.jsx` | `As preferências ficam disponíveis depois de a grelha horária ser configurada.` | `A disponibilidade aparece depois de configurar a grelha horária.` |
| `AvailabilityEditorModal.jsx` | `A disponibilidade fica disponível depois de a grelha horária ser configurada.` | `A disponibilidade aparece depois de configurar a grelha horária.` |
| `MyAvailability.jsx` | `Sem permissões para consultar preferências de disponibilidade.` | `Sem permissões para consultar a disponibilidade.` |
| `MyAvailability.jsx` | `Falha ao carregar preferências de disponibilidade. Tente novamente.` | `Falha ao carregar a disponibilidade. Tente novamente.` |
| `MyAvailability.jsx` | Botão `Guardar preferências` | `Guardar disponibilidade` |
| `MyAvailability.jsx` | `Preferências guardadas.` | `Disponibilidade guardada.` |
| `AvailabilityGrid.jsx` | `Grelha de preferências de disponibilidade` | `Grelha de disponibilidade` |
| `home.js` | `O professor define as suas preferências, consulta…`; título `Defina preferências` | `O professor define a sua disponibilidade, consulta…`; `Defina a disponibilidade` |
| `workflow.js` | Título `As preferências são definidas pelo professor`; ponto `Escolha cada nível de preferência.` | `A disponibilidade é definida pelo professor`; `Escolha o nível de cada bloco.` |
| `TeacherWorkflowSection.jsx` | `Minhas preferências`; `As preferências, o horário ativo, os registos e o progresso seguem a mesma rotina.` | `Minha Disponibilidade`; `A disponibilidade, o horário ativo, os registos e o progresso seguem a mesma rotina.` |
| `SubjectForm.jsx` | Rótulo `Sala Preferencial` | `Tipo de sala` |
| `Subjects.jsx` | Coluna `Requisito de Sala` | `Tipo de sala` |

O tipo de sala é obrigatório no motor (`constraint_policy.py`). "Preferencial" sugeria o contrário e confundia-se com o nível.

## Contracts and Invariants

### Identificadores

| Campo | Aponta para |
| :--- | :--- |
| `teacher_id` no `commit` | `teacher.id`. Nunca `organization_membership.id` nem `users.id`. |
| Email da linha | `users.email` da conta do membro, normalizado com `_email`. |
| `timeslot_id` | `timeslot.id` da versão visível na data da escola. |
| `class_id` | `class.id`. |

### Invariantes

- **I01** A validação não grava nada.
- **I02** O `commit` volta a validar com dados novos. Um erro impede qualquer gravação.
- **I03** Toda a consulta filtra por `organization_id`. A RLS forçada protege as tabelas.
- **I04** O `commit` escreve só por `set_teacher_availability` e `replace_class_availability`.
- **I05** O modelo, a validação e o `commit` usam a mesma versão visível da grelha.
- **I06** O parser aceita só os quatro nomes dos níveis.
- **I07** Um nível em falta significa Neutro, na grelha atual e no ficheiro.

## States and Transitions

Não se aplica. A importação não cria estados novos: valida e grava de uma vez, como as outras secções.

## Failure Modes

Códigos novos. Os restantes são os das turmas.

| Código | Gravidade | Mensagem | Campo |
| :--- | :--- | :--- | :--- |
| `teacher_reference_missing` | Erro | `Não existe nenhum professor com este email.` | `teacher_email` |
| `teacher_inactive` | Erro | `Este professor está arquivado ou já não leciona. Retire a linha ou reative-o na Equipa.` | `teacher_email` |
| `duplicate_teacher_day` | Erro | `Este professor já tem uma linha para este dia.` | — |
| `all_blocks_impossible` (professor) | Aviso | `O professor fica com todos os blocos em Impossível. Se tiver aulas, a geração do horário fica bloqueada.` | — |
| `all_blocks_impossible` (turma) | Aviso | `A turma fica com todos os blocos em Impossível. Se tiver aulas, a geração do horário fica bloqueada.` | — |

`level_invalid` mantém `Escreva Impossível, Evitar, Neutro ou Preferencial.` para os dois recursos.

## Cenários de risco

| ID | Perigo | Cenário (teste que falha primeiro) | Ficheiro de teste |
| :--- | :--- | :--- | :--- |
| R01 | Confusão de identificadores | Com ids de membro e de professor diferentes, o `commit` grava no `teacher.id` certo. | `backend/tests/integration/committed/test_bulk_import.py` |
| R02 | Identificador | `Ana@Escola.PT` no ficheiro resolve `ana@escola.pt`, e `ana@escola.pt` resolve um email guardado com maiúsculas. | `backend/tests/unit/test_bulk_import_policy.py` |
| R03 | Escrita múltipla | Cinco linhas de dias do mesmo professor dão uma grelha com os cinco dias. | `test_bulk_import_policy.py`, `test_bulk_import.py` |
| R04 | Escrita múltipla | Os professores ausentes do ficheiro mantêm a grelha. | `test_bulk_import.py` |
| R05 | Estados vazios e limites | Um professor arquivado e um membro que perdeu a capacidade de professor, com perfil mantido por histórico, ficam fora do modelo e dão `teacher_inactive`. | `test_bulk_import_policy.py`, `test_bulk_import.py` |
| R06 | Isolamento de tenant | O email de um professor de outra organização dá `teacher_reference_missing`; a outra organização fica igual. | `backend/tests/integration/committed/test_tenant_isolation_business.py` |
| R07 | Escrita múltipla | Um professor criado no mesmo lote recebe a grelha do ficheiro. | `test_bulk_import.py` |
| R08 | Versão ou data | Com uma versão futura pendente, o modelo e o `commit` usam a versão visível. | `test_bulk_import.py` |
| R09 | Identificador | Um ficheiro de professores no cartão das turmas, no cartão "Professores e competências" e o inverso dão `resource_mismatch`. | `test_bulk_import_policy.py` |
| R10 | Reversão | Grelha igual dá 0 blocos alterados; apagar a linha de um dia conta os blocos não Neutro desse dia. | `test_bulk_import_policy.py` |
| R11 | Estados vazios e limites | Com 120 professores e 10 salas, a pré-visualização traz os 120 professores. | `test_bulk_import_policy.py` |
| R12 | Estados vazios e limites | `Proibido` e `Prefere` dão `level_invalid`; `impossivel` e `NEUTRO` são aceites. | `test_bulk_import_policy.py` |
| R13 | Leitores do motor | Importar a grelha de um professor com aulas regista uma alteração `BULK_IMPORT` e muda a fingerprint. | `test_bulk_import.py` |
| R14 | Estados vazios e limites | Uma grelha toda em Impossível dá aviso e `can_commit` verdadeiro, para professor e turma. | `test_bulk_import_policy.py` |
| R15 | Estados vazios e limites | Sem professores ativos o modelo traz só o cabeçalho; sem blocos devolve a mensagem exata. | `test_bulk_import_policy.py`, `test_bulk_import.py` |
| R16 | Escrita múltipla | Um professor arquivado entre a validação e o `commit` faz o `commit` falhar sem gravar. | `test_bulk_import.py` |
| R17 | Uniformização | O preflight de um professor todo em Impossível e a prontidão sem bloco possível usam as mensagens novas. | `backend/tests/contracts/test_preflight_service.py`, `backend/tests/contracts/test_school_readiness_service.py` |
| R18 | Interface | As duas tabelas mostram `Blocos que mudam` e `Sem alterações` para zero. | `frontend/src/test/BulkImport.test.jsx` |
| R19 | Leitores do motor | Depois do `commit`, as chaves da disponibilidade dos professores são invalidadas. | `frontend/src/test/importInvalidations.test.jsx` |
| R20 | Uniformização | `/my-availability` mostra `Minha Disponibilidade` no título e no menu; `Guardar disponibilidade` grava e mostra `Disponibilidade guardada.` | `frontend/src/test/MyAvailability.test.jsx`, `frontend/src/test/DefaultLayout.test.jsx`, `frontend/e2e/foundation/teacher-self-service-availability.spec.js` |
| R21 | Uniformização | O formulário da disciplina mostra o campo `Tipo de sala` e a lista mostra a coluna `Tipo de sala`. | `frontend/src/test/SubjectForm.test.jsx`, `frontend/src/test/Subjects.test.jsx` |

Perigos sem cenário:

- Histórico: a disponibilidade não altera Sumários, Faltas nem minutos creditados.
- Cadeia de migrações: não há migração.

## Coexistência

- Base `main` em `e787aa5`. Última revisão Alembic `0004_joint_lesson_groups`. Esta funcionalidade não acrescenta revisões.
- Pull requests abertos a 15 de outubro de 2026: #129 e #130 (só documentação) e três atualizações do Dependabot. Nenhum toca nos ficheiros do inventário.
- Os ramos `feat/class-availability-engine`, `feat/class-module-selection-server-isolated` e `feat/joint-lessons` já entraram em `main` por squash. Não há trabalho concorrente.
- `bulk_import_policy.py` e `bulk_import_service.py` são ficheiros quentes. Só os slices S2 a S5 os mudam, em sequência.

## Verification Procedure

Use os perfis da [Command Reference](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type):

1. Política pura (S2, S3): perfil "Backend pure logic" com o filtro `bulk_import`.
2. Serviço e `commit` (S4, S5): perfil "Backend endpoint, service, or query", depois `integration` com o filtro `bulk_import or tenant_isolation`.
3. Mensagens do preflight (S1): perfil "Backend endpoint, service, or query" com o filtro `preflight or readiness`. O filtro só reduz `integration`; os testes `contracts` correm todos.
4. Interface (S1, S6, S7): perfil "Frontend component or hook" com os ficheiros de teste do slice.
   S7 muda o título de uma rota: corra também o perfil "Frontend route or user journey" com os projetos `app` e `auth`, quando houver dados de teste Clerk.
5. Pull request: os quatro checks obrigatórios do CI.
6. Depois do merge, reconstrua o contentor `frontend` e confirme localmente:
   descarregue o modelo, altere dois professores, verifique a tabela e importe.

## Source Map

- Política e parser: `backend/app/services/bulk_import_policy.py`
- Serviço: `backend/app/services/bulk_import_service.py`
- Gravação: `backend/app/services/teacher_service.py` (`set_teacher_availability`)
- Mensagens: `backend/app/services/preflight_service.py`, `backend/app/services/school_readiness_service.py`
- Interface: `frontend/src/pages/BulkImport.jsx`, `frontend/src/features/imports/data.js`

## Related Documents

Documentação a atualizar no PR 2. O PR 1 atualiza o [Glossário](../00_getting_started/GLOSSARY.md): entradas "Nível de disponibilidade" e "Tipo de sala", e o nome da página do professor na entrada "Disponibilidade".

| Documento | Mudança |
| :--- | :--- |
| [Bulk Import CSV](../07_data_and_seed/BULK_IMPORT_CSV.md) | Secção nova, tabela de modelos, "Blocos que mudam", aviso, limite da pré-visualização e nomes das funções partilhadas. |
| [API Reference](../05_backend_api/API_REFERENCE.md) | Recurso `teacher_availability`. |
| [Feedback Message Matrix](../06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md) | Erros de célula da secção nova. |
| [Repository Map](../00_getting_started/REPOSITORY_MAP.md) | A disponibilidade dos professores também se grava por importação. |

Outros documentos:

- [WBS](TEACHER_AVAILABILITY_IMPORT_WBS.md)
- [Class Availability Tech Spec](CLASS_AVAILABILITY_TECH_SPEC.md)
- [School Configuration](SCHOOL_CONFIGURATION.md)
