import {
  TUTORIAL_ACTIONS,
  getTutorialStep,
} from './tutorialContent'
import {
  TutorialScenarioError,
  applyTutorialDemoAction,
  createTutorialApiSnapshot,
} from './tutorialScenario'
import { addDays } from '../../utils/formatUtils'

function normalizePath(url = '') {
  const path = String(url).split('?')[0].split('/').filter(Boolean).join('/')
  return '/' + path
}

function createTutorialApiError(message, { config, method, path, stepId, status = 400, code = 'TUTORIAL_API_ERROR' } = {}) {
  const error = new Error(message)
  error.config = config
  error.method = method
  error.path = path
  error.stepId = stepId
  error.response = {
    status,
    data: { detail: { code, message } },
    headers: {},
    config,
  }
  return error
}

function parseJson(value, metadata) {
  if (value == null || value === '') return {}
  if (typeof value === 'object') return value
  if (typeof value !== 'string') throw createTutorialApiError('O corpo do pedido deve ser JSON.', metadata)
  try {
    return JSON.parse(value)
  } catch {
    throw createTutorialApiError('JSON inválido no pedido do guia.', metadata)
  }
}

function response(config, data, status = 200) {
  return {
    data,
    status,
    statusText: status === 201 ? 'Created' : 'OK',
    headers: {},
    config,
    request: null,
  }
}

function findNumeric(collection, id) {
  const number = Number(id)
  if (!Number.isInteger(number) || number < 1 || number > collection.length) return null
  return collection[number - 1]
}

function dateAtWeekStart(weekStart, dayOffset) {
  const date = new Date(`${weekStart}T12:00:00Z`)
  if (Number.isNaN(date.getTime())) return null
  date.setUTCDate(date.getUTCDate() + dayOffset)
  return date.toISOString().slice(0, 10)
}

function getClassSubjects(snapshot, scenario, classId) {
  const cls = scenario.classes.find((item) => item.id === classId)
  const course = scenario.courses.find((item) => item.id === cls?.courseId)
  if (!cls || !course) return null
  return {
    class_id: snapshot.classes.find((item) => item.name === cls.name)?.id,
    class_name: cls.name,
    course_id: snapshot.courses.find((item) => item.name === course.name)?.id,
    course_name: course.name,
    course_abbreviation: course.code,
    grade_level: cls.gradeLevel,
    subjects: scenario.classSubjects
      .filter((assignment) => assignment.classId === cls.id)
      .map((assignment) => {
        const subject = scenario.subjects.find((item) => item.id === assignment.subjectId)
        const teacher = scenario.teachers.find((item) => item.id === assignment.teacherId)
        const snapshotSubject = snapshot.subjects.find((item) => item.name === subject.name)
        return {
          id: snapshot.assignments.find((item) => item.subject_id === snapshotSubject?.id)?.id,
          subject_id: snapshotSubject?.id,
          subject_name: subject.name,
          required_room_type: subject.roomType.toLowerCase(),
          joint_group: null,
          teacher_id: snapshot.teachers.find((item) => item.name === teacher?.name)?.id ?? null,
          teacher_name: teacher?.name ?? null,
          // O guia mostra a seleção de módulos apenas para leitura, com tudo marcado.
          modules: (snapshotSubject?.modules || []).map((module) => ({ ...module, selected: true })),
        }
      }),
  }
}

function getAvailability(snapshot, scenario) {
  const values = new Map(scenario.availability.slots.map((slot) => [slot.timeslotId, slot.score]))
  return snapshot.timeslots.map((timeslot, index) => ({
    timeslot_id: timeslot.id,
    score: values.get(scenario.timeslots[index].id) ?? 1,
  }))
}

