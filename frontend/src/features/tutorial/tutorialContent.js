export const TUTORIAL_VERSION = 3
const TUTORIAL_STORAGE_PREFIX = `cronos:tutorial:v${TUTORIAL_VERSION}`

export const TUTORIAL_STATUSES = Object.freeze([
  'NOT_STARTED',
  'IN_PROGRESS',
  'COMPLETED',
  'SKIPPED',
])

const TUTORIAL_PAGES = Object.freeze([
  'Subjects',
  'CourseDetails',
  'Members',
  'Rooms',
  'ClassSubjects',
  'MyAvailability',
  'Schedules',
  'Occurrences',
  'Timesheets',
])

export const TUTORIAL_ACTIONS = Object.freeze({
  UPDATE_SUBJECT: 'UPDATE_SUBJECT',
  UPDATE_CLASS: 'UPDATE_CLASS',
  UPDATE_MEMBER_COMPETENCIES: 'UPDATE_MEMBER_COMPETENCIES',
  UPDATE_ROOM: 'UPDATE_ROOM',
  UPDATE_CLASS_SUBJECT_TEACHER: 'UPDATE_CLASS_SUBJECT_TEACHER',
  UPDATE_AVAILABILITY: 'UPDATE_AVAILABILITY',
  GENERATE_SCHEDULE: 'GENERATE_SCHEDULE',
  APPROVE_SCHEDULE: 'APPROVE_SCHEDULE',
  CREATE_OCCURRENCE: 'CREATE_OCCURRENCE',
  DECIDE_SUBSTITUTION: 'DECIDE_SUBSTITUTION',
  APPROVE_RECOVERY: 'APPROVE_RECOVERY',
})

export const TUTORIAL_CHAPTERS = Object.freeze([
  Object.freeze({
    number: 1,
    title: 'Preparar a escola',
    introduction: 'A turma 10.º TIS prepara-se para começar as aulas. Vamos conhecer as peças que permitem organizar a sua semana.',
  }),
  Object.freeze({
    number: 2,
    title: 'Acompanhar a semana',
    introduction: 'Durante a semana, o professor de Programação faltou. Vamos acompanhar a resposta da escola e as horas que ficaram por lecionar.',
  }),
])

export const TUTORIAL_COPY = Object.freeze({
  ribbon: 'Ambiente de demonstração · os dados da escola não são alterados.',
  initialNote: 'Cada passo apresenta um exemplo preparado. Pode experimentar ou continuar sem preencher formulários. Ao mudar de passo ou recarregar, o exemplo é reposto.',
  persistenceFailure: 'Não foi possível guardar o progresso neste dispositivo. Pode continuar, mas a visita poderá recomeçar ao sair.',
  completion: 'Já conheceu as ferramentas que acompanham a preparação e a semana da escola. Pode regressar às suas tarefas e rever o guia quando precisar.',
  optionalAction: 'Pode experimentar',
  reviewLabel: (stepNumber) => `A rever o passo ${stepNumber}`,
  returnToCurrent: 'Voltar ao passo atual',
})

