export const homeHero = {
  title: 'Horários para o Ensino Profissional Português',
  body: 'Resolva imprevistos em menos de 1 minuto e adapte o horário antes que as horas por cumprir cheguem ao verão.',
  image: {
    webpSrc: '/marketing/product/hero-schedule.webp',
    fallbackSrc: '/marketing/product/hero-schedule.png',
    alt: 'Grelha de horários do Cronos aberta num computador.',
    width: 480,
    height: 600,
  },
}

export const problemStates = [
  { id: 'absence', label: 'Professor falta', detail: 'A aula prevista fica sem docente.' },
  { id: 'lesson', label: 'Aula fica por cumprir', detail: 'A ocorrência precisa de uma decisão.' },
  { id: 'debt', label: 'Dívida acumula', detail: 'As horas por cumprir deixam de estar visíveis.' },
  { id: 'calendar', label: 'Calendário prolonga-se', detail: 'A escola só descobre o problema no final do ano.' },
]

export const minuteWorkflow = [
  { id: 'occurrence-created', title: 'Registar a falta', text: 'Crie a ocorrência a partir da aula certa e mantenha o contexto da decisão.' },
  { id: 'substitute-recommendations', title: 'Escolher um substituto elegível', text: 'Consulte docentes disponíveis e escolha uma opção compatível com a aula.' },
  { id: 'substitution-confirmed', title: 'Confirmar a decisão', text: 'Confirme a substituição e atualize o saldo de horas no mesmo instante.' },
]

export const adaptiveStates = [
  { id: 'protected-past', title: 'Passado protegido', text: 'O que já aconteceu e os blocos protegidos não são alterados.', icon: 'check' },
  { id: 'recalculated-future', title: 'Futuro recalculado', text: 'O Cronos reorganiza apenas os blocos futuros editáveis.', icon: 'calendar' },
  { id: 'school-approval', title: 'A escola aprova', text: 'A escola revê a proposta e confirma as alterações antes de publicar.', icon: 'school' },
]

export const people = {
  primary: { id: 'direction', title: 'Direção', text: 'Acompanhe a escola com uma visão comum sobre horários, ocorrências e horas por cumprir', image: { webpSrc: '/marketing/direcao-role.webp', fallbackSrc: '/marketing/direcao-role.png', alt: 'Responsável de direção numa escola', width: 500, height: 334 } },
  secondary: [
    { id: 'coordination', title: 'Coordenação', text: 'Organize alterações e decisões com o contexto da aula', image: { webpSrc: '/marketing/secretaria-role.webp', fallbackSrc: '/marketing/secretaria-role.png', alt: 'Responsável de coordenação escolar', width: 500, height: 334 } },
    { id: 'teachers', title: 'Professores', text: 'Consulte o horário e registe o que aconteceu na sala', image: { webpSrc: '/marketing/professores-role.webp', fallbackSrc: '/marketing/professores-role.png', alt: 'Professor numa sala de aula', width: 500, height: 334 } },
  ],
}
