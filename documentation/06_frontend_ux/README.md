# Frontend UX

Esta secção define a interface e experiência de utilizador do Cronos.

## Conteúdo Principal
- [**BRAND_GUIDELINES.md**](./BRAND_GUIDELINES.md): Diretrizes de design, paleta premium e governação de tokens.
- [**ACCESSIBILITY_REPORT.md**](./ACCESSIBILITY_REPORT.md): Relatório de conformidade WCAG e acessibilidade.
- [**BRAND_COLOR_SYSTEM_WBS.md**](./BRAND_COLOR_SYSTEM_WBS.md): Estado atual do sistema de cor e nota de migração concluída.
- [**UX_CONSISTENCY_SCHEDULES.md**](./UX_CONSISTENCY_SCHEDULES.md): Padrões de experiência e consistência de estado nos horários.
- [**WEBSITE_INSTITUCIONAL_WBS.md**](./WEBSITE_INSTITUCIONAL_WBS.md): PRD/WBS do marketing site V3, fonte oficial da landing pública atual.
- [**WBS_REFATORACAO_SCHOOL_CONFIG.md**](./WBS_REFATORACAO_SCHOOL_CONFIG.md): Refatoração da página de Configuração da Escola.
- [**WBS_CORRECAO_BUGS_UI_UX_OPERACAO_REAL.md**](./WBS_CORRECAO_BUGS_UI_UX_OPERACAO_REAL.md): Correção de bugs UI/UX em operação real (✅ todas as correções aplicadas a 03 Maio 2026).

## Auditoria Frontend (Maio 2026)
- [**auditoria-frontend-ui-ux.md**](../auditoria-frontend-ui-ux.md): Auditoria completa (46 findings, 100% corrigidos a 03 Maio 2026). Inclui registo de correções, novas utilidades e componentes.

## Novos Componentes e Utilidades (Maio 2026)

### Utilitários Centralizados
| Ficheiro | Descrição |
|----------|-----------|
| `src/utils/formatUtils.js` | Formatação de datas e números (PT-PT). Usar em toda a app. |
| `src/utils/terminology.js` | Terminologia padronizada (`TXT`, `humanizeOperationalDetail`, `EVENT_TYPE_LABELS`). Substitui todas as strings hardcoded. |

### Componentes Transversais
| Ficheiro | Descrição |
|----------|-----------|
| `src/components/ErrorBoundary.jsx` | Captura erros de renderização e mostra ecrã de recuperação. |
| `src/components/ConfirmationModal.jsx` | Modal de confirmação reutilizável. Substitui `window.confirm()` em toda a app. |

### Sub-Componentes Extraídos
| Ficheiro | Origem |
|----------|--------|
| `src/components/schedules/KPISidebar.jsx` | Extraído de Schedules.jsx |
| `src/components/schedules/DraftPanel.jsx` | Extraído de Schedules.jsx |
| `src/components/schedules/GenerationStatusPanel.jsx` | Extraído de Schedules.jsx |
| `src/components/schedules/PreflightErrorPanel.jsx` | Extraído de Schedules.jsx |
| `src/components/timesheets/TeacherCard.jsx` | Extraído de Timesheets.jsx |

### Sidebar Responsiva
- Sidebar colapsável com toggle (ícone hamburger) para admin e professor.
- Estado de colapso persistido em `localStorage` (chave `hz-sidebar-collapsed`).
- Larguras: 280px (expandida) / 72px (colapsada).
- Admin: experiência desktop-first. Professor: mobile-first com padding reduzido.

## Melhorias Estruturais (Maio 2026)

### Code Splitting
Todas as páginas protegidas usam `React.lazy()` + `Suspense`. Apenas Login/Register são carregadas no bundle inicial. Redução do bundle principal: 621KB → 381KB (39%).

### Sistema de Toasts
- `contexts/ToastContext.jsx`: `ToastProvider` + hook `useToast()`.
- Toasts com auto-dismiss (4s), posicionados no canto superior direito.
- Substitui `CAlert` inline por feedback não-bloqueante.
- Variantes: `toast.success()`, `toast.error()`, `toast.warning()`, `toast.info()`.

### Focus Trap em Modais
- `hooks/useFocusTrap.js`: hook que aprisiona o foco dentro do modal ativo.
- Deteta automaticamente o `.modal-content` no DOM (compatível com portal do CoreUI).
- Restaura o foco ao elemento original quando o modal fecha.
- Integrado em: `GenericModalForm`, `ConfirmationModal`, `LessonLogModal`.

### BrandPanel Partilhado
- `components/auth/BrandPanel.jsx`: painel de marca reutilizável entre Login e Register.
- Props: `tagline` (texto descritivo), `stats` (array de {value, label}).
- Reduziu duplicação de ~80 linhas de JSX em cada página.

### Skeleton Loaders
- `components/SkeletonTable.jsx`: placeholder animado para tabelas (usa `rows` e `columns`).
- `components/SkeletonGrid.jsx`: placeholder animado para grelhas (usa `rows` e `cols`).
- `components/Skeleton.css`: animação shimmer com `@keyframes`.
- Integração futura: substituir spinners no `SmartTable` e `WeekGrid`.

### Breadcrumbs
- `components/Breadcrumbs.jsx`: navegação hierárquica para páginas de cursos.
- Integrado em: `CourseDetails`, `ClassDetails`, `ClassSubjects`.
- Substitui breadcrumbs manuais inline (‹ como separador, último item ativo).

### Testes Adicionais
| Ficheiro | Cobertura |
|----------|-----------|
| `test/formatUtils.test.js` | 16 testes: formatDate, formatDateTime, formatWeekRange, formatNumber, addDays, etc. |
| `test/terminology.test.js` | 10 testes: TXT, humanizeOperationalDetail, EVENT_TYPE_LABELS |
| `test/ErrorBoundary.test.jsx` | 4 testes: render normal, erro, fallback, botão painel |
| `test/ConfirmationModal.test.jsx` | 7 testes: título/mensagem, callbacks, loading, variant |
- **Login e Register** redesenhados com layout "Editorial Authority":
  - Layout dividido: formulário (60%) + painel de marca escuro (40%) com textura de grão.
  - Painel de marca com fundo `brand-950`, monograma HZ dourado, elementos decorativos e estatísticas.
  - Formulário com labels em maiúsculas, inputs com ícones integrados, validação em tempo real.
  - Barra de progresso no Register (campos preenchidos).
  - Link animado com underline entre Login ↔ Register.
  - Responsivo: painel de marca colapsa para banner horizontal em mobile.
- CSS: classes `.zen-link-underline` e `.zen-login-brand-panel` em `index.css`.

## Compromisso
- UX consistente com autorização por role, foco operacional e estética premium de autoridade.
- Terminologia padronizada em PT-PT (tratamento formal).
- Zero `window.confirm()` — usar `ConfirmationModal`.
- Zero `alert()` — usar alertas CoreUI (CAlert).
- Termos técnicos (`CP-SAT`, `solver`, `worker`, `churn`, `backlog`) traduzidos para vocabulário do domínio escolar.
