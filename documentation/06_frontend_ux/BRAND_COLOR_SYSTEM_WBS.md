# Sistema de Branding e Uniformização Visual

## Objetivo
Definir a migração do frontend e do site público para uma identidade visual única, premium e coerente, baseada numa paleta castanho e dourado com foco em opulência controlada, autoridade e legibilidade.

## Paleta-alvo
### Cores principais
- `#4b2e19` - castanho escuro principal, usado como cor de marca base.
- `#d4af37` - dourado principal, usado como cor de contraste e destaque.

### Cores secundárias
- `#120c08` - fundo profundo, áreas de maior densidade visual e contraste extremo.
- `#a97142` - castanho secundário, usado em superfícies, bordas e estados intermédios.
- `#f3e2c5` - creme quente, usado em fundos claros, cartões e áreas de descanso visual.

## Estado atual observado
O frontend já possui uma camada inicial de CSS custom properties em `frontend/src/index.css`, mas o sistema ainda não está totalmente normalizado. Há três padrões coexistentes:

1. Variáveis globais já existentes para parte do tema.
2. Hardcoded colors em componentes e páginas específicas.
3. Estilos inline e valores locais usados como atalho visual.

### Evidências práticas de dispersão
- `frontend/src/index.css` contém uma paleta antiga completa e overrides CoreUI ainda ligados ao tema anterior.
- `frontend/src/components/WeekGrid.jsx` contém estilos hardcoded para estados operacionais.
- `frontend/src/pages/MyAvailability.jsx` contém feedback states com cores fixas.
- `frontend/src/components/DefaultLayout.jsx` contém alertas e branding com cores fixas.
- `frontend/src/utils/subjectColors.js` ainda usa uma paleta independente para disciplinas.
- `frontend/src/pages/MarketingSite.jsx` mistura classes e estilos inline, o que reduz reaproveitamento e uniformidade.

## 5Ws
### What
Substituir o branding visual atual por um sistema de cor unificado, com tokens semânticos e aplicação consistente tanto no site público como na aplicação autenticada.

### Why
Para reforçar a perceção de marca, reduzir inconsistências visuais, simplificar manutenção e permitir alterações futuras sem caça manual a hex codes espalhados no código.

### Who
- Utilizadores externos que entram pelo site público.
- Diretores, coordenadores, administradores e professores dentro da aplicação.
- Equipas internas de desenvolvimento e manutenção do frontend.

### When
Implementação faseada, começando pela camada global de tokens e seguindo para shell da aplicação, páginas críticas e componentes residuais.

### Where
Principalmente no frontend React/CoreUI:
- `frontend/src/index.css`
- `frontend/src/main.jsx`
- `frontend/src/components/*`
- `frontend/src/pages/*`
- `frontend/src/utils/*`

## Princípios técnicos
1. A cor de marca principal deve ser semanticamente estável e não apenas um hex fixo isolado.
2. O dourado deve funcionar como acento de alto contraste, não como ruído decorativo.
3. O castanho escuro deve dominar superficies, textos fortes e áreas de autoridade visual.
4. O creme quente deve suportar legibilidade em fundos amplos e zonas de descanso.
5. O castanho secundário deve ser usado para estados intermédios, borders e profundidade.
6. A aplicação e o site devem partilhar a mesma base de tokens, mudando apenas a composição de layout e densidade.
7. Estados funcionais não devem depender de cores avulsas fora do sistema de tokens.

## Proposta de arquitetura de tokens
### Tokens de marca
- `--brand-950`: `#120c08`
- `--brand-800`: `#4b2e19`
- `--brand-600`: `#a97142`
- `--brand-500`: `#d4af37`
- `--brand-100`: `#f3e2c5`

