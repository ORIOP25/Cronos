import { validateClassDraft } from '../../utils/classDraft'
import { normalizeModule } from '../../utils/subjectModules'
import { ROOM_TYPES } from '../../utils/presentation'
import {
  TUTORIAL_ACTIONS,
  TUTORIAL_STEPS,
  getTutorialStep,
} from './tutorialContent'

const DEMO_WEEK_START = '2025-09-15'
const DEMO_REFERENCE_DATE = '2025-09-20T12:00:00Z'
const DEMO_HARD_END_DATE = '2026-07-31'
const SLOT_DURATION_MINUTES = 60

export class TutorialScenarioError extends Error {
  constructor(message, { code = 'TUTORIAL_SCENARIO_INVALID', status = 400 } = {}) {
    super(message)
    this.name = 'TutorialScenarioError'
    this.code = code
    this.status = status
  }
}

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function numericId(collection, internalId) {
  const index = collection.findIndex((item) => item.id === internalId)
  return index < 0 ? null : index + 1
}

function internalId(collection, value) {
  const numeric = Number(value)
  if (!Number.isInteger(numeric) || numeric < 1 || numeric > collection.length) return null
  return collection[numeric - 1].id
}

function requireEntity(collection, value, label) {
  const internal = typeof value === 'string' && value.startsWith('demo-') ? value : internalId(collection, value)
  const entity = collection.find((item) => item.id === internal)
  if (!entity) throw new TutorialScenarioError(`${label} não existe no exemplo.`, { code: 'DEMO_ENTITY_NOT_FOUND', status: 404 })
  return entity
}

function createTimeslots() {
  const starts = ['08:00', '10:00', '14:00', '16:00']
  return Array.from({ length: 5 }, (_, day) => starts.map((start, index) => ({
    id: `demo-timeslot-${day * starts.length + index + 1}`,
    dayOfWeek: day,
    startTime: start,
    endTime: `${String(Number(start.slice(0, 2)) + 1).padStart(2, '0')}:${start.slice(3)}`,
  }))).flat()
}

function createBlocks(timeslots) {
  return [
    {
      id: 'demo-block-programming-1',
      date: '2025-09-15',
      timeslotId: timeslots[0].id,
      classId: 'demo-class-10-tis',
      subjectId: 'demo-subject-programming',
      teacherId: 'demo-teacher-programming',
      roomId: 'demo-room-lab',
      lessonLogStatus: 'PENDING',
    },
    {
      id: 'demo-block-programming-2',
      date: '2025-09-16',
      timeslotId: timeslots[4].id,
      classId: 'demo-class-10-tis',
      subjectId: 'demo-subject-programming',
      teacherId: 'demo-teacher-programming',
      roomId: 'demo-room-lab',
      lessonLogStatus: 'COMPLETED',
    },
    {
      id: 'demo-block-recovery-1',
      date: '2025-09-23',
      timeslotId: timeslots[4].id,
      classId: 'demo-class-10-tis',
      subjectId: 'demo-subject-programming',
      teacherId: 'demo-teacher-programming',
      roomId: 'demo-room-lab',
      lessonLogStatus: 'PENDING',
      isRecovery: true,
    },
    {
      id: 'demo-block-mathematics-1',
      date: '2025-09-17',
      timeslotId: timeslots[8].id,
      classId: 'demo-class-10-tis',
      subjectId: 'demo-subject-mathematics',
      teacherId: 'demo-teacher-mathematics',
      roomId: 'demo-room-classroom',
      lessonLogStatus: 'COMPLETED',
    },
  ]
}

