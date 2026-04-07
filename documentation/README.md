## Horario Zen Documentation

Este indice define a verdade documental estavel do projeto.
So inclui informacao confirmada e com alta probabilidade de permanecer estavel.

## 5 Ws do projeto

### What
Horario Zen e uma aplicacao SaaS para gestao e geracao de horarios no Ensino Profissional em Portugal.
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
- baseline do motor de horarios estavel e iterativo;
- hard end date obrigatoria;
- target end date como objetivo de otimizacao;
- prioridade funcional seguinte: faltas e substituicoes.

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