function getOccurrence(snapshot, scenario, occurrence) {
  const block = scenario.blocks.find((item) => item.id === occurrence.blockId)
  const cls = scenario.classes.find((item) => item.id === block?.classId)
  const subject = scenario.subjects.find((item) => item.id === block?.subjectId)
  const teacher = scenario.teachers.find((item) => item.id === block?.teacherId)
  const timeslotIndex = scenario.timeslots.findIndex((item) => item.id === block?.timeslotId)
  const timeslot = snapshot.timeslots[timeslotIndex]
  return {
    id: scenario.occurrences.indexOf(occurrence) + 1,
    version: occurrence.version,
    date: occurrence.date,
    status: occurrence.status,
    operational_state: occurrence.operationalState,
    decided_at: occurrence.decidedAt ?? null,
    substitute_teacher_id: occurrence.substituteTeacherId ? snapshot.teachers.find((item) => item.name === scenario.teachers.find((teacherItem) => teacherItem.id === occurrence.substituteTeacherId)?.name)?.id ?? null : null,
    substitute_subject_id: occurrence.substituteSubjectId ? snapshot.subjects.find((item) => item.name === scenario.subjects.find((subjectItem) => subjectItem.id === occurrence.substituteSubjectId)?.name)?.id ?? null : null,
    class_id: snapshot.classes.find((item) => item.name === cls?.name)?.id,
    class_name: cls?.name,
    subject_id: snapshot.subjects.find((item) => item.name === subject?.name)?.id,
    subject_name: subject?.name,
    planned_teacher_id: snapshot.teachers.find((item) => item.name === teacher?.name)?.id,
    timeslot_start_time: timeslot?.start_time,
    timeslot_end_time: timeslot?.end_time,
    reason: occurrence.reason,
    lesson_log_summary: occurrence.lessonLogSummary,
    lesson_log_notes: occurrence.lessonLogNotes,
    created_at: `${occurrence.date}T08:00:00Z`,
    decided_by_membership_id: occurrence.decidedAt ? 1 : null,
  }
}

function getScheduleSlots(snapshot, scenario, params = {}) {
  const requestedWeek = params.week_start || scenario.weekStart
  const requestedWeekStart = dateAtWeekStart(requestedWeek, 0)
  const requestedWeekEnd = dateAtWeekStart(requestedWeek, 6)
  const publishedRecovery = new Set(scenario.publishedRecoveryBlockIds)
  return scenario.blocks
    .filter((block) => !block.isRecovery || publishedRecovery.has(block.id))
    .filter((block) => block.date >= requestedWeekStart && block.date <= requestedWeekEnd)
    .map((block, index) => {
      const classInfo = snapshot.classes.find((item) => item.name === scenario.classes.find((cls) => cls.id === block.classId)?.name)
      const subject = snapshot.subjects.find((item) => item.name === scenario.subjects.find((subjectItem) => subjectItem.id === block.subjectId)?.name)
      const teacher = snapshot.teachers.find((item) => item.name === scenario.teachers.find((teacherItem) => teacherItem.id === block.teacherId)?.name)
      const room = snapshot.rooms.find((item) => item.name === scenario.rooms.find((roomItem) => roomItem.id === block.roomId)?.name)
      const timeslot = snapshot.timeslots[scenario.timeslots.findIndex((item) => item.id === block.timeslotId)]
      const occurrence = scenario.occurrences.find((item) => item.blockId === block.id)
      const dayOffset = scenario.timeslots.find((item) => item.id === block.timeslotId)?.dayOfWeek ?? 0
      const date = block.date || dateAtWeekStart(requestedWeek, dayOffset)
      return {
        id: index + 1,
        date,
        timeslot_id: timeslot?.id,
        timeslot,
        subject,
        teacher,
        room,
        class_info: classInfo,
        scheduler_lesson_id: scenario.blocks.indexOf(block) + 1,
        // Normal schedule blocks are addressed through the scheduler lesson id.
        // An operational block id would make LessonLogModal treat every demo
        // lesson as an already-created occurrence.
        operational_block_id: block.isOperational ? scenario.blocks.indexOf(block) + 1 : null,
        lesson_log_status: occurrence ? 'OCCURRENCE' : block.lessonLogStatus,
        occurrence_id: occurrence ? scenario.occurrences.indexOf(occurrence) + 1 : null,
        occurrence_status: occurrence?.status ?? null,
        occurrence_decided_at: occurrence?.decidedAt ?? null,
        can_create_occurrence: !occurrence,
        can_decide_occurrence: Boolean(occurrence && !occurrence.decidedAt),
        is_past: new Date(`${date}T${timeslot?.end_time ?? '00:00:00'}`) <= new Date(scenario.referenceDate),
        is_draft: Boolean(scenario.draft && block.isRecovery),
        week_timesheet_status: Number(params.teacher_id) === 1 ? 'SUBMITTED' : 'OPEN',
        timesheet_id: teacher?.id,
      }
    })
    .filter((slot) => (!params.class_id || slot.class_info?.id === Number(params.class_id)) && (!params.teacher_id || slot.teacher?.id === Number(params.teacher_id)))
}

