# Cronos Marketing Site V3

## Estado
Versao oficial atual do site publico do Cronos.

Esta versao substitui a landing V2 centrada em beneficio generico por uma pagina mais explicita, longa e orientada a rotina escolar. A mensagem principal passa a posicionar o Cronos como uma aplicacao para gerir horarios no ensino profissional portugues, ligando planeamento, execucao real, sumarios, ocorrencias e progresso de UFCDs.

## PRD

### Objetivo
Criar uma homepage publica que permita a um decisor escolar perceber rapidamente:
- o que e o Cronos;
- para que tipo de escola foi construido;
- que rotinas escolares cobre no trabalho diario;
- porque a gestao de horarios no ensino profissional exige mais do que uma grelha semanal;
- como a aplicacao ajuda a direcao, secretaria e professores no trabalho diario.

### Publico-alvo
- Diretores e administradores de escolas profissionais.
- Coordenadores pedagogicos e coordenadores de curso.
- Secretarias e equipas responsaveis por horarios.
- Professores que registam aulas, sumarios e disponibilidade.
- Escolas portuguesas com cursos profissionais, UFCDs, modulos e carga horaria variavel.

### Problema a resolver
Muitas escolas gerem horarios, faltas, substituicoes, sumarios e progresso curricular em ficheiros separados. No ensino profissional, isto cria um problema adicional: nao basta saber que uma disciplina aparece no horario; e necessario saber que horas de cada UFCD/modulo ja foram dadas, que aulas ficaram por compensar e como ajustar o futuro sem apagar o historico operacional.

### Posicionamento
O Cronos e uma aplicacao para gerir horarios no ensino profissional portugues. Centraliza cursos, turmas, professores, salas, UFCDs/modulos, disponibilidade docente, horarios, sumarios, ocorrencias, substituicoes, fecho semanal e progresso curricular.

### Mensagem principal
> Horarios do ensino profissional, controlados do plano a aula dada.

Mensagem de apoio:
> O Cronos gera horarios por turma e professor, adapta alteracoes de ultima hora, regista sumarios e acompanha horas de UFCDs, modulos e cursos num unico lugar.

### Principios de copy
- Explicar capacidades e rotinas reais antes de usar linguagem aspiracional.
- Evitar frases vagas como "gestao fluida", "revolucao" ou "experiencia eficiente" sem contexto.
- Evitar o modelo "nao e X, e Y".
- Usar vocabulario escolar: horarios, turmas, professores, salas, sumarios, ocorrencias, substituicoes, UFCDs, modulos, horas dadas, horas por cumprir.
- Traduzir conceitos tecnicos para linguagem operacional.

### Estrutura da pagina
1. Header com navegacao curta, CTA de demonstracao e link "Entrar".
2. Hero explicito: Cronos como aplicacao de horarios para ensino profissional.
3. Faixa de areas principais: horarios, ocorrencias, sumarios/progresso e gerador.
4. Secao "O que o Cronos faz" com modulos funcionais concretos.
5. Secao de percurso: preparar, gerar, publicar, registar, ajustar e acompanhar.
6. Secao dedicada ao gerador de horarios, explicada sem termos tecnicos.
7. Secao narrativa da semana letiva, com preparacao, publicacao, imprevistos e fecho semanal.
8. Secao de valor por perfil: direcao, secretaria e professores.
9. Secao visual do produto.
10. Testemunhos.
11. Contacto e CTA para demonstracao.
12. Footer.

### Rotinas e capacidades obrigatorias a comunicar
- Painel da direcao.
- Gestao de horarios por turma e professor.
- Geracao de horarios completa e ajuste das proximas semanas com minimo de alteracoes.
- Propostas de horario, leitura do que muda e aprovacao antes de publicar.
- Criacao e gestao de ocorrencias.
- Faltas, furos, aulas dadas e substituicoes.
- Recomendacoes de substitutos elegiveis.
- Adaptacao do horario a ocorrencias e alteracoes de ultima hora.
- Sumarios e notas de aula.
- Fecho semanal por professor.
- Disponibilidade/preferencias dos professores.
- Acesso dos professores a horarios, sumarios, disponibilidade e progresso.
- Acompanhamento de progresso de UFCDs, modulos, disciplinas, turmas e cursos.
- Gestao de cursos profissionais, turmas, disciplinas, UFCDs/modulos.
- Gestao de professores, competencias, salas, capacidade e tipo de sala.
- Preparacao de calendario, pausas, feriados, grelha horaria, almoco e periodo letivo.
- Separacao entre horario planeado e execucao real.
- Historico e rastreabilidade das decisoes operacionais.

### Criterios de aceitacao
- A primeira dobra deve explicar que o Cronos gere horarios no ensino profissional portugues.
- O site deve ficar mais completo do que a V2, com mais contexto sobre produto.
- A pagina deve tornar visiveis rotinas reais da aplicacao, nao beneficios abstratos.
- A explicacao do gerador deve ser nao tecnica e orientada a valor escolar.
- O link "Entrar" deve continuar disponivel e apontar para `/login`.
- O CTA de demonstracao deve continuar presente no header, hero e contacto.
- O design deve manter as cores atuais: creme, castanho escuro e dourado.
- O CSS deve continuar isolado em classes `cronos-*`.
- A pagina deve ser responsiva sem sobreposicoes de texto.
- `npm run lint` e `npm run build` devem passar.

## WBS

### 1. Planeamento e documentacao
- Atualizar PRD/WBS oficial do marketing site para V3.
- Atualizar README de UX e README do frontend para mencionar V3.
- Atualizar guidelines de marca quando ainda referirem V2.

### 2. Arquitetura de conteudo
- Reestruturar navegacao para ancoras de produto.
- Reescrever hero com posicionamento explicito.
- Criar secoes adicionais para tornar a pagina mais completa.
- Separar conteudo em arrays de dados para facilitar manutencao.

### 3. Implementacao JSX
- Atualizar `frontend/src/pages/MarketingSite.jsx`.
- Rever `navItems`, service tiles, workflow, rotina semanal, perfis, testemunhos e contacto.
- Manter link "Entrar" para `/login`.
- Manter imagens existentes em `public/marketing/`.

### 4. Implementacao CSS
- Atualizar `frontend/src/pages/MarketingSite.css`.
- Criar estilos para novas secoes:
  - overview/product modules;
  - workflow detalhado;
  - gerador;
  - rotina semanal em formato narrativo;
  - roles/personas;
- Ajustar espacamento para uma pagina mais longa e escaneavel.
- Garantir responsividade desktop, tablet e mobile.

### 5. QA
- Executar `npm run lint`.
- Executar `npm run build`.
- Abrir homepage em browser local.
- Verificar desktop e mobile.
- Corrigir overflow, desalinhamentos ou texto cortado.

### 6. Entrega
- Reportar ficheiros alterados.
- Reportar comandos de validacao.
- Indicar que o rollback da pagina experimental ja foi mantido.
