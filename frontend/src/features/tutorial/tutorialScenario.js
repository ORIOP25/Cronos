export const TUTORIAL_VERSION = 2
export const TUTORIAL_STORAGE_PREFIX = `cronos:tutorial:v${TUTORIAL_VERSION}`

export const TUTORIAL_STATUSES = Object.freeze([
  'NOT_STARTED',
  'IN_PROGRESS',
  'COMPLETED',
  'SKIPPED',
])

const STEP_DEFINITIONS = [
  ['structure_overview', 1, 'Dashboard', 'observation', 'Visão geral da estrutura', 'Conheça a sequência de configuração que prepara uma escola para o primeiro horário.', 'continue', 'Continuar', false],
  ['subject_create', 1, 'Disciplinas', 'exercise', 'Criar disciplina', 'Guarde a disciplina preparada. Os dados pertencem apenas a esta demonstração.', 'save-subject', 'Guardar disciplina', true],
  ['module_add', 1, 'Disciplinas', 'exercise', 'Adicionar módulo', 'Adicione o módulo UFCD preparado com carga horária positiva.', 'add-module', 'Adicionar módulo', true],
  ['course_create', 1, 'Cursos', 'exercise', 'Criar curso', 'Guarde o curso profissional preparado para o cenário local.', 'save-course', 'Guardar curso', true],
  ['class_create', 1, 'Cursos', 'exercise', 'Criar turma', 'Guarde a turma preparada com ano curricular e lotação.', 'save-class', 'Guardar turma', true],
  ['teacher_add', 1, 'Equipa', 'exercise', 'Adicionar professor', 'Guarde o professor preparado no cenário de demonstração.', 'save-teacher', 'Guardar professor', true],
  ['teacher_competency', 1, 'Equipa', 'exercise', 'Registar competência', 'Associe a competência preparada à disciplina indicada.', 'save-competency', 'Guardar competência', true],
  ['room_add', 1, 'Salas', 'exercise', 'Adicionar sala', 'Guarde a sala preparada com tipologia e capacidade compatíveis.', 'save-room', 'Guardar sala', true],
  ['assignment_create', 1, 'Cursos', 'exercise', 'Associar disciplina à turma', 'Guarde a associação curricular compatível.', 'save-assignment', 'Guardar associação', true],
  ['availability_review', 1, 'Equipa', 'exercise', 'Rever disponibilidade', 'Confirme a matriz preparada. Apenas IMPOSSIBLE bloqueia um bloco.', 'confirm-availability', 'Confirmar disponibilidade', true],
  ['schedule_prepare', 1, 'Horários', 'exercise', 'Preparar exemplo', 'Prepare o horário estático. Nenhum solver ou pedido operacional é executado.', 'prepare-schedule', 'Preparar exemplo', true],
  ['schedule_review', 1, 'Horários', 'observation', 'Rever exemplo de horário', 'Observe o exemplo preparado antes da aprovação simulada.', 'continue', 'Continuar', false],
  ['schedule_approve', 1, 'Horários', 'exercise', 'Aprovar exemplo', 'Aprove o horário preparado para continuar a demonstração.', 'approve-schedule', 'Aprovar exemplo', true],
  ['chapter_transition', 1, 'Horários', 'transition', 'Resolver a primeira ocorrência', 'O horário está aprovado. Amanhã um professor falta e a turma precisa de uma resposta operacional.', 'resolve-occurrence', 'Resolver ocorrência', true],
  ['published_block_open', 2, 'Horários', 'exercise', 'Abrir bloco publicado', 'Abra o bloco publicado que terá uma ocorrência.', 'open-block', 'Abrir bloco', false],
  ['occurrence_create', 2, 'Horários', 'exercise', 'Criar ocorrência', 'Registe a falta no bloco aberto. Isto envia a situação para uma decisão operacional.', 'create-occurrence', 'Criar ocorrência', true],
  ['substitute_teacher_select', 2, 'Faltas', 'exercise', 'Selecionar professor', 'Selecione apenas o professor local indicado para a substituição.', 'select-teacher', 'Selecionar professor', true],
  ['substitute_subject_select', 2, 'Faltas', 'exercise', 'Selecionar disciplina', 'Selecione apenas a disciplina local indicada para a substituição.', 'select-subject', 'Selecionar disciplina', true],
  ['substitution_complete', 2, 'Faltas', 'exercise', 'Concluir substituição', 'Conclua a substituição preparada sem tocar em dados reais.', 'complete-substitution', 'Concluir substituição', true],
  ['debt_observe', 2, 'Fecho Semanal', 'observation', 'Observar dívida de horas', 'Veja a dívida original. O histórico permanece preservado.', 'continue', 'Continuar', false],
  ['repair_simulate', 2, 'Horários', 'exercise', 'Simular reparação', 'Simule uma reparação estática num horizonte futuro.', 'simulate-repair', 'Simular reparação', true],
  ['repair_compare', 2, 'Horários', 'observation', 'Comparar reparação', 'Compare a dívida original com a projeção da reparação.', 'continue', 'Continuar', false],
  ['history_verify', 2, 'Horários', 'exercise', 'Confirmar histórico', 'Confirme que o histórico da reparação permanece intacto.', 'confirm-history', 'Confirmar histórico', false],
  ['repair_approve', 2, 'Horários', 'exercise', 'Aprovar reparação', 'Aprove a reparação simulada e conclua o guia local.', 'approve-repair', 'Aprovar reparação', false],
]