function getDraftDiff(scenario, draftId) {
  if (!scenario.draft) return null
  const numericDraftId = scenario.draft?.id === 'demo-draft-recovery' ? 72 : 71
  if (numericDraftId !== Number(draftId)) return null
  const isRecovery = scenario.draft.kind === 'RECOVERY'
  return {
    is_first_generation: !isRecovery,
    physical: [{
      change_type: isRecovery ? 'ADDED' : 'MOVED',
      lesson_id: 1,
      class_id: 1,
      subject_id: 1,
      before: isRecovery ? null : { date: '2025-09-16', start: '09:00', end: '10:00', room_id: 1 },
      after: { date: scenario.draft.projectedCompletionDate, start: '09:00', end: '10:00', room_id: 1 },
    }],
    modular: isRecovery ? [] : [{
      lesson_id: 1,
      class_id: 1,
      subject_id: 1,
      before: [{ module_id: 1, offset_minutes: 0, minutes: 50 }],
      after: [{ module_id: 1, offset_minutes: 50, minutes: 50 }],
    }],
    counts: {
      added: isRecovery ? 1 : 0,
      moved: isRecovery ? 0 : 1,
      removed: 0,
      room_changed: 0,
      modular_updates: isRecovery ? 0 : 1,
    },
  }
}

function schedulerStatus(snapshot, scenario) {
  const proposal = snapshot.currentDraft
  const published = Boolean(scenario.publishedRecoveryBlockIds.length)
  return {
    configured: true,
    school_year: {
      id: 1,
      label: '2025/2026',
      start_date: '2025-09-01',
      preferred_end_date: '2025-12-19',
      hard_end_date: scenario.hardEndDate ?? '2026-07-15',
      timezone: 'Europe/Lisbon',
    },
    publication_state: published ? 'PUBLISHED' : 'UNPUBLISHED',
    active_version_id: published ? 1 : null,
    revisions: {
      input: 0,
      planning: 0,
      last_completed_planning: null,
      last_successful_generation_at: null,
    },
    eligibility: {
      can_generate: !proposal,
      reasons: proposal ? [] : ['FIRST_GENERATION'],
      blocker: null,
    },
    default_strategy: published ? 'ADAPTIVE_RECOVERY' : 'COMPLETE_GENERATION',
    active_job: null,
    pending_proposal: proposal,
  }
}

function createJobResponse(scenario, jobId) {
  const job = Object.values(scenario.jobs).find((item) => item.id === jobId)
  if (!job) return null
  const proposalId = scenario.draft
    ? (scenario.draft.id === 'demo-draft-recovery' ? 72 : 71)
    : null
  return {
    id: 81,
    strategy: job.strategy ?? scenario.draft?.strategy ?? 'COMPLETE_GENERATION',
    status: job.status,
    result_code: job.status === 'SUCCEEDED' ? 'COMPLETE' : job.status,
    stop_reason: job.status === 'SUCCEEDED' ? 'ROUND_LIMIT' : null,
    queue_position: null,
    queued_at: '2025-09-15T07:00:00Z',
    started_at: '2025-09-15T07:00:01Z',
    finished_at: '2025-09-15T07:00:02Z',
    heartbeat_at: '2025-09-15T07:00:02Z',
    cancellation_requested: false,
    proposal_id: proposalId,
    summary: null,
  }
}

