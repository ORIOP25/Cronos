function createTutorialApiError(message, { config, method, path, stepId }) {
  const error = new Error(message)
  error.config = config
  error.method = method
  error.path = path
  error.stepId = stepId
  return error
}

function parseJson(value, metadata) {
  if (value == null || value === '') return {}
  if (typeof value !== 'string') {
    if (typeof value === 'object' && (!Array.isArray(value) || metadata.stepId === 'availability_review')) return value
    throw createTutorialApiError('O corpo do pedido deve ser um objeto JSON.', metadata)
  }
  try {
    const parsed = JSON.parse(value)
    if (!parsed || typeof parsed !== 'object' || (Array.isArray(parsed) && metadata.stepId !== 'availability_review')) throw new Error('JSON body must be an object')
    return parsed
  } catch {
    throw createTutorialApiError('JSON inválido no pedido do guia.', metadata)
  }
}

const response = (config, data, status = 200) => Promise.resolve({
  data,
  status,
  statusText: status === 204 ? 'No Content' : 'OK',
  headers: {},
  config,
  request: null,
})

const normalizePath = (url = '') => `/${String(url).split('?')[0].replace(/^\/+/, '')}`

function apiScenario(scenario) {
  const subjectNumbers = new Map(scenario.subjects.map((subject, index) => [subject.id, index + 1]))
  const courseNumbers = new Map(scenario.courses.map((course, index) => [course.id, index + 1]))
  const subjectId = (id) => subjectNumbers.get(id)
  const subjects = scenario.subjects.map((subject, index) => ({
    id: index + 1,
    name: subject.name,
    required_room_type: subject.roomType.toLowerCase(),
    modules: scenario.modules
      .filter((module) => module.subjectId === subject.id)
      .map((module, moduleIndex) => ({
        id: scenario.modules.findIndex((candidate) => candidate.id === module.id) + 1,
        name: module.name,
        code: module.name,
        hours_total: module.requiredMinutes / 60,
        order: moduleIndex,
      })),
  }))
  const rooms = scenario.rooms.map((room, index) => ({ ...room, id: index + 1, type: room.type.toLowerCase() }))
  const teachers = scenario.teachers.map((teacher, index) => ({
    id: index + 1,
    name: teacher.name,
    subject_ids: teacher.competencies.map(subjectId).filter(Number.isInteger),
    current_classes_count: index,
  }))
  const classes = scenario.classes.map((item, index) => ({
    id: index + 1,
    name: item.name,
    grade_level: item.gradeLevel,
    size: item.size,
    start_year: 2025,
    end_year: 2028,
    course_id: courseNumbers.get(item.courseId) || 1,
  }))
  const courses = scenario.courses.map((course, index) => ({
    id: index + 1,
    name: course.name,
    abbreviation: course.code,
    classes: classes.filter((item) => item.course_id === index + 1),
    subjects,
  }))
  const members = teachers.map((teacher, index) => ({
    id: index + 1,
    organization_display_name: teacher.name,
    email: `professor${index + 1}@demo.cronos.pt`,
    capabilities: ['teacher'],
    teacher_access_mode: 'scheduler_only',
    subject_ids: teacher.subject_ids,
    access_status: 'active',
    lifecycle_status: 'active',
    provider_state: 'confirmed',
    lock_version: 1,
    actions: { can_edit: true, can_remove: false, can_resend_invite: false, can_retry_sync: false, can_restore: false },
  }))
  const timeslots = scenario.weeklyGrid.days.flatMap((_, dayIndex) => scenario.weeklyGrid.slots.map((time, slotIndex) => ({
    id: dayIndex * 100 + slotIndex + 1,
    day_of_week: dayIndex,
    start_time: `${time}:00`.slice(0, 8),
    end_time: `${String(Number(time.slice(0, 2)) + 1).padStart(2, '0')}:${time.slice(3)}:00`.slice(0, 8),
  })))
  return { subjects, rooms, teachers, classes, courses, members, timeslots }
}

/**
 * Axios adapter used only while /guide is mounted. It lets the real Cronos
 * pages exercise their normal hooks without allowing a domain request to
 * leave the browser.
 */
