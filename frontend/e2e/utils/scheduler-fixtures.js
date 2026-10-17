import { spawnSync } from 'node:child_process'
import { expect } from '@playwright/test'
import {
  expectRouteReady,
  goTo,
} from './clerk-helpers.js'

const API_PREFIX = '/api/v1'
const REQUEST_TIMEOUT_MS = 30_000
const JOB_TIMEOUT_MS = 120_000
const FIXTURE = {
  subjectName: 'E2E Dashboard Subject',
  moduleName: 'E2E Dashboard Module',
  moduleCode: 'E2E-DASH-1',
  courseName: 'E2E Dashboard Course',
  courseAbbreviation: 'E2EDASH',
  className: 'E2E Dashboard Class',
  roomName: 'E2E Dashboard Room',
}

function fixtureDates() {
  const start = new Date()
  start.setHours(12, 0, 0, 0)
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7) - 14)
  const end = new Date(start)
  end.setDate(end.getDate() + 60)
  const iso = (date) => date.toISOString().slice(0, 10)
  return {
    schoolStartDate: iso(start),
    schoolHardEndDate: iso(end),
    startYear: start.getFullYear(),
    endYear: Math.max(end.getFullYear(), start.getFullYear() + 1),
  }
}

export async function apiRequest(page, method, path, body, timeoutMs = REQUEST_TIMEOUT_MS) {
  return page.evaluate(
    async ({ apiPrefix, method: requestMethod, path: requestPath, body: requestBody, timeout }) => {
      const organizationId = window.Clerk?.organization?.id ?? null
      const tokenOptions = organizationId ? { organizationId } : undefined
      let token = null
      try {
        token = await window.Clerk?.session?.getToken?.(tokenOptions)
      } catch {
        token = null
      }
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), timeout)
      try {
        const response = await fetch(`${apiPrefix}${requestPath}`, {
          method: requestMethod,
          credentials: 'same-origin',
          headers,
          body: requestBody === undefined ? undefined : JSON.stringify(requestBody),
          signal: controller.signal,
        })
        const text = await response.text()
        let data = null
        try { data = text ? JSON.parse(text) : null } catch { data = text }
        if (!response.ok) throw new Error(`${requestMethod} ${requestPath} failed: ${response.status} ${text}`)
        return data
      } finally {
        clearTimeout(timeoutId)
      }
    },
    { apiPrefix: API_PREFIX, method, path, body, timeout: timeoutMs },
  )
}

export async function getNormalRoomTypeId(page) {
  const roomTypes = await apiRequest(page, 'GET', '/room-types/')
  const normalRoomType = roomTypes.find((roomType) => roomType.is_normal)
  if (!Number.isInteger(normalRoomType?.id)) throw new Error('Prepared E2E school has no Normal room type.')
  return normalRoomType.id
}

export async function seedMinimalSchedulerInputs(page, requestedTeacherEmail = process.env.E2E_CLERK_TEACHER_EMAIL) {
  const dates = fixtureDates()
  await resetSchedulerState(page)
  const subject = await ensureSubject(page)
  const members = await apiRequest(page, 'GET', '/members')
  const teacherEmail = requestedTeacherEmail
  if (!teacherEmail) throw new Error('E2E_CLERK_TEACHER_EMAIL is required for scheduler E2E.')
  const teacherMember = members.items.find((member) => (
    member.email.toLowerCase() === teacherEmail.toLowerCase()
  ))
  if (!teacherMember) throw new Error(`Prepared E2E teacher member not found: ${teacherEmail}`)
  const subjectIds = Array.from(new Set([...(teacherMember.subject_ids || []), subject.id]))
  const capabilities = Array.from(new Set([...teacherMember.capabilities, 'teacher']))
  const teacher = await apiRequest(page, 'PATCH', `/members/${teacherMember.id}`, {
    capabilities,
    teacher_access_mode: capabilities.includes('admin') ? 'platform' : teacherMember.teacher_access_mode || 'scheduler_only',
    subject_ids: subjectIds,
    lock_version: teacherMember.lock_version,
  })
  if (!teacher.teacher_id) throw new Error('Prepared E2E teacher has no teacher_id.')

  await apiRequest(page, 'POST', '/school/settings/', {
    school_start_date: dates.schoolStartDate,
    school_hard_end_date: dates.schoolHardEndDate,
    preferred_end_date: dates.schoolHardEndDate,
    repair_stability_window_days: 0,
  })
  await apiRequest(page, 'POST', '/school/grid-settings/regenerate', {
    grid_settings: { lunch_window_start: '12:30', lunch_window_end: '14:00', lunch_min_duration_minutes: 60 },
    timeslots: {
      start_time: '09:00', end_time: '14:00', slot_duration_minutes: 60,
      break_duration_minutes: 0, days_of_week: [0, 1, 2, 3, 4],
    },
  })
  await ensureRoom(page)
  const course = await ensureCourse(page, subject.id)
  const classroom = await ensureClass(page, course.id, dates)
  await ensureClassSubject(page, classroom.id, subject.id, teacher.teacher_id)
  return classroom
}