function methodNotAllowed({ fail, method, path }) {
  return fail('Método ' + method.toUpperCase() + ' não permitido em ' + path + '.', 405, 'METHOD_NOT_ALLOWED')
}

function handleBasicRoutes(context) {
  const { method, path, snapshot, read, config, fail } = context
  if (path === '/readiness/prevalidation') {
    if (method !== 'get') return methodNotAllowed(context)
    return read({ status: 'READY', fingerprint: null, issues: [] })
  }
  if (path === '/members/me') {
    if (method !== 'get') return methodNotAllowed(context)
    return read({ id: 1, organization_display_name: 'Prof. António Silva', capabilities: ['admin', 'teacher'], access_status: 'active', teacher_id: 1 })
  }
  if (path === '/timeslots/range') {
    if (method !== 'get') return methodNotAllowed(context)
    const fromDate = config?.params?.from_date
    if (!fromDate) return fail('Intervalo de datas em falta.', 422, 'TUTORIAL_ROUTE_NOT_DECLARED')
    const days = Array.from({ length: 7 }, (_, offset) => {
      const date = addDays(fromDate, offset)
      const weekday = (new Date(`${date}T12:00:00`).getDay() + 6) % 7
      return {
        date,
        version_id: null,
        effective_date: null,
        blocks: snapshot.timeslots
          .filter((slot) => slot.day_of_week === weekday)
          .map((slot) => ({
            id: slot.id,
            day_of_week: slot.day_of_week,
            start_time: slot.start_time,
            end_time: slot.end_time,
          })),
      }
    })
    return read({ days, transition_date: null })
  }
  const collections = { '/subjects': snapshot.subjects, '/rooms': snapshot.rooms, '/courses': snapshot.courses, '/classes': snapshot.classes, '/teachers': snapshot.teachers, '/timeslots': snapshot.timeslots }
  if (Object.hasOwn(collections, path)) return method === 'get' ? read(collections[path]) : methodNotAllowed(context)
  return null
}

function handleSubjectRoute(context) {
  const { method, path, scenario, snapshot, body, read, write, fail } = context
  if (!/^\/subjects\/\d+$/.test(path)) return null
  const id = Number(path.split('/').at(-1))
  if (!findNumeric(scenario.subjects, id)) return fail('A disciplina indicada não existe no exemplo.', 404, 'DEMO_ENTITY_NOT_FOUND')
  if (method === 'get') return read(snapshot.subjects[id - 1])
  if (method === 'patch') return write(TUTORIAL_ACTIONS.UPDATE_SUBJECT, { subjectId: id, data: body }, (_next, nextSnapshot) => nextSnapshot.subjects[id - 1])
  return methodNotAllowed(context)
}

function handleRoomRoute(context) {
  const { method, path, scenario, snapshot, body, read, write, fail } = context
  if (!/^\/rooms\/\d+$/.test(path)) return null
  const id = Number(path.split('/').at(-1))
  if (!findNumeric(scenario.rooms, id)) return fail('A sala indicada não existe no exemplo.', 404, 'DEMO_ENTITY_NOT_FOUND')
  if (method === 'get') return read(snapshot.rooms[id - 1])
  if (method === 'patch') return write(TUTORIAL_ACTIONS.UPDATE_ROOM, { roomId: id, data: body }, (_next, nextSnapshot) => nextSnapshot.rooms[id - 1])
  return methodNotAllowed(context)
}