export function createTutorialApiAdapter({ getScenario, onDomainMutation }) {
  return async (config) => {
    const path = normalizePath(config.url)
    const method = String(config.method || 'get').toLowerCase()
    const scenario = getScenario()
    const stepId = config.tutorialStepId || scenario?.workflow?.lastCheckpoint || null
    const metadata = { config, method, path, stepId }
    let body
    try {
      body = parseJson(config.data, metadata)
    } catch (error) {
      return Promise.reject(error)
    }
    const data = apiScenario(scenario)
    const mutation = method !== 'get'
    const done = (payload, status = 200) => {
      const localResponse = response(config, payload, status)
      return localResponse.then((result) => {
        if (mutation) onDomainMutation?.({ method, path, body, payload })
        return result
      })
    }
    const rejectMethod = () => Promise.reject(createTutorialApiError(
      `Método ${method.toUpperCase()} não permitido em ${path}.`,
      metadata,
    ))
    const read = (allowed, payload) => allowed.includes(method) ? response(config, payload) : rejectMethod()
    const write = (allowed, payload, status = 200) => allowed.includes(method) ? done(payload, status) : rejectMethod()

    if (path === '/members/me') return read(['get'], {
      id: 1,
      organization_display_name: 'Prof. António Silva',
      capabilities: ['admin', 'teacher'],
      access_status: 'active',
      teacher_id: 1,
    })

    if (path === '/subjects/') return method === 'get' ? read(['get'], data.subjects) : write(['post'], { id: 99, ...body }, 201)
    if (/^\/subjects\/\d+$/.test(path)) return write(['patch', 'delete'], { id: Number(path.split('/').at(-1)), ...body })
    if (path === '/rooms/') return method === 'get' ? read(['get'], data.rooms) : write(['post'], { id: 99, ...body }, 201)
    if (/^\/rooms\/\d+$/.test(path)) return write(['patch', 'delete'], { id: Number(path.split('/').at(-1)), ...body })
    if (path === '/courses/') return method === 'get' ? read(['get'], data.courses) : write(['post'], { id: 99, ...body }, 201)
    if (/^\/courses\/\d+$/.test(path)) {
      const course = data.courses.find((item) => item.id === Number(path.split('/').at(-1))) || data.courses[0]
      return method === 'get' ? read(['get'], course) : write(['patch', 'delete'], { ...course, ...body })
    }
    if (/^\/courses\/\d+\/classes$/.test(path)) return write(['post'], { id: 99, ...body }, 201)
    if (path === '/classes/') return read(['get'], data.classes)
    if (/^\/classes\/\d+$/.test(path)) {
      const item = data.classes.find((entry) => entry.id === Number(path.split('/').at(-1))) || data.classes[0]
      return read(['get'], { ...item, course: data.courses.find((course) => course.id === item.course_id), subjects: data.subjects })
    }
    if (/^\/classes\/\d+\/subjects$/.test(path)) {
      const payload = {
        class_id: 1,
        class_name: data.classes[0].name,
        course_id: 1,
        course_name: data.courses[0].name,
        grade_level: data.classes[0].grade_level,
        subjects: data.subjects.slice(0, 2).map((subject, index) => ({
          subject_id: subject.id,
          subject_name: subject.name,
          required_room_type: subject.required_room_type,
          teacher_id: index === 0 ? data.teachers[0].id : null,
          teacher_name: index === 0 ? data.teachers[0].name : null,
        })),
      }
      return method === 'get' ? read(['get'], payload) : write(['post', 'patch', 'delete'], payload)
    }
    if (/^\/classes\/\d+\/available-subjects$/.test(path)) return read(['get'], data.subjects.slice(2))
    if (/^\/classes\/subjects\/\d+\/eligible-teachers$/.test(path)) return read(['get'], data.teachers)
    if (/^\/classes\/\d+\/subjects\/\d+$/.test(path)) return write(['patch', 'delete'], {})
    if (path === '/teachers/') return read(['get'], data.teachers)
    if (path === '/members') return method === 'get' ? read(['get'], { items: data.members, total: data.members.length }) : write(['post'], { id: 99, ...body }, 201)
    if (/^\/members\/\d+\/(remove|resend-invitation|retry-sync|restore)$/.test(path)) return write(['post'], { ...data.members[0], ...body })
    if (/^\/members\/\d+$/.test(path)) return write(['patch'], { ...data.members[0], ...body })
    if (path === '/timeslots/') return read(['get'], data.timeslots)
    if (path === '/teachers/me/availability') {
      const availability = data.timeslots.map((slot) => ({ timeslot_id: slot.id, score: 1 }))
      return method === 'get' ? read(['get'], availability) : write(['put'], body)
    }
    if (path === '/scheduler/status') return read(['get'], {
      pending_draft_id: scenario.workflow.schedulePrepared ? 71 : null,
      primary_action: scenario.workflow.schedulePrepared ? 'REVIEW_PENDING_DRAFT' : 'GENERATE_SCHEDULE',
      can_generate_new_draft: !scenario.workflow.schedulePrepared,
      can_regenerate_with_confirmation: scenario.workflow.schedulePrepared,
      blocked_reason: null,
    })
    if (path === '/scheduler/drafts/current') return read(['get'], scenario.workflow.schedulePrepared ? {
      draft_id: 71,
      strategy: scenario.workflow.repairSimulated ? 'ADAPTIVE_REPAIR' : 'COMPLETE_GENERATION',
      result_category: 'COMPLETE',
      changed_blocks: 4,
      affected_classes: 2,
      affected_teachers: 3,
      affected_days: 2,
      disruption_score: 8,
      debt_hours_before: scenario.debt.originalHours,
      debt_hours_recovered: scenario.workflow.repairSimulated ? 1 : 0,
      debt_hours_remaining: scenario.workflow.repairSimulated ? 1 : 2,
      warnings: [],
      recommended_actions: [],
      can_approve: true,
    } : null)
    if (path === '/scheduler/generate') return write(['post'], { job_id: 81 }, 202)
    if (/^\/scheduler\/jobs\/\d+\/cancel$/.test(path)) return write(['post'], {})
    if (/^\/scheduler\/jobs\/\d+$/.test(path)) return read(['get'], { job_id: 81, job_status: 'SUCCEEDED' })
    if (/^\/scheduler\/drafts\/\d+\/(approve|reject)$/.test(path)) return write(['post'], {}, 204)
    if (/^\/scheduler\/drafts\/\d+\/diff$/.test(path)) return read(['get'], [
      { block_id: 1, change_type: 'MOVED', subject_name: 'Programação', before_label: 'Seg 08:30', after_label: 'Ter 16:30' },
    ])
    if (path === '/schedule/week') return read(['get'], scenario.gridPreview.map((slot, index) => ({
      id: index + 1,
      date: `2025-09-${15 + index}`,
      timeslot_id: data.timeslots[index].id,
      timeslot: data.timeslots[index],
      subject: { id: index + 1, name: slot.subject },
      teacher: { id: index + 1, name: slot.teacher },
      room: { id: index + 1, name: slot.room },
      class_info: { id: index + 1, name: slot.className },
      active_schedule_block_id: index + 1,
      lesson_log_status: 'PENDING',
      can_create_occurrence: true,
      is_past: true,
    })))
    if (/^\/schedule\/(active|operational)-blocks\/\d+\/log$/.test(path)) return write(['put'], { id: 41, ...body })
    if (path === '/occurrences/') return read(['get'], { items: [{
      id: 41,
      version: 1,
      date: scenario.occurrence.date,
      status: scenario.workflow.substitutionCompleted ? 'SUBSTITUTED' : 'GAP',
      operational_state: 'OPEN_PENDING',
      class_id: data.classes[0].id,
      class_name: data.classes[0].name,
      subject_id: data.subjects[0].id,
      subject_name: data.subjects[0].name,
      planned_teacher_id: data.teachers[0].id,
      timeslot_start_time: '08:30:00',
      timeslot_end_time: '09:20:00',
      reason: scenario.occurrence.reason,
    }], total: 1 })
    if (path === '/occurrences/debts') return read(['get'], { items: [{ class_id: 1, class_name: data.classes[0].name, subject_name: data.subjects[0].name, debt_hours: scenario.debt.originalHours, gap_occurrences: 1 }] })
    if (/^\/occurrences\/\d+\/substitutes\/recommendations$/.test(path)) return read(['get'], data.teachers.slice(1).map((teacher, index) => ({ id: index + 1, rank: index + 1, teacher_id: teacher.id, teacher_name: teacher.name, subject_id: data.subjects[index].id, subject_name: data.subjects[index].name, score: 100 - index })))
    if (/^\/occurrences\/\d+\/cancel$/.test(path)) return write(['post'], { id: 41, version: 2, ...body })
    if (/^\/occurrences\/\d+$/.test(path)) return write(['patch'], { id: 41, version: 2, ...body })
    if (path === '/timesheets/') return read(['get'], data.teachers.map((teacher, index) => ({ id: index + 1, teacher_id: index + 1, teacher_name: teacher.name, status: 'OPEN', planned_hours: 22, actual_hours: 20, debt_hours: index === 0 ? 2 : 0 })))

    return Promise.reject(createTutorialApiError(
      `Rota do guia não declarada: ${method.toUpperCase()} ${path}.`,
      metadata,
    ))
  }
}
