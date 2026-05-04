# Arquitetura Completa - Horário Zen

Este documento descreve detalhadamente a arquitetura completa da aplicação **Horário Zen**, abrangendo desde a infraestrutura até as camadas de backend, frontend e motor de otimização de horários. Todo o sistema assenta numa arquitetura limpa, multitenant e isolada.

## 1. Diagrama de Arquitetura (Mermaid)

```mermaid
flowchart TB
    classDef frontend fill:#61dafb,stroke:#333,stroke-width:2px,color:black
    classDef backend fill:#059669,stroke:#333,stroke-width:2px,color:white
    classDef worker fill:#d97706,stroke:#333,stroke-width:2px,color:white
    classDef infra fill:#3b82f6,stroke:#333,stroke-width:2px,color:white
    classDef db fill:#334155,stroke:#333,stroke-width:2px,color:white

    User((Usuário\nAdmin/Professor))

    subgraph "Docker Compose Infrastructure"
        subgraph "Frontend Context"
            SPA["Frontend (React + Vite)\nPorta: 5173\nZustand, React Query, CoreUI"]:::frontend
        end

        subgraph "Backend Framework (FastAPI)"
            API["Backend API\nPorta: 8000\nRoteadores (V1), Middlewares,\nIsolamento Multi-tenant"]:::backend
            Cache["Redis Cache\n(FastAPI Cache)"]:::infra
        end

        subgraph "Background & Scheduling Engine"
            Broker["Redis Broker\n(Filas do Celery)"]:::infra
            CeleryWorker["Celery Worker\n(CP-SAT, Gerador de Horários)"]:::worker
            CeleryBeat["Celery Beat\n(Tarefas Periódicas)"]:::worker
        end

        subgraph "Data Layer"
            PostgreSQL[(PostgreSQL 15\nSQLAlchemy ORM)]:::db
        end
    end

    User -->|Acesso via Browser| SPA
    SPA -->|Proxy API Requests| API
    API <-->|Redis Cache & Rate Limiting| Cache
    API -->|Consultas REST & Transações| PostgreSQL
    API -->|Dispacha Tarefas (Solve)| Broker
    Broker -->|Consome Mensagens| CeleryWorker
    CeleryBeat -->|Gatilhos Cron| Broker
    CeleryWorker <-->|Modelos, Restrições & Escrita| PostgreSQL
```

## 2. Visão Detalhada da Arquitetura

### 2.1. Infraestrutura (Orquestração via Docker)
O ecossistema roda de forma coesa utilizando contentores (Docker Compose):
- **Frontend**: Servidor web (Vite) na porta 5173 para servir os bundles ou fazer proxy para o Backend em desenvolvimento.
- **Backend**: Uvicorn servindo a aplicação ASGI FastAPI na porta 8000.
- **Celery Worker**: Nó de processamento assíncrono para operações custosas, primariamente a geração de horários via Constraint Programming.
- **Celery Beat**: Scheduler interno de background jobs para rotinas diárias (ex: data rotations, cleanup).
- **PostgreSQL**: SGBD relacional onde todo o domínio reside (Porta 5432).
- **Redis**: Sistema In-Memory que funciona simultaneamente como broker do Celery e cache de resultados do FastAPI.

### 2.2. Frontend (React SPA)
O Frontend obedece a uma lógica rígida de separação por Role e consistência visual:
- **Tecnologias Core**: React 19, Vite, CoreUI 5.
- **State Management**: `zustand` centraliza o estado global de utilizador e sessão persistente (e.g. `useAuthStore`).
- **Comunicação Assíncrona**: React Query (TanStack Query v5) com cache configurado por perfil de mutabilidade (STATIC_OPTS para metadados, DYNAMIC_OPTS para dados operacionais). Sem `alert()` ou `window.confirm()` nativos.
- **Controlo de Acesso (Routing)**: `react-router-dom v7` segmentado em `AdminOnlyRoute` e `TeacherOnlyRoute` com redirecionamento e feedback de acesso negado.
- **Estrutura de Diretórios** (pós-auditoria Maio 2026):
  - `src/utils/` — `formatUtils.js` (datas PT-PT), `terminology.js` (textos padronizados), `subjectColors.js` (paleta de disciplinas)
  - `src/components/` — `ErrorBoundary.jsx`, `ConfirmationModal.jsx`, `SmartTable.jsx`, `GenericModalForm.jsx`, `WeekGrid.jsx`, `AvailabilityGrid.jsx`, `AnalyticsHeatmap.jsx`, `LessonLogModal.jsx`, `ReplacementModal.jsx`, `SubstitutionStep.jsx`
  - `src/components/dashboard/` — Widgets do Command Center (AlertBar, ResourceCounts, ScheduleHealthCard, ClassProgressOverview, DebtSummaryCard, QuickActions)
  - `src/components/Forms/` — formulários CRUD (Teacher, Subject, Course, Class, Room, Timeslot)
  - `src/components/schedules/` — KPISidebar, DraftPanel, GenerationStatusPanel, PreflightErrorPanel
  - `src/components/timesheets/` — TeacherCard
  - `src/components/ImportForms/` — formulários de importação em massa
  - `src/pages/` — 18 páginas (Login, Register, MarketingSite, Dashboard, Schedules, MySchedules, MyAvailability, Teachers, Subjects, Rooms, Classes, Courses, CourseDetails, ClassDetails, ClassSubjects, SchoolConfig, Timesheets, Timeslots, Occurrences, ScheduleAuditDashboard)
  - `src/hooks/` — `useSchoolData.js` (todos os hooks React Query)
