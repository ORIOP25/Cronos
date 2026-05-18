---

# **📘 Dossiê Técnico e Estratégico: Cronos (v0.8)**

Data: 07 de Janeiro de 2026

Versão: 0.8 (Pivô para Arquitetura Dinâmica & Modular)

Classificação: Documentação Técnica e de Negócio (Confidencial)

Autor: Rodrigo Manguinhas

---

## **1\. Sumário Executivo**

O **Cronos** é uma plataforma SaaS (*Software as a Service*) B2B desenhada para resolver o problema crítico da gestão temporal em instituições de ensino, com foco especializado em **Escolas Profissionais e Sistemas Modulares**.

Ao contrário das soluções tradicionais que tratam o horário escolar como uma grelha estática semanal (Setembro a Junho), o Cronos adota uma abordagem de **Agendamento Dinâmico (*Rolling Horizon*)**. O sistema reconhece que o ensino profissional requer flexibilidade para gerir cargas horárias modulares (UFCDs), compensar atrasos pedagógicos e adaptar-se à disponibilidade variável dos docentes ao longo do ano.

A proposta de valor não é apenas "gerar um horário", mas sim oferecer um **Sistema Operativo de Gestão de Tempo** que garante o cumprimento dos planos curriculares, otimiza recursos e resolve imprevistos diários (substituições) em tempo real.

---

## **2\. Análise de Negócio e Oportunidade (Business Case)**

### **2.1. O Problema (A "Dor" do Mercado)**

As escolas profissionais em Portugal enfrentam desafios únicos que o software "legacy" (e.g., aSc TimeTables, Excel) não resolve eficazmente:

1. **Ensino Modular vs. Horário Rígido:** Os cursos funcionam por módulos (ex: 15h, 50h). Um professor pode ter carga horária intensiva num mês e nula no próximo. Ferramentas estáticas obrigam a refazer o horário manualmente quase todas as semanas.  
2. **Gestão de Saldo de Horas:** Diretores de turma perdem dias a calcular manualmente se a turma "TGEI-12" está atrasada a Matemática ou adiantada a Inglês.  
3. **Ineficiência de Recursos:** Salas específicas (Laboratórios, Oficinas) ficam vazias ou sobrelotadas devido a planeamento deficiente.  
4. **O Caos das Substituições:** A falta de um professor implica telefonemas urgentes. Não há uma visão imediata de quem é o "melhor" substituto (livre, da mesma área, e com saldo de horas para dar).

### **2.2. A Solução (Unique Selling Proposition \- USP)**

O Cronos diferencia-se por três pilares:

1. **Agendamento Dinâmico:** O horário não é para "o ano todo". É gerado para períodos específicos (ex: mensal ou bimestral), tendo em conta o progresso real das turmas.  
2. **Rastreio de Progresso (ClassProgress):** O sistema sabe que o Módulo A tem 50h e que já foram dadas 30h. O algoritmo prioriza automaticamente as disciplinas atrasadas na próxima geração de horário.  
3. **Assistente de Resolução de Conflitos:** Quando um horário é impossível, o sistema não dá apenas erro; diagnostica a causa (Relaxation Analysis) e sugere alterações.

---

## **3\. Arquitetura de Engenharia (System Design)**

O sistema segue uma arquitetura **Client-Server desacoplada**, desenhada para alta escalabilidade e manutenibilidade.

### **3.1. Visão Geral (Diagrama Lógico)**

Fragmento do código

\[Frontend (React SPA)\] \<--\> \[Load Balancer (Nginx)\] \<--\> \[API Gateway (FastAPI)\]  
                                                            |  
        \-----------------------------------------------------  
        |                       |                           |  
\[Service Layer\]           \[Solver Worker\]             \[Notification Service\]  
(Lógica de Negócio)       (Google OR-Tools)           (Celery \+ Email)  
        |                       |  
\[Data Layer (ORM)\]        \[Redis Cache\]  
        |  
\[PostgreSQL Database\]

### **3.2. Princípios de Engenharia (The "Why")**

