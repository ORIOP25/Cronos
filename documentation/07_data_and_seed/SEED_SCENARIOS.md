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

### Baseline
Foco:
- validar regras hard basicas;
- validar roles (admin/professor) no escopo minimo;
- validar tenant isolation.

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

## Pontos ainda a definir (nao fechados)
- volumes exatos por perfil baseline/stress;
- limiares numericos de aceitacao por tempo de execucao.

## Impacto por layer

### Interface
- permite testes previsiveis de respostas e estados de UI.

### Regras de negocio
- valida invariantes e hard constraints em dados realistas.

### Base de dados
- confirma isolamento tenant e consistencia transacional.