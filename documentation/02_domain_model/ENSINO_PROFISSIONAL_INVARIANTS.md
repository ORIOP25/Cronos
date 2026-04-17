# Invariantes de dominio do Ensino Profissional

## Objetivo
Eliminar ambiguidades funcionais no nucleo do produto.
Este documento define apenas regras consideradas estaveis.

## 5 Ws do dominio

### What
Dominio modular, medido por progresso de modulo por turma.
Nao e um modelo anual fixo de disciplina fechada por periodo unico.

### Who
No sistema:
- admin governa e aprova operacao da organizacao.
- professor fornece disponibilidade e consulta o proprio horario.

Fora do sistema:
- alunos nao sao entidade operacional individual do produto.

### Where
Escopo de operacao por organizacao (tenant).
Nenhuma regra deve cruzar dados entre organizacoes.

### When
As regras valem em planeamento e em execucao diaria.
Mudancas de plano aplicam-se ao futuro sem reescrever passado executado.

### Why
Sem estes invariantes, o motor pode gerar resultado visualmente aceitavel mas operacionalmente invalido.

## Invariantes nucleares

1. Ensino profissional e orientado a modulos.
2. Progresso e medido por modulo (hours_completed / hours_total).
3. Uma disciplina pode ter varios modulos com ordem obrigatoria.
4. Geracao de horario ocorre a nivel organizacional, nao por turma isolada.
5. Isolamento por organization_id e obrigatorio em leitura e escrita.
6. Historico de execucao e imutavel.
7. Substituicao de aula da turma X so pode usar docente de outra disciplina da propria turma X.
8. Docente da mesma disciplina, mas de outra turma, nao e elegivel para substituicao da turma X.
9. Em caso de multiplos elegiveis, o sistema recomenda candidatos por ranking deterministico.
10. A decisao final da substituicao e sempre aprovada pelo admin.

## Regras de autorizacao confirmadas

### admin
- acesso total dentro da organizacao;
- aprova e publica decisoes operacionais.

### professor
- marca disponibilidade;
- consulta o proprio horario;
- sem permissao para gerir horarios de outros ou aprovar operacao global.

## Invariantes de role e sincronismo professor-admin (Alpha V1 - Ponto 10)

### What
Fecho dos invariantes funcionais para a experiencia professor/acessos:
- fronteira self-service por role;
- sincronismo entre horario publicado e vista do professor;
- observabilidade tecnica sem mutacao de estado de negocio.

### Who
- admin: governa publicacao e monitorizacao operacional;
- professor: atua apenas no proprio contexto autenticado;
- equipa tecnica: garante consistencia entre interface, regras e API.

### Where
- interface: menu e rotas por role;
- regras de negocio/API: contratos `teachers` e `schedule` para self-service;
- base de dados: leituras tenant-scoped e historico de eventos operacionais.

### When
- em cada login/navegacao por role;
- em cada leitura semanal do professor;
- em cada publicacao ativa refletida no fluxo `Meus Horarios`.

### Why
- garantir least privilege real para professor;
- impedir divergencia entre horario publicado e horario consultado;
- manter triagem operacional com dados objetivos sem alterar o dominio executado.

Regras de negocio fechadas:
1. Professor so consome contratos self-service do proprio contexto autenticado.
2. Professor nao consulta horario de outra turma/professor por manipulacao de parametros.
3. Endpoints self-service do professor sao explicitamente negados para role admin.
4. Vista semanal do professor usa sempre horario publicado ativo (is_draft=false) como fonte de verdade.
5. Sincronismo professor-admin segue alvo operacional de 30s (p95) e tolerancia de 60s (p99) na Alpha.
6. Observabilidade de endpoints do professor e sinal tecnico; nao altera estado funcional de ocorrencias/progresso.

## Explicacao teorica

Num dominio modular, a pergunta central nao e apenas "qual aula acontece hoje".
A pergunta central e "como o conjunto de aulas executadas faz o modulo avancar de forma correta e auditavel".

## Explicacao pratica

Quando ocorre uma alteracao operacional:
- o plano futuro pode ser ajustado;
- o que ja aconteceu fica preservado;
- qualquer ajuste deve continuar respeitando ordem de modulo e isolamento por tenant.

## Exemplo operacional

Cenario:
- turma T1 da organizacao A;
- disciplina D com modulos M1 e M2 em sequencia.

Regra aplicada:
- M2 nao pode ser tratado como concluido sem progresso valido em M1.

Conseqencia:
- o sistema pode replanejar aulas futuras de D, mas nao "apagar" ocorrencias executadas para forcar conclusao artificial.

## Impacto por layer

### Interface
- mostra apenas operacoes permitidas por role.

### Regras de negocio
- aplica invariantes de modulo, ordem e tenant em todas as decisoes.

### Base de dados
- persiste progresso e ocorrencias de forma consistente e auditavel.