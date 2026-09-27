# WBS técnico — implementação e validação do Scheduler v1

Data: 23 de setembro de 2026.
Estado: decomposição de trabalho futuro. Nenhuma campanha descrita neste documento foi executada pela sua criação.

Documentos de referência: [plano](SCHEDULER_V1_REVAMP_PLAN.md) e [especificação técnica](SCHEDULER_V1_TECH_SPEC.md).
Branch de execução: `codex/scheduler-v1-revamp`.

## 1. Objetivo e utilização

Este WBS transforma a especificação em pacotes de trabalho verificáveis.
Inclui implementação, refatoração, experiências, correções, limpeza e lançamento.
Não é apenas uma lista de testes a executar no fim.

Cada pacote identifica entregas, dependências e evidência para fecho.
As campanhas C01–C20 são ciclos experimentais obrigatórios, distribuídos pelas fases de implementação.
Os casos T01–T30 do plano continuam obrigatórios.

O objetivo é demonstrar correção, qualidade e recuperação operacional em ambientes diversos.
Nenhuma quantidade finita de testes prova fiabilidade em todos os ambientes possíveis.
A confiança resulta de invariantes, oráculos independentes, diversidade, testes longitudinais e evidência reproduzível.

### Responsabilidades

| Papel | Responsabilidade |
| :--- | :--- |
| Implementador | Código, testes, análise, correções, relatórios e documentação. Pode ser o próprio proprietário com assistência. |
| Proprietário | Validar exemplos escolares, compromissos de qualidade e gates local/remoto. |
| Automação local/CI | Executar verificações e preservar evidência; não substituir a interpretação dos resultados. |

Todos os pacotes técnicos pertencem ao implementador.
Aceitações identificadas como funcionais ou de lançamento pertencem ao proprietário.
Não pressupor uma equipa adicional nem criar dependências organizacionais artificiais.

Estados de trabalho: `por iniciar → em execução → em validação → concluído`.
Uma regressão reabre o pacote responsável e regista os pacotes afetados.
“Concluído” exige artefacto, teste ou ensaio e resultado analisado.

## 2. Regras transversais

- Clean Code: funções pequenas, unidades explícitas, comportamento visível e nomes do domínio.
- Clean Architecture: domínio sem ORM, HTTP, Celery, CP-SAT ou relógio global.
- TDD: reproduzir a falha antes da correção; implementar o mínimo e refatorar depois.
- Ponytail full: reutilizar runner, bibliotecas e containers; evitar framework genérico de experiências.
- Manter um único job global e medir paralelismo interno 1/2/4/8.
- Não criar metas fixas de p95 ou timeouts de qualidade.
- Não modificar dados, fixtures ou expectativas para esconder um erro.
- Não enfraquecer estabilidade, integridade, autorização ou cobertura curricular para obter um resultado.
- Não executar ensaios Railway/Cloudflare antes do gate local.
- Não exigir migração ou compatibilidade com dados antigos de teste.

Na implementação, o ciclo de cada tarefa é:

```text
exemplo/requisito → teste que falha → implementação mínima
→ teste verde → refatoração → regressões relacionadas → evidência
```

Nas experiências, alterar uma variável de cada vez para explicar causas.
Depois combinar variáveis para testar interações e comportamento realista.
Uma alteração de fixture é uma nova versão; não apaga o resultado anterior.

## 3. Árvore de entregas e dependências

| Pacote | Entrega | Fase | Depende de |
| :--- | :--- | :--- | :--- |
| W00 | Ambiente, inventário e controlo de execução | P0 | Plano e tech spec |
| W01 | Domínio curricular e temporal | P1 | W00 |
| W02 | Baseline de dados e transações | P2 | W01 |
| W03 | Oráculos, validador e laboratório | P3 | W01; W02 para integração |
| W04 | CompleteGeneration correto | P4 | W01, W03 |
| W05 | Qualidade inicial e datas coletivas | P5 | W04 |
| W06 | AdaptiveRecovery e reconciliação | P6 | W02, W05 |
| W07 | Paragem e diagnóstico sustentados | P7 | W03–W06 |
| W08 | Fila, snapshots e publicação | P8 | W02, W04; integração final com W06–W07 |
| W09 | API e aplicação escolar | P9 | W01, W02, W08 |
| W10 | Campanhas combinadas e anuais | P6–P10 | W06; completar com W07–W09 |
| W11 | Calibração e recursos | P10 | W07, W10 |
| W12 | Remoção de legado e candidate local | P11 | W00–W11 |
| W13 | Validação remota | P12A | W12 aceite |
| W14 | Corte final e entrega | P12B | W13 aceite |

Os pacotes descrevem dependências, não obrigam a PRs gigantes.
Entregar fatias verticais pequenas quando as suas dependências estiverem prontas.
Executar campanhas progressivamente; não adiar a descoberta de problemas para W10.

## 4. Pacotes de implementação

### W00 — Ambiente e inventário

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W00.1 | Mapear chamadas do gerador, ledger, módulos, mapas, UI, scripts e migrations. | Inventário com consumidor, contrato atual e destino novo. |
| W00.2 | Confirmar branch, imagens, volumes de teste e serviços locais. | Manifesto identifica commit, Docker, CPU/RAM e bases de teste. |
| W00.3 | Impedir deployments automáticos da branch durante P0–P11. | Rever configurações; CI pode testar sem publicar nem limpar serviços remotos. |
| W00.4 | Executar setup/doctor e checks atuais relevantes. | Registar falhas pré-existentes separadamente; ambiente local reproduzível. |
| W00.5 | Definir diretórios de artefactos e limites de segurança de laboratório. | Primeira execução curta produz manifesto, resultado e logs sem segredos. |

