# Endpoint standards

## Objetivo
Padronizar contratos da API para manter previsibilidade funcional e seguranca operacional.

## 5 Ws da camada API

### What
API HTTP da plataforma para operacao de horarios, disponibilidade e eventos operacionais.

### Who
Perfis suportados:
- admin: acesso total no tenant;
- professor: apenas disponibilidade e consulta do proprio horario.

### Where
Sempre no contexto da organizacao autenticada.
Qualquer endpoint deve respeitar organization_id.

### When
Aplicado em todo novo endpoint e em revisao de endpoints existentes.

### Why
Reduzir ambiguidade de contrato e evitar comportamentos inconsistentes entre frontend e backend.

## Regras obrigatorias de contrato

1. Dependencias FastAPI via Annotated.
2. Requests e responses tipados com Pydantic v2.
3. Status code explicito para sucesso e erro esperado.
4. Sem bare except.
5. Operacoes criticas dentro de transacao atomica.

## Regras de autorizacao

### admin
- pode executar operacoes de administracao da organizacao, geracao e aprovacao.

### professor
- pode apenas:
	- registar/atualizar a propria disponibilidade;
	- consultar o proprio horario.

Qualquer operacao fora deste escopo deve ser negada para professor.

## Modelo de erro (padrao minimo)

Mesmo sem formato final fechado, toda resposta de erro deve deixar claro:
- tipo do erro;
- motivo operacional;
- contexto suficiente para troubleshooting sem expor dados sensiveis.

## Clean architecture na API

API pertence a Layer Interface.
Portanto:
- recebe e valida input;
- chama casos de uso/servicos de negocio;
- devolve contrato de saida;
- nao decide regra de dominio por conta propria.

## Exemplo pratico (sem fixar rota)

Caso de uso: "professor atualiza disponibilidade"

Contrato esperado:
- autenticacao valida;
- professor so altera dados proprios;
- dados persistidos com tenant isolation;
- resposta confirma atualizacao sem expor dados de terceiros.

## Impacto por layer

### Interface
- contrato estavel e previsivel para consumo frontend.

### Regras de negocio
- negocio centralizado em servicos/casos de uso, nao no controlador HTTP.

### Base de dados
- persistencia com isolamento por organization_id e consistencia transacional.