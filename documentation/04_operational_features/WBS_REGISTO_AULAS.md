# Plano WBS: Funcionalidade de Registo de Aulas, Fecho Semanal e Transição de Ano Letivo

## 1. O Conceito (Os 5 Ws)

*   **Who (Quem):** Professores (para o registo diário/semanal das aulas lecionadas) e Administradores (para a aprovação de semanas e gestão do ano letivo).
*   **What (O quê):** Uma nova arquitetura de execução de aulas que permite o registo de horas dadas (com ou sem sumário), o fecho (submissão) de semanas completas pelos professores (workflow tipo *Tempo*), aprovação pelo Admin e, por fim, o *Soft-Reset* do ano letivo com retenção de dados base.
*   **Where (Onde):** O registo individual será feito diretamente nos blocos da página `/schedules`. A aprovação semanal terá um painel dedicado para a administração (ex: `/timesheets` ou um separador em `/occurrences`). O *Soft-Reset* viverá em `Configurações > Calendário`.
*   **When (Quando):** Os professores registam aulas após a sua ocorrência. As semanas são submetidas no fim da última aula da semana. O *Soft-Reset* ocorre no final do ano letivo, antes de preparar as novas turmas.
*   **Why (Porquê):** Para eliminar a falha estrutural de usar "Ocorrências" para registar aulas normais (que é um anti-padrão), para simplificar o preenchimento diário, para garantir que o Admin tem controlo sobre o histórico submetido e para que o sistema possa transitar de ano sem obrigar ao re-preenchimento de entidades base (professores, cursos, salas).

---

## 2. WBS (Work Breakdown Structure)

Este plano técnico divide a implementação em Fases, Tarefas e Resultados Esperados (Critérios de Aceitação). Nenhum passo pode ser considerado concluído sem que o Resultado Esperado seja validado com testes já existentes ou novos testes criados para o efeito. Em caso de dúvida, deve-se consultar os próximos passos ou anteriores deste documento, consultar qualquer outra documentação e/ou código existente.

### Fase 1: Atualização do Domínio e Base de Dados (Backend)

Esta fase prepara o alicerce para gravar os dados de execução e as submissões semanais.

*   **1.1. Criar modelo `LessonLog` (ou adicionar campos no `ScheduleBlock`)**
    *   **Descrição:** Criar a tabela `lesson_logs` (relacionada 1-para-1 com `schedule_blocks` ou `generated_blocks`).
    *   **Campos técnicos:** `block_id` (FK), `status` (Enum: `PENDING`, `COMPLETED`, `OCCURRENCE`), `summary` (Text, Nullable), `notes` (Text, Nullable).
    *   **Resultado Esperado:** O modelo SQLAlchemy está definido. Uma *query* na base de dados permite extrair um bloco gerado e o seu respetivo `LessonLog` através de um `.join()`.

*   **1.2. Criar modelo `TeacherWeeklyTimesheet`**
    *   **Descrição:** Criar a tabela para gerir o estado da submissão da semana.
    *   **Campos técnicos:** `id`, `teacher_id` (FK), `week_start_date` (Date), `week_end_date` (Date), `status` (Enum: `OPEN`, `SUBMITTED`, `APPROVED`), `submitted_at` (DateTime, Nullable).
    *   **Resultado Esperado:** Tabela criada na BD e devidamente relacionada com a entidade `Teacher`.

*   **1.3. Gerar e aplicar a migração (Alembic)**
    *   **Descrição:** Criar o script Alembic (`alembic revision --autogenerate -m "Add lesson_logs and timesheets"`) e correr `alembic upgrade head`.
    *   **Resultado Esperado:** As tabelas existem fisicamente no PostgreSQL local/remoto.

*   **1.4. Refatorizar o Progresso da Disciplina**
    *   **Descrição:** O sistema que conta as "Horas Dadas" de uma disciplina deve passar a consultar o `status` (`COMPLETED`) na tabela `LessonLog`, desassociando-se do antigo método que usava a tabela de ocorrências.
    *   **Resultado Esperado:** Um endpoint de progresso retorna +1 hora sempre que um LessonLog transita para `COMPLETED`, e reverte para a hora anterior se voltar para `PENDING`.

---

### Fase 2: Interface de Registo Diário (Professor na página `/schedules`)

Esta fase transforma o professor num agente ativo na página de horários, permitindo-lhe confirmar as aulas e criar ocorrências nas suas próprias aulas.

*   **2.1. Regras de Negócio e Permissões de Acesso aos Blocos**
    *   **Descrição:** No frontend, injetar a lógica que distingue o Admin do Professor (usando o contexto de Auth). O Professor apenas pode interagir com os blocos que pertencem ao seu `teacher_id`.
    *   **Resultado Esperado:** Ao fazer login como Professor, o clique sobre um bloco que lhe pertence abre o Modal de Ação. É completamente proibido um professor conseguir visualizar ou interagir com blocos que pertençam a outros professores.