Não tomar testes atuais verdes como prova da nova arquitetura.
Não executar resets para preparar este documento; a limpeza pertence à implementação.

### W01 — Domínio curricular e temporal

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W01.1 | Valores imutáveis, minutos inteiros e intervalos semiabertos. | Intervalos adjacentes permitidos; negativos e durações inválidas rejeitados. |
| W01.2 | Procura `Q-E`, crédito parcial e módulos cronológicos. | T01–T03; durações heterogéneas; nenhum arredondamento por módulo. |
| W01.3 | Execução, reversões e acertos auditados. | T04–T07, T29–T30; execução repetida não credita duas vezes. |
| W01.4 | Dívida, reservas e liquidação muitos-para-muitos. | Cancelar recuperação não duplica dívida; conservação em cada evento. |
| W01.5 | Calendário, timezone e janela por dias de grelha. | T08–T09; N=0; limite inclusivo e passagem de data. |
| W01.6 | Definições de qualidade e elegibilidade. | T15–T19, T21–T22; comparador puro e relógio recebido como valor. |

Executar C01, C09, C13 e os casos pequenos de C14.
Fecho: regras observáveis testadas sem base de dados nem solver.

### W02 — Baseline de dados

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W02.1 | Schema de atribuições, ledger, parcelas e dívida. | Constraints e equações após comandos e reversões. |
| W02.2 | Versões, aulas, propostas, jobs e revisões. | Identidade estável, uma versão ativa e idempotência. |
| W02.3 | Baseline Alembic, grants, RLS e índices. | Instalação vazia; auditorias existentes; rejeição de referências entre escolas. |
| W02.4 | Transações de progresso e mudanças de configuração. | Escritas concorrentes não perdem revisão nem duplicam crédito. |
| W02.5 | Procedimento local de reset com alvos explícitos. | Reset repetível apenas em dados de teste; autenticação externa não atingida. |

Executar C13 e C17 em PostgreSQL real do Docker.
Fecho: invariantes de domínio preservadas através da persistência.

### W03 — Validação independente e laboratório

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W03.1 | Validador de cobertura, recursos, datas e estabilidade. | Candidatos adulterados deliberadamente são rejeitados pelo motivo correto. |
| W03.2 | Oráculo enumerativo para instâncias mínimas. | Viabilidade e ótimo conhecidos sem reutilizar restrições CP-SAT. |
| W03.3 | Gerador de fixtures com testemunhos e variantes. | Testemunho validado independentemente; mutations rastreáveis. |
| W03.4 | Manifests, seeds separadas e reprodução de casos. | Mesmo manifesto reconstrói os mesmos inputs. |
| W03.5 | Modo de campanhas no runner existente. | Seleção por ID, recolha de outputs, falhas e retoma de campanha. |
| W03.6 | Comparador de relatórios e cobertura de cenários. | Identifica regressão por família, casos omitidos e execução inconclusiva. |

Usar JSON/JSONL e resumo Markdown antes de considerar outro armazenamento.
Separar `fixture_seed`, `event_seed` e `solver_seed`.
Retomar uma campanha significa executar casos pendentes; não pressupõe checkpoint interno do CP-SAT.
Fecho: o laboratório consegue detetar erros plantados no candidato e no próprio gerador de fixtures.

### W04 — CompleteGeneration correto

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W04.1 | Compilar atribuições e disponibilidade conjunta. | Professor fixo, preferência soft e dias densos: T13–T14. |
| W04.2 | Quotas anuais por duração e crédito final. | Equações exatas; soma semanal não basta: T10. |
| W04.3 | Colocação detalhada e realimentação de conflitos. | T11; reabrir semanas; timeout não produz corte falso. |
| W04.4 | Salas elegíveis e matching completo. | T12; restrições específicas, lotações e intervalos sobrepostos. |
| W04.5 | Materializar, projetar módulos e validar ano completo. | T27, T30; candidato sem salas ou procura incompleta não passa. |

Executar C01–C08 e C10 em instâncias pequenas antes de aumentar escala.
Fecho: corpus viável obrigatório completo e válido; corpus impossível corretamente distinguido de pesquisa inconclusiva.

### W05 — Qualidade da geração inicial

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W05.1 | Vetor de conclusões ordenado da mais tardia para a mais precoce. | Oráculo encontra contraexemplo onde soma das datas daria decisão errada. |
| W05.2 | Furos docentes, depois turmas, preferências e salas. | T19; prioridade não depende da ordem das variáveis. |
| W05.3 | Incumbente anual e limites com âmbito explícito. | Melhorias locais não degradam prioridades globais. |
| W05.4 | Relatório de conclusão, margem e recuperabilidade. | C10–C11; não atrasar artificialmente para igualar turmas. |

Fecho: qualidade comparada com oráculos pequenos e baseline nos grandes, sem score fictício de perfeição.

### W06 — AdaptiveRecovery

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W06.1 | Identificar falta, excesso e aulas inválidas. | Baseline inválido não é aceite por ter sido publicado anteriormente. |
| W06.2 | Inserção, movimentos e expansão por conflitos. | C02–C04, C08; escapar de bairro local inviável quando há testemunho global. |
| W06.3 | Correspondência de identidades e custo de perturbação. | Trocar IDs não esconde movimentos; modular não conta como movimento físico. |
| W06.4 | Proteção progressiva da margem e excesso prioritário. | T15–T18; comparações C10–C12 aceites. |
| W06.5 | Reconciliar propostas, dívida e currículo após reparação. | C13–C14; nada é liquidado apenas porque existe uma proposta. |