async function resetSchedulerState(page) {
  const status = await apiRequest(page, 'GET', '/scheduler/status')
  if (status?.pending_proposal?.proposal_id) {
    await apiRequest(page, 'POST', `/scheduler/drafts/${status.pending_proposal.proposal_id}/reject`)
  }
  if (status?.school_year?.id) {
    await apiRequest(page, 'POST', '/school/settings/soft-reset', { confirm_phrase: 'Confirmo' })
  }
}

async function ensureSubject(page) {
  const subjects = await apiRequest(page, 'GET', '/subjects/')
  const existing = subjects.find((subject) => subject.name === FIXTURE.subjectName)
  const module = {
    ...(existing?.modules?.[0]?.id ? { id: existing.modules[0].id } : {}),
    name: FIXTURE.moduleName,
    code: FIXTURE.moduleCode,
    hours_total: 2,
    order: 0,
  }
  const payload = { name: FIXTURE.subjectName, room_type_id: await getNormalRoomTypeId(page), modules: [module] }
  return existing
    ? apiRequest(page, 'PATCH', `/subjects/${existing.id}`, payload)
    : apiRequest(page, 'POST', '/subjects/', payload)
}

async function ensureCourse(page, subjectId) {
  const courses = await apiRequest(page, 'GET', '/courses/')
  const existing = courses.find((course) => course.name === FIXTURE.courseName)
  const payload = {
    name: FIXTURE.courseName,
    abbreviation: FIXTURE.courseAbbreviation,
    subject_ids: [subjectId],
  }
  return existing
    ? apiRequest(page, 'PATCH', `/courses/${existing.id}`, payload)
    : apiRequest(page, 'POST', '/courses/', { ...payload, teacher_assignments: [], classes_config: [] })
}

async function ensureClass(page, courseId, dates) {
  const course = await apiRequest(page, 'GET', `/courses/${courseId}`)
  const existing = course.classes.find((classroom) => classroom.name === FIXTURE.className)
  const payload = {
    name: FIXTURE.className,
    size: 20,
    grade_level: 10,
    start_year: dates.startYear,
    end_year: dates.endYear,
  }
  return existing
    ? apiRequest(page, 'PATCH', `/courses/${courseId}/classes/${existing.id}`, payload)
    : apiRequest(page, 'POST', `/courses/${courseId}/classes`, payload)
}

async function ensureRoom(page) {
  const rooms = await apiRequest(page, 'GET', '/rooms/')
  const existing = rooms.find((room) => room.name === FIXTURE.roomName)
  const payload = { name: FIXTURE.roomName, room_type_id: await getNormalRoomTypeId(page), capacity: 30 }
  return existing
    ? apiRequest(page, 'PATCH', `/rooms/${existing.id}`, payload)
    : apiRequest(page, 'POST', '/rooms/', payload)
}

async function ensureClassSubject(page, classId, subjectId, teacherId) {
  let subjects = await apiRequest(page, 'GET', `/classes/${classId}/subjects`)
  if (!subjects.subjects.some((subject) => subject.subject_id === subjectId)) {
    await apiRequest(page, 'POST', `/classes/${classId}/subjects`, { subject_id: subjectId })
  }
  subjects = await apiRequest(page, 'GET', `/classes/${classId}/subjects`)
  for (const subject of subjects.subjects) {
    if (subject.subject_id !== subjectId) {
      await apiRequest(page, 'DELETE', `/classes/${classId}/subjects/${subject.subject_id}`)
    }
  }
  await apiRequest(page, 'PATCH', `/classes/${classId}/subjects/${subjectId}`, { teacher_id: teacherId })
}