const STEP_INSTRUCTIONS = Object.freeze({
  structure_overview: 'Veja as bases pela ordem apresentada. O horário só é fiável quando currículo, recursos e disponibilidade estão completos.',
  subject_create: 'Abra “Nova Disciplina”. Crie “Sistemas Embebidos” e guarde apenas os dados gerais da disciplina.',
  module_add: 'Edite a disciplina criada e adicione a UFCD 5412 com 25 horas antes de guardar.',
  course_create: 'Abra “Novo Curso”. Crie “Técnico de Eletrónica” e guarde os dados gerais do curso.',
  class_create: 'Edite o curso criado e configure a turma “10.º TE” com ano curricular e lotação.',
  teacher_add: 'Abra “Adicionar membro”. Crie o professor “Rui Almeida” sem configurar competências nesta etapa.',
  teacher_competency: 'Edite o professor criado e associe-lhe a disciplina que pode lecionar.',
  room_add: 'Abra “Nova Sala”. Crie “Laboratório 3”, escolha o tipo Laboratório e indique capacidade 24.',
  assignment_create: 'Use “Adicionar disciplina”. Associe uma disciplina disponível e escolha um professor elegível.',
  availability_review: 'Marque um bloco como indisponível e guarde. Restrições impossíveis impedem o motor de colocar aulas nesse período.',
  schedule_prepare: 'Selecione “Gerar Horário”. O Cronos valida as bases e cria um rascunho antes de publicar alterações.',
  schedule_review: 'Leia os indicadores e as diferenças do rascunho. Esta revisão evita publicar conflitos ou alterações inesperadas.',
  schedule_approve: 'Selecione “Aprovar” apenas depois de rever o impacto. A aprovação transforma o rascunho no horário ativo.',
  chapter_transition: 'Continue para acompanhar uma falta desde o bloco publicado até à reparação da dívida de horas.',
  published_block_open: 'Na grelha semanal, abra o bloco de Programação. A operação começa sempre no contexto da aula planeada.',
  occurrence_create: 'No registo da aula, selecione “Criar Ocorrência” e confirme. O horário planeado permanece no histórico.',
  substitute_teacher_select: 'Na ocorrência pendente, selecione “Decidir” para abrir a decisão operacional.',
  substitute_subject_select: 'Escolha “Substituída”. O Cronos apresenta apenas combinações elegíveis de professor e disciplina.',
  substitution_complete: 'Reveja o candidato recomendado, confirme a decisão e guarde. A escolha fica auditável no histórico.',
  debt_observe: 'Observe as horas planeadas e realizadas. Uma aula não dada cria dívida sem apagar o planeamento original.',
  repair_simulate: 'Selecione “Gerar novamente” e confirme. O rascunho de reparação procura recuperar horas futuras.',
  repair_compare: 'Compare dívida inicial, horas recuperadas e dívida restante antes de aceitar a reparação.',
  history_verify: 'Confirme que a ocorrência e o bloco original continuam visíveis. Reparar nunca deve reescrever o passado.',
  repair_approve: 'Aprove o rascunho de reparação. Só esta ação publica os novos blocos futuros.',
})