- **Sidebar**: Colapsável (280px/72px) com toggle para admin e professor. Estado persistido em localStorage. Admin: experiência desktop-first. Professor: mobile-first com padding adaptativo.
- **Terminologia**: Centralizada em `src/utils/terminology.js` (`TXT`). Padronizada para PT-PT com tratamento formal. Termos técnicos do motor (`CP-SAT`, `solver`, `worker`) traduzidos para vocabulário do domínio escolar.
- **CSP**: `script-src 'self' 'unsafe-inline'` (sem `'unsafe-eval'`).

### 2.3. Backend API (FastAPI)
- **Estruturação Funcional (Clean Architecture):** Separa os Controllers (rotas), Serviços (lógica comercial e de acesso) e Modelos (estruturas da BD e Pydantic).
- **Isolamento de Segurança (Multi-tenant):** Toda e qualquer ação de CRUD valida a `organization_id` do utilizador.
- **Middlewares Críticos:**
  - `SlowAPIMiddleware` para rate-limiting visando estabilidade (Prevenção de ataques de negação de serviço e loops do UI).
  - Segurança nativa `CORSMiddleware`.
  - Tratamento unificado (`HTTPException`s standardizadas).
- **API Routers principais**:
  - `/dashboard`: Endpoint agregador do Command Center (alertas, saúde do horário, progresso curricular, recursos, dívidas).
  - `/schedule`, `/occurrences`, `/substitutions`: Centro nervoso da operação de ensino e do planeamento.
  - CRUD Tradicional: `/courses`, `/classes`, `/teachers`, `/rooms`.

### 2.4. Motor de Agendamento Assíncrono (Scheduler Engine CP-SAT)
Localizado principalmente nos workers do Celery (`app/solver_tasks.py`). É executado como background job devido ao seu elevado tempo computacional. Funciona por fases rígidas:
1. **FETCH (Reunião de Dados)**: Reúne professores, salas, disponibilidades e restrições configuradas (Hard Rules/Soft Rules).
2. **SOLVE (Cálculo)**: Motor Google OR-Tools CP-SAT calcula matrizes com padronização lexicográfica e balanceada para as necessidades de carga-horária do plano curricular português (Ensino Profissional).
3. **EXPAND (Mapeamento Anual)**: Projeções do padrão gerado ao longo de datas de calendário, evadindo dias feriados/finais de semana ou feriados regionais.
4. **SAVE (Persistência)**: Salva as projeções em batch na entidade `ScheduleOutput`.

### 2.5. Modelo de Dados (PostgreSQL + SQLAlchemy)
Inteiramente desenhado para refletir as normativas do Ensino Profissional:
- **Entidades Físicas**: `Organization`, `User`, `Teacher`, `Course`, `Subject`, `Room`, `Class`. Associadas via tabelas cruzadas (e.g., `teacher_subject_link`).
- **Horário de Registo (Real vs Projetado)**: Trabalha com `Timeslot` (blocos horários) e assenta resultados nas ocorrências em `ScheduleOutput`.
- **Eventos Dinâmicos**: `Substitution` e Occurrences, refletindo o caráter não-estático do planeamento escolar (absorvendo as necessidades de faltas/substituições pontuais).

---
*Este documento reflete a versão atual estabelecida segundo as restrições arquitetónicas dos pilares de Otimização, Estabilidade, Escalabilidade e Segurança definidos no projeto Horário Zen.*