function handleCourseRoute(context) {
  const { method, path, scenario, snapshot, body, read, write, fail } = context
  if (/^\/courses\/\d+$/.test(path)) {
    const id = Number(path.split('/').at(-1))
    if (!findNumeric(scenario.courses, id)) return fail('O curso indicado não existe no exemplo.', 404, 'DEMO_ENTITY_NOT_FOUND')
    if (method === 'get') return read(snapshot.courses[id - 1])
    return fail('Apenas a edição de uma turma preparada está disponível no guia.', 403, 'DEMO_ACTION_NOT_ALLOWED')
  }
  const match = /^\/courses\/(\d+)\/classes\/(\d+)$/.exec(path)
  if (!match) return null
  const [, courseId, classId] = match
  if (!findNumeric(scenario.courses, courseId) || !findNumeric(scenario.classes, classId)) return fail('A turma ou curso indicado não existe no exemplo.', 404, 'DEMO_ENTITY_NOT_FOUND')
  if (method === 'get') return read(snapshot.classes[Number(classId) - 1])
  if (method === 'patch') return write(TUTORIAL_ACTIONS.UPDATE_CLASS, { courseId: Number(courseId), classId: Number(classId), data: body }, (_next, nextSnapshot) => nextSnapshot.classes[Number(classId) - 1])
  return methodNotAllowed(context)
}

function handleClassDetailRoute(context) {
  const { method, path, scenario, snapshot, read, fail } = context
  if (!/^\/classes\/\d+$/.test(path)) return null
  const id = Number(path.split('/').at(-1))
  const cls = findNumeric(scenario.classes, id)
  if (!cls) return fail('A turma indicada não existe no exemplo.', 404, 'DEMO_ENTITY_NOT_FOUND')
  if (method !== 'get') return methodNotAllowed(context)
  const course = snapshot.courses.find((item) => item.id === snapshot.classes[id - 1].course_id)
  const classSubjects = getClassSubjects(snapshot, scenario, cls.id)
  const subjects = classSubjects.subjects.map((item) => ({ ...snapshot.subjects[item.subject_id - 1], total_hours: snapshot.subjects[item.subject_id - 1].modules.reduce((total, module) => total + module.hours_total, 0), completed_hours: 0, overall_percentage: 0 }))
  return read({ ...snapshot.classes[id - 1], course, subjects })
}

function handleClassSubjectsRoute(context) {
  const { method, path, scenario, snapshot, read, fail } = context
  if (!/^\/classes\/\d+\/subjects$/.test(path)) return null
  const id = Number(path.split('/')[2])
  if (!findNumeric(scenario.classes, id)) return fail('A turma indicada não existe no exemplo.', 404, 'DEMO_ENTITY_NOT_FOUND')
  if (method === 'get') return read(getClassSubjects(snapshot, scenario, scenario.classes[id - 1].id))
  return methodNotAllowed(context)
}

function handleAvailableSubjectsRoute(context) {
  const { method, path, scenario, snapshot, read, fail } = context
  if (!/^\/classes\/\d+\/available-subjects$/.test(path)) return null
  const id = Number(path.split('/')[2])
  if (method !== 'get' || !findNumeric(scenario.classes, id)) return fail('A turma indicada não existe ou a rota não é de consulta.', method === 'get' ? 404 : 405, 'METHOD_NOT_ALLOWED')
  const associated = new Set(scenario.classSubjects.filter((item) => item.classId === scenario.classes[id - 1].id).map((item) => item.subjectId))
  return read(snapshot.subjects.filter((subject) => !associated.has(scenario.subjects[subject.id - 1].id)))
}

function handleEligibleTeachersRoute(context) {
  const { method, path, scenario, snapshot, read, fail } = context
  if (!/^\/classes\/subjects\/\d+\/eligible-teachers$/.test(path)) return null
  const subjectId = Number(path.split('/')[3])
  if (method !== 'get' || !findNumeric(scenario.subjects, subjectId)) return fail('A disciplina indicada não existe.', 404, 'DEMO_ENTITY_NOT_FOUND')
  return read(snapshot.teachers.filter((teacher) => teacher.subject_ids.includes(subjectId)))
}