function createBaseScenario(stepId) {
  const timeslots = createTimeslots()
  const blocks = createBlocks(timeslots)
  const scenario = {
    stepId,
    weekStart: DEMO_WEEK_START,
    referenceDate: DEMO_REFERENCE_DATE,
    hardEndDate: DEMO_HARD_END_DATE,
    slotDurationMinutes: SLOT_DURATION_MINUTES,
    timeslots,
    courses: [
      { id: 'demo-course-informatics', name: 'Curso de Informática', code: 'TIS', active: true },
    ],
    classes: [
      {
        id: 'demo-class-10-tis',
        name: '10.º TIS',
        courseId: 'demo-course-informatics',
        gradeLevel: 10,
        size: 24,
        startYear: 2025,
        endYear: 2028,
        active: true,
      },
    ],
    subjects: [
      { id: 'demo-subject-programming', name: 'Programação', roomType: 'LAB' },
      { id: 'demo-subject-mathematics', name: 'Matemática', roomType: 'NORMAL' },
    ],
    modules: [
      { id: 'demo-module-programming-1', subjectId: 'demo-subject-programming', name: 'Fundamentos de programação', code: 'UFCD-PROG-1', requiredMinutes: 120 },
      { id: 'demo-module-programming-2', subjectId: 'demo-subject-programming', name: 'Estruturas de dados', code: 'UFCD-PROG-2', requiredMinutes: 180 },
      { id: 'demo-module-mathematics-1', subjectId: 'demo-subject-mathematics', name: 'Matemática aplicada', code: 'UFCD-MAT-1', requiredMinutes: 120 },
    ],
    teachers: [
      { id: 'demo-teacher-programming', name: 'Prof. António Silva', email: 'antonio.silva@demo.cronos.pt', competencies: ['demo-subject-programming'] },
      { id: 'demo-teacher-mathematics', name: 'Prof.ª Maria Santos', email: 'maria.santos@demo.cronos.pt', competencies: ['demo-subject-mathematics'] },
    ],
    rooms: [
      { id: 'demo-room-lab', name: 'Laboratório de Programação', type: 'LAB', capacity: 28 },
      { id: 'demo-room-classroom', name: 'Sala 101', type: 'NORMAL', capacity: 30 },
    ],
    classSubjects: [
      { id: 'demo-class-subject-programming', classId: 'demo-class-10-tis', subjectId: 'demo-subject-programming', teacherId: 'demo-teacher-programming' },
      { id: 'demo-class-subject-mathematics', classId: 'demo-class-10-tis', subjectId: 'demo-subject-mathematics', teacherId: 'demo-teacher-mathematics' },
    ],
    availability: {
      teacherId: 'demo-teacher-programming',
      slots: timeslots.map((slot) => ({ timeslotId: slot.id, score: 1 })),
    },
    blocks,
    occurrences: [],
    draft: null,
    publishedRecoveryBlockIds: [],
    jobs: {},
    history: [
      {
        id: 'demo-history-substitution',
        occurrenceId: 'demo-occurrence-history',
        date: '2025-09-15',
        preserved: true,
      },
    ],
    debt: {
      hoursOwedMinutes: 120,
      proposedRecoveryMinutes: 60,
      remainingMinutes: 60,
      asOfDate: '2025-09-20',
    },
  }

  if (stepId === 'substitutions') scenario.occurrences = [createOpenOccurrence('demo-occurrence-open', blocks[0])]
  if (stepId === 'weekly_close') scenario.occurrences = [createOpenOccurrence('demo-occurrence-open', blocks[0])]
  if (stepId === 'hour_debts') scenario.occurrences = [
    createGapOccurrence('demo-occurrence-gap-1', blocks[0]),
    createGapOccurrence('demo-occurrence-gap-2', blocks[1]),
  ]
  if (stepId === 'history') scenario.occurrences = [createHistoryOccurrence(blocks[0])]
  if (stepId === 'recovery') {
    scenario.occurrences = [createHistoryOccurrence(blocks[0])]
    scenario.draft = createRecoveryDraft()
  }
  return scenario
}

function createOpenOccurrence(id, block) {
  return {
    id,
    blockId: block.id,
    date: block.date,
    status: 'GAP',
    operationalState: 'OPEN_PENDING',
    reason: 'Falta justificada',
    substituteTeacherId: null,
    substituteSubjectId: null,
    version: 1,
    lessonLogSummary: '',
    lessonLogNotes: '',
  }
}

