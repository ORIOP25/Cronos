export const workflowChapters = [
  { id: 'prepare', label: 'Preparar e gerar', title: 'O horário começa na rotina diária da escola', text: 'Defina cursos, turmas, UFCDs, salas, disponibilidades e calendário antes de gerar uma proposta.', points: ['Reúna as regras e os dados da escola num só lugar.', 'Gere uma proposta que a escola pode rever.', 'Mantenha a configuração ligada ao ano letivo.'], result: 'Uma base clara para começar o ano.' },
  { id: 'adapt', label: 'Publicar e adaptar', title: 'Quando o dia muda, o futuro é recalculado', text: 'O passado e os blocos protegidos ficam preservados. A escola revê a proposta antes de aprovar qualquer alteração futura.', points: ['Proteja o que já aconteceu.', 'Reorganize apenas o futuro editável.', 'Veja o efeito no calendário antes de publicar.'], result: 'Decisões explicadas antes de chegarem à comunidade.' },
  { id: 'finish', label: 'Acompanhar e recuperar', title: 'As horas por cumprir deixam de aparecer tarde demais', text: 'Acompanhe o progresso por turma, disciplina e UFCD para perceber cedo onde é preciso recuperar.', points: ['Veja horas dadas e horas por cumprir.', 'Relacione ocorrências com o progresso.', 'Saiba com antecedência quando o ano vai terminar.'], result: 'Um fim de ano acompanhado desde o início.' },
]

export const teacherWorkflowMoments = [
  {
    id: 'prepare',
    label: 'Preparar',
    title: 'A disponibilidade é definida pelo professor',
    text: 'Cada docente marca cada bloco da grelha como Preferencial, Neutro, Evitar ou Impossível.',
    points: ['Escolha o nível de cada bloco.', 'Altere apenas os blocos necessários.', 'Guarde a grelha quando estiver pronta.'],
    result: 'A disponibilidade entra no planeamento sem trocas de ficheiros.',
  },
  {
    id: 'teach',
    label: 'Lecionar',
    title: 'A aula começa no bloco certo',
    text: 'O professor consulta o horário ativo e abre o registo da aula correspondente.',
    points: ['Consulte alterações confirmadas.', 'Escreva o sumário e marque a aula como dada.', 'Sinalize uma ocorrência quando necessário.'],
    result: 'Cada registo mantém o contexto da aula planeada.',
  },
  {
    id: 'track',
    label: 'Acompanhar',
    title: 'O progresso fica visível durante o ano',
    text: 'Depois de completar os registos, o professor submete a semana e consulta as UFCDs das suas turmas.',
    points: ['Confirme os registos da semana.', 'Submeta a semana para revisão.', 'Consulte horas cumpridas e progresso.'],
    result: 'O trabalho da semana fica refletido no progresso das UFCDs.',
  },
]