*   **2.2. Modal de Ação do Bloco (Sumário e Notas)**
    *   **Descrição:** Ao clicar num bloco, surge um modal ou painel lateral contendo botões "Concluir Aula", "Registar Falta" e campos opcionais "Sumário" e "Notas".
    *   **Resultado Esperado:** A interface mostra os campos. Preencher os campos e submeter faz uma chamada PATCH/POST ao backend, criando o `LessonLog`.

*   **2.3. Bloqueio no Tempo (Viagens ao Futuro)**
    *   **Descrição:** Implementar a lógica (Front e Back) que impede a alteração do `status` de uma aula que ainda não terminou.
    *   **Resultado Esperado:** Tentar concluir um bloco cuja hora de fim (`end_time`) é superior a `datetime.now()` resulta num botão "disabled" no frontend e num `HTTP 400 Bad Request` na API.

*   **2.4. Feedbacks Visuais no Horário**
    *   **Descrição:** Alterar o componente de renderização do bloco.
    *   **Resultado Esperado:** Blocos `PENDING` (opacos/normais), `COMPLETED` (sólidos/verdes), `OCCURRENCE` (tracejados/vermelhos).

---

### Fase 3: Workflow de Fecho Semanal (Tempo Style)

A lógica central da aprovação em massa e validação semanal.

*   **3.1. Botão "Registar Semana" para o Professor**
    *   **Descrição:** Na UI do `/schedules` do Professor, adicionar o botão de fecho da semana vista.
    *   **Resultado Esperado:** O botão só está ativo se **todas** as aulas geradas para aquele professor naquela semana tiverem o status definido (diferente de `PENDING`) **E** se não houver aulas agendadas para o futuro nessa semana. Caso contrário, encontra-se `disabled` (ou com *tooltip* a explicar o motivo).

*   **3.2. Endpoint de Submissão Semanal**
    *   **Descrição:** A API que recebe o pedido do professor e altera o estado do `TeacherWeeklyTimesheet` para `SUBMITTED`.
    *   **Resultado Esperado:** Um POST com sucesso que tranca imediatamente todas as aulas dessa semana. O Professor, ao recarregar a página, não consegue alterar (adicionar sumários ou mudar *status*) nenhuma aula dessa semana.

*   **3.3. Criação do Painel Administrativo de Fecho**
    *   **Descrição:** Criar uma nova página/tab (ex: `Aprovações Semanais` ou `/timesheets`) exclusiva para Admins. Usar o componente `SmartTable` para listar `TeacherWeeklyTimesheet`.
    *   **Resultado Esperado:** Uma tabela que lista os professores, as semanas (ex: 12 Out - 16 Out) e o estado (Pendente, Submetido, Aprovado).

*   **3.4. Aprovação e Reabertura de Semana pelo Admin**
    *   **Descrição:** Ações que permitem ao Admin fechar (`APPROVED`) ou rejeitar/reabrir (`OPEN`) uma timesheet, diretamente na tabela ou no modal.
    *   **Resultado Esperado:** Ao aprovar, o estado consolida. Ao reabrir (mudança forçada para `OPEN`), o professor ganha acesso novamente para editar as aulas. Todas as validações visuais funcionam corretamente.

---

### Fase 4: Gestão do Ano Letivo (Soft-Reset)

A preparação da transição do ano.

*   **4.1. Construção da UI na Configuração da Escola**
    *   **Descrição:** Em `/settings` (Configurações da Escola) > tab "Calendário", adicionar um botão vermelho de "Recomeçar Ano Letivo".
    *   **Resultado Esperado:** O botão abre um Wizard (Modal de Passos).

*   **4.2. Modal de Confirmação (Wizard Destrutivo)**
    *   **Descrição:** O modal avisa que todas as gerações, ocorrências, progresso de disciplinas e sumários serão apagados, preservando os professores, turmas, cursos, disciplinas, módulos, e salas. O Progresso por Disciplina e módulo deve ser resetado para 0.   
    *   **Resultado Esperado:** O botão final de perigo só fica `enabled` quando o utilizador faz *check* numa *checkbox* de responsabilidade E digita exatamente a palavra "Confirmo" num input textual.

*   **4.3. Endpoint de Soft-Reset (Database Wipe Parcial)**
    *   **Descrição:** O endpoint que efetivamente corre o `TRUNCATE` ou as `DELETE` queries nas tabelas dinâmicas.
    *   **Tabelas a limpar:** `schedule_blocks`, `occurrences`, `lesson_logs`, `teacher_weekly_timesheets`.
    *   **Tabelas a sofrer Reset:** `SubjectProgress` ou equivalentes devem voltar a 0 horas.
    *   **Resultado Esperado:** Após execução com sucesso (HTTP 200), o sistema apresenta-se vazio de horários mas mantendo os utilizadores e estruturas base perfeitamente intactos. A escola está pronta para o próximo ano.