function createGapOccurrence(id, block) {
  return { ...createOpenOccurrence(id, block), operationalState: 'DECIDED_GAP' }
}

function createHistoryOccurrence(block) {
  return {
    ...createOpenOccurrence('demo-occurrence-history', block),
    status: 'SUBSTITUTED',
    operationalState: 'DECIDED_SUBSTITUTED',
    substituteTeacherId: 'demo-teacher-mathematics',
    substituteSubjectId: 'demo-subject-mathematics',
    decidedAt: '2025-09-15T11:00:00Z',
  }
}

function createRecoveryDraft() {
  return {
    id: 'demo-draft-recovery',
    kind: 'RECOVERY',
    strategy: 'ADAPTIVE_REPAIR',
    triggerType: 'EXPLICIT_DEBT',
    resultCategory: 'PARTIAL_RECOVERY',
    debtHoursBefore: 2,
    debtHoursRecovered: 1,
    debtHoursRemaining: 1,
    changedBlocks: 1,
    affectedClasses: 1,
    affectedTeachers: 1,
    affectedDays: 1,
    disruptionScore: 2,
    projectedCompletionDate: '2025-09-23',
    mainBlockerMessage: 'Uma hora continua por agendar.',
    recommendedActions: ['Agendar a hora restante numa semana futura.'],
    warnings: [],
    canApprove: true,
  }
}

function createScheduleDraft() {
  return {
    id: 'demo-draft-schedule',
    kind: 'SCHEDULE',
    strategy: 'COMPLETE_GENERATION',
    triggerType: 'FIRST_GENERATION',
    resultCategory: 'COMPLETE_SUCCESS',
    debtHoursBefore: 0,
    debtHoursRecovered: 0,
    debtHoursRemaining: 0,
    changedBlocks: 4,
    affectedClasses: 1,
    affectedTeachers: 2,
    affectedDays: 3,
    disruptionScore: 4,
    projectedCompletionDate: '2025-09-19',
    mainBlockerMessage: null,
    recommendedActions: [],
    warnings: [],
    canApprove: true,
  }
}

function ensureAction(scenario, actionType) {
  const step = getTutorialStep(scenario.stepId)
  if (!step?.allowedActions.includes(actionType)) {
    throw new TutorialScenarioError(`A ação ${actionType} não está disponível neste passo.`, { code: 'DEMO_ACTION_NOT_ALLOWED', status: 403 })
  }
}

function normalizeSubjectModules(modules) {
  if (!Array.isArray(modules)) throw new TutorialScenarioError('Os módulos devem ser um array.', { code: 'INVALID_MODULES' })
  const normalized = modules.map(normalizeModule)
  if (normalized.some((module) => !module)) throw new TutorialScenarioError('Cada módulo precisa de nome e horas positivas.', { code: 'INVALID_MODULES' })
  return normalized.map((module, index) => ({
    id: `demo-module-edited-${index + 1}`,
    name: module.name,
    code: module.code,
    requiredMinutes: module.hours_total * 60,
  }))
}

function applySubjectUpdate(next, action) {
  const subject = requireEntity(next.subjects, action.subjectId ?? action.id, 'A disciplina')
  const data = action.data ?? action
  if (data.name != null) {
    const name = String(data.name).trim()
    if (!name) throw new TutorialScenarioError('O nome da disciplina é obrigatório.')
    subject.name = name
  }
  if (data.required_room_type != null || data.roomType != null) {
    const type = String(data.required_room_type ?? data.roomType).toUpperCase()
    if (!ROOM_TYPES[type.toLowerCase()] && !Object.keys(ROOM_TYPES).some((key) => key.toUpperCase() === type)) {
      throw new TutorialScenarioError('O tipo de sala da disciplina é inválido.')
    }
    subject.roomType = type
  }
  if (data.modules != null) {
    const modules = normalizeSubjectModules(data.modules)
    next.modules = next.modules.filter((module) => module.subjectId !== subject.id)
    next.modules.push(...modules.map((module) => ({ ...module, subjectId: subject.id })))
  }
}