async function ensureSubjectWithModules(page, fixture) {
  const subjects = await apiRequest(page, 'GET', '/subjects/')
  const existing = subjects.find((subject) => subject.name === fixture.subjectName)
  const modules = fixture.moduleNames.map((name, index) => ({
    ...(existing?.modules?.[index]?.id ? { id: existing.modules[index].id } : {}),
    name,
    code: fixture.moduleCodes[index],
    hours_total: 2,
    order: index,
  }))
  const payload = { name: fixture.subjectName, room_type_id: await getNormalRoomTypeId(page), modules }
  if (existing) await apiRequest(page, 'PATCH', `/subjects/${existing.id}`, payload)
  else await apiRequest(page, 'POST', '/subjects/', payload)
  const refreshed = await apiRequest(page, 'GET', '/subjects/')
  const saved = refreshed.find((subject) => subject.name === fixture.subjectName)
  if (!saved) throw new Error(`Fixture subject not found: ${fixture.subjectName}`)
  return saved
}

async function ensureNamedCourse(page, subjectId, fixture) {
  const courses = await apiRequest(page, 'GET', '/courses/')
  const existing = courses.find((course) => course.name === fixture.courseName)
  const payload = { name: fixture.courseName, abbreviation: fixture.courseAbbreviation, subject_ids: [subjectId] }
  return existing
    ? apiRequest(page, 'PATCH', `/courses/${existing.id}`, payload)
    : apiRequest(page, 'POST', '/courses/', { ...payload, teacher_assignments: [], classes_config: [] })
}

async function ensureNamedClass(page, courseId, name, dates) {
  const course = await apiRequest(page, 'GET', `/courses/${courseId}`)
  const existing = course.classes.find((classroom) => classroom.name === name)
  const payload = { name, size: 20, grade_level: 10, start_year: dates.startYear, end_year: dates.endYear }
  return existing
    ? apiRequest(page, 'PATCH', `/courses/${courseId}/classes/${existing.id}`, payload)
    : apiRequest(page, 'POST', `/courses/${courseId}/classes`, payload)
}

async function ensureNamedRoom(page, name, capacity = 30) {
  const rooms = await apiRequest(page, 'GET', '/rooms/')
  const existing = rooms.find((room) => room.name === name)
  const payload = { name, room_type_id: await getNormalRoomTypeId(page), capacity }
  return existing
    ? apiRequest(page, 'PATCH', `/rooms/${existing.id}`, payload)
    : apiRequest(page, 'POST', '/rooms/', payload)
}

async function prepareFixtureTeacher(page, subjectId) {
  const members = await apiRequest(page, 'GET', '/members')
  const teacherEmail = process.env.E2E_CLERK_TEACHER_EMAIL
  if (!teacherEmail) throw new Error('E2E_CLERK_TEACHER_EMAIL is required for scheduler E2E.')
  const teacherMember = members.items.find((member) => member.email.toLowerCase() === teacherEmail.toLowerCase())
  if (!teacherMember) throw new Error(`Prepared E2E teacher member not found: ${teacherEmail}`)
  const teacher = await apiRequest(page, 'PATCH', `/members/${teacherMember.id}`, {
    capabilities: Array.from(new Set([...teacherMember.capabilities, 'teacher'])),
    teacher_access_mode: teacherMember.teacher_access_mode || 'scheduler_only',
    subject_ids: Array.from(new Set([...(teacherMember.subject_ids || []), subjectId])),
    lock_version: teacherMember.lock_version,
  })
  if (!teacher.teacher_id) throw new Error('Prepared E2E teacher has no teacher_id.')
  return teacher
}

async function configureFixtureSchool(page, dates) {
  await apiRequest(page, 'POST', '/school/settings/', {
    school_start_date: dates.schoolStartDate,
    school_hard_end_date: dates.schoolHardEndDate,
    preferred_end_date: dates.schoolHardEndDate,
    repair_stability_window_days: 0,
  })
  await apiRequest(page, 'POST', '/school/grid-settings/regenerate', {
    grid_settings: { lunch_window_start: '12:30', lunch_window_end: '14:00', lunch_min_duration_minutes: 60 },
    timeslots: {
      start_time: '09:00', end_time: '14:00', slot_duration_minutes: 60,
      break_duration_minutes: 0, days_of_week: [0, 1, 2, 3, 4],
    },
  })
}

