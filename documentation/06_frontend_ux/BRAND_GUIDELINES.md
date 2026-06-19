# Cronos - Brand & Design Guidelines

Este documento define a identidade visual atual do Cronos para a aplicacao operacional e para o marketing site publico.

## 1. Principio de marca
Cronos deve transmitir controlo, clareza e confianca sem parecer uma ferramenta fria ou excessivamente tecnica. A marca visual combina uma base editorial premium com componentes simples, funcionais e legiveis.

## 2. Marketing Site V3
A landing publica atual usa uma direcao visual propria, isolada em `frontend/src/pages/MarketingSite.css`, e comunica o Cronos como aplicacao de gestao de horarios para o ensino profissional portugues.

### Paleta
| Token local | Hex | Uso |
| --- | --- | --- |
| `--cronos-cream` | `#fbf6e6` | Fundo principal publico |
| `--cronos-paper` | `#fffdf7` | Cards, formulario e superficies claras |
| `--cronos-brown` | `#3b2415` | Texto principal, botoes, footer |
| `--cronos-brown-2` | `#24150d` | Footer e contraste profundo |
| `--cronos-muted` | `#806e5f` | Texto secundario |
| `--cronos-accent` | `#f2a20c` | CTAs secundarios, detalhes, estrelas |
| `--cronos-green` | `#2f7d63` | Apoio visual em avatares/estado |
| `--cronos-blue` | `#476da8` | Apoio visual em avatares/estado |
| `--cronos-red` | `#a4573e` | Apoio visual pontual |

### Layout
- Composicao editorial larga.
- Header minimalista com navegacao curta, CTA de demonstracao e acesso "Entrar".
- Cards retangulares, borda fina e pouca sombra.
- Footer escuro com a palavra "Cronos." em escala grande.
- Imagens do produto ou produto em contexto devem ser preferidas a ilustracoes abstratas.

### Tipografia
- `--font-body` para quase toda a landing.
- `--font-display` apenas em momentos editoriais pontuais, como enfase em "Cronos".
- Letter spacing deve permanecer neutro nas novas implementacoes.

### UI
- Botoes retangulares, sem arredondamento decorativo.
- Inputs com linha inferior no formulario publico.
- SVGs lineares simples para icones.
- Elementos decorativos devem ser subtis e nunca competir com o conteudo.

## 3. Aplicacao operacional
A aplicacao autenticada continua a usar os tokens globais definidos em `frontend/src/index.css`.

### Tokens globais principais
| Token | Uso |
| --- | --- |
| `--brand-50` | Fundo geral claro |
| `--brand-100` | Superficies subtis |
| `--brand-800` | Acoes principais e headings |
| `--brand-950` | Fundos profundos |
| `--brand-500` | Acentos, destaques e estados |

## 4. Regras de manutencao
1. O marketing site publico deve usar classes `cronos-*` para evitar colisao com a app.
2. Componentes autenticados devem continuar a usar tokens globais e classes operacionais existentes.
3. Nao usar hex codes inline em JSX quando uma variavel CSS existir.
4. Alteracoes de identidade que afetem a landing publica devem atualizar `WEBSITE_INSTITUCIONAL_WBS.md`.
5. A copy publica deve explicar rotinas e capacidades reais antes de linguagem aspiracional: horarios, ocorrencias, sumarios, disponibilidade, UFCDs, modulos, professores, salas, cursos e progresso.
