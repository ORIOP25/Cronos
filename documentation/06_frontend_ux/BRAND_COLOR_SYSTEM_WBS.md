# Brand Color System - Estado Atual

## Estado
Concluido e suplantado pela implementacao atual.

Este documento substitui o WBS antigo de migracao cromatica. A versao anterior descrevia problemas ja resolvidos no marketing site, incluindo mistura de estilos inline e falta de isolamento visual.

## Decisao atual
- O marketing site publico usa uma camada visual propria em `frontend/src/pages/MarketingSite.css`.
- As classes publicas usam o prefixo `cronos-*`.
- A aplicacao autenticada continua a usar os tokens globais em `frontend/src/index.css`.
- A direcao oficial de marca esta documentada em `BRAND_GUIDELINES.md`.
- O PRD/WBS oficial da landing esta documentado em `WEBSITE_INSTITUCIONAL_WBS.md`.

## Resultado
- `MarketingSite.jsx` ja nao depende de CoreUI para compor a landing publica.
- A landing deixou de ter estilos inline estruturais.
- A mensagem publica passou a privilegiar explicacao objetiva do produto, com foco em horarios, ocorrencias, sumarios, disponibilidade e progresso UFCD.
- Os assets publicos da nova landing vivem em `frontend/public/marketing/`.

## Regra para novas alteracoes
Qualquer nova cor deve entrar primeiro como variavel CSS no escopo correto:
- `MarketingSite.css` para a landing publica.
- `index.css` para a aplicacao autenticada ou componentes partilhados.

Evitar reabrir a migracao antiga; a fonte de verdade e agora o par `BRAND_GUIDELINES.md` e `WEBSITE_INSTITUCIONAL_WBS.md`.