export const TUTORIAL_STEPS = Object.freeze(STEP_DEFINITIONS.map(([
  id,
  chapter,
  activeNavItem,
  kind,
  title,
  description,
  actionId,
  actionLabel,
  isSkippable,
], index) => Object.freeze({
  id,
  chapter,
  stepNumber: STEP_DEFINITIONS.slice(0, index + 1).filter((definition) => definition[1] === chapter).length,
  screen: getScreenForStep(id),
  activeNavItem: getNavPath(activeNavItem),
  activeNavLabel: activeNavItem,
  kind,
  title,
  description,
  instruction: STEP_INSTRUCTIONS[id],
  action: Object.freeze({ id: actionId, label: actionLabel }),
  target: getTargetForStep(id),
  completion: getCompletionForStep(id, kind),
  isSkippable,
})))

function getCompletionForStep(stepId, kind) {
  if (kind !== 'exercise' || stepId === 'history_verify') return 'panel'
  if (['published_block_open', 'substitute_teacher_select', 'substitute_subject_select'].includes(stepId)) return 'interaction'
  return 'mutation'
}

function getTargetForStep(stepId) {
  return {
    subject_create: 'new-subject',
    module_add: 'new-subject',
    course_create: 'new-course',
    class_create: 'new-course',
    teacher_add: 'new-member',
    teacher_competency: 'new-member',
    room_add: 'new-room',
    assignment_create: 'add-class-subject',
    availability_review: 'availability-workspace',
    schedule_prepare: 'generate-schedule',
    schedule_approve: 'approve-schedule',
    published_block_open: 'schedule-grid',
    occurrence_create: 'lesson-log-modal',
    substitute_teacher_select: 'decision-open',
    substitute_subject_select: 'decision-substitute',
    substitution_complete: 'occurrence-decision',
    repair_simulate: 'regenerate-schedule',
    repair_approve: 'approve-schedule',
  }[stepId] || null
}

function getScreenForStep(stepId) {
  if (stepId === 'structure_overview' || ['subject_create', 'module_add', 'course_create', 'class_create'].includes(stepId)) return 'curriculum'
  if (['teacher_add', 'teacher_competency', 'room_add'].includes(stepId)) return 'people-resources'
  if (stepId === 'assignment_create') return 'assignments'
  if (stepId === 'availability_review') return 'availability'
  if (['schedule_prepare', 'schedule_review', 'schedule_approve', 'chapter_transition'].includes(stepId)) return 'schedule'
  if (['published_block_open', 'occurrence_create', 'substitute_teacher_select', 'substitute_subject_select', 'substitution_complete'].includes(stepId)) return 'occurrence'
  if (stepId === 'debt_observe') return 'debt'
  return 'repair'
}

function getNavPath(label) {
  return {
    Dashboard: '/dashboard',
    Disciplinas: '/subjects',
    Cursos: '/courses',
    Equipa: '/members',
    Salas: '/rooms',
    Horários: '/schedules',
    Faltas: '/absences',
    'Fecho Semanal': '/timesheets',
  }[label]
}

const DEMO_GRID = Object.freeze([
  Object.freeze({ id: 'demo-slot-1', day: 'Seg', time: '08:30–09:20', subjectId: 'demo-subject-prog', subject: 'Programação', room: 'Lab 2', teacher: 'Prof. António Silva', className: '10.º TIS', status: 'APPROVED' }),
  Object.freeze({ id: 'demo-slot-2', day: 'Seg', time: '09:30–10:20', subjectId: 'demo-subject-redes', subject: 'Redes', room: 'Lab 2', teacher: 'Prof. António Silva', className: '10.º TIS', status: 'APPROVED' }),
  Object.freeze({ id: 'demo-slot-3', day: 'Ter', time: '10:30–11:20', subjectId: 'demo-subject-mat', subject: 'Matemática', room: 'Sala 101', teacher: 'Prof.ª Maria Santos', className: '11.º TGEI', status: 'APPROVED' }),
  Object.freeze({ id: 'demo-slot-4', day: 'Qua', time: '14:30–15:20', subjectId: 'demo-subject-design', subject: 'Design', room: 'Atelier', teacher: 'Prof.ª Ana Martins', className: '12.º TGPSI', status: 'APPROVED' }),
])