const STEP_DEFINITIONS = [
  {
    id: 'curriculum',
    chapter: 1,
    page: 'Subjects',
    activeNavItem: '/subjects',
    title: 'Disciplinas e módulos',
    description: 'A turma vai ter Programação. A disciplina organiza os conteúdos; os módulos indicam as horas previstas para cada parte.',
    instruction: 'Abra a edição da disciplina e consulte os módulos.',
    allowedActions: [TUTORIAL_ACTIONS.UPDATE_SUBJECT],
    target: 'edit-record-1',
    allowedTargets: ['edit-record-1'],
  },
  {
    id: 'courses_classes',
    chapter: 1,
    page: 'CourseDetails',
    activeNavItem: '/courses',
    title: 'Cursos e turmas',
    description: 'O 10.º TIS faz parte do curso de Informática. Cada turma reúne o ano de escolaridade, o período de formação e os alunos.',
    instruction: 'Consulte os dados da turma preparada.',
    allowedActions: [TUTORIAL_ACTIONS.UPDATE_CLASS],
    target: 'edit-class-1',
    allowedTargets: ['edit-class-1'],
  },
  {
    id: 'team',
    chapter: 1,
    page: 'Members',
    activeNavItem: '/members',
    title: 'Professores e competências',
    description: 'Agora conhecemos quem pode acompanhar a turma. As competências indicam as disciplinas que cada professor pode lecionar.',
    instruction: 'Abra um professor e consulte as suas competências.',
    allowedActions: [TUTORIAL_ACTIONS.UPDATE_MEMBER_COMPETENCIES],
    target: 'edit-member-1',
    allowedTargets: ['edit-member-1'],
  },
  {
    id: 'rooms',
    chapter: 1,
    page: 'Rooms',
    activeNavItem: '/rooms',
    title: 'Salas',
    description: 'A aula de Programação precisa de um laboratório com lugares suficientes. O tipo de sala e a lotação ajudam a encontrar espaços adequados.',
    instruction: 'Consulte o laboratório e a sua lotação.',
    allowedActions: [TUTORIAL_ACTIONS.UPDATE_ROOM],
    target: 'edit-record-1',
    allowedTargets: ['edit-record-1'],
  },
  {
    id: 'class_plan',
    chapter: 1,
    page: 'ClassSubjects',
    activeNavItem: '/courses',
    title: 'Plano de estudos da turma',
    description: 'A turma já tem um percurso. No plano de estudos, as disciplinas ficam associadas à turma e aos professores atribuídos.',
    instruction: 'Consulte uma disciplina e o professor associado.',
    allowedActions: [TUTORIAL_ACTIONS.UPDATE_CLASS_SUBJECT_TEACHER],
    target: 'class-subject-teacher',
    allowedTargets: ['class-subject-teacher'],
  },
  {
    id: 'availability',
    chapter: 1,
    page: 'MyAvailability',
    activeNavItem: '/my-availability',
    title: 'Disponibilidade docente',
    description: 'Antes de distribuir as aulas, conhecemos a disponibilidade dos professores. A grelha distingue preferências e períodos impossíveis.',
    instruction: 'Experimente marcar um período na grelha.',
    allowedActions: [TUTORIAL_ACTIONS.UPDATE_AVAILABILITY],
    target: 'availability-workspace',
    allowedTargets: ['availability-workspace'],
  },
  {
    id: 'schedule',
    chapter: 1,
    page: 'Schedules',
    activeNavItem: '/schedules',
    title: 'Horários',
    description: 'As peças estão reunidas. O Cronos pode preparar um rascunho, que pode ser revisto antes da aprovação e publicação.',
    instruction: 'Se quiser, gere o exemplo e consulte a proposta.',
    allowedActions: [TUTORIAL_ACTIONS.GENERATE_SCHEDULE, TUTORIAL_ACTIONS.APPROVE_SCHEDULE],
    target: 'generate-schedule',
    allowedTargets: ['generate-schedule', 'review-schedule-changes', 'approve-schedule'],
  },
  {
    id: 'occurrences',
    chapter: 2,
    page: 'Schedules',
    activeNavItem: '/schedules',
    title: 'Ocorrências',
    description: 'A aula de Programação não decorreu como previsto. O registo da ocorrência permite acompanhar o que aconteceu e a decisão seguinte.',
    instruction: 'Abra a aula e consulte “Criar Ocorrência”.',
    allowedActions: [TUTORIAL_ACTIONS.CREATE_OCCURRENCE],
    target: 'schedule-grid',
    allowedTargets: ['schedule-grid'],
  },
  {
    id: 'substitutions',
    chapter: 2,
    page: 'Occurrences',
    activeNavItem: '/absences',
    title: 'Substituições',
    description: 'Uma professora de Matemática aparece entre as opções. A substituição regista a alternativa escolhida; as horas de Programação continuam por lecionar.',
    instruction: 'Abra “Decidir” e consulte a opção “Substituída”.',
    allowedActions: [TUTORIAL_ACTIONS.DECIDE_SUBSTITUTION],
    target: 'decision-open',
    allowedTargets: ['decision-open'],
  },
  {
    id: 'weekly_close',
    chapter: 2,
    page: 'Timesheets',
    activeNavItem: '/timesheets',
    title: 'Fecho Semanal',
    description: 'A semana reúne aulas dadas, ocorrências e registos pendentes. Aqui acompanha os registos e o estado de submissão e aprovação semanal.',
    instruction: 'Selecione um professor e consulte a semana.',
    allowedActions: [],
    target: 'timesheets-workspace',
    allowedTargets: ['timesheets-workspace'],
  },
  {
    id: 'hour_debts',
    chapter: 2,
    page: 'Occurrences',
    activeNavItem: '/absences',
    tab: 'debts',
    title: 'Dívidas de Horas',
    description: 'Algumas horas previstas continuam por lecionar. Esta página reúne os valores associados a cada turma e disciplina.',
    instruction: 'Consulte o resumo de Programação.',
    allowedActions: [],
    target: 'occurrences-workspace',
    allowedTargets: ['occurrences-workspace'],
  },
  {
    id: 'recovery',
    chapter: 2,
    page: 'Schedules',
    activeNavItem: '/schedules',
    title: 'Recuperação de horas',
    description: 'A proposta reserva aulas futuras para parte das horas em falta. Compare o que fica agendado e o que ainda falta agendar.',
    instruction: 'Abra “Ver alterações” na proposta preparada.',
    allowedActions: [TUTORIAL_ACTIONS.APPROVE_RECOVERY],
    target: 'review-schedule-changes',
    allowedTargets: ['review-schedule-changes', 'approve-schedule'],
  },
  {
    id: 'history',
    chapter: 2,
    page: 'Occurrences',
    activeNavItem: '/absences',
    tab: 'historical',
    title: 'Histórico',
    description: 'A semana deixou decisões para consultar. O histórico conserva a ocorrência e a substituição, mesmo quando o horário recebe alterações futuras.',
    instruction: 'Consulte a data, a turma e a disciplina da substituição.',
    allowedActions: [],
    target: 'occurrences-workspace',
    allowedTargets: ['occurrences-workspace'],
  },
]