function applyClassUpdate(next, action) {
  const course = requireEntity(next.courses, action.courseId, 'O curso')
  const cls = requireEntity(next.classes, action.classId, 'A turma')
  if (cls.courseId !== course.id) throw new TutorialScenarioError('A turma não pertence ao curso indicado.', { code: 'CLASS_COURSE_MISMATCH', status: 400 })
  const existing = next.classes.filter((item) => item.id !== cls.id && item.courseId === course.id)
  const validation = validateClassDraft(action.data ?? action, existing.map((item) => ({ name: item.name })))
  if (validation.error) throw new TutorialScenarioError(validation.error, { code: 'INVALID_CLASS' })
  Object.assign(cls, {
    name: validation.value.name,
    size: validation.value.size,
    gradeLevel: validation.value.grade_level,
    startYear: validation.value.start_year,
    endYear: validation.value.end_year,
  })
}

function applyMemberUpdate(next, action) {
  const teacher = requireEntity(next.teachers, action.memberId ?? action.id, 'O professor')
  const data = action.data ?? action
  if (!Array.isArray(data.subject_ids ?? data.subjectIds)) throw new TutorialScenarioError('As competências devem ser um array.')
  const subjectIds = data.subject_ids ?? data.subjectIds
  teacher.competencies = subjectIds.map((id) => internalId(next.subjects, id) ?? id)
  if (teacher.competencies.some((id) => !next.subjects.some((subject) => subject.id === id))) {
    throw new TutorialScenarioError('A competência indicada não existe no exemplo.', { code: 'SUBJECT_NOT_FOUND', status: 404 })
  }
}

function applyRoomUpdate(next, action) {
  const room = requireEntity(next.rooms, action.roomId ?? action.id, 'A sala')
  const data = action.data ?? action
  const name = String(data.name ?? room.name).trim()
  const capacity = Number(data.capacity ?? room.capacity)
  const type = String(data.type ?? room.type).toUpperCase()
  if (!name || !Number.isInteger(capacity) || capacity < 1 || !ROOM_TYPES[type.toLowerCase()]) throw new TutorialScenarioError('Os dados da sala são inválidos.')
  Object.assign(room, { name, capacity, type })
}

function applyClassSubjectTeacherUpdate(next, action) {
  const cls = requireEntity(next.classes, action.classId, 'A turma')
  const subject = requireEntity(next.subjects, action.subjectId, 'A disciplina')
  const teacher = requireEntity(next.teachers, action.teacherId, 'O professor')
  if (cls.id !== next.classes[0].id) throw new TutorialScenarioError('A turma não está preparada para este exemplo.', { code: 'DEMO_ENTITY_NOT_FOUND', status: 404 })
  if (!teacher.competencies.includes(subject.id)) throw new TutorialScenarioError('O professor não tem competência para esta disciplina.', { code: 'INELIGIBLE_TEACHER', status: 400 })
  const assignment = next.classSubjects.find((item) => item.classId === cls.id && item.subjectId === subject.id)
  if (!assignment) throw new TutorialScenarioError('A disciplina não está associada à turma.', { code: 'CLASS_SUBJECT_NOT_FOUND', status: 404 })
  assignment.teacherId = teacher.id
}

function applyAvailabilityUpdate(next, action) {
  const slots = action.slots ?? action.data ?? action
  if (!Array.isArray(slots)) throw new TutorialScenarioError('A disponibilidade deve ser um array.')
  const validIds = new Set(next.timeslots.map((slot) => numericId(next.timeslots, slot.id)))
  const seen = new Set()
  const normalized = slots.map((slot) => {
    const id = Number(slot.timeslot_id ?? slot.timeslotId)
    const score = Number(slot.score)
    if (!validIds.has(id) || seen.has(id) || ![-1, 0, 1, 2].includes(score)) throw new TutorialScenarioError('A grelha de disponibilidade contém um período inválido.')
    seen.add(id)
    return { timeslotId: internalId(next.timeslots, id), score }
  })
  next.availability.slots = next.timeslots.map((slot) => normalized.find((entry) => entry.timeslotId === slot.id) ?? { timeslotId: slot.id, score: 1 })
}

