# Estrutura documental oficial

## Objetivo
Definir como a pasta documentation deve ser organizada para manter:
- clareza para negocio e engenharia;
- consistencia com clean architecture;
- rastreabilidade entre requisito funcional e implementacao tecnica;
- baixo risco de contradicoes entre ficheiros.

## Principio central
So documentar informacao confirmada.
Se um tema nao estiver fechado, escrever "a definir" sem inventar detalhe.

## Mapa por 3 layers

### Layer 1 - Interface
Escopo:
- contratos de API;
- comportamento de UX;
- regras de apresentacao e interacao.

Pastas:
- 05_backend_api/
- 06_frontend_ux/

### Layer 2 - Regras de negocio
Escopo:
- estrategia de produto;
- invariantes de dominio;
- hard constraints e objetivos soft do motor;
- fluxos operacionais de faltas e substituicoes.

Pastas:
- 01_product_strategy/
- 02_domain_model/
- 03_scheduler_engine/
- 04_operational_features/

### Layer 3 - Base de dados
Escopo:
- persistencia e seeds;
- seguranca e qualidade aplicadas ao dado;
- observabilidade operacional orientada a consistencia dos dados.

Pastas:
- 07_data_and_seed/
- 08_security_quality/
- 09_ops_observability/

## Convencoes de escrita

Cada documento estrategico deve incluir:
- 5 Ws do assunto;
- explicacao teorica;
- explicacao pratica;
- pelo menos um exemplo operacional;
- impacto por layer (Interface, Regras de negocio, Base de dados) quando aplicavel.

## Convencoes de mudanca

Sempre que um documento for alterado:
1. Explicar o que mudou.
2. Explicar porque mudou.
3. Explicar impacto operacional e de seguranca.
4. Listar follow-ups quando existirem dependencias nao fechadas.