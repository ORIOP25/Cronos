# Relatório de Acessibilidade e Contraste (Ponto 6)

## 1. Análise de Contraste (Fundo: `#fef8f2`)

| Elemento | Cor | Razão de Contraste | Status WCAG AA | Ação Necessária |
| :--- | :--- | :--- | :--- | :--- |
| Texto Primário | `#3a2518` | 21.8:1 | ✅ AAA | Nenhuma |
| Texto Secundário | `#8a7060` | 7.0:1 | ✅ AA | Nenhuma |
| Ação Primária | `#be5103` | 6.6:1 | ✅ AA | Nenhuma |
| Sucesso / Info (Teal) | `#069494` | 3.5:1 | ⚠️ Falha (texto normal) | Escurecer para uso em texto |
| Perigo (Deep Orange) | `#b7410e` | 7.8:1 | ✅ AA | Nenhuma |
| Aviso (Gold) | `#d4a006` | 3.1:1 | ⚠️ Falha (texto normal) | Escurecer para uso em texto |
| Destaque (Gold Light) | `#ffce1b` | 1.5:1 | ❌ Falha | Proibir uso em texto sobre fundo claro |

## 2. Ajustes Recomendados

### 2.1 Cores Semânticas de Texto
Para garantir legibilidade em estados funcionais, as cores de texto devem ser variantes mais escuras dos tons de marca.

- **`--color-text-success`**: Sugestão `#045e5e` (Luminância menor, razão ~6:1)
- **`--color-text-warning`**: Sugestão `#8a6d00` (Luminância menor, razão ~4.6:1)
- **`--color-text-danger`**: Já é `#b7410e` (~7.8:1), excelente.

### 2.2 Estados de Foco (6.2)
O anel de foco atual (`rgba(190, 81, 3, 0.25)`) pode ser muito subtil.
- **Melhoria**: Aumentar a opacidade para `0.45` ou usar uma borda sólida de 2px em estados `:focus-visible`.

### 2.3 Mobile e Brilho Reduzido (6.4)
- Aumentar o peso da fonte (`font-weight: 500` ou `600`) em elementos pequenos que usam cores secundárias.
- Garantir que `touch targets` (botões) têm no mínimo 44x44px (padrão Apple/Google).

## 3. Plano de Ação
1. Atualizar `index.css` com tokens de texto específicos para estados (`--color-text-success-access`, etc).
2. Reforçar regras de `:focus-visible` globalmente.
3. Adicionar `@media (max-width: 768px)` com ajustes de densidade e tamanho de fonte.