function handleClassSubjectTeacherRoute(context) {
  const { method, path, body, write } = context
  const match = /^\/classes\/(\d+)\/subjects\/(\d+)$/.exec(path)
  if (!match) return null
  const [, classId, subjectId] = match
  if (method === 'patch') return write(TUTORIAL_ACTIONS.UPDATE_CLASS_SUBJECT_TEACHER, { classId: Number(classId), subjectId: Number(subjectId), teacherId: body.teacher_id }, (_next, nextSnapshot) => getClassSubjects(nextSnapshot, _next, _next.classes[Number(classId) - 1].id))
  return methodNotAllowed(context)
}

function handleMemberRoutes(context) {
  const { method, path, scenario, snapshot, body, read, write, fail } = context
  if (path === '/members') {
    if (method === 'get') return read({ items: snapshot.members, total: snapshot.members.length, limit: snapshot.members.length, offset: 0 })
    return fail('A criação de membros não está disponível no guia.', 403, 'DEMO_ACTION_NOT_ALLOWED')
  }
  if (!/^\/members\/\d+$/.test(path)) return null
  const id = Number(path.split('/').at(-1))
  if (!findNumeric(scenario.teachers, id)) return fail('O professor indicado não existe no exemplo.', 404, 'DEMO_ENTITY_NOT_FOUND')
  if (method === 'get') return read(snapshot.members[id - 1])
  if (method === 'patch') return write(TUTORIAL_ACTIONS.UPDATE_MEMBER_COMPETENCIES, { memberId: id, data: body }, (_next, nextSnapshot) => nextSnapshot.members[id - 1])
  return methodNotAllowed(context)
}

function handleAvailabilityRoute(context) {
  const { method, path, body, snapshot, scenario, read, write } = context
  if (path === '/teachers/me/presence') {
    if (method !== 'get') return methodNotAllowed(context)
    return read({ lunch_required: true, minimum_hours: null, max_gap_hours: null })
  }
  if (path !== '/teachers/me/availability') return null
  if (method === 'get') return read(getAvailability(snapshot, scenario))
  if (method === 'put') return write(TUTORIAL_ACTIONS.UPDATE_AVAILABILITY, { slots: Array.isArray(body) ? body : body.availability }, (_next, nextSnapshot) => getAvailability(nextSnapshot, _next))
  return methodNotAllowed(context)
}

function handleSchedulerStatusRoute(context) {
  const { method, path, snapshot, scenario, read } = context
  if (path === '/scheduler/status') return method === 'get' ? read(schedulerStatus(snapshot, scenario)) : methodNotAllowed(context)
  if (path === '/scheduler/drafts/current') return method === 'get' ? read(snapshot.currentDraft) : methodNotAllowed(context)
  return null
}

function handleSchedulerDraftRoute(context) {
  const { method, path, scenario, read, fail } = context
  if (!/^\/scheduler\/drafts\/\d+\/diff$/.test(path)) return null
  if (method !== 'get') return methodNotAllowed(context)
  const diff = getDraftDiff(scenario, path.split('/')[3])
  return diff ? read(diff) : fail('O rascunho indicado não existe ou já não está pendente.', 404, 'DRAFT_NOT_FOUND')
}

function handleSchedulerJobRoute(context) {
  const { method, path, scenario, read, write, stepId, fail } = context
  if (path === '/scheduler/generate') {
    if (method !== 'post') return methodNotAllowed(context)
    return write(TUTORIAL_ACTIONS.GENERATE_SCHEDULE, {}, (next) => ({ job: createJobResponse(next, 'demo-job-schedule') }))
  }
  if (/^\/scheduler\/jobs\/\d+$/.test(path)) {
    if (method !== 'get') return methodNotAllowed(context)
    if (Number(path.split('/')[3]) !== 81) return fail('A tarefa indicada não existe.', 404, 'JOB_NOT_FOUND')
    const job = createJobResponse(scenario, 'demo-job-schedule')
    return job ? read(job) : fail('A tarefa indicada não existe.', 404, 'JOB_NOT_FOUND')
  }
  if (!/^\/scheduler\/drafts\/\d+\/approve$/.test(path)) return null
  if (method !== 'post') return methodNotAllowed(context)
  const draftId = Number(path.split('/')[3])
  const actionType = stepId === 'recovery' ? TUTORIAL_ACTIONS.APPROVE_RECOVERY : TUTORIAL_ACTIONS.APPROVE_SCHEDULE
  return write(actionType, { draftId }, () => ({ proposal_id: draftId, status: 'APPROVED', active_version_id: 1, approved_at: '2025-09-15T07:05:00Z' }))
}