function createBaseScenario() {
  return {
    id: 'demo-cronos-school',
    startDate: '2025-09-15',
    hardEndDate: '2026-07-31',
    slotDuration: 50,
    breakDuration: 10,
    lunch: { start: '12:30', end: '14:30', minimumMinutes: 60 },
    courses: [
      { id: 'demo-course-technology', name: 'Técnico de Informática', code: 'TIS', active: true },
      { id: 'demo-course-management', name: 'Técnico de Gestão', code: 'TGEI', active: true },
    ],
    classes: [
      { id: 'demo-class-10a', name: '10.º TIS', courseId: 'demo-course-technology', gradeLevel: 10, size: 24, active: true },
      { id: 'demo-class-11b', name: '11.º TGEI', courseId: 'demo-course-management', gradeLevel: 11, size: 22, active: true },
      { id: 'demo-class-12c', name: '12.º TGPSI', courseId: 'demo-course-technology', gradeLevel: 12, size: 20, active: true },
    ],
    subjects: [
      { id: 'demo-subject-prog', name: 'Programação', roomType: 'LAB' },
      { id: 'demo-subject-mat', name: 'Matemática', roomType: 'NORMAL' },
      { id: 'demo-subject-redes', name: 'Redes', roomType: 'LAB' },
      { id: 'demo-subject-gestao', name: 'Gestão', roomType: 'NORMAL' },
      { id: 'demo-subject-design', name: 'Design', roomType: 'ART' },
    ],
    modules: [
      { id: 'demo-module-prog', subjectId: 'demo-subject-prog', name: 'UFCD 0782', requiredMinutes: 100 },
      { id: 'demo-module-mat', subjectId: 'demo-subject-mat', name: 'UFCD 0783', requiredMinutes: 100 },
      { id: 'demo-module-redes', subjectId: 'demo-subject-redes', name: 'UFCD 0790', requiredMinutes: 100 },
      { id: 'demo-module-gestao', subjectId: 'demo-subject-gestao', name: 'UFCD 0665', requiredMinutes: 100 },
      { id: 'demo-module-design', subjectId: 'demo-subject-design', name: 'UFCD 0132', requiredMinutes: 100 },
    ],
    teachers: [
      { id: 'demo-teacher-silva', name: 'Prof. António Silva', competencies: ['demo-subject-prog', 'demo-subject-redes'] },
      { id: 'demo-teacher-santos', name: 'Prof.ª Maria Santos', competencies: ['demo-subject-mat'] },
      { id: 'demo-teacher-costa', name: 'Prof. João Costa', competencies: ['demo-subject-gestao'] },
      { id: 'demo-teacher-martins', name: 'Prof.ª Ana Martins', competencies: ['demo-subject-design'] },
    ],
    rooms: [
      { id: 'demo-room-101', name: 'Sala 101', type: 'NORMAL', capacity: 30 },
      { id: 'demo-room-lab2', name: 'Lab 2', type: 'LAB', capacity: 26 },
      { id: 'demo-room-atelier', name: 'Atelier', type: 'ART', capacity: 24 },
    ],
    weeklyGrid: { days: ['Seg', 'Ter', 'Qua', 'Qui', 'Sex'], slots: ['08:30', '09:30', '10:30', '11:30', '14:30', '15:30'] },
    gridPreview: DEMO_GRID,
    approvedSchedule: { id: 'demo-approved-schedule', status: 'PREPARED', generationId: 'demo-generation-1', blocks: DEMO_GRID.length },
    associations: [{ id: 'demo-assignment-1', classId: 'demo-class-10a', subjectId: 'demo-subject-prog' }],
    availability: {
      status: 'NEUTRAL',
      matrix: [
        { teacher: 'Prof. António Silva', monday: 'AVAILABLE', tuesday: 'NEUTRAL', wednesday: 'AVAILABLE' },
        { teacher: 'Prof.ª Maria Santos', monday: 'NEUTRAL', tuesday: 'AVAILABLE', wednesday: 'AVAILABLE' },
      ],
    },
    occurrence: { id: 'demo-occurrence-1', date: '2025-09-16', blockId: 'demo-slot-1', reason: 'Falta justificada', status: 'PREPARED' },
    substitution: { teacherId: 'demo-teacher-costa', teacher: 'Prof. João Costa', subjectId: 'demo-subject-prog', subject: 'Programação', status: 'PREPARED' },
    debt: { originalHours: 2, projectedHours: 2, unit: 'horas', source: 'demo-occurrence-1' },
    repair: {
      futureDate: '2025-09-23',
      original: { hours: 2, historyId: 'demo-history-1' },
      proposed: { hours: 1, block: 'Ter 16:30–17:20' },
      history: [{ id: 'demo-history-1', event: 'Dívida criada', date: '2025-09-16', preserved: true }],
    },
    workflow: {
      subjectCreated: false,
      moduleAdded: false,
      courseCreated: false,
      classCreated: false,
      teacherAdded: false,
      competencySaved: false,
      roomAdded: false,
      assignmentCreated: false,
      availabilityConfirmed: false,
      schedulePrepared: false,
      scheduleReviewed: false,
      scheduleApproved: false,
      publishedBlockOpen: false,
      occurrenceCreated: false,
      substituteTeacherSelected: false,
      substituteSubjectSelected: false,
      substitutionCompleted: false,
      repairSimulated: false,
      repairCompared: false,
      repairApproved: false,
      historyPreserved: true,
      lastCheckpoint: null,
    },
  }
}

