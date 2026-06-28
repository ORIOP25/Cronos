# Cronos Frontend

Frontend React/Vite do Cronos.

## Stack
- React 19
- Vite 7
- React Router
- Clerk
- CoreUI
- React Query
- Vitest
- Playwright

## Scripts
```bash
npm run dev
npm run build
npm run lint
npm run test
npm run test:e2e
```

## Marketing site publico
A homepage publica vive em:

- `src/pages/MarketingSite.jsx`
- `src/pages/MarketingSite.css`

Assets publicos da landing:

- `public/marketing/hero-laptop.png`
- `public/marketing/product-panorama.png`

Esta e a versao oficial atual do site publico. A implementacao antiga foi substituida por uma landing editorial V3 orientada a produto, com copy explicita para gestao de horarios no ensino profissional portugues.

## Rotas
- `/`: marketing site para utilizadores signed-out.
- `/login`: autenticacao.
- `/register`: registo.
- Rotas autenticadas: dashboard, horarios, cursos, professores, salas, sumarios, progresso e configuracao.

## Notas de manutencao
- O marketing site usa classes `cronos-*` para evitar conflitos com a aplicacao autenticada.
- A app operacional continua a usar os tokens globais em `src/index.css`.
- Evitar novas dependencias visuais sem necessidade clara.
- Atualizar `documentation/06_frontend_ux/WEBSITE_INSTITUCIONAL_WBS.md` quando a estrutura publica mudar.