if (STEP_DEFINITIONS.some((step) => !TUTORIAL_PAGES.includes(step.page))) {
  throw new Error('Tutorial content references an unsupported application page.')
}

export const TUTORIAL_STEPS = Object.freeze(STEP_DEFINITIONS.map((step) => Object.freeze({
  ...step,
  allowedActions: Object.freeze([...step.allowedActions]),
})))

export function getTutorialStep(stepId) {
  return TUTORIAL_STEPS.find((step) => step.id === stepId) || null
}

export function getTutorialStepIndex(stepId) {
  return TUTORIAL_STEPS.findIndex((step) => step.id === stepId)
}

export function getTutorialStepNumber(stepId) {
  const index = getTutorialStepIndex(stepId)
  return index < 0 ? null : index + 1
}

export function getTutorialChapter(chapterNumber) {
  return TUTORIAL_CHAPTERS.find((chapter) => chapter.number === chapterNumber) || null
}

export function getNextTutorialStep(stepId) {
  const index = getTutorialStepIndex(stepId)
  return index >= 0 ? TUTORIAL_STEPS[index + 1] || null : null
}

export function getTutorialStorageKey(userId, organizationId) {
  if (userId == null || organizationId == null || userId === '' || organizationId === '') return null
  return `${TUTORIAL_STORAGE_PREFIX}:user:${userId}:org:${organizationId}`
}
