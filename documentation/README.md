## Cronos Documentation

Este indice define a verdade documental estavel do projeto.
So inclui informacao confirmada e com alta probabilidade de permanecer estavel.

## 5 Ws do projeto

### What

Cronos e uma aplicacao SaaS para gestao e geracao de horarios no Ensino Profissional em Portugal.
Nao e um calendario anual estatico. E um sistema operacional dinamico que planeia, replaneia e regista execucao real.

### Who
Perfis de utilizador confirmados:
- admin: acesso total dentro da sua organizacao.
- professor (normal/comum): apenas marca disponibilidade e consulta os seus horarios.

Nao existe suporte operacional individual para alunos dentro da aplicacao.
A escola continua responsavel por essa gestao fora do escopo do produto.

### Where
Escopo B2B: escolas profissionais privadas em Portugal.
Arquitetura multi-tenant: cada escola opera isolada por organization_id.

### When
Fase atual confirmada:
- novo baseline do motor de horarios fechado em `03_scheduler_engine/PRD_SCHEDULE_GENERATOR_NEW_BASELINE.md`;
- arquitetura tecnica fechada em `03_scheduler_engine/TECH_SPEC_SCHEDULE_GENERATOR_NEW_BASELINE.md`;
- hard end date obrigatoria;
- sem target/preferred end date como objetivo de otimizacao;
- prioridade funcional seguinte: implementar o novo schedule generator por WBS.

### Why
Objetivo de negocio:
- eliminar a burocracia e a friccao operacional na gestao de horarios do Ensino Profissional;
- oferecer produto premium para area administrativa, com foco em confiabilidade e controlo real de execucao.

## Estrutura documental por 3 layers (clean architecture)

### Layer 1: Interface
Responsavel pela entrada e saida do sistema, sem decidir regras de dominio.

Ficheiros principais:
- 05_backend_api/
- 06_frontend_ux/

### Layer 2: Regras de negocio
Responsavel pelas decisoes do dominio (invariantes, motor, fluxo operacional, autorizacao por papel).

Ficheiros principais:
- 01_product_strategy/
- 02_domain_model/
- 03_scheduler_engine/
- 04_operational_features/

### Layer 3: Base de dados
Responsavel por persistencia, isolamento por tenant, historico imutavel e consistencia transacional.

Ficheiros principais:
- 07_data_and_seed/
- 08_security_quality/
- 09_ops_observability/

## Regras de qualidade desta documentacao

- Registar apenas factos confirmados.
- Quando um topico nao estiver fechado, marcar explicitamente como "a definir".
- Evitar detalhes especulativos.
- Priorizar rastreabilidade entre decisao de negocio e impacto tecnico.

## Documentos Transversais

- [CONTRIBUTING.md](00_governance/CONTRIBUTING.md) — Guia de contribuicao (Alembic, estilo, CI)
- [AUDITORIA_ARQUITETURAL_ALPHA_1.0.md](08_security_quality/AUDITORIA_ARQUITETURAL_ALPHA_1.0.md) — Auditoria de qualidade (28 findings, Maio 2026)
- [auditoria-frontend-ui-ux.md](auditoria-frontend-ui-ux.md) — Auditoria completa de frontend UI/UX (46 findings, 100% corrigidos a 03 Maio 2026)

## Planeamento de entrega

- WBS oficial da Alpha V1: 01_product_strategy/WBS_ALPHA_V1_ENTREGA.md
- Baseline fechado para Equipa/membros/Clerk: 01_product_strategy/PRD_CLERK_TEACHER_USER_CREATION.md
- Especificacao tecnica do baseline Equipa/membros/Clerk: 01_product_strategy/TECH_SPEC_CLERK_BACKED_EQUIPA_MEMBER_MANAGEMENT.md
- WBS de implementacao Equipa/membros/Clerk: 01_product_strategy/WBS_CLERK_BACKED_EQUIPA_MEMBER_MANAGEMENT.md

## Fonte canonica para implementacao da Alpha V1

Para implementacao e validacao da Alpha V1, considerar como fonte oficial:
- estrutura por layers em 00_governance ate 09_ops_observability;
- WBS oficial em 01_product_strategy/WBS_ALPHA_V1_ENTREGA.md;
- para gestao de membros, acessos, convites Clerk e substituicao do CRUD admin de professores, o PRD, a Tech Spec e o WBS de Equipa acima sao a baseline normativa.

Documentos fora desta estrutura podem existir como historico/contexto e nao substituem as decisoes fechadas da Alpha V1.