const WORKFLOW_KEYS = Object.freeze({
  subject_create: 'subjectCreated',
  module_add: 'moduleAdded',
  course_create: 'courseCreated',
  class_create: 'classCreated',
  teacher_add: 'teacherAdded',
  teacher_competency: 'competencySaved',
  room_add: 'roomAdded',
  assignment_create: 'assignmentCreated',
  availability_review: 'availabilityConfirmed',
  schedule_prepare: 'schedulePrepared',
  schedule_review: 'scheduleReviewed',
  schedule_approve: 'scheduleApproved',
  chapter_transition: 'publishedBlockOpen',
  published_block_open: 'publishedBlockOpen',
  occurrence_create: 'occurrenceCreated',
  substitute_teacher_select: 'substituteTeacherSelected',
  substitute_subject_select: 'substituteSubjectSelected',
  substitution_complete: 'substitutionCompleted',
  repair_simulate: 'repairSimulated',
  repair_compare: 'repairCompared',
  repair_approve: 'repairApproved',
})

const MAX_TUTORIAL_TEXT = 120

function boundedText(value, field) {
  if (value == null) return undefined
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  return normalized ? { [field]: normalized.slice(0, MAX_TUTORIAL_TEXT) } : null
}

function optionalBoundedText(value, field) {
  if (value == null || (typeof value === 'string' && !value.trim())) return undefined
  return boundedText(value, field)
}

function boundedNumber(value, field, { min = 0, max = 100000 } = {}) {
  if (value == null || value === '') return undefined
  const normalized = Number(value)
  return Number.isFinite(normalized) && normalized >= min && normalized <= max
    ? { [field]: normalized }
    : null
}

function mergeChanges(...parts) {
  const result = {}
  for (const part of parts) {
    if (part === null) return null
    if (part) Object.assign(result, part)
  }
  return result
}