function applyGenerate(next) {
  if (next.draft) throw new TutorialScenarioError('Já existe um rascunho pendente.', { code: 'PENDING_DRAFT', status: 409 })
  next.draft = createScheduleDraft()
  next.jobs['demo-job-schedule'] = { id: 'demo-job-schedule', status: 'SUCCEEDED', resultCategory: 'COMPLETE_SUCCESS' }
}

function applyApproval(next, action) {
  const draftId = action.draftId ?? action.id
  if (!next.draft || next.draft.id !== (typeof draftId === 'string' && draftId.startsWith('demo-') ? draftId : draftId === 72 ? 'demo-draft-recovery' : 'demo-draft-schedule')) {
    throw new TutorialScenarioError('O rascunho indicado não existe ou já não está pendente.', { code: 'DRAFT_NOT_FOUND', status: 404 })
  }
  if (next.draft.kind === 'RECOVERY') next.publishedRecoveryBlockIds.push('demo-block-recovery-1')
  next.draft = null
}

function applyOccurrence(next, action) {
  const block = requireEntity(next.blocks, action.blockId ?? action.activeBlockId, 'O bloco')
  if (action.status !== 'OCCURRENCE') throw new TutorialScenarioError('Este exercício aceita apenas a intenção OCCURRENCE.')
  if (next.occurrences.some((occurrence) => occurrence.blockId === block.id && occurrence.status !== 'REVOKED')) {
    throw new TutorialScenarioError('Este bloco já tem uma ocorrência.', { code: 'OCCURRENCE_ALREADY_EXISTS', status: 409 })
  }
  next.occurrences.push(createOpenOccurrence('demo-occurrence-created', block))
  block.lessonLogStatus = 'OCCURRENCE'
}

function applySubstitution(next, action) {
  if (action.status !== 'SUBSTITUTED') throw new TutorialScenarioError('Este exercício aceita apenas a decisão SUBSTITUTED.')
  const occurrence = requireEntity(next.occurrences, action.occurrenceId ?? action.id, 'A ocorrência')
  const teacher = requireEntity(next.teachers, action.substituteTeacherId ?? action.teacherId, 'A professora substituta')
  const subject = requireEntity(next.subjects, action.substituteSubjectId ?? action.subjectId, 'A disciplina substituta')
  if (!teacher.competencies.includes(subject.id)) throw new TutorialScenarioError('A recomendação não corresponde às competências apresentadas.', { code: 'INVALID_SUBSTITUTE', status: 400 })
  occurrence.status = 'SUBSTITUTED'
  occurrence.operationalState = 'DECIDED_SUBSTITUTED'
  occurrence.substituteTeacherId = teacher.id
  occurrence.substituteSubjectId = subject.id
  occurrence.decidedAt = '2025-09-15T11:00:00Z'
  occurrence.version += 1
}

export function createTutorialScenario(stepId) {
  if (!getTutorialStep(stepId)) throw new TutorialScenarioError('O passo do guia não existe.', { code: 'UNKNOWN_STEP', status: 400 })
  const scenario = createBaseScenario(stepId)
  if (Object.values(tutorialScenarioInvariants(scenario)).some((value) => !value)) {
    throw new TutorialScenarioError('O cenário do guia não cumpre os invariantes da demonstração.')
  }
  return scenario
}