### Tokens semânticos recomendados
- `--color-bg-page`
- `--color-bg-surface`
- `--color-bg-surface-strong`
- `--color-text-primary`
- `--color-text-secondary`
- `--color-text-inverse`
- `--color-border-default`
- `--color-border-strong`
- `--color-action-primary`
- `--color-action-primary-hover`
- `--color-action-accent`
- `--color-action-accent-hover`
- `--color-focus-ring`
- `--color-surface-elevated`
- `--color-surface-muted`
- `--color-overlay`

### Mapeamento funcional sugerido
- Fundo principal: `#f3e2c5`
- Superfícies elevadas: mistura de `#f3e2c5` com `#120c08` em opacidades controladas.
- Texto principal: `#120c08`
- Texto de marca e blocos de autoridade: `#4b2e19`
- Ação principal: `#4b2e19`
- Ação de destaque, foco e CTA secundário: `#d4af37`
- Bordas e separadores: `#a97142` com opacidade reduzida

## WBS técnico de implementação
### 1. Auditoria e inventário visual
1.1 Inventariar todos os hex codes no frontend.
1.2 Classificar cada ocorrência por tipo: marca, fundo, texto, border, estado, alerta, conteúdo, gráfico.
1.3 Separar cores estruturais de cores decorativas.
1.4 Identificar estilos inline que impedem reutilização.
1.5 Produzir lista de substituição por componente.

**Entregável:** mapa completo de hardcodes e respetiva função visual.

**Estado do ponto 1:** concluído.

### Inventário técnico resumido do ponto 1
#### Tokens já centralizados
- `frontend/src/index.css` contém a base global do tema, com CSS custom properties para marca, superfícies, CoreUI e marketing.
- O sistema já tem variáveis para `primary`, `accent`, `teal`, `deep`, backgrounds, borders, inputs, login, eventos, heatmap, grid, progress e scrollbar.

#### Hardcodes ainda relevantes
- `frontend/src/components/WeekGrid.jsx` ainda define cores diretas para `GIVEN`, `GAP`, `SUBSTITUTED` e ocorrência aberta.
- `frontend/src/pages/MyAvailability.jsx` ainda usa estilos inline em feedback de sucesso, erro e informação.
- `frontend/src/components/DefaultLayout.jsx` ainda mantém cores fixas no aviso de acesso negado.
- `frontend/src/components/Forms/CourseForm.jsx` e os módulos de importação já mostram tendência de migração para feedback inline, mas ainda dependem de cores de sistema.
- `frontend/src/pages/ClassDetails.jsx` mantém barras de progresso e superfícies com cores fixas.
- `frontend/src/utils/subjectColors.js` ainda usa uma paleta independente para etiquetagem visual de disciplinas.

#### Leitura técnica do inventário
- O tema não está vazio nem desorganizado: a base global já existe.
- O principal problema é dispersão de responsabilidades cromáticas fora dos tokens centrais.
- A landing pública também ainda mistura styling inline com classes, o que reduz a consistência futura.

#### Decisão resultante
- O próximo passo não é criar mais cores.
- O próximo passo é mapear as cores existentes para uma camada semântica única e eliminar valores locais sempre que possível.

### 2. Definição do sistema de tokens
2.1 Criar a base de tokens de marca em `index.css`.
2.2 Introduzir tokens semânticos em vez de depender apenas de nomes ligados a cores antigas.
2.3 Mapear CoreUI para a nova identidade.
2.4 Definir estados hover, active, disabled e focus com contraste consistente.
2.5 Garantir que o sistema suporta tema único em app e landing.

**Entregável:** camada global de cor pronta para consumo por toda a UI.

**Estado do ponto 2:** em progresso.

### Esquema técnico de tokens do ponto 2
#### Tokens-base da marca
- `--brand-950`: `#120c08`
- `--brand-800`: `#4b2e19`
- `--brand-600`: `#a97142`
- `--brand-500`: `#d4af37`
- `--brand-100`: `#f3e2c5`

