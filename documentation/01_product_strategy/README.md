# Product Strategy

Esta secao fixa compromissos estrategicos estaveis do Cronos.

## Conteudo principal
- OBJECTIVO_FINAL_OVERVIEW.md: 5 Ws oficiais, operacao diaria ponta a ponta e criterios minimos da fase atual.
- PRD_CLERK_TEACHER_USER_CREATION.md: fonte de verdade do baseline fechado para `Equipa`, `/members`, convites Clerk, capacidades locais e remocao do CRUD admin visivel em `/teachers`.
- TECH_SPEC_CLERK_BACKED_EQUIPA_MEMBER_MANAGEMENT.md: especificacao tecnica que traduz o PRD de `Equipa` em arquitetura, schema, API, operacoes Clerk, webhooks, autorizacao, migracao e testes.
- WBS_CLERK_BACKED_EQUIPA_MEMBER_MANAGEMENT.md: plano de execucao diretamente implementavel para aplicar o baseline Clerk-backed de `Equipa`, migracao, API `/members`, frontend, limpeza legacy e testes.
- WBS_ALPHA_V1_ENTREGA.md: work breakdown structure detalhado para fechar a Alpha V1 (implementacao, testes e edge cases).
- WBS_VISAO_PROFESSOR_E_ACESSOS.md: plano detalhado para separar experiencia admin/professor no menu, rotas e sincronismo de horarios do professor.
- ALPHA_PILOT_GO_NO_GO.md: checklist de prontidao, suporte reativo e recolha de feedback para decisao final do piloto.
- ROLLOUT_CHECKLIST_PROFESSOR_ACESSOS.md: checklist tecnico-operacional por role para promocao staging -> piloto da feature professor/acessos.

## Decisoes ja fechadas
- modelo SaaS premium para escolas profissionais privadas;
- modelo de adocao self-service com suporte ao cliente sob demanda;
- `Equipa` e o espaco admin visivel para gerir membros; `/members` e a fronteira API canonica de staff management;
- capacidades locais de membro (`teacher`, `admin`, ou ambas) substituem roles mutuamente exclusivos como fonte de permissao de produto;
- Clerk e a fonte de verdade para identidade, password, convite, aceitacao e membership de organizacao;
- sem escopo de apoio individual ao aluno;
- foco operacional em gestao de horarios e confiabilidade de execucao.