function handleScheduleRoutes(context) {
  const { method, path, config, snapshot, scenario, write, read } = context
  if (path === '/schedule/week') {
    if (method !== 'get') return methodNotAllowed(context)
    return read(getScheduleSlots(snapshot, scenario, config.params))
  }
  if (!/^\/schedule\/(lessons|operational-blocks)\/\d+\/log$/.test(path)) return null
  if (method !== 'put') return methodNotAllowed(context)
  return write(TUTORIAL_ACTIONS.CREATE_OCCURRENCE, { blockId: Number(path.split('/')[3]), status: context.body.status }, (_next, nextSnapshot) => nextSnapshot)
}

function handleOccurrenceCollectionRoute(context) {
  const { method, path, config, snapshot, scenario, read } = context
  if (path !== '/occurrences') return null
  if (method !== 'get') return methodNotAllowed(context)
  const items = scenario.occurrences.map((occurrence) => getOccurrence(snapshot, scenario, occurrence)).filter((occurrence) => !config.params?.status || occurrence.operational_state === config.params.status)
  return read({ items, total: items.length, limit: items.length, offset: 0 })
}

function handleOccurrenceDebtsRoute(context) {
  const { method, path, snapshot, scenario, read } = context
  if (path !== '/occurrences/debts') return null
  if (method !== 'get') return methodNotAllowed(context)
  const cls = snapshot.classes[0]
  const subject = snapshot.subjects[0]
  return read({
    items: [{ class_id: cls.id, class_name: cls.name, subject_id: subject.id, subject_name: subject.name, teacher_id: snapshot.teachers[0].id, teacher_name: snapshot.teachers[0].name, gap_occurrences: 2, hours_owed: 2, hours_owed_overdue: 2 }],
    total_gaps: 2,
    total_hours_owed: 2,
    total_hours_owed_overdue: 2,
    as_of_date: scenario.debt.asOfDate,
  })
}

function handleOccurrenceRecommendationRoute(context) {
  const { method, path, scenario, snapshot, read, fail } = context
  if (!/^\/occurrences\/\d+\/substitutes\/recommendations$/.test(path)) return null
  if (method !== 'get') return methodNotAllowed(context)
  const occurrence = findNumeric(scenario.occurrences, Number(path.split('/')[2]))
  if (!occurrence) return fail('A ocorrência indicada não existe.', 404, 'DEMO_ENTITY_NOT_FOUND')
  return read([{ id: 1, rank: 1, score: 100, teacher_id: 2, teacher_name: snapshot.teachers[1].name, subject_id: 2, subject_name: snapshot.subjects[1].name }])
}

function handleOccurrenceDetailRoute(context) {
  const { method, path, scenario, snapshot, body, read, write, fail } = context
  if (!/^\/occurrences\/\d+$/.test(path)) return null
  const id = Number(path.split('/').at(-1))
  if (!findNumeric(scenario.occurrences, id)) return fail('A ocorrência indicada não existe.', 404, 'DEMO_ENTITY_NOT_FOUND')
  if (method === 'get') return read(getOccurrence(snapshot, scenario, scenario.occurrences[id - 1]))
  if (method === 'patch') return write(TUTORIAL_ACTIONS.DECIDE_SUBSTITUTION, { occurrenceId: id, status: body.status, substituteTeacherId: body.substitute_teacher_id, substituteSubjectId: body.substitute_subject_id }, (_next, nextSnapshot) => getOccurrence(nextSnapshot, _next, _next.occurrences[id - 1]))
  return methodNotAllowed(context)
}