export function applyTutorialDemoAction(scenario, action) {
  if (!scenario || typeof scenario !== 'object' || !getTutorialStep(scenario.stepId)) throw new TutorialScenarioError('O cenário do guia é inválido.')
  if (!action || typeof action !== 'object') throw new TutorialScenarioError('A ação experimental é inválida.')
  ensureAction(scenario, action.type)
  const next = clone(scenario)
  switch (action.type) {
    case TUTORIAL_ACTIONS.UPDATE_SUBJECT: applySubjectUpdate(next, action); break
    case TUTORIAL_ACTIONS.UPDATE_CLASS: applyClassUpdate(next, action); break
    case TUTORIAL_ACTIONS.UPDATE_MEMBER_COMPETENCIES: applyMemberUpdate(next, action); break
    case TUTORIAL_ACTIONS.UPDATE_ROOM: applyRoomUpdate(next, action); break
    case TUTORIAL_ACTIONS.UPDATE_CLASS_SUBJECT_TEACHER: applyClassSubjectTeacherUpdate(next, action); break
    case TUTORIAL_ACTIONS.UPDATE_AVAILABILITY: applyAvailabilityUpdate(next, action); break
    case TUTORIAL_ACTIONS.GENERATE_SCHEDULE: applyGenerate(next); break
    case TUTORIAL_ACTIONS.APPROVE_SCHEDULE:
    case TUTORIAL_ACTIONS.APPROVE_RECOVERY: applyApproval(next, action); break
    case TUTORIAL_ACTIONS.CREATE_OCCURRENCE: applyOccurrence(next, action); break
    case TUTORIAL_ACTIONS.DECIDE_SUBSTITUTION: applySubstitution(next, action); break
    default: throw new TutorialScenarioError(`Ação experimental não suportada: ${action.type}.`, { code: 'UNSUPPORTED_DEMO_ACTION', status: 403 })
  }
  return next
}

function subjectApi(scenario, subject) {
  return {
    id: numericId(scenario.subjects, subject.id),
    name: subject.name,
    required_room_type: subject.roomType.toLowerCase(),
    modules: scenario.modules.filter((module) => module.subjectId === subject.id).map((module, index) => ({
      id: numericId(scenario.modules, module.id),
      name: module.name,
      code: module.code,
      hours_total: module.requiredMinutes / 60,
      order: index,
    })),
  }
}

export function createTutorialApiSnapshot(scenario) {
  const subjects = scenario.subjects.map((subject) => subjectApi(scenario, subject))
  const courses = scenario.courses.map((course) => ({
    id: numericId(scenario.courses, course.id),
    name: course.name,
    abbreviation: course.code,
    classes: scenario.classes.filter((item) => item.courseId === course.id).map((item) => ({
      id: numericId(scenario.classes, item.id),
      name: item.name,
      grade_level: item.gradeLevel,
      size: item.size,
      start_year: item.startYear,
      end_year: item.endYear,
      course_id: numericId(scenario.courses, item.courseId),
    })),
    subjects,
  }))
  const teachers = scenario.teachers.map((teacher) => ({
    id: numericId(scenario.teachers, teacher.id),
    name: teacher.name,
    subject_ids: teacher.competencies.map((id) => numericId(scenario.subjects, id)).filter(Number.isInteger),
    current_classes_count: scenario.classSubjects.filter((item) => item.teacherId === teacher.id).length,
    email: teacher.email,
  }))
  const classes = scenario.classes.map((item) => ({
    id: numericId(scenario.classes, item.id),
    name: item.name,
    grade_level: item.gradeLevel,
    size: item.size,
    start_year: item.startYear,
    end_year: item.endYear,
    course_id: numericId(scenario.courses, item.courseId),
  }))
  const members = scenario.teachers.map((teacher, index) => ({
    id: index + 1,
    organization_display_name: teacher.name,
    email: teacher.email,
    capabilities: ['teacher'],
    teacher_access_mode: 'scheduler_only',
    subject_ids: teachers[index].subject_ids,
    access_status: 'active',
    lifecycle_status: 'active',
    provider_state: 'confirmed',
    lock_version: 1,
    actions: { can_edit: true, can_remove: false, can_resend_invite: false, can_retry_sync: false, can_restore: false },
  }))
  const rooms = scenario.rooms.map((room) => ({ id: numericId(scenario.rooms, room.id), name: room.name, type: room.type.toLowerCase(), capacity: room.capacity }))
  const timeslots = scenario.timeslots.map((slot) => ({
    id: numericId(scenario.timeslots, slot.id),
    day_of_week: slot.dayOfWeek,
    start_time: `${slot.startTime}:00`,
    end_time: `${slot.endTime}:00`,
  }))
  const assignments = scenario.classSubjects.map((assignment) => ({
    id: numericId(scenario.classSubjects, assignment.id),
    class_id: numericId(scenario.classes, assignment.classId),
    subject_id: numericId(scenario.subjects, assignment.subjectId),
    teacher_id: numericId(scenario.teachers, assignment.teacherId),
  }))
  const currentDraft = scenario.draft ? {
    proposal_id: scenario.draft.id === 'demo-draft-recovery' ? 72 : 71,
    status: 'PENDING',
    strategy: scenario.draft.strategy,
    kind: scenario.draft.kind,
    created_at: '2025-09-15T07:00:02Z',
    base_version_id: null,
    policy_version: scenario.draft.kind === 'RECOVERY' ? 'v1-uncalibrated' : 'baseline-v1',
    is_stale: false,
    stale_reason: null,
    can_approve: scenario.draft.canApprove,
    warnings: scenario.draft.warnings,
    diagnostics: [],
    projected_completion_date: scenario.draft.projectedCompletionDate,
    hard_end_date: scenario.draft.hardEndDate,
    metrics: {
      completion_dates: {},
      latest_completion_date: scenario.draft.projectedCompletionDate,
      margin_days: 4,
      excess_days: scenario.draft.kind === 'RECOVERY' ? 1 : 0,
      disruption_cost: scenario.draft.disruptionScore,
      changed_lessons: scenario.draft.changedBlocks,
      classes_after_preferred: scenario.draft.kind === 'RECOVERY' ? [1] : [],
      warnings: scenario.draft.warnings,
    },
  } : null
  return { subjects, courses, classes, teachers, members, rooms, timeslots, assignments, currentDraft }
}