Fecho: reparar não significa apenas encontrar a primeira cobertura completa.
Guardar melhores resultados e evidência de alternativas exploradas.

### W07 — Paragem e diagnóstico

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W07.1 | Resultados e certificados tipados. | T26; ótimo local não vira ótimo anual; unknown não vira impossible. |
| W07.2 | Pré-verificações e explicações de conflitos. | C08, C15; valores mínimos apenas quando demonstrados. |
| W07.3 | Controlador de exploração e retorno adicional. | Replay de trajetórias C19 com ganhos perdidos e esforço poupado. |
| W07.4 | Segurança, finalização e cancelamento. | C16; limite cobre construção, solve e persistência. |

Fecho: política explicável e mensurada, sem p95 como comando de paragem.

### W08 — Execução e publicação

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W08.1 | Revisões, snapshots e verificação de atualidade. | T24; alteração em fila, solve e aprovação invalida corretamente. |
| W08.2 | FIFO global, lock e token de tentativa. | T23; várias escolas e entrega duplicada mantêm um único cálculo. |
| W08.3 | Heartbeat, supervisor e recuperação de processo. | C16; terminação anterior confirmada antes de takeover. |
| W08.4 | Proposta e relógio de 28 dias atómicos. | T21–T22; falha/rejeição/aprovação não reiniciam indevidamente. |
| W08.5 | Aprovação e reconciliação numa transação. | Rollback a meio mantém integralmente a versão anterior. |

Fecho: C16–C17 em containers reais, incluindo falhas induzidas.

### W09 — API e aplicação escolar

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W09.1 | Contratos, autorização e geração idempotente. | GET não escreve; organização deriva do utilizador; duplo clique não duplica job. |
| W09.2 | Estado, fila, cancelamento e motivos de elegibilidade. | UI concorda com servidor; não existe geração automática por ocorrência. |
| W09.3 | Proposta, diferenças, alertas e aprovação. | Diferença modular separada da física; alerta além da preferência persiste. |
| W09.4 | Turmas, sumários, ocorrências, mapas e acertos. | Consumidores aceitam várias parcelas por aula e conservação de minutos. |
| W09.5 | Acessibilidade e percurso escolar completo. | C20; linguagem escolar, teclado, erros e frontend Docker atualizado. |

Fecho: percurso manual do proprietário sobre dados locais e E2E reproduzível.

### W10 — Campanhas integradas

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W10.1 | Matriz de fatores e combinações por pares. | Relatório lista pares válidos cobertos e exclusões justificadas. |
| W10.2 | Interações críticas de três ou mais fatores. | C08–C14 em topologias distintas, não só seeds diferentes. |
| W10.3 | Replays anuais com eventos acumulados. | C14; validação após cada passo e aprovação. |
| W10.4 | Fronteiras de viabilidade e reversão de pressão. | C02–C08, C15; transição explicada, não inferida pelo timeout. |
| W10.5 | Redução de falhas a casos mínimos. | Cada falha corrigida origina regressão determinística persistente. |

Fecho: matriz obrigatória concluída, resultados analisados e defeitos resolvidos ou explicitamente bloqueantes.

### W11 — Desempenho e calibração

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W11.1 | Comparar workers 1/2/4/8 no hardware local. | C18; CPU, RAM, qualidade e tempo, incluindo falhas. |
| W11.2 | Perfilar construção, procura, solver e persistência. | Otimizar o custo dominante observado; evitar otimização especulativa. |
| W11.3 | Calibrar política adaptativa e paragem. | C11, C19; treino separado de avaliação reservada. |
| W11.4 | Fixar baseline e parâmetros candidatos. | Manifesto versionado e relatório por família; nenhum p95 alvo inventado. |

Após otimização, repetir a falha, vizinhos da matriz e regressões relevantes.
Repetir campanha ampla quando o algoritmo, política, schema ou fronteira de concorrência mudar.

### W12 — Candidate e gate local

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W12.1 | Remover implementação, campos e contratos antigos. | Pesquisa de consumidores sem referências funcionais ao legado. |
| W12.2 | Instalação limpa e checks completos. | Suites, contratos, segurança, integridade e E2E verdes em Docker. |
| W12.3 | Avaliação reservada da candidate congelada. | Mesmo commit e política; casos não utilizados na calibração. |
| W12.4 | Dossier local e aceitação. | Proprietário revê resultados, limitações e runbooks concretos. |

Bloquear o gate por violações de integridade, isolamento, cobertura ou publicação incorreta.
Não compensar um erro crítico com uma média de qualidade alta.

### W13 — Validação remota, apenas após W12

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W13.1 | Publicar candidate identificada em Railway/Cloudflare. | Verificar commit, imagens, configuração e ausência de réplicas solver sobrepostas. |
| W13.2 | Repetir subconjunto representativo e casos extremos locais. | Validar integrações reais, latência, memória, filas e publicação. |
| W13.3 | Repetir configurações finalistas de workers. | Baseline remota separada; vencedor local não assumido como vencedor remoto. |
| W13.4 | Corrigir divergências através do ciclo local. | Falha remota reproduzida quando possível; regressões locais e remotas relevantes repetidas. |

Usar o ambiente de produção autorizado, ainda sem escolas reais, apenas nesta fase.
Não executar todos os ensaios destrutivos locais remotamente sem necessidade técnica.
Validar os modos de falha próprios do deployment e o procedimento de recuperação.

### W14 — Corte e entrega