async function attachClassSubjectWithModules(page, classId, subjectId, teacherId, moduleIds) {
  let subjects = await apiRequest(page, 'GET', `/classes/${classId}/subjects`)
  if (!subjects.subjects.some((subject) => subject.subject_id === subjectId)) {
    await apiRequest(page, 'POST', `/classes/${classId}/subjects`, { subject_id: subjectId })
  }
  subjects = await apiRequest(page, 'GET', `/classes/${classId}/subjects`)
  for (const subject of subjects.subjects) {
    if (subject.subject_id !== subjectId) {
      await apiRequest(page, 'DELETE', `/classes/${classId}/subjects/${subject.subject_id}`)
    }
  }
  await apiRequest(page, 'PATCH', `/classes/${classId}/subjects/${subjectId}`, {
    teacher_id: teacherId,
    module_ids: moduleIds,
  })
}

const JOINT_ACCEPTANCE_FIXTURE = {
  subjectName: 'E2E Joint Subject',
  moduleNames: [
    'E2E Joint M1',
    'E2E Joint M2',
    'E2E Joint M3',
    'E2E Joint M4',
    'E2E Joint M5',
    'E2E Joint M6',
  ],
  moduleCodes: ['E2E-J1', 'E2E-J2', 'E2E-J3', 'E2E-J4', 'E2E-J5', 'E2E-J6'],
  courseName: 'E2E Joint Course',
  courseAbbreviation: 'E2EJOINT',
  classNames: ['E2E Joint A', 'E2E Joint B'],
  roomName: 'E2E Joint Room',
}

/**
 * Two classes with four shared modules (M1..M4) and one separate module each
 * (M5 in A, M6 in B), ready for the joint acceptance journey. The joint group
 * is created later through the UI.
 */
export async function seedJointAcceptanceInputs(page) {
  const dates = fixtureDates()
  await resetSchedulerState(page)
  const subject = await ensureSubjectWithModules(page, JOINT_ACCEPTANCE_FIXTURE)
  const teacher = await prepareFixtureTeacher(page, subject.id)
  await configureFixtureSchool(page, dates)
  await ensureNamedRoom(page, JOINT_ACCEPTANCE_FIXTURE.roomName, 60)
  const course = await ensureNamedCourse(page, subject.id, JOINT_ACCEPTANCE_FIXTURE)
  const classes = []
  for (const name of JOINT_ACCEPTANCE_FIXTURE.classNames) {
    classes.push(await ensureNamedClass(page, course.id, name, dates))
  }
  const moduleIdByName = new Map(subject.modules.map((module) => [module.name, module.id]))
  const names = JOINT_ACCEPTANCE_FIXTURE.moduleNames
  const sharedModuleIds = names.slice(0, 4).map((name) => moduleIdByName.get(name))
  const separateModuleIds = {
    a: moduleIdByName.get(names[4]),
    b: moduleIdByName.get(names[5]),
  }
  await attachClassSubjectWithModules(
    page, classes[0].id, subject.id, teacher.teacher_id, [...sharedModuleIds, separateModuleIds.a],
  )
  await attachClassSubjectWithModules(
    page, classes[1].id, subject.id, teacher.teacher_id, [...sharedModuleIds, separateModuleIds.b],
  )
  return {
    courseId: course.id,
    subjectId: subject.id,
    classes: classes.map((classroom) => ({ id: classroom.id, name: classroom.name })),
    sharedModuleIds,
    separateModuleIds,
  }
}

// The Compose project the runner owns for this run: a generated local project or
// the one an external (CI) run already exports. Nothing else may reach the seed.
const RESERVED_E2E_COMPOSE_PROJECT = /^cronos-(?:test|ci)-/

/**
 * Move the first published joint lesson of the E2E Joint fixture into the past
 * so the acceptance journey can log it and decide its gap. The test-only build
 * runs inside the backend container the caller owns. The project and file come
 * from the runner environment, are validated against the reserved prefixes and
 * are never guessed or printed. Any guard failure exits non-zero and this
 * helper fails closed without a fallback.
 */