export function normalizeTutorialChanges(stepId, changes = {}) {
  if (!changes || typeof changes !== 'object' || Array.isArray(changes)) return null
  switch (stepId) {
    case 'subject_create':
      return mergeChanges(boundedText(changes.name, 'name'), boundedText(changes.required_room_type, 'roomType'))
    case 'module_add': {
      const module = Array.isArray(changes.modules) ? changes.modules[0] : changes
      if (!module || typeof module !== 'object' || Array.isArray(module)) return null
      return mergeChanges(
        boundedText(module.name, 'moduleName'),
        boundedText(module.code, 'moduleCode'),
        boundedNumber(module.hours_total, 'moduleHours', { min: 1, max: 200 }),
        boundedNumber(module.requiredMinutes, 'requiredMinutes', { min: 1, max: 10000 }),
      )
    }
    case 'course_create':
      return mergeChanges(boundedText(changes.name, 'name'), boundedText(changes.abbreviation, 'code'))
    case 'class_create':
      return mergeChanges(
        boundedText(changes.name, 'name'),
        boundedNumber(changes.grade_level ?? changes.gradeLevel, 'gradeLevel', { min: 1, max: 20 }),
        boundedNumber(changes.size, 'size', { min: 1, max: 1000 }),
      )
    case 'teacher_add':
      return mergeChanges(
        boundedText(changes.name ?? changes.organization_display_name, 'name'),
        optionalBoundedText(changes.email, 'email'),
      )
    case 'teacher_competency': {
      const ids = changes.subject_ids
      if (ids != null && (!Array.isArray(ids) || ids.length > 8 || ids.some((id) => !Number.isInteger(Number(id))))) return null
      const subjectId = changes.subject_id ?? (Array.isArray(ids) ? ids[0] : undefined)
      return subjectId == null ? {} : boundedNumber(subjectId, 'subjectId', { min: 1, max: 1000000 })
    }
    case 'room_add':
      return mergeChanges(
        boundedText(changes.name, 'name'),
        boundedText(changes.type, 'type'),
        boundedNumber(changes.capacity, 'capacity', { min: 1, max: 10000 }),
      )
    case 'assignment_create':
      return mergeChanges(
        boundedNumber(changes.class_id ?? changes.classId, 'classId', { min: 1, max: 1000000 }),
        boundedNumber(changes.subject_id ?? changes.subjectId, 'subjectId', { min: 1, max: 1000000 }),
        boundedNumber(changes.teacher_id ?? changes.teacherId, 'teacherId', { min: 1, max: 1000000 }),
      )
    case 'availability_review':
      return mergeChanges(
        boundedText(changes.status, 'status'),
        boundedNumber(changes.score, 'score', { min: -1, max: 2 }),
      )
    default:
      return {}
  }
}

function normalizeBodyForStep(stepId, body) {
  if (!body || typeof body !== 'object' || (Array.isArray(body) && stepId !== 'availability_review')) return null
  if (stepId === 'module_add') {
    if (!Array.isArray(body.modules) || body.modules.length === 0) return null
    return normalizeTutorialChanges(stepId, { modules: body.modules })
  }
  if (stepId === 'class_create' && Array.isArray(body.classes_config)) {
    if (body.classes_config.length === 0) return null
    return normalizeTutorialChanges(stepId, body.classes_config[0])
  }
  if (stepId === 'availability_review') {
    if (!Array.isArray(body.availability) && !Array.isArray(body)) return normalizeTutorialChanges(stepId, body)
    const entries = Array.isArray(body) ? body : body.availability
    if (entries.some((entry) => !entry || typeof entry !== 'object' || Array.isArray(entry))) return null
    return { status: 'NEUTRAL' }
  }
  if (stepId === 'teacher_competency') return normalizeTutorialChanges(stepId, body)
  return normalizeTutorialChanges(stepId, body)
}

export const TUTORIAL_MUTATION_RULES = Object.freeze([
  { stepId: 'subject_create', method: 'post', pathMatcher: /^\/subjects\/$/, expectedActionId: 'save-subject' },
  { stepId: 'module_add', method: 'patch', pathMatcher: /^\/subjects\/\d+$/, expectedActionId: 'add-module' },
  { stepId: 'module_add', method: 'post', pathMatcher: /^\/subjects\/$/, expectedActionId: 'add-module' },
  { stepId: 'course_create', method: 'post', pathMatcher: /^\/courses\/$/, expectedActionId: 'save-course' },
  { stepId: 'class_create', method: 'post', pathMatcher: /^\/courses\/$/, expectedActionId: 'save-class' },
  { stepId: 'class_create', method: 'post', pathMatcher: /^\/courses\/\d+\/classes$/, expectedActionId: 'save-class' },
  { stepId: 'teacher_add', method: 'post', pathMatcher: /^\/members$/, expectedActionId: 'save-teacher' },
  { stepId: 'teacher_competency', method: 'patch', pathMatcher: /^\/members\/\d+$/, expectedActionId: 'save-competency' },
  { stepId: 'teacher_competency', method: 'post', pathMatcher: /^\/members$/, expectedActionId: 'save-competency' },
  { stepId: 'room_add', method: 'post', pathMatcher: /^\/rooms\/$/, expectedActionId: 'save-room' },
  { stepId: 'assignment_create', method: 'post', pathMatcher: /^\/classes\/\d+\/subjects$/, expectedActionId: 'save-assignment' },
  { stepId: 'availability_review', method: 'put', pathMatcher: /^\/teachers\/me\/availability$/, expectedActionId: 'confirm-availability' },
  { stepId: 'schedule_prepare', method: 'post', pathMatcher: /^\/scheduler\/generate$/, expectedActionId: 'prepare-schedule' },
  { stepId: 'schedule_approve', method: 'post', pathMatcher: /^\/scheduler\/drafts\/\d+\/approve$/, expectedActionId: 'approve-schedule' },
  { stepId: 'occurrence_create', method: 'patch', pathMatcher: /^\/occurrences\/\d+$/, expectedActionId: 'create-occurrence' },
  { stepId: 'substitution_complete', method: 'patch', pathMatcher: /^\/occurrences\/\d+$/, expectedActionId: 'complete-substitution' },
  { stepId: 'repair_simulate', method: 'post', pathMatcher: /^\/scheduler\/generate$/, expectedActionId: 'simulate-repair' },
  { stepId: 'repair_approve', method: 'post', pathMatcher: /^\/scheduler\/drafts\/\d+\/approve$/, expectedActionId: 'approve-repair' },
].map((rule) => Object.freeze(rule)))

