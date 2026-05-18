# Guião de Apresentação — Cronos
## Demo informal para Professor / Cliente Piloto

---

## Resumo para levares contigo (cartão de bolso)

| O quê | Ação |
|-------|------|
| **Login admin** | `ana.silva@escola.pt` / `1234` |
| **Login professor** | `ana.matos@epnorte.pt` / `1234` (ou qualquer outro prof) |
| **App** | `http://localhost:5173` |
| **Dados** | Escola Profissional do Norte, 3 cursos, 9 turmas, 10 profs, horário gerado |
| **Se algo falhar** | "Está em desenvolvimento, é normal — mas o core funciona" |

---

## Estrutura da Sessão (25-30 min)

| Ato | Duração | Tema |
|-----|---------|------|
| 0 | 2 min | Abertura — o problema |
| 1 | 5 min | Dashboard + Configuração da escola |
| 2 | 5 min | Gestão de entidades (cursos, turmas, profs) |
| 3 | 8 min | ⚡ Geração de horário (WOW moment) |
| 4 | 5 min | Operação diária — faltas e substituições |
| 5 | 3 min | Experiência do professor |
| 6 | 2 min | Fecho semanal / timesheets |
| 7 | 3 min | Encerramento e pergunta aberta |

---

# ATO 0 — Abertura (2 min)

**NÃO ABRAS O PORTÁTIL AINDA.**

> "Obrigado por teres aceitado ser o primeiro a ver isto. Isto é o Cronos."

Conta a história em 3 frases:

1. **O problema**: "As escolas profissionais têm um problema único — os horários não são grelhas fixas semanais. As UFCDs têm durações diferentes, há módulos que acabam a meio do ano, as turmas avançam a ritmos diferentes, e andam a gerir tudo em Excel."

2. **A solução**: "O Cronos não é um gerador de horários. É um sistema operacional para a escola — gera horários, mas também gere o que realmente acontece durante o ano. Regista aulas dadas, faltas, substituições, e pode regenerar o horário quando as coisas mudam."

3. **O gancho**: "O que te vou mostrar é uma escola fictícia mas realista, com 3 cursos e 9 turmas, completamente funcional."

---

# ATO 1 — Dashboard + Configuração (5 min)

### Abrir o portátil e fazer login

```
http://localhost:5173/login
Login: ana.silva@escola.pt
Pass:  1234
```

**ANTES de carregar, já ter o browser aberto no login.**

### 1.1 Dashboard (`/dashboard`)

**O que mostras:**
- Os cartões KPI no topo (9 turmas, 10 professores, 9 salas, 3 cursos)
- O "Raio-X de Disponibilidade" (heatmap) — aponta para como mostras a disponibilidade agregada dos professores

**O que dizes:**
> "Isto é o dashboard da direção. Visão geral de tudo — quantas turmas, professores, salas. Este heatmap mostra a disponibilidade dos professores por dia e hora. Verde = ok, vermelho = há poucos profs disponíveis naquele slot. Isto ajuda a planear."

**Tempo: 1 minuto. Não te demores.**

### 1.2 Configuração da Escola (`/config`)

**Navegar:** Sidebar → Configuração

**O que mostras (passa pelos 3 tabs rapidamente):**
1. **Período Letivo** — datas do ano letivo (início, fim, margem de segurança)
2. **Calendário e Interrupções** — clica em "Sincronizar Feriados" para mostrar que importa feriados nacionais automaticamente
3. **Grelha Horária** — blocos de 60 min, 8:30-18:00, Seg-Sex, janela de almoço

**O que dizes:**
> "Aqui a escola configura o ano letivo: datas, feriados, grelha horária. Os feriados nacionais são importados automaticamente. Tudo o que configuras aqui alimenta diretamente o motor de horários."

**Tempo: 2 minutos.**

---

# ATO 2 — Gestão de Entidades (5 min)

### 2.1 Cursos e Turmas (`/courses`)

**Navegar:** Sidebar → Cursos