| ID | Trabalho e entrega concreta | Teste/evidência para fecho |
| :--- | :--- | :--- |
| W14.1 | Preparar release, merge e acompanhar CI. | CI associado a cada push passa; revisão candidata identificada. |
| W14.2 | Parar entrada de jobs, limpar dados de ensaio e instalar baseline final. | Alvos verificados; nenhum job antigo ativo; instalação íntegra. |
| W14.3 | Smoke final de geração, aprovação e execução. | API, worker e frontend servem a mesma release compatível. |
| W14.4 | Entregar runbook, relatórios e limitações conhecidas. | Aceitação final e procedimento de recuperação da nova v1 ensaiado. |

## 5. Protocolo obrigatório de cada loop experimental

Cada campanha executa o seguinte ciclo, mesmo quando o primeiro cenário passa:

```text
X: baseline conhecida → executar → validar → analisar
Y: mutação controlada de X → executar → validar → comparar X/Y
Z: aumentar pressão ou introduzir interação → executar → validar → comparar
R: remover a pressão ou aplicar ação administrativa → executar → validar recuperação
```

Se ocorrer uma falha:

```text
congelar inputs e outputs → classificar → reduzir caso → escrever teste vermelho
→ corrigir causa → teste verde → repetir X/Y/Z/R e vizinhos afetados
→ atualizar relatório → avançar para outra topologia/escala
```

Não confundir três mudanças distintas:

| Mudança | Finalidade | Regra |
| :--- | :--- | :--- |
| Mudar cenário | Explorar ambiente diferente. | Preservar versão anterior e declarar o delta. |
| Mudar configuração | Comparar workers/política/limites. | Fixar inputs e commit para isolar o efeito. |
| Mudar código | Corrigir ou otimizar. | TDD e repetição da comparação anterior. |

Para comparar causas, derivar X/Y/Z da mesma baseline restaurada.
Para simular operação real, encadear eventos sobre o estado aprovado anterior.
Registar `execution_mode=isolated` ou `execution_mode=longitudinal`.
Nunca comparar uma cadeia acumulada com um cenário limpo como se só uma variável tivesse mudado.

### Análise obrigatória após cada passo

| Pergunta | Evidência |
| :--- | :--- |
| Cobriu a procura toda? | Minutos por atribuição, crédito executado, previsto e residual. |
| Respeitou recursos e datas? | Validador independente, colisões, estabilidade e limites. |
| Liquidou dívida corretamente? | Reconciliação por origem; reservas separadas de execução. |
| Que qualidade produziu? | Vetor completo, conclusões por turma, excesso, movimentos e furos. |
| Que esforço consumiu? | Tempos por fase, CPU, pico RAM, workers e trajetória. |
| Porque terminou? | Motivo, prova/estimativa e âmbito global ou local. |
| O que mudou face ao controlo? | Diff de inputs, outputs e métricas; hipótese explicativa. |
| O próximo passo está justificado? | Manter, corrigir, alargar pesquisa, refinar fixture ou aumentar pressão. |

Mesmo um resultado válido pode ser uma regressão de qualidade ou rendimento.
Mesmo uma instância impossível pode representar um teste passado, se diagnosticada corretamente.
Um caso viável conhecido sem solução encontrada é uma falha de rendimento, não uma prova de impossibilidade.

## 6. Classificação dos cenários e oráculos

Cada caso declara uma expectativa antes da execução:

| Categoria | Construção e aceitação |
| :--- | :--- |
| `FEASIBLE_WITH_WITNESS` | Existe horário testemunho validado. O gerador deve encontrar proposta completa nos casos obrigatórios. |
| `INFEASIBLE_PROVEN` | Prova independente, enumeração ou défice necessário documentado. Não aceitar solução nem diagnóstico contraditório. |
| `INVALID_INPUT` | Falta configuração obrigatória ou existem dados inconsistentes. Rejeitar na fronteira adequada. |
| `EXPLORATORY_UNKNOWN` | Viabilidade ainda desconhecida. Registar resultado; não usar como prova de sucesso ou impossibilidade sem evidência. |

Começar fixtures viáveis por calendários testemunho e derivar os requisitos.
Acrescentar também topologias desenhadas independentemente para não favorecer apenas horários fáceis de construir.
Criar impossibilidades mínimas retirando um recurso indispensável e demonstrando o conflito.
Conservar casos grandes exploratórios, mas não substituir o corpus obrigatório por casos sem oráculo.

“Espaço disponível” significa interseção efetiva de turma, professor atribuído, período, sala e janela editável.
Contar apenas buracos no calendário da turma é insuficiente.
Registar capacidade por recurso e gargalo, incluindo disponibilidade simultânea.
Não usar uma razão agregada procura/capacidade como certificado de viabilidade.

## 7. Catálogo de campanhas iterativas

Todas as sequências seguintes incluem executar, validar e analisar entre cada seta.
Nas campanhas de reparação, começar sempre por uma versão publicada e execução coerente com a data simulada.

### C01 — Geração limpa e currículo

**Pacotes:** W01, W03–W05. **Regressões:** T01, T13–T14, T27, T30.

X: escola pequena, períodos uniformes, recursos suficientes e nenhuma ocorrência.
→ Y: módulos que atravessam aulas, incluindo 75+75 minutos em períodos de 50.
→ Z: períodos mistos, crédito parcial final e três módulos numa aula.
→ R: procura toda cumprida; confirmar resultado vazio útil, sem aulas inventadas.

Repetir com 10/30/45/60 turmas e grelhas diferentes.
Analisar conservação, duração física, datas de conclusão e custo de construção.

### C02 — Poucas horas em muito espaço

**Pacotes:** W04, W06. **Regressões:** T04, T17.

