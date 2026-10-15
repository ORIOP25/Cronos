import { publicAsset } from '../../../utils/publicAsset'

export const homeHero = {
  title: 'Gestão de Horários para o Ensino Profissional',
  body: 'Cronos ajuda escolas profissionais a gerir horários, faltas e substituições.',
  image: {
    webpSrc: publicAsset('/marketing/product/hero-schedule.webp'),
    fallbackSrc: publicAsset('/marketing/product/hero-schedule.png'),
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
  primary: { id: 'direction', title: 'Direção', text: 'Acompanhe a escola com uma visão comum sobre horários, ocorrências e horas por cumprir', image: { webpSrc: publicAsset('/marketing/direcao-role.webp'), fallbackSrc: publicAsset('/marketing/direcao-role.png'), alt: 'Responsável de direção numa escola', width: 500, height: 334 } },
  secondary: [
    { id: 'coordination', title: 'Coordenação', text: 'Organize alterações e decisões com o contexto da aula', image: { webpSrc: publicAsset('/marketing/secretaria-role.webp'), fallbackSrc: publicAsset('/marketing/secretaria-role.png'), alt: 'Responsável de coordenação escolar', width: 500, height: 334 } },
    { id: 'teachers', title: 'Professores', text: 'Consulte o horário e registe o que aconteceu na sala', image: { webpSrc: publicAsset('/marketing/professores-role.webp'), fallbackSrc: publicAsset('/marketing/professores-role.png'), alt: 'Professor numa sala de aula', width: 500, height: 334 } },
  ],
}

export const teacherUncertainty = {
  eyebrow: 'Para os professores',
  title: 'O horário mudou. O professor soube?',
  body: 'Quando a informação fica espalhada entre mensagens e ficheiros, uma alteração cria dúvidas antes da aula seguinte.',
  versions: [
    { id: 'previous', label: 'Mensagem recebida', room: 'Sala 1.06', state: 'Versão anterior' },
    { id: 'active', label: 'Horário ativo', room: 'Sala 2.12', state: 'Atualizado' },
  ],
}

export const teacherScheduleHub = {
  title: 'O dia do professor começa no horário',
  body: 'O professor define a sua disponibilidade, consulta alterações confirmadas, regista cada aula e acompanha o progresso das UFCDs.',
  actions: [
    { id: 'preferences', title: 'Defina a disponibilidade', text: 'Marque cada bloco como Preferencial, Neutro, Evitar ou Impossível.' },
    { id: 'changes', title: 'Consulte alterações', text: 'Veja a versão ativa e saiba o que mudou.' },
    { id: 'lesson', title: 'Registe a aula', text: 'Escreva o sumário, sinalize ocorrências e submeta a semana.' },
    { id: 'progress', title: 'Acompanhe UFCDs', text: 'Consulte o progresso das turmas que leciona.' },
  ],
  blocks: [
    { id: 'programming', day: 1, row: 1, label: 'Programação', className: '11.º TGPSI' },
    { id: 'networks', day: 3, row: 2, label: 'Redes', className: '10.º TGPSI' },
    { id: 'systems', day: 2, row: 3, label: 'Sistemas', className: '11.º TGPSI' },
    { id: 'recovery', day: 4, row: 1, label: 'Programação', className: '10.º TGPSI' },
  ],
}