**O que mostras:**
- A lista dos 3 cursos (TGPSI, TAG, TDESP)
- Clica em TGPSI → vê as turmas 10A, 11A, 12A
- Clica numa turma → vê as disciplinas associadas com barras de progresso
- Mostra a atribuição de professores às disciplinas

**O que dizes:**
> "A escola tem 3 cursos. Cada curso tem turmas de 10.º, 11.º e 12.º ano. Dentro de cada turma, atribuis as disciplinas e os professores. Vês aqui as barras de progresso — quantas horas já foram dadas vs. o total do módulo. Isto é o que permite ao motor saber quais os módulos atrasados e priorizá-los na geração."

**Tempo: 2 minutos.**

### 2.2 Professores e Salas (`/teachers`, `/rooms`)

**Navegar:** Sidebar → Professores → depois Salas

**O que mostras:**
- Lista de 10 professores com as disciplinas que cada um leciona
- Lista de 9 salas com tipo (Normal, Lab, Ginásio) e capacidade

**O que dizes:**
> "Cada professor tem as suas competências — que disciplinas pode dar. As salas têm tipo e capacidade. O motor de horários respeita isto: não mete um professor a dar uma disciplina que não é dele, nem uma turma de 26 alunos numa sala de 22."

**Tempo: 1 minuto.**

### 2.3 Disponibilidade dos Professores

**Navegar:** Fazer logout e login como professor (`ana.matos@epnorte.pt` / `1234`)

**O que mostras:**
- A grelha de disponibilidade com as 4 cores (Preferido, Neutro, Evitar, Impossível)

**O que dizes:**
> "Cada professor marca a sua disponibilidade. Pinta na grelha — verde escuro é 'prefiro', amarelo é 'tanto faz', laranja é 'evito', vermelho é 'impossível'."

**Navegar:** Voltar a fazer login como admin (`ana.silva@escola.pt` / `1234`)

**Tempo: 1 minuto.**

---

# ATO 3 — ⚡ Geração de Horário (8 min) ← O MOMENTO WOW

**Navegar:** Sidebar → Horários

### 3.1 Ver o horário existente

**O que mostras:**
- O seletor "Turma" / "Professor"
- Escolhe uma turma (ex: TGPSI 10A)
- Navega entre semanas com as setas
- Mostra o horário preenchido — cada célula com disciplina, professor, sala

**O que dizes:**
> "Isto é o horário ativo. Navegas por semana, por turma ou por professor. Cada bloco mostra a disciplina, o professor e a sala."

**Tempo: 1 minuto.**

### 3.2 Gerar um novo horário

**Ação:**
1. Clica no dropdown: "Reparação (mín. alterações)"
2. Clica "Gerar Horário"
3. **Espera o solver correr** — mostra a barra de progresso:
   - "A carregar dados da escola..."
   - "A calcular o melhor horário..."
   - "A gerar blocos no calendário..."
   - "A guardar resultados..."

**ENQUANTO O SOLVER CORRE, conta o que está a acontecer:**

> "Isto agora está a correr o motor. Está a usar um solver de programação por restrições — o mesmo tipo de algoritmo que a Google usa para otimizar rotas. Ele respeita: conflitos de professores, capacidade das salas, tipo de sala (não metes Informática num ginásio), disponibilidade dos professores, e prioriza as disciplinas que estão com horas em atraso."

**Tempo: 2-3 minutos (depende da velocidade do solver).**

### 3.3 Rever o rascunho

**Quando a geração terminar, aparece o DraftPanel:**

- Mostra o resumo: X blocos adicionados, Y removidos, Z mantidos
- Mostra as estatísticas de qualidade

**O que dizes:**
> "Como escolhi modo 'reparação', ele gerou um rascunho. Mostra-me exatamente o que mudou. Posso aprovar ou rejeitar. Se aprovar, substitui o horário ativo a partir de hoje, mantendo o que já passou."

**Ação:** Clica "Aprovar e Ativar"

**Tempo: 2 minutos (incluindo espera do solver).**