X: inserir 1h residual num calendário com muitas interseções elegíveis.
→ Y: distribuir essa hora por duas atribuições e períodos de durações diferentes.
→ Z: manter a quantidade, mas concentrar disponibilidade num único professor.
→ R: repor disponibilidade e comparar movimentos e conclusão.

Verificar se a reparação usa espaço livre antes de perturbar desnecessariamente o horário.
Não exigir zero movimentos quando isso contrariar prioridades superiores.

### C03 — Muitas horas em pouco espaço

**Pacotes:** W04, W06, W10. **Regressões:** T11, T15, T18.

X: 10h residuais com solução testemunho apertada.
→ Y: 50h, repartidas entre turmas com professores partilhados.
→ Z: retirar capacidade elegível até ultrapassar uma fronteira demonstrada.
→ R: devolver capacidade mínima ou aumentar explicitamente o limite autorizado.

Analisar expansão do bairro, cedência entre turmas, uso da margem e diagnóstico de défice.
Não aceitar solução parcial nem extensão silenciosa da data limite.

### C04 — Poucas horas em pouco espaço

**Pacotes:** W04, W06, W07. **Regressões:** T10–T12, T26.

X: uma aula e uma posição conjunta elegível.
→ Y: a posição exige mover uma aula de outra turma.
→ Z: a cadeia atravessa várias semanas e uma sala específica.
→ R: retirar o último recurso indispensável e depois restaurá-lo.

Testar também residual de um minuto ocupando um período inteiro.
Distinguir inviabilidade local, inviabilidade global e dificuldade da pesquisa.

### C05 — Muitas horas em muito espaço

**Pacotes:** W04–W05, W11. **Regressões:** T27.

X: procura elevada com muitas colocações equivalentes.
→ Y: adicionar salas realmente equivalentes.
→ Z: ampliar grelha e horizonte sem aumentar procura.
→ R: retirar alternativas redundantes, mantendo o testemunho.

Analisar simetria, memória e crescimento das variáveis.
Mais alternativas não devem alterar validade, mas podem dificultar uma pesquisa limitada.
Não confundir regressão de runtime com violação de monotonicidade matemática.

### C06 — Escassez e abundância de professores

**Pacotes:** W04, W06, W09. **Regressões:** T14–T15, T20.

X: atribuições válidas com docentes suficientes.
→ Y: escola reatribui explicitamente disciplinas a menos docentes, aumentando partilha.
→ Z: baixa de dois meses de um professor crítico e retorno com procura acumulada.
→ R: escola atribui explicitamente um substituto ou restaura disponibilidade.

Ramo adicional: acrescentar docentes sem atribuições → confirmar que não criam capacidade fictícia.
Depois atribuir disciplinas a esses docentes → medir capacidade efetivamente utilizável.
Separar professor obrigatório em falta, que é input inválido, de professor atribuído sem capacidade suficiente.
O solver nunca distribui serviço docente por iniciativa própria.

### C07 — Escassez e abundância de salas

**Pacotes:** W04, W06, W11. **Regressões:** T12, T20.

X: salas suficientes e matching conhecido.
→ Y: retirar salas gerais, uma de cada vez, até à capacidade crítica.
→ Z: retirar o único laboratório elegível ou limitar a única sala com lotação suficiente.
→ R: devolver sala elegível; depois adicionar salas redundantes.

Acrescentar salas sem equipamento necessário não resolve falta de laboratório.
Verificar reservas por data, indisponibilidade parcial e continuidade das salas publicadas.
Analisar cortes devolvidos ao detalhe e custo das alternativas redundantes.

### C08 — Capacidade aparente e interações críticas

**Pacotes:** W03–W07, W10. **Regressões:** T10–T12, T26.

X: totais semanais suficientes com interseções temporais válidas.
→ Y: conservar os totais, deslocando disponibilidades para períodos incompatíveis.
→ Z: combinar professor partilhado, sala específica e estabilidade longa.
→ R: restaurar uma interseção indispensável e demonstrar solução.

Executar pares e triplos: docente×sala, docente×calendário, sala×estabilidade, docente×sala×prazo.
O detalhe deve refutar falsas promessas do agregado sem eliminar quotas viáveis por escolhas locais arbitrárias.

### C09 — Curto, médio e longo prazo

**Pacotes:** W01, W06, W08. **Regressões:** T03, T07–T09, T24.

Definir horizontes de teste pela grelha, nunca como novos limites de produto:

- Curto: primeiros cinco dias da grelha depois da fronteira editável.
- Médio: alterações entre duas e seis semanas depois dessa fronteira.
- Longo: alterações no restante período letivo, incluindo proximidade do limite final.

X: mesma ocorrência no curto prazo.
→ Y: mesma ocorrência no médio prazo, restaurando o estado de controlo.
→ Z: ocorrência equivalente no longo prazo.
→ R: colocar o alvo dentro da estabilidade e confirmar proteção física.

Repetir com janela 0, 1, 9 dias e janela que cobre todo o futuro disponível.
Repetir grelhas de 3/5/7 dias, feriados e mudança de data entre gerar e aprovar.
Comparar perturbação, urgência e capacidade real; não esperar igual dificuldade entre horizontes.

### C10 — Preferência, limite absoluto e justiça entre turmas

**Pacotes:** W05–W07. **Regressões:** T15–T18.

X: concluir todas as turmas antes da preferência.
→ Y: a turma atrasada só melhora se outra ceder capacidade.
→ Z: construir pares de alternativas que terminam na preferência, um dia depois e no limite absoluto.
→ R: ultrapassar o limite absoluto no testemunho proposto; o validador deve rejeitá-lo.