export function tutorialScenarioInvariants(scenario) {
  const allEntities = [...scenario.courses, ...scenario.classes, ...scenario.subjects, ...scenario.modules, ...scenario.teachers, ...scenario.rooms, ...scenario.classSubjects, ...scenario.timeslots, ...scenario.blocks]
  const programming = scenario.subjects.find((subject) => subject.id === 'demo-subject-programming')
  const mathsTeacher = scenario.teachers.find((teacher) => teacher.id === 'demo-teacher-mathematics')
  return {
    step: Boolean(getTutorialStep(scenario.stepId)),
    chapters: TUTORIAL_STEPS.filter((step) => step.chapter === 1).length === 7 && TUTORIAL_STEPS.filter((step) => step.chapter === 2).length === 6,
    demoIds: allEntities.every((item) => item.id.startsWith('demo-')),
    curriculum: Boolean(programming) && scenario.modules.some((module) => module.subjectId === programming.id && module.requiredMinutes > 0),
    classCourse: scenario.classes.every((item) => scenario.courses.some((course) => course.id === item.courseId)),
    eligibleTeachers: scenario.classSubjects.every((assignment) => scenario.teachers.some((teacher) => teacher.id === assignment.teacherId && teacher.competencies.includes(assignment.subjectId))),
    roomCapacity: scenario.rooms.some((room) => room.type === 'LAB' && room.capacity >= scenario.classes[0].size),
    calendar: scenario.weekStart === DEMO_WEEK_START && scenario.referenceDate === DEMO_REFERENCE_DATE && scenario.slotDurationMinutes === 60,
    debt: scenario.debt.hoursOwedMinutes === 120 && scenario.debt.proposedRecoveryMinutes === 60 && scenario.debt.remainingMinutes === 60,
    substituteEligibility: Boolean(mathsTeacher?.competencies.includes('demo-subject-mathematics')),
    historyPreserved: scenario.history.every((event) => event.preserved),
  }
}

export { TUTORIAL_ACTIONS, TUTORIAL_STEPS, getTutorialStep }
