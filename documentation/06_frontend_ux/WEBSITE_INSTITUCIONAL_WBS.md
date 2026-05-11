# Website Institucional Apérius

## Objetivo
Definir o site publico institucional separado da aplicação operacional.

## Direção de marca
- Tom de voz simples, humano e orientado a dores reais de escolas profissionais.
- Linguagem sem jargão técnico desnecessário.
- Base visual premium, limpa e com muito whitespace.
- Tipografia editorial alvo: Playfair Display para títulos e Inter para corpo.
- Paleta editorial atual: alabaster, charcoal, taupe e dourado, sem cores saturadas.
- Implementação feita com o stack já existente no frontend, sem novas dependências de UI.

## Estrutura de conteúdo
### Home
- Hero com promessa clara: reduzir o caos da gestão de horários.
- Bloco de dor: faltas de última hora, horários feitos à mão, módulos sem controlo claro, substituições sem memória.
- Cenário prático: professor falta e o admin substitui em poucos cliques.
- Secção de prova operacional: como o produto ajuda no dia a dia.

### Produtos
- Substituições rápidas.
- Controlo por módulos.
- Histórico transparente do que aconteceu.

### Brand principles
- Secção editorial para "show, don't tell".
- Sistema visual consistente entre landing e aplicação.
- Bloco de narrativa curta sobre a origem do produto.

### Pricing
- Cartões simples e muito espaço em branco.
- Estrutura por dimensão da escola.
- Valores finais: a definir ou sob consulta conforme contexto.

### About
- Missão focada em aliviar a sobrecarga administrativa.
- Posicionamento centrado em escolas profissionais.

### Contacto
- CTA para apresentação do fluxo real.
- Conteúdo orientado a próxima conversa, não a formulários longos.

## Regras UX
- Visual premium sem exagero decorativo.
- Mobile-first.
- Microinterações subtis.
- Não misturar a mensagem institucional com a operação autenticada da aplicação.
- CTA discretos e poucos por página.
- Consistência de tipografia, espaçamento e linguagem entre secções.
- Storytelling curto, específico e ancorado em dores reais.

## Implementação atual
- Hero com hierarquia editorial forte e chamada principal em destaque.
- Secção de estatísticas curtas para reforço visual sem poluição.
- Blocos de conteúdo com bordas finas, espaços amplos e alternância de fundo claro/escuro.
- Fundo fixo e plano, sem gradientes decorativos nem grelhas verticais visíveis.
- Acento visual azul/verde para equilibrar a identidade interna da aplicação.
- Testemunhos curtos e FAQ editorial para fechar a narrativa com mais prova e mais clareza.
- Texturas e efeitos visuais mantidos via CSS existente, sem dependências adicionais.
- A landing publica foi ajustada para usar as classes CSS ja presentes no frontend, mantendo CoreUI e React como base e evitando utilitarios visuais externos.

## Decisão de navegação
- A landing pública vive na raiz do site.
- A aplicação operacional continua separada no fluxo autenticado.