Incluir preferência igual ao limite absoluto e previsão de excesso detetada ainda em novembro.
Geração inicial não usa margem posterior à preferência.
Recuperação prioriza reduzir excesso, mesmo com muitos movimentos permitidos.

### C11 — Estabilidade versus margem

**Pacotes:** W06–W07, W11. **Regressões:** T16–T19.

X: conservar aulas custa um dia adicional, ainda longe da preferência.
→ Y: mesmo compromisso perto da preferência.
→ Z: mesmo compromisso implica ultrapassar a preferência.
→ R: comparar poucas/muitas alterações e alterações próximas/repetidas.

Guardar pares de resultados que o proprietário consegue comparar em linguagem escolar.
Validar monotonicidade e prioridades antes de ajustar coeficientes.
Repetir política escolhida em topologias reservadas para evitar sobreajuste aos exemplos.

### C12 — Acumular ocorrências ou reparar frequentemente

**Pacotes:** W06, W08, W10. **Regressões:** T21–T22, T24.

X: reproduzir uma sequência de ocorrências e pedir reparação após cada uma.
→ Y: restaurar baseline e acumular a mesma sequência antes de pedir reparação.
→ Z: alterar a frequência administrativa, incluindo renovação aos 28 dias.
→ R: cancelar ou rejeitar propostas e verificar os motivos ainda disponíveis.

Não exigir horários idênticos: decisões anteriores e estabilidade alteram o espaço de pesquisa.
Comparar efeito acumulado, minutos, datas finais e perturbação.
Nenhuma ocorrência inicia automaticamente o solver.

### C13 — Contabilidade sob alterações sucessivas

**Pacotes:** W01–W02, W06, W09. **Regressões:** T02–T07, T29–T30.

X: cancelar aula, criar dívida, planear recuperação e aprovar.
→ Y: cancelar a recuperação; voltar a planear; executar; repetir o comando de execução.
→ Z: acerto +600 e depois reversão -600, com origem auditada.
→ R: substituição por outra disciplina, sumário atrasado e correção retroativa.

Validar cada transição, não apenas o saldo final.
Incluir várias dívidas numa aula, uma dívida em várias aulas e excesso de crédito protegido.
Quando uma operação é inválida, exigir rollback integral e explicação; não forçar a sequência a continuar com dados corrompidos.

### C14 — Ano letivo completo

**Pacotes:** W06, W10–W12. **Regressões:** T01–T30 conforme eventos.

X: gerar, aprovar e executar semanas sem ocorrências.
→ Y: introduzir faltas dispersas, substituições e acertos reais simulados.
→ Z: baixa de dois meses de professor partilhado, encerramento de sala e turmas desigualmente atrasadas.
→ R: regressar recursos, reparar, executar até ao fim e reconciliar todo o ano.

Executar perfis tranquilo, irregular, concentrado em crises e próximo da saturação.
Avançar o relógio explicitamente; nunca editar datas fora dos comandos de teste.
Registar dezenas e centenas de eventos com seeds e sequência persistida.
Se a sequência tornar o ano impossível, exigir diagnóstico e ação administrativa explícita para retomar.
Não pedir ao solver para resolver uma impossibilidade física.

### C15 — Diagnóstico e recuperação administrativa

**Pacotes:** W07, W09. **Regressões:** T20, T26.

X: caso viável conhecido.
→ Y: remover capacidade indispensável e provar o défice.
→ Z: comparar mensagem de impossibilidade com interrupção de segurança sem prova.
→ R: diretor altera disponibilidade, professor atribuído, limite ou progresso efetivamente reconhecido.

Após a alteração, verificar elegibilidade e nova tentativa manual.
Validar que a ação sugerida se relaciona com a causa demonstrada.
Acrescentar casos com várias causas simultâneas e quantidades mínimas apenas parcialmente conhecidas.

### C16 — Falhas e concorrência operacional

**Pacotes:** W07–W08, W12. **Regressões:** T23–T26.

X: duas escolas pedem geração; confirmar FIFO e um cálculo global.
→ Y: duplicar mensagem, repetir pedido HTTP e interromper dispatch.
→ Z: matar processo, perder ligação do lock e reiniciar o serviço.
→ R: reconciliar tentativa abandonada e executar pedido ainda autorizado.

Repetir falhas durante construção, solve, validação, persistência e aprovação.
Incluir cancelamento concorrente com sucesso e escrita durante fila/solve/aprovação.
Induzir limite de memória e CPU em containers de teste dedicados.
Confirmar que heartbeat e cancelamento não ficam presos atrás do solve.
Verificar CPU anterior terminado antes de começar outra geração; fencing de escrita isolado não basta.

### C17 — Isolamento, instalação e integridade

**Pacotes:** W02, W08–W09, W12. **Regressões:** T28.

X: instalar base vazia e criar duas escolas.
→ Y: tentar referências, consultas e aprovações cruzadas.
→ Z: provocar falha a meio de publicação ou acerto.
→ R: verificar rollback, reinstalar localmente e repetir sem estado residual.

Usar role real sem bypass RLS.
O executor global pode escolher jobs sem ganhar acesso indiscriminado aos dados de todas as escolas.

### C18 — Escala e hardware

**Pacotes:** W11; repetição selecionada em W13. **Regressões:** T27.

X: mesmo caso com um worker interno.
→ Y: repetir com 2/4/8, intercalando ordem das configurações.
→ Z: reduzir quotas CPU/RAM e aumentar escala 10/30/45/60 turmas.
→ R: repetir configuração candidata nos casos fáceis, simétricos e difíceis.

Não executar solver jobs concorrentes para acelerar esta campanha.
Separar escalabilidade de infraestrutura de qualidade matemática.
Guardar configurações que falharam por OOM ou segurança; não descartá-las da comparação.