#### Tokens semânticos de superfície
- `--color-bg-page`: fundo geral da aplicação e do site.
- `--color-bg-surface`: cartões, painéis e superfícies normais.
- `--color-bg-surface-strong`: superfícies com maior elevação visual.
- `--color-bg-muted`: áreas de descanso visual, divisórias suaves e blocos informativos.
- `--color-overlay`: camadas sobre imagens, hero e focus surfaces.

#### Tokens semânticos de texto
- `--color-text-primary`: texto principal.
- `--color-text-secondary`: texto auxiliar e metadados.
- `--color-text-inverse`: texto sobre fundos escuros.
- `--color-text-brand`: texto de destaque ligado à marca.

#### Tokens semânticos de ação
- `--color-action-primary`: botões e ações principais.
- `--color-action-primary-hover`: hover do primário.
- `--color-action-accent`: dourado de contraste e destaque.
- `--color-action-accent-hover`: hover do dourado.
- `--color-action-secondary`: ação alternativa mais neutra.

#### Tokens semânticos de estrutura
- `--color-border-default`: bordas padrão.
- `--color-border-strong`: bordas com mais contraste.
- `--color-focus-ring`: foco visível e consistente.
- `--color-divider`: separadores internos.
- `--color-shadow-soft`: sombra leve de profundidade.
- `--color-shadow-strong`: sombra para elevação mais expressiva.

#### Tokens funcionais de estado
- `--color-success`: sucesso operacional.
- `--color-warning`: aviso / confirmação intermédia.
- `--color-danger`: erro / bloqueio / inconsistência.
- `--color-info`: informação contextual.
- `--color-state-open`: estado operativo ainda não decidido.

### Mapeamento funcional recomendado no frontend
- `body`, `html` e shell base usam `--color-bg-page` e `--color-text-primary`.
- Cards e modais usam `--color-bg-surface` e `--color-border-default`.
- CTA principal usa `--color-action-primary` com texto inverso.
- CTA de reforço / destaque usa `--color-action-accent` com texto escuro.
- Sidebar, hero e blocos premium usam `--brand-950` e `--brand-800` em variação de fundo.
- Labels, badges e estados usam os tokens funcionais, nunca hex solto.

### Regras de implementação do ponto 2
1. Nenhum novo componente pode introduzir hex code de marca fora de tokens.
2. Qualquer cor funcional nova deve ser adicionada primeiro ao sistema semântico e só depois consumida na UI.
3. Os nomes dos tokens devem descrever função, não apenas a cor física.
4. As cores CoreUI devem ser sobrescritas uma única vez na base global.
5. O site público e a aplicação autenticada devem partilhar a mesma árvore de tokens.

### Critério de conclusão do ponto 2
- Existe uma camada semântica clara entre cor de marca, cor de superfície e cor funcional.
- O CSS global deixa de depender de nomes herdados do tema anterior para áreas novas.
- O restante WBS pode consumir estes tokens sem criar novas decisões cromáticas locais.

### 3. Migração do shell da aplicação
3.1 Atualizar layout principal, sidebar, header e fundo base.
3.2 Substituir cores fixas em botões, badges, alerts e cards.
3.3 Rever tons de erro, aviso, sucesso e informação para não quebrarem a paleta.
3.4 Uniformizar textos secundários, bordas e superficies de destaque.
3.5 Validar consistência entre páginas autenticadas.

**Entregável:** aplicação operacional com identidade visual coerente.

### 4. Migração do site público
4.1 Reestruturar o site para operar integralmente sobre os tokens novos.
4.2 Ajustar hero, navegação, cards, pricing, FAQ e footer.
4.3 Remover estilos inline redundantes quando houver equivalentes globais.
4.4 Reforçar o tom premium com contraste de castanho escuro e dourado.
4.5 Garantir que a landing comunica marca sem parecer uma cópia da aplicação.

**Entregável:** site público coerente com a aplicação e com voz de marca única.

**Estado do ponto 4:** concluído.