1. **Clean Architecture:**  
   * A lógica de negócio (Services) está isolada da camada de apresentação (API Endpoints) e da base de dados. Isto permite mudar a base de dados ou a framework web sem reescrever a lógica core.  
2. **Assincronismo (Async I/O):**  
   * Como a geração de horários é uma tarefa pesada (CPU-bound) e a API deve ser rápida (I/O-bound), usamos **FastAPI** (assíncrono) para a web e **Celery** para tarefas pesadas em background. A interface nunca "bloqueia" enquanto o horário é gerado.  
3. **Idempotência e Atomicidade:**  
   * Operações críticas (criar horário, aplicar substituição) são transacionais. Ou acontece tudo, ou não acontece nada, garantindo que a base de dados nunca fica num estado inconsistente.

---

## **4\. Stack Tecnológica Detalhada**

Selecionámos ferramentas "Industry Standard" para 2025/2026, focadas em tipagem forte e performance.

### **4.1. Backend (O "Cérebro")**

* **Linguagem:** Python 3.12+ (Uso estrito de Type Hints para reduzir bugs).  
* **Framework Web:** FastAPI. *Porquê?* Performance próxima de Go/Node.js, documentação automática (Swagger) e validação de dados nativa.  
* **Base de Dados:** PostgreSQL 15\. *Porquê?* Robustez, suporte a queries complexas e integridade referencial estrita (essencial para não haver aulas órfãs).  
* **ORM:** SQLAlchemy 2.0 (Async). *Porquê?* Abstração segura de SQL, prevenindo Injection Attacks e facilitando a gestão de relações complexas.  
* **Solver:** Google OR-Tools (CP-SAT). *Porquê?* O melhor solver open-source para problemas de Constraint Programming. Permite definir regras "Hard" e "Soft" com alta performance.  
* **Task Queue:** Celery \+ Redis. *Porquê?* Para processar a geração de horários e envio de emails fora do ciclo de pedido-resposta HTTP.

### **4.2. Frontend (A Interface)**

* **Framework:** React 18+ (Vite). *Porquê?* Ecossistema vasto, componentização.  
* **Estado:** Zustand. *Porquê?* Mais simples e leve que Redux, suficiente para gerir sessões e dados globais.  
* **Data Fetching:** TanStack Query (React Query). *Porquê?* Gere cache, loading states e re-fetching automaticamente, vital para uma app com muitos dados tabelares.  
* **UI Kit:** CoreUI / Tailwind CSS. *Porquê?* Desenvolvimento rápido de interfaces responsivas e profissionais.

---

## **5\. Estrutura de Dados (Data Modeling)**

A modelagem de dados foi reestruturada para suportar o **Ensino Profissional**.

### **5.1. Entidades Core (Ensino Modular)**

* **Organization:** O "Tenant" (A Escola).  
* **User vs. Teacher:**  
  * User: Credenciais de acesso, Role (Admin/Teacher).  
  * Teacher: A entidade pedagógica. Tem disponibilidade, competências. Separação necessária para histórico e segurança.  
* **Course (Curso):** (Novo) Ex: "Técnico de Gestão e Programação".  
* **Subject (Disciplina):** A categoria macro. Ex: "Matemática", "Programação".  
* **Module (Módulo/UFCD):** (Novo) A unidade atómica de ensino.  
  * Atributos: name, hours\_total (carga horária total), subject\_id, course\_id.  
* **ClassProgress (Progresso):** (Novo) Tabela pivot que rastreia o estado.  
  * Atributos: class\_id, module\_id, hours\_completed, status (Ativo/Concluído).  
* **Timeslot:** (Refinado)  
  * Criação via "Bulk Generator" (Gerador em massa) para preencher a grelha da escola rapidamente.  
  * Atributos: day\_of\_week, start\_time, end\_time.

### **5.2. Entidades de Agendamento**