### C19 — Qualidade versus tempo

**Pacotes:** W07, W11.

X: trajetórias prolongadas com limites finitos de laboratório.
→ Y: simular offline diferentes critérios de paragem sobre as mesmas trajetórias.
→ Z: repetir online as políticas finalistas em casos reservados.
→ R: analisar ganhos relevantes perdidos, tempo poupado e incerteza.

Incluir melhoria precoce seguida de estagnação e melhoria tardia após uma longa fase sem incumbente novo.
Incluir famílias nunca vistas na calibração para testar comportamento conservador.
Não transformar ausência recente de melhoria em prova de proximidade do ótimo.

### C20 — Percurso escolar completo

**Pacotes:** W09, W12; smoke em W13–W14.

X: configurar escola, gerar, rever e aprovar.
→ Y: professor regista aula/ocorrência; administrador acumula motivos e pede atualização.
→ Z: proposta fica desatualizada ou ultrapassa preferência; rever mensagens e ações.
→ R: corrigir configuração, gerar novamente quando elegível e aprovar versão válida.

Incluir navegação por teclado, refresh, resposta atrasada, duplo clique e sessão sem permissão.
Confirmar mapas, detalhe de turma, sumários e relatórios concordantes com o mesmo estado curricular.
Usar adaptadores locais de teste para integrações externas durante a fase local.
Autenticação e deployment reais são validados posteriormente em W13.

## 8. Matriz de variedade e cobertura

### Eixos obrigatórios

| Eixo | Níveis mínimos de exploração |
| :--- | :--- |
| Escala | Microcasos enumeráveis; 10, 30, 45 e 60 turmas. |
| Procura de reparação | 0, 1, 10 e 50h; residual parcial; fronteira exata e um minuto além. |
| Espaço efetivo | Amplo, apertado viável, capacidade exata, insuficiente, aparente sem interseção. |
| Distribuição | Uma atribuição; muitas disciplinas; uma turma; várias turmas; conflito concentrado/disperso. |
| Docentes | Independentes, partilhados, gargalo único, baixa curta/prolongada, substituto explicitamente atribuído, excedentes não atribuídos. |
| Salas | Amplas, escassas, equivalentes, específicas, lotação crítica, reservas, redundantes inúteis. |
| Horizonte | Curto, médio, longo; ano inicial, meio do ano e proximidade do fim. |
| Calendário | Grelhas 3/5/7 dias, feriados, almoço, durações mistas, mudança de hora, intervalos sobrepostos. |
| Estabilidade | 0, 1, 9 dias; fronteira exata; todo o horizonte protegido. |
| Datas finais | Antes da preferência; na preferência; depois; no limite; impossibilidade antes do limite. |
| Eventos | Falta, cancelamento, substituição, correção, alteração curricular, disponibilidade e reatribuição docente. |
| Histórico | Limpo; poucas alterações; alterações repetidas; dezenas/centenas de eventos. |
| Operação | Sucesso, cancelamento, timeout, erro, stale, crash, reentrega, aprovação concorrente. |
| Hardware | Workers 1/2/4/8; quotas reais CPU/RAM; local e remoto em baselines separadas. |

Horas são convertidas explicitamente em minutos curriculares: 1h=60min, 10h=600min, 50h=3000min.
O número de blocos depende das durações físicas; não equiparar hora curricular a um bloco.
“Espaço amplo” e “apertado” devem ter capacidades e testemunhos registados, não apenas etiquetas subjetivas.

### Seleção sem explosão cartesiana

1. Cobrir cada nível isoladamente com um caso explicável.
2. Cobrir todos os pares válidos dos eixos semânticos no manifesto aprovado.
3. Acrescentar interações críticas explícitas de três ou mais fatores.
4. Repetir topologias representativas nas quatro escalas reais.
5. Executar campanhas anuais para interações acumuladas que pares estáticos não capturam.
6. Reservar famílias novas para avaliação final.

Separar a matriz semântica da matriz de hardware.
Não multiplicar cada microteste de contabilidade por todas as configurações de workers.
Restrições entre níveis incompatíveis devem ser explícitas no manifesto.
O relatório calcula cobertura efetiva; enumerar combinações não equivale a executá-las.

Interações críticas mínimas:

- Muitas horas × pouco espaço × professor partilhado × prazo próximo.
- Poucas horas × sala única × janela longa × períodos incompatíveis.
- Crédito parcial × módulos cruzados × substituição × acerto retroativo.
- Baixa prolongada × turmas com atrasos diferentes × limite preferencial.
- Sala redundante × docentes redundantes não atribuídos × elevada simetria.
- Aprovação atrasada × mudança de data × execução entretanto registada.
- Cancelamento × perda de worker × entrega duplicada × tentativa antiga.

## 9. Repetições, orçamento e critérios de término

Definir o manifesto e os limites de laboratório antes de lançar cada campanha.
O orçamento de ensaio controla trabalho experimental; não constitui SLA ou p95 do produto.

Protocolo inicial mínimo:

| Camada | Repetição inicial |
| :--- | :--- |
| Regressões determinísticas | Cada caso em cada alteração relevante; repetir identicamente se investigar instabilidade. |
| Microcasos com oráculo | Enumeração exaustiva dentro do tamanho declarado. |
| Famílias sintéticas | Pelo menos três topologias distintas por família antes de declarar cobertura da família. |
| Comparação de pesquisa | Cinco seeds de solver por par fixture/configuração finalista. |
| Replays anuais | Três sequências de eventos por perfil e escala obrigatória, sobre baseline identificada. |
| Comparação final de hardware | Várias repetições por seed quando houver variância material; número fixado no manifesto. |