export function matchTutorialMutations({ method, path, body }) {
  return TUTORIAL_MUTATION_RULES
    .filter((candidate) => candidate.method === method && candidate.pathMatcher.test(path))
    .map((rule) => ({ ...rule, changes: normalizeBodyForStep(rule.stepId, body) }))
    .filter(({ changes }) => changes !== null)
}

export function matchTutorialMutation({ stepId, method, path, body }) {
  return matchTutorialMutations({ method, path, body })
    .find((candidate) => !stepId || candidate.stepId === stepId) || null
}

export function createTutorialScenario({ stepId, status, values = {}, skippedStepIds = [] } = {}) {
  const scenario = createBaseScenario()
  const currentIndex = Math.max(0, TUTORIAL_STEPS.findIndex((step) => step.id === stepId))
  const applied = new Set([
    ...TUTORIAL_STEPS.slice(0, currentIndex).map((step) => step.id),
    ...(status === 'COMPLETED' && stepId ? [stepId] : []),
    ...Object.keys(values).filter((id) => values[id]?.completed === true),
    ...skippedStepIds,
  ])

  for (const [id, workflowKey] of Object.entries(WORKFLOW_KEYS)) {
    if (applied.has(id)) scenario.workflow[workflowKey] = true
  }

  const subjectChanges = values.subject_create
  if (subjectChanges?.name) scenario.subjects[0] = { ...scenario.subjects[0], name: subjectChanges.name }
  if (subjectChanges?.roomType) scenario.subjects[0] = { ...scenario.subjects[0], roomType: subjectChanges.roomType.toUpperCase() }

  const moduleChanges = values.module_add
  if (moduleChanges?.moduleName || moduleChanges?.moduleHours || moduleChanges?.requiredMinutes) {
    scenario.modules[0] = {
      ...scenario.modules[0],
      ...(moduleChanges.moduleName ? { name: moduleChanges.moduleName } : {}),
      ...(moduleChanges.moduleHours ? { requiredMinutes: moduleChanges.moduleHours * 60 } : {}),
      ...(moduleChanges.requiredMinutes ? { requiredMinutes: moduleChanges.requiredMinutes } : {}),
    }
  }

  const courseChanges = values.course_create
  if (courseChanges?.name || courseChanges?.code) {
    scenario.courses[0] = { ...scenario.courses[0], ...(courseChanges.name ? { name: courseChanges.name } : {}), ...(courseChanges.code ? { code: courseChanges.code } : {}) }
  }
  const classChanges = values.class_create
  if (classChanges?.name || classChanges?.gradeLevel || classChanges?.size) {
    scenario.classes[0] = { ...scenario.classes[0], ...classChanges }
  }
  const teacherChanges = values.teacher_add
  if (teacherChanges?.name || teacherChanges?.email) {
    scenario.teachers[0] = { ...scenario.teachers[0], ...(teacherChanges.name ? { name: teacherChanges.name } : {}), ...(teacherChanges.email ? { email: teacherChanges.email } : {}) }
  }
  const competencyChanges = values.teacher_competency
  if (competencyChanges?.subjectId) {
    const subject = scenario.subjects[competencyChanges.subjectId - 1] || scenario.subjects[0]
    scenario.teachers[0] = { ...scenario.teachers[0], competencies: [subject.id] }
  }
  const roomChanges = values.room_add
  if (roomChanges?.name || roomChanges?.type || roomChanges?.capacity) {
    scenario.rooms[0] = { ...scenario.rooms[0], ...(roomChanges.name ? { name: roomChanges.name } : {}), ...(roomChanges.type ? { type: roomChanges.type.toUpperCase() } : {}), ...(roomChanges.capacity ? { capacity: roomChanges.capacity } : {}) }
  }
  const assignmentChanges = values.assignment_create
  if (assignmentChanges?.classId || assignmentChanges?.subjectId || assignmentChanges?.teacherId) {
    scenario.associations[0] = {
      ...scenario.associations[0],
      ...(assignmentChanges.classId ? { classId: scenario.classes[assignmentChanges.classId - 1]?.id || scenario.classes[0].id } : {}),
      ...(assignmentChanges.subjectId ? { subjectId: scenario.subjects[assignmentChanges.subjectId - 1]?.id || scenario.subjects[0].id } : {}),
      ...(assignmentChanges.teacherId ? { teacherId: scenario.teachers[assignmentChanges.teacherId - 1]?.id || scenario.teachers[0].id } : {}),
    }
  }
  if (values.availability_review?.status) scenario.availability.status = values.availability_review.status.toUpperCase()

  scenario.workflow.lastCheckpoint = stepId || TUTORIAL_STEPS[0].id
  if (scenario.workflow.schedulePrepared) scenario.workflow.scheduleReviewed = applied.has('schedule_review') || applied.has('schedule_approve')
  if (scenario.workflow.scheduleReviewed) scenario.workflow.scheduleApproved = applied.has('schedule_approve') || applied.has('chapter_transition')
  if (scenario.workflow.scheduleApproved) scenario.workflow.publishedBlockOpen = applied.has('published_block_open') || applied.has('occurrence_create')
  if (scenario.workflow.publishedBlockOpen) scenario.workflow.occurrenceCreated = applied.has('occurrence_create') || applied.has('substitute_teacher_select')
  if (scenario.workflow.occurrenceCreated) scenario.workflow.substituteTeacherSelected = applied.has('substitute_teacher_select') || applied.has('substitute_subject_select')
  if (scenario.workflow.substituteTeacherSelected) scenario.workflow.substituteSubjectSelected = applied.has('substitute_subject_select') || applied.has('substitution_complete')
  if (scenario.workflow.substitutionCompleted) scenario.debt.projectedHours = scenario.debt.originalHours
  if (scenario.workflow.repairSimulated) {
    scenario.debt.projectedHours = 1
    scenario.repair.proposed.hours = 1
  }
  return scenario
}