### 3.4 Auditoria (`/schedules/audit`)

**Navegar:** Sidebar → Auditoria

**O que mostras:**
- O histórico de gerações
- Clica numa geração para ver estatísticas

**O que dizes:**
> "Todas as gerações ficam registadas. Podes ver o que cada geração produziu, comparar, auditar. Transparência total."

**Tempo: 30 segundos.**

---

# ATO 4 — Operação Diária: Faltas e Substituições (5 min)

**Navegar:** Voltar a Horários (`/schedules`)

### 4.1 Registrar uma falta (visão do professor)

**O que mostras:**
- Na grelha do horário, clica num slot passado
- Abre o `LessonLogModal`
- Explica as opções: "Aula Dada" ou "Criar Ocorrência"
- Clica "Criar Ocorrência"

**O que dizes:**
> "O professor abre o horário dele, clica na aula passada, e regista se deu a aula ou se houve uma falta. Se criar uma ocorrência, aquilo vai parar à mesa do diretor para decidir o que fazer."

**Tempo: 1 minuto.**

### 4.2 Gerir a falta (visão do admin)

**Navegar:** Sidebar → Faltas

**O que mostras:**
- Tab "Decisões Pendentes" — mostra a ocorrência que acabaste de criar
- Clica "Decidir"
- O modal mostra recomendações de substitutos (professores disponíveis naquele slot, com a mesma competência)
- Seleciona um substituto e confirma

**O que dizes:**
> "Quando um professor falta, o sistema sugere automaticamente substitutos. Tem em conta: está disponível? Tem competência para aquela disciplina? Não tem aula nesse slot? Está classificado por ordem de adequação. O diretor escolhe e confirma. Se não houver ninguém elegível, assume 'furo'. Tudo fica registado no progresso da turma."

**Tempo: 2 minutos.**

### 4.3 Dívidas de horas

**Navegar:** Tab "Dívidas de Horas" (dentro de Faltas)

**O que mostras:**
- As horas em dívida acumuladas por turma/disciplina

**O que dizes:**
> "Quando há um furo, a turma fica com horas em dívida. O motor, na próxima geração, vai priorizar essas disciplinas para recuperar o atraso."

**Tempo: 1 minuto.**

---

# ATO 5 — Experiência do Professor (3 min)

**Navegar:** Logout → Login como `ana.matos@epnorte.pt` (ou outro prof)

### 5.1 Meus Horários (`/my-schedules`)

**O que mostras:**
- O horário pessoal do professor
- Clica num slot → regista "Aula Dada" com sumário
- O botão "Submeter Semana" no topo

**O que dizes:**
> "O professor só vê o horário dele. Regista cada aula com o sumário. No fim da semana, submete. Não pode esquecer-se de aulas — o botão só desbloqueia quando tudo está registado."

**Tempo: 1.5 minutos.**

### 5.2 Meu Progresso (`/my-progress`)

**O que mostras:**
- Barras de progresso por disciplina/turma

**O que dizes:**
> "O professor vê o progresso curricular dele — quantas horas já deu em cada módulo. Sabe exatamente onde está atrasado ou adiantado."

**Tempo: 30 segundos.**

### 5.3 Preferências (`/my-availability`)

**O que mostras:**
- Grelha de preferências

**O que dizes:**
> "E aqui marca as preferências de horário. O que ele pintar influencia diretamente o motor. Se puser 'impossível' numa manhã de quarta, o solver nunca lhe agenda aulas ali."

**Tempo: 30 segundos.**

---

# ATO 6 — Fecho Semanal (2 min)

**Navegar:** Logout → Login como admin → Sidebar → Fecho Semanal (`/timesheets`)

**O que mostras:**
- Lista de professores com status (Aberto / Submetido / Aprovado)
- Clica num professor submetido
- Vê a grelha da semana dele (read-only)
- Clica "Aprovar"