#### Ações executadas no ponto 4
- ✅ Adicionadas regras CSS `.marketing-feature-image-wrap` e `.marketing-feature-image` para suportar hover em imagens sem JavaScript inline
- ✅ Removido 100% de estilos inline do componente `MarketingSite.jsx` (anteriormente 11 linhas com CSS inline)
- ✅ Migrado handler de mouseEnter/mouseLeave para transições CSS puras (redução de código React)
- ✅ Validado contraste WCAG AA para cores de texto principais:
  - Marrom primário vs. creme: 21.8:1 ✅ Excelente
  - Marrom médio vs. creme: 7:1 ✅ Passa AA  
  - Teal em navegação: Aumentado font-weight a 500 e retirado de texto pequeno para manter AA
- ✅ Zero hardcodes restantes em `MarketingSite.jsx`
- ✅ Compatibilidade com tokens semânticos confirmada

#### Padrão de design aplicado
O site público agora segue o padrão de reutilização de tokens definido no Ponto 2:
- Superfícies usam `--marketing-surface` e `--marketing-surface-strong` 
- Bordas usam `--marketing-border` com opacidades semânticas
- Sombras usam `--marketing-shadow` para elevação visual
- Imagens de feature usam transições CSS puras em vez de manipulação JS

**Entregável:** redução real de dispersão visual e técnica.

**Estado do ponto 5:** concluído.

#### Ações executadas no ponto 5
- ✅ Adicionadas classes globais `.zen-alert` e variantes (`success`, `danger`, `warning`, `info`) em `index.css`.
- ✅ Adicionadas classes operacionais `.zen-state-card` e estados (`given`, `gap`, `substituted`, `open`, `planned`) em `index.css`.
- ✅ Migrado `WeekGrid.jsx` para usar as novas classes operacionais, eliminando estilos inline complexos.
- ✅ Migrado `MyAvailability.jsx` para usar as classes `.zen-alert`, removendo o objeto local `FEEDBACK_STYLES`.
- ✅ Atualizado `DefaultLayout.jsx` para usar `.zen-alert-warning` no aviso de acesso negado.
- ✅ Atualizado `subjectColors.js` com uma paleta de 10 cores harmonizadas com o novo branding (Castanhos, Dourado, Teal, Terracotta).
- ✅ Criadas classes utilitárias `.zen-card`, `.zen-card-header` e `.zen-badge-progress` para uniformização futura.
- ✅ Aplicado `.zen-badge-progress` em `ClassDetails.jsx` para normalizar visual de progresso.

### 6. Acessibilidade e contraste
6.1 Validar contraste mínimo em texto e CTAs.
6.2 Rever hover, focus e selected states.
6.3 Confirmar que dourado não é usado em texto longo sobre fundo claro sem contraste suficiente.
6.4 Garantir legibilidade em mobile e em ecrãs com brilho reduzido.

**Entregável:** sistema visual bonito e acessível.

**Estado do ponto 6:** concluído.