Estes mínimos iniciam a investigação; não provam significância estatística nem estabilizam automaticamente p95.
Aumentar amostras quando houver variância, regressões inconsistentes ou conclusões ambíguas.
Não parar de recolher amostras apenas porque apareceu um resultado favorável.
Conservar resultados anteriores e explicar qualquer mudança do protocolo.

Perfis anuais obrigatórios: tranquilo, irregular, crises concentradas e saturação.
Escalas anuais obrigatórias: 10/30/45/60 turmas.
Uma sequência com impossibilidade prevista termina corretamente com diagnóstico e intervenção explícita, não com sucesso artificial.

Fechar uma campanha quando:

- Todos os passos e combinações obrigatórios estão executados e analisados.
- Casos viáveis obrigatórios produzem propostas completas e válidas.
- Casos impossíveis/inputs inválidos têm classificação e explicação corretas.
- Nenhuma violação de integridade, proteção ou isolamento permanece aberta.
- Regressões de qualidade/recursos foram resolvidas ou impedem o gate até decisão explícita sustentada.
- Variância e limites da conclusão constam do relatório.

Limites de segurança que interrompem um caso não contam como cobertura bem-sucedida desse caso.
Se o computador local não suportar um ensaio obrigatório, registar o bloqueio.
Não mover silenciosamente a campanha para Railway; aplica-se a regra de exceção explícita do plano.

## 10. Artefactos, relatórios e triagem

Reutilizar `.test-artifacts/` do runner existente.
Acrescentar subdiretório de campanhas apenas na implementação.
Não versionar dumps enormes ou dados pessoais; versionar fixtures compactas e receitas de geração.

Cada execução conserva:

```text
campaign_id, case_id, case_version, parent_case_id, mutation
execution_mode, expectation, oracle_reference
commit, image_digest, schema_version, policy_version
fixture_seed, event_seed, solver_seed, workers
hardware, limits, input_digest, event_sequence
result, validation_report, objective_vector, trajectory
timings_by_phase, CPU_seconds, peak_RSS, proof_scope
analysis, defect_reference, next_action
```

O relatório de campanha contém baseline, hipótese, matriz prevista/executada, resultados, falhas e conclusão.
Mostrar piores casos e distribuições por família, além de medianas.
Separar tempo até primeira solução, tempo até proposta persistida e espera em fila.
Listar execuções censuradas e inconclusivas junto das concluídas.

| Classe de problema | Ação |
| :--- | :--- |
| Fixture/teste errado | Corrigir gerador ou oráculo com revisão rastreável; invalidar apenas conclusões afetadas. |
| Violação de domínio | Bloquear candidate; reduzir caso e corrigir com TDD. |
| Falha de pesquisa em caso viável | Preservar testemunho; analisar candidatos, cortes, bairros e recursos. |
| Qualidade pior | Comparar vetor e trajetória; localizar prioridade ou custo incorreto. |
| Runtime/RAM pior | Perfilar fase dominante; manter mesmas condições na comparação. |
| Falha operacional | Injetar novamente no ponto exato; verificar idempotência e atomicidade. |
| Expectativa escolar ambígua | Apresentar resultados concretos e alternativas; não escolher pesos ocultamente. |

Após corrigir, executar o caso mínimo, a família original e famílias que partilham a regra alterada.
Antes dos gates, executar a matriz obrigatória da candidate final.
Se ajustar código/política após observar o conjunto reservado, esses casos passam a regressão conhecida.
Criar nova amostra reservada para avaliar generalização da candidate seguinte.

## 11. Gates e rastreabilidade final

| Gate | Pacotes/campanhas | Evidência obrigatória |
| :--- | :--- | :--- |
| G1 — Domínio | W01–W03; C01, C09, C13 | Minutos, estabilidade, ledger e validador independentes. |
| G2 — Geração | W04–W05; C01–C08, C10 | Cobertura completa, salas e qualidade coletiva demonstradas. |
| G3 — Recuperação | W06–W07; C02–C15, C19 | Reparação, justiça, margem, diagnóstico e paragem corretos. |
| G4 — Aplicação | W08–W09; C12–C13, C16–C17, C20 | Ciclo manual, isolamento e publicação atómica. |
| G5 — Candidate local | W10–W12; C01–C20 | Matriz, replays anuais, hardware, limpeza e avaliação reservada. |
| G6 — Remoto | W13; subconjunto declarado C14, C16, C18, C20 | Baseline Railway/Cloudflare e integrações reais. |
| G7 — Lançamento | W14 | CI verde, baseline final, smoke e aceitação. |

G1–G4 são gates técnicos progressivos. G5 é a fronteira obrigatória entre Docker local e validação remota.
G6 e G7 não substituem G5.

| Regressões do plano | Campanhas principais |
| :--- | :--- |
| T01–T07 | C01, C09, C13, C14 |
| T08–T09 | C09, C14, C20 |
| T10–T14 | C01, C04, C06–C08 |
| T15–T20 | C03, C06–C07, C10–C11, C14–C15 |
| T21–T22 | C12, C20 |
| T23–T26 | C04, C08, C15–C16 |
| T27 | C01, C05, C14, C18 |
| T28 | C17, C20 |
| T29–T30 | C01, C13–C14 |

O dossier final reúne cobertura por decisão D01–D31, regressão T01–T30, pacote W00–W14 e campanha C01–C20.
Não encerrar a entrega apenas porque todos os testes unitários passaram.
Encerrar quando a candidate demonstrar comportamento correto em cenários estáticos, alterações acumuladas e falhas de operação.