**O que dizes:**
> "No fim da semana, o diretor revê o que cada professor submeteu. Vê os sumários, as faltas, aprova ou reabre. Isto fecha a semana operacionalmente. As horas dadas são contabilizadas automaticamente no progresso das turmas."

**Tempo: 1.5 minutos.**

---

# ATO 7 — Encerramento (3 min)

**Fecha o portátil ou minimiza a janela. Contacto visual.**

### 7.1 Resumo relâmpago (30 seg)

> "Em 25 minutos viste: configurar a escola, gerir entidades, gerar um horário com um solver real, gerir uma falta com substituição automática, a experiência do professor, e o fecho semanal. Tudo integrado."

### 7.2 Perguntas de encerramento

> "O que achas que falta para uma escola real?"

> "Conheces alguma escola que estaria interessada em ser piloto?"

> "Viste algo que farias de forma diferente?"

### 7.3 Não te esqueças de:

- Pedir o email dele para follow-up
- Dizer que vais enviar um resumo depois
- Agradecer o tempo e a honestidade

---

# CHECKLIST PRÉ-APRESENTAÇÃO

### No dia anterior

- [ ] Fazer dry-run completo (seguir este guião do início ao fim)
- [ ] Verificar que o solver gera sem erros
- [ ] Confirmar que o login admin e professor funcionam
- [ ] Carregar portátil a 100%
- [ ] Desligar notificações do Windows/Slack/Teams/etc
- [ ] Ter o browser aberto no login, já com credenciais preenchidas
- [ ] Levar carregador

### 15 min antes

- [ ] Abrir portátil, ligar ao hotspot (se o café não tiver WiFi)
- [ ] Fazer login como admin → verificar que o dashboard carrega rápido
- [ ] Navegar para /schedules e confirmar que o horário aparece
- [ ] Fechar o browser e reabrir no ecrã de login
- [ ] Colocar em modo "Não Perturbar"

### Durante a apresentação

- [ ] Falar devagar. Há tempo.
- [ ] Se o solver demorar 2 min, usa esse tempo para explicar a teoria
- [ ] Se algo crashar: "Está em dev, peço desculpa, vamos saltar para a próxima funcionalidade"
- [ ] Não pedir desculpa por features incompletas — foca-te no que funciona
- [ ] Olhar para a pessoa, não para o ecrã

---

# PERGUNTAS QUE ELE PODE FAZER (e respostas rápidas)

| Pergunta | Resposta |
|----------|----------|
| "Quanto custa?" | "Ainda estou a definir o modelo, mas será SaaS — subscrição por aluno ou por escola. Quero o teu input nisso." |
| "Já testaste numa escola real?" | "Ainda não. Esta demo é o primeiro passo. Tu és o piloto." |
| "E se houver um bug?" | "Por isso o piloto é controlado — eu acompanho de perto." |
| "Isto funciona sem internet?" | "Não, é cloud. Mas em Portugal todas as escolas têm ligação." |
| "Os professores vão adotar isto?" | "A interface deles é muito simples — 3 páginas: horário, progresso, disponibilidade. Em 5 minutos aprendem." |
| "Como é que importo os dados da escola?" | "Tem importação por Excel. Mostrei-te rapidamente, mas posso fazer uma demo focada nisso." |
| "E as pautas? E sumários oficiais?" | "Ainda não estão implementados, mas estão no roadmap. Quero priorizar com base no feedback do piloto." |
| "Quem fez o motor?" | "Eu. Usei o Google OR-Tools, uma biblioteca de otimização usada em logística e indústria. Adaptei para horários escolares." |

---

# NOTAS TÉCNICAS

- **URL:** `http://localhost:5173`
- **API:** `http://localhost:8000`
- **Seed atual:** `small-realistic` (Escola Profissional do Norte)
- **Para recriar dados limpos:** `docker compose exec backend python seed_data.py --profile small-realistic --reset`
- **Após reset, recriar horário:** Fazer login → ir a /schedules → Gerar Horário (Completo)
- **Senha de todos os utilizadores:** `1234`

---

**Boa sorte. Vai correr bem.**