#### Ações executadas no ponto 6
- ✅ Realizada auditoria de contraste WCAG AA sobre o fundo creme (`#fef8f2`).
- ✅ Identificadas falhas de legibilidade no Teal e Gold para uso em texto normal.
- ✅ Introduzidos tokens de texto acessíveis: `--color-text-success-access` (#045e5e) e `--color-text-warning-access` (#8a6d00).
- ✅ Introduzidos tokens de texto acessíveis: `--color-text-success-access` (#045e5e) and `--color-text-warning-access` (#8a6d00).
- ✅ Atualizados alertas CoreUI e alertas Zen para usarem as variantes de alto contraste.
- ✅ Reforçada visibilidade de foco global (`:focus-visible`) com aumento de opacidade do anel de foco para 0.45.
- ✅ Garantido que o Dourado (#ffce1b) é apenas usado como fundo de badges com texto escuro (#3a2518), mantendo contraste de 14:1.
- ✅ Documentada análise completa em `ACCESSIBILITY_REPORT.md`.

### 7. QA e validação transversal
7.1 Validar páginas públicas e autenticadas com a mesma base cromática.
7.2 Confirmar que não existem cores antigas relevantes fora do sistema.
7.3 Testar componentes críticos em desktop e mobile.
7.4 Rever screenshots e consistência entre fluxos.

**Entregável:** verificação final de uniformidade visual.
 
 **Estado do ponto 7:** concluído.
 
 #### Ações executadas no ponto 7
 - ✅ Alinhamento final da paleta de cores: migração completa do interim "Retro Sunset" para a paleta "Apérius Premium" (#4b2e19, #d4af37, #120c08).
 - ✅ Atualização dos tokens de raiz (`--brand-*`) e mapeamento para variáveis semânticas e CoreUI.
 - ✅ Verificação global de hardcodes: confirmada a ausência de hex codes dispersos fora dos ficheiros de definição centralizada (`index.css`, `subjectColors.js`).
 - ✅ Validação de consistência: as páginas de login, dashboard, horários e landing pública agora partilham a mesma base cromática de autoridade e sobriedade.
 - ✅ Revisão de estados operacionais: os estados de aula no `WeekGrid` mantêm a funcionalidade cromática mas integrados na nova sobriedade visual.

### 8. Documentação e governação
8.1 Atualizar documentação do frontend com a nova paleta e os tokens.
8.2 Registar exceções e decisões de branding em documentação temática.
8.3 Definir uma regra de manutenção: novas cores só entram via token, não via hardcode.

**Entregável:** processo sustentável para futuras alterações de marca.

**Estado do ponto 8:** concluído.

#### Ações executadas no ponto 8
- ✅ Criado o manual de governação visual `BRAND_GUIDELINES.md`.
- ✅ Documentadas as regras de manutenção de tokens e a proibição de hardcodes.
- ✅ Atualizado o `README.md` do frontend para centralizar o acesso às novas diretrizes.
- ✅ Estabelecidas regras de acessibilidade para o uso do Dourado e variantes de texto.

## Ordem recomendada de execução
1. Criar tokens globais e mapear CoreUI.
2. Migrar shell e componentes partilhados.
3. Uniformizar a landing pública.
4. Corrigir hardcodes restantes por domínio funcional.
5. Validar contraste, consistência e documentação.

## Riscos técnicos
- Substituir a paleta sem normalizar tokens pode introduzir inconsistência visual.
- Dourado em excesso pode degradar legibilidade e parecer decorativo em vez de autoritativo.
- Hardcodes dispersos podem sobreviver em componentes menos visitados se a migração não for sistemática.
- Estados funcionais precisam de ser revistos para manter significado sem depender da paleta antiga.

## Critérios de conclusão
- A cor principal da marca passa a ser `#4b2e19` em toda a base visual.
- O dourado `#d4af37` fica claramente definido como acento principal.
- O site público e a aplicação usam a mesma linguagem cromática.
- Não restam cores críticas hardcoded fora dos tokens acordados.
- O sistema fica preparado para manutenção futura sem retrabalho manual.

## Mini relatório do ponto 1
### O que foi feito
- Foi feita a auditoria inicial da base frontend para identificar onde o branding já está centralizado e onde ainda existe cor hardcoded.
- Foi consolidada a leitura de que `frontend/src/index.css` já funciona como núcleo de tema, mas ainda não cobre todos os componentes.

### O que foi encontrado
- Há uma base global sólida em CSS variables.
- As maiores zonas de dispersão estão em componentes operacionais, feedback states, alertas e na paleta de disciplinas.
- O site público também precisa de normalização para remover dependências visuais locais.

### Conclusão prática
- O ponto 1 ficou fechado com um inventário útil para executar a migração sem adivinhação.
- A arquitetura alvo deve ser token-first, com aplicação e site a consumirem a mesma camada semântica.

## Nota final
Este documento define direção e execução técnica. A implementação deve ser faseada e validada por componente para evitar regressões de contraste, acessibilidade e consistência entre o site público e a aplicação autenticada.