function handleTimesheetRoute(context) {
  const { method, path, config, snapshot, scenario, read } = context
  if (path !== '/timesheets') return null
  if (method !== 'get') return methodNotAllowed(context)
  const requestedWeek = config.params?.week_start_date || scenario.weekStart
  const requestedStatus = config.params?.status
  const requestedWeekEnd = dateAtWeekStart(requestedWeek, 6)
  const rows = snapshot.teachers.map((teacher, index) => ({
    id: index + 1,
    teacher_id: index + 1,
    teacher_name: teacher.name,
    week_start_date: requestedWeek,
    week_end_date: requestedWeekEnd,
    status: index === 0 ? 'SUBMITTED' : 'OPEN',
    total_slots: index === 0 ? 2 : 1,
    registered_slots: index === 0 ? 2 : 1,
    completed_slots: 1,
    occurrence_slots: index === 0 ? 1 : 0,
  })).filter((row) => !requestedStatus || row.status === requestedStatus)
  return read(rows)
}

const TUTORIAL_ROUTE_HANDLERS = [
  handleBasicRoutes,
  handleSubjectRoute,
  handleRoomRoute,
  handleCourseRoute,
  handleClassDetailRoute,
  handleClassSubjectsRoute,
  handleAvailableSubjectsRoute,
  handleEligibleTeachersRoute,
  handleClassSubjectTeacherRoute,
  handleMemberRoutes,
  handleAvailabilityRoute,
  handleSchedulerStatusRoute,
  handleSchedulerDraftRoute,
  handleSchedulerJobRoute,
  handleScheduleRoutes,
  handleOccurrenceCollectionRoute,
  handleOccurrenceDebtsRoute,
  handleOccurrenceRecommendationRoute,
  handleOccurrenceDetailRoute,
  handleTimesheetRoute,
]

export function createTutorialApiAdapter({
  stepId: configuredStepId,
  readOnly = false,
  getScenario,
  applyAction,
} = {}) {
  const apply = applyAction || ((action) => applyTutorialDemoAction(getScenario(), action))

  return async (config = {}) => {
    const method = String(config.method || 'get').toLowerCase()
    const path = normalizePath(config.url)
    const scenario = getScenario?.()
    const stepId = configuredStepId || scenario?.stepId
    const metadata = { config, method, path, stepId }
    if (!scenario) throw createTutorialApiError('O cenário do guia não está disponível.', metadata)

    const body = parseJson(config.data, metadata)
    const snapshot = createTutorialApiSnapshot(scenario)
    const fail = (message, status = 400, code = 'TUTORIAL_ROUTE_NOT_DECLARED') => {
      throw createTutorialApiError(message, { ...metadata, status, code })
    }
    const read = (data) => Promise.resolve(response(config, data))
    const write = (requiredAction, action, dataFactory) => {
      const step = getTutorialStep(stepId)
      if (readOnly) return fail('A revisão do guia é apenas de consulta.', 403, 'DEMO_READ_ONLY')
      if (!step?.allowedActions.includes(requiredAction)) return fail('A ação ' + requiredAction + ' não está disponível neste passo.', 403, 'DEMO_ACTION_NOT_ALLOWED')
      let next
      try {
        next = apply({ type: requiredAction, ...action })
      } catch (error) {
        if (error instanceof TutorialScenarioError) return fail(error.message, error.status, error.code)
        throw error
      }
      const nextSnapshot = createTutorialApiSnapshot(next)
      return Promise.resolve(response(config, dataFactory(next, nextSnapshot)))
    }
    const context = { config, method, path, scenario, snapshot, body, stepId, read, write, fail }
    for (const handler of TUTORIAL_ROUTE_HANDLERS) {
      const result = handler(context)
      if (result !== null) return result
    }
    return fail('Rota do guia não declarada: ' + method.toUpperCase() + ' ' + path + '.', 400, 'TUTORIAL_ROUTE_NOT_DECLARED')
  }
}

export { normalizePath, createTutorialApiError }
