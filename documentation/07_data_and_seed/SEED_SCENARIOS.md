# Seed scenarios

## Objetivo
Padronizar dados de seed para validar comportamento funcional e operacional sem ambiguidade.

## 5 Ws da seed strategy

### What
Conjuntos de dados sinteticos para testes de geracao, operacao e seguranca de tenant.

### Who
Usado por equipa tecnica para validacao de backend, motor e operacao.

### Where
Ambientes de desenvolvimento, teste e validacao controlada.

### When
Antes de validacao funcional relevante e antes de release de mudancas criticas.

### Why
Sem seeds consistentes, resultados de teste ficam pouco reproduziveis.

## Perfis de seed

### Small-realistic (perfil canonico)
Foco:
- facilitar testes manuais de navegacao e operacao com dados legiveis;
- manter modelo de dados completo em escala menor;
- reduzir ruido de nomes tecnicos em validacao manual.

Caracteristicas:
- 1 organizacao;
- 3 cursos completos (10, 11, 12);
- salas, professores, disponibilidades, disciplinas, modulos, links, lessons e progresso;
- nomes realistas para escola, cursos, turmas e professores.

Comando:
- `python seed_data.py --profile small-realistic --reset`

Nota:
- `seed_data_small_realistic.py` e o modulo auxiliar deste perfil (execucao direta mantida apenas para compatibilidade local).

### Baseline
Foco:
- validar regras hard basicas;
- validar roles (admin/professor) no escopo minimo;
- validar tenant isolation.

### Operacional Alpha (Passo 6)
Foco:
- validar operacao diaria de faltas/substituicoes com dados canonicos;
- incluir cenarios obrigatorios de recomendacao:
	- caso com multiplos elegiveis;
	- caso sem elegivel com fallback GAP;
- validar isolamento entre pelo menos 2 tenants com cenarios em paralelo;
- manter dataset pequeno e deterministico para execucao rapida em CI.

### Large-scale
Foco:
- validar comportamento padrao em escala elevada multi-tenant;
- servir como perfil de referencia por omissao no runner canonico;
- suportar validacoes de performance e robustez em carga realista alargada.

Comando:
- `python seed_data.py --profile large-scale --reset`

### Stress
Foco:
- validar comportamento com carga maior;
- observar estabilidade de geracao e consultas;
- identificar gargalos sem comprometer verdade de dominio.

## Regras obrigatorias da seed

1. Dados separados por organization_id.
2. Nenhum dataset deve misturar registos entre tenants.
3. Cenarios devem incluir ao menos um caso de conflito potencial para validar bloqueio hard.
4. Cenarios operacionais devem incluir eventos de falta/substituicao para rastreabilidade.

## Exemplo pratico

Cenario baseline:
- Organizacao A com turmas e professores proprios.
- Organizacao B com estrutura separada.

Validacao esperada:
- consultas e mutacoes de A nao acedem dados de B;
- geracao de A nao usa disponibilidade de B.

## Decisao fechada para Alpha V1 (sem pendencias)

Volumes de referencia por perfil:
- baseline: usar `seed_data.py --profile baseline --reset` (1 organizacao, 6 turmas, conjunto funcional minimo completo);
- small-realistic: usar `seed_data.py --profile small-realistic --reset` (1 organizacao, 3 cursos completos, nomenclatura realista para validacao manual);
- large-scale: usar `seed_data.py --profile large-scale --reset` (perfil de referencia em escala elevada com cobertura multi-tenant);
- operacional alpha: usar `seed_data.py --profile operational --reset` (2 organizacoes, cenarios deterministas de ocorrencias/substituicoes para validacao do passo 6);
- stress: usar `seed_data.py --profile stress --reset` (atualmente equivalente ao large-scale em volume, reservado para evolucao futura de carga maxima).

Seed canonico (nao destrutivo por omissao):
- `python seed_data.py` preserva dados existentes e apenas sincroniza alias de login necessario.

Limiares numericos de aceitacao por tempo de execucao:
- baseline: concluir seed completa em ate 180 segundos em ambiente de CI/referencia;
- operacional alpha: concluir seed completa em ate 180 segundos em ambiente de CI/referencia;
- stress: concluir seed completa em ate 1800 segundos em ambiente de CI/referencia;
- consistencia: 3 execucoes consecutivas sem erro funcional nem violacao de tenant isolation.

## Passo 6 - contrato de validacao operacional

### Cenarios obrigatorios incluidos
1. multi_eligible_substitution:
- ocorrencia com pelo menos 2 candidatos elegiveis no mesmo tenant;
- ranking deterministico validado pelo backend.

2. no_eligible_fallback_gap:
- ocorrencia com 0 elegiveis no tenant;
- estado operacional resolvido como GAP (fallback explicito).

3. tenant_isolation_check:
- segunda organizacao com dados proprios e utilizadores proprios;
- consultas de recomendacao nao atravessam fronteira de organization_id.

### Comandos de execucao
Ambiente local:
- `python seed_data.py --profile operational --reset`

CI/referencia:
- `pytest tests/test_seed_operational_scenarios.py -q`

Consistencia (repeticoes):
- suite valida assinatura identica em 3 execucoes consecutivas do perfil operacional.

### Nota operacional importante
- execucoes com `--reset` devem ser seguidas de restart do servico backend;
- motivo: evitar `InvalidCachedStatementError` no pool asyncpg apos mudanca estrutural de schema com o backend em execucao.

## Impacto por layer

### Interface
- permite testes previsiveis de respostas e estados de UI.

### Regras de negocio
- valida invariantes e hard constraints em dados realistas.

### Base de dados
- confirma isolamento tenant e consistencia transacional.