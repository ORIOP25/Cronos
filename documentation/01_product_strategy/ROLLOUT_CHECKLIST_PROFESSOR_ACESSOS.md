# Rollout Checklist - Professor e Acessos

## Objetivo
Formalizar o gate operacional de staging para piloto no escopo da feature de visao professor e controlo de acessos.

## 5 Ws

### What
Checklist de validacao por role para:
- menu e rotas por permissao;
- contratos self-service de professor;
- sincronismo tecnico de horario professor-admin;
- monitorizacao de erro e latencia por endpoint critico.

### Who
- admin da escola piloto: valida experiencia administrativa e reflexo no professor;
- professor da escola piloto: valida fluxo self-service e leitura do proprio horario;
- equipa tecnica: valida monitorizacao, alertas e regressao automatizada.

### Where
- staging com seed canonico da escola;
- backend API e frontend de producao candidata.

### When
- antes da promocao para piloto;
- apos qualquer alteracao em permissao/rota/contrato de professor;
- apos incidentes de 403/5xx nos endpoints criticos do professor.

### Why
- reduzir risco de regressao de autorizacao no arranque do piloto;
- garantir que o sincronismo professor-admin permanece previsivel;
- suportar triagem rapida com sinais objetivos de observabilidade.

## Checklist go/no-go por role

### Admin
1. Nao visualiza tabs de professor no menu.
2. Nao acede rotas teacher-only sem redirecionamento para dashboard.
3. Consegue consultar `GET /api/v1/teachers/observability/summary`.
4. Consegue validar alertas 403/5xx por endpoint critico em janela de 15 minutos.

### Professor
1. Visualiza exatamente duas tabs: Minhas Preferencias e Meus Horarios.
2. `GET /api/v1/teachers/me/availability` responde com dados self-service do proprio contexto.
3. `GET /api/v1/schedule/me/horizon` responde com horizonte valido ou erro operacional claro.
4. `GET /api/v1/schedule/week` nao aceita escopo de outra turma/professor (403).

### Operacao tecnica
1. Latencia p95 por endpoint critico disponivel no resumo operacional.
2. Taxa 5xx > 2% dispara alerta `HIGH_5XX_RATE`.
3. Burst 403 com count >= 10 e taxa >= 20% dispara alerta `ABNORMAL_403_RATE`.
4. Simulacao de recuperacao remove alerta apos normalizacao de taxa.

## Criterio de promocao

Promover para piloto apenas se:
1. 100% da checklist por role estiver verde.
2. Sem alertas ativos de severidade high no resumo de 15 minutos.
3. Sem regressao aberta de tenant isolation ou autorizacao no escopo professor.

## Itens a definir
- janela final de monitorizacao para go/no-go alem dos 15 minutos padrao: a definir.
- canal operacional oficial para distribuicao do checklist assinado: a definir.