export function tutorialScenarioInvariants(scenario) {
  const allDemoIds = [
    ...scenario.courses,
    ...scenario.classes,
    ...scenario.subjects,
    ...scenario.modules,
    ...scenario.teachers,
    ...scenario.rooms,
  ].map((item) => item.id)
  return {
    courses: scenario.courses.length === 2,
    classes: scenario.classes.length === 3,
    subjects: scenario.subjects.length === 5,
    modules: scenario.modules.length === 5 && scenario.modules.every((module) => module.requiredMinutes > 0),
    teachers: scenario.teachers.length === 4,
    rooms: scenario.rooms.length === 3,
    demoIds: allDemoIds.every((id) => id.startsWith('demo-')),
    weeklyGrid: scenario.weeklyGrid.days.length === 5 && scenario.weeklyGrid.slots.length > 0,
    historyPreserved: scenario.workflow.historyPreserved === true && scenario.repair.history.every((event) => event.preserved),
  }
}

export function getTutorialStep(stepId) {
  return TUTORIAL_STEPS.find((step) => step.id === stepId) || null
}

export function getTutorialStepIndex(stepId) {
  return TUTORIAL_STEPS.findIndex((step) => step.id === stepId)
}

export function getNextTutorialStep(stepId) {
  const index = getTutorialStepIndex(stepId)
  return index >= 0 ? TUTORIAL_STEPS[index + 1] || null : null
}

export function getTutorialStorageKey(clerkUserId, clerkOrgId) {
  const user = clerkUserId || 'anonymous'
  const org = clerkOrgId || 'personal'
  return `${TUTORIAL_STORAGE_PREFIX}:user:${user}:org:${org}`
}