export async function seedEndedJointLesson(page) {
  const settings = await apiRequest(page, 'GET', '/school/settings/')
  const organizationId = settings?.organization_id
  const clerkOrgId = await page.evaluate(() => window.Clerk?.organization?.id ?? null)
  const project = process.env.E2E_COMPOSE_PROJECT_NAME ?? ''
  const composeFile = process.env.E2E_COMPOSE_FILE ?? ''
  if (!organizationId) throw new Error('The E2E school settings did not expose organization_id.')
  if (!clerkOrgId) throw new Error('window.Clerk.organization.id is required to guard the joint seed.')
  if (!composeFile) throw new Error('E2E_COMPOSE_FILE is required to run the joint seed.')
  if (!RESERVED_E2E_COMPOSE_PROJECT.test(project)) {
    throw new Error(`Refusing to seed joint history outside a reserved E2E Compose project: ${project || '(unset)'}`)
  }
  const result = spawnSync('docker', [
    'compose', '-f', composeFile, '-p', project, 'exec', '-T', 'backend',
    'python', 'scripts/seed_e2e_joint_history.py',
    '--organization-id', String(organizationId),
    '--expected-clerk-org-id', clerkOrgId,
  ], { encoding: 'utf8' })
  if (result.error) throw result.error
  if (result.status !== 0) {
    throw new Error(`seed_e2e_joint_history exited ${result.status}: ${result.stderr?.trim() || result.stdout?.trim()}`)
  }
  const lastLine = (result.stdout ?? '').trim().split(/\r?\n/).filter(Boolean).at(-1)
  if (!lastLine) throw new Error('seed_e2e_joint_history returned no JSON result.')
  const history = JSON.parse(lastLine)
  if (!history.school_date || !Array.isArray(history.lesson_ids) || history.lesson_ids.length < 2) {
    throw new Error(`seed_e2e_joint_history returned an unexpected result: ${lastLine}`)
  }
  return history
}

/**
 * Undo the joint group this journey created. Once a member class has executed a
 * joint module the product refuses the undo (J19), so the group stays and the
 * disposable test stack removes it; the refusal is reported instead of forced.
 */
export async function deleteJointGroup(page, classId) {
  const subjects = await apiRequest(page, 'GET', `/classes/${classId}/subjects`)
  const groupId = subjects.subjects.find((subject) => subject.joint_group)?.joint_group?.id
  if (!groupId) return 'absent'
  try {
    await apiRequest(page, 'DELETE', `/joint-lesson-groups/${groupId}`)
    return 'deleted'
  } catch (error) {
    if (/failed: 409\b/.test(error?.message ?? '') && error.message.includes('JOINT_MODULE_STARTED')) {
      return 'started'
    }
    throw error
  }
}

export async function waitForJobToSucceed(page, jobId) {
  let lastJob = null
  await expect.poll(
    async () => {
      lastJob = await apiRequest(page, 'GET', `/scheduler/jobs/${jobId}`)
      if (['FAILED', 'STALE', 'CANCELLED', 'INFEASIBLE', 'INCONCLUSIVE'].includes(lastJob.status)) {
        throw new Error(`scheduler job ${jobId} ended with ${lastJob.status}`)
      }
      return lastJob.status
    },
    {
      intervals: [100, 250, 500],
      timeout: JOB_TIMEOUT_MS,
      message: `scheduler job ${jobId} should succeed`,
    },
  ).toBe('SUCCEEDED')
  return lastJob
}

export async function generateAndApproveThroughUi(page) {
  await goTo(page, '/schedules')
  await expectRouteReady(page, '/schedules')
  const generateResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/scheduler/generate') &&
    response.request().method() === 'POST'
  ))
  await page.getByRole('button', { name: /(?:Gerar|Atualizar) Hor.rio/i }).click()
  await page.getByRole('button', { name: /Iniciar gera/i }).click()
  const response = await generateResponse
  const responseText = await response.text()
  expect(response.ok(), `scheduler generate failed: ${response.status()} ${responseText}`).toBeTruthy()
  const job = await waitForJobToSucceed(page, JSON.parse(responseText).job.id)
  await expect(page.getByText(/Proposta pronta para revis/i)).toBeVisible({ timeout: 30_000 })
  const approvalResponse = page.waitForResponse((candidate) => (
    candidate.url().includes('/api/v1/scheduler/drafts/') &&
    candidate.url().endsWith('/approve') && candidate.request().method() === 'POST'
  ))
  await page.getByRole('button', { name: /^Aprovar$/i }).click()
  const approval = await approvalResponse
  expect(approval.ok(), `draft approval failed: ${approval.status()} ${await approval.text()}`).toBeTruthy()
  return job
}

export async function firstPublishedFutureSlot(page, classId) {
  const monday = new Date()
  monday.setHours(12, 0, 0, 0)
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7))
  for (let week = 0; week < 10; week += 1) {
    const weekStart = new Date(monday)
    weekStart.setDate(weekStart.getDate() + week * 7)
    const slots = await apiRequest(
      page, 'GET',
      `/schedule/week?class_id=${classId}&week_start=${weekStart.toISOString().slice(0, 10)}`,
    )
    const published = slots.find((slot) => slot.scheduler_lesson_id)
    if (published) return published
  }
  throw new Error('No published future slot was found.')
}