* **SchedulePeriod:** (Novo) Define a validade de um horário. Ex: "Horário Novembro 2025".  
* **Lesson:** A intenção de aula. Liga Class, Teacher, Subject e Module.  
* **ScheduleOutput:** A concretização. Liga Lesson, Timeslot e Room.  
* **Substitution:** Registo de alterações pontuais.  
  * Atributos: original\_lesson\_id, substitute\_teacher\_id, date, reason.

---

## **6\. Lógica Algorítmica (O "Solver")**

O motor de otimização (app/core/solver\_engine.py) opera em três fases distintas:

### **6.1. Fase de Preparação (Data Ingestion)**

1. Recebe o intervalo de tempo (Wizard).  
2. Consulta o ClassProgress para determinar quais os módulos mais atrasados.  
3. Calcula o "Peso" (Prioridade) de cada disciplina com base no desvio do plano curricular.

### **6.2. Fase de Resolução (Constraint Programming)**

Utiliza o modelo CP-SAT com variáveis booleanas x\[lesson, timeslot, room\].

* **Hard Constraints (Invioláveis):**  
  * Um professor não pode estar em 2 sítios ao mesmo tempo.  
  * Uma turma não pode ter 2 aulas ao mesmo tempo.  
  * Capacidade da sala \>= Tamanho da turma.  
  * Tipo de sala (Lab/Ginásio) corresponde ao requisito da disciplina.  
* **Soft Constraints (Otimizáveis \- com sistema de penalização):**  
  * Minimizar "furos" (janelas vazias) para professores.  
  * Maximizar aulas do mesmo módulo sequenciais (blocos de 2h).  
  * **Prioridade Dinâmica:** Minimizar o desvio entre hours\_completed e a meta temporal do curso.

### **6.3. Fase de Análise de Falha (Relaxation)**

Se o solver retornar INFEASIBLE:

1. O sistema executa um "Diagnóstico".  
2. Desativa progressivamente grupos de restrições (ex: ignora preferências de professores).  
3. Identifica o **Minimal Unsatisfiable Core** (o conjunto mínimo de regras que causa o bloqueio).  
4. Retorna ao utilizador: *"Não é possível gerar o horário porque o Prof. Silva não tem disponibilidade suficiente para a carga horária de Matemática. Sugestão: Aumentar disponibilidade ou reduzir horas semanais."*

---

## **7\. Infraestrutura e Segurança**

### **7.1. Segurança**

* **Autenticação:** OAuth2 com JWT (JSON Web Tokens). Tokens de curta duração (Access) e longa duração (Refresh).  
* **Password Hashing:** Argon2 ou bcrypt (Industry standard).  
* **Proteção de Dados:** Isolamento lógico por organization\_id em todas as queries (Multi-tenancy via software). Nenhuma escola vê dados de outra.

### **7.2. DevOps & Deploy**

* **Docker Compose:** Orquestração local de serviços (Backend, Frontend, DB, Redis, Worker).  
* **Reverse Proxy (Nginx):** Gere SSL/TLS e encaminha tráfego.  
* **Backup:** Scripts automatizados (pg\_dump) para backup diário da base de dados.

---

## **8\. Roadmap de Desenvolvimento (Próximos Passos)**

1. **Imediato (v0.8):**  
   * Implementar tabelas Course e Module.  
   * Criar o "Bulk Generator" de Timeslots no Frontend.  
2. **Curto Prazo (v0.9):**  
   * Desenvolver o "Wizard de Geração" (Passo-a-passo).  
   * Implementar a lógica de cálculo de "Saldo de Horas".  
3. **Lançamento (v1.0):**  
   * Testes de carga no Solver.  
   * Polimento final da UX/UI.  
   * Lançamento Comercial (Beta Fechado).

---

Conclusão Final:

O Cronos evoluiu de uma ferramenta académica para uma solução de engenharia robusta, atacando um nicho de mercado mal servido (Ensino Profissional). A arquitetura modular e o foco na gestão dinâmica de tempo posicionam o produto como um parceiro operacional indispensável para as escolas, garantindo não apenas a criação do horário, mas a viabilidade do ano letivo.

