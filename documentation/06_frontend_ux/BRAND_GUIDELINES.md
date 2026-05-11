# Aperius - Brand & Design Guidelines

Este documento define a identidade visual e o sistema de design do Aperius, garantindo consistência entre a página pública e a aplicação operacional.

## 1. Paleta de Cores (Premium Palette)

O sistema baseia-se numa paleta de autoridade, inspirada em tons terrosos e metais nobres.

| Token | Hex | Uso Principal |
| :--- | :--- | :--- |
| `--brand-950` | `#120c08` | Texto principal, fundos profundos |
| `--brand-800` | `#4b2e19` | Cor primária da marca, botões principais, cabeçalhos |
| `--brand-600` | `#a97142` | Cor secundária, bordas fortes, acentos quentes |
| `--brand-500` | `#d4af37` | Dourado premium, acentos de destaque, estados de aviso |
| `--brand-100` | `#f3e2c5` | Fundos de superfície, áreas de destaque subtil |
| `--brand-50` | `#fdfcf8` | Fundo principal da página (Off-white) |

## 2. Sistema de Tokens Semânticos

Nunca utilize Hex Codes diretamente nos componentes. Utilize sempre as variáveis semânticas:

### Superfícies
- `--color-bg-page`: Fundo geral da aplicação.
- `--color-bg-surface`: Fundo de cards e modais (geralmente branco).
- `--color-bg-surface-strong`: Cabeçalhos de cards e secções destacadas.

### Texto
- `--color-text-primary`: Texto de leitura e títulos (Brand 950).
- `--color-text-secondary`: Texto de apoio (Brand 800).
- `--color-text-brand`: Texto com a cor da marca.

### Ações (Botões/Links)
- `--color-action-primary`: Botão principal.
- `--color-action-accent`: Destaque (Gold).
- `--color-action-secondary`: Ações neutras.

## 3. Estados Operacionais (Acessibilidade)

Para garantir contraste WCAG AA sobre o fundo claro, utilize as variantes de texto acessível:

- **Sucesso/Info (Teal)**: Texto deve usar `--color-text-success-access` (`#045e5e`).
- **Aviso (Gold)**: Texto deve usar `--color-text-warning-access` (`#8a6d00`).
- **Perigo**: Texto deve usar `--color-text-danger-access` (`#b7410e`).

**Regra do Dourado**: O dourado (`#d4af37` ou `#ffce1b`) só deve ser usado como fundo se o texto for escuro (`#120c08`). Nunca use dourado para texto longo sobre fundo claro.

## 4. Governação e Manutenção

1. **Proibição de Hardcodes**: É estritamente proibido o uso de `style={{ color: '#...' }}` para cores da marca.
2. **Inclusão de Novas Cores**: Se uma nova cor for necessária, deve ser adicionada como token no `:root` do `index.css`.
3. **Consistência Cross-Page**: Qualquer alteração na marca deve ser validada tanto no `MarketingSite.jsx` quanto no `DefaultLayout.jsx`.
4. **Mobile First**: As cores secundárias devem manter peso visual suficiente para legibilidade em ecrãs com pouco brilho.
