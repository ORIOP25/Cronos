import { expect } from '@playwright/test'
import { execFile } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'
import {
  expectRouteReady,
  goTo,
} from './clerk-helpers.js'

const API_PREFIX = '/api/v1'
const REQUEST_TIMEOUT_MS = 30_000
const JOB_TIMEOUT_MS = 120_000
const execFileAsync = promisify(execFile)
const repoRoot = fileURLToPath(new URL('../../../', import.meta.url))
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

export async function seedSchedulerV1Records(page, { classId, subjectId, preferredEndDate }) {
  const composeFile = process.env.E2E_COMPOSE_FILE
  const composeProject = process.env.COMPOSE_PROJECT_NAME
  if (!composeFile || !composeProject) throw new Error('E2E Docker stack is required.')
  const member = await apiRequest(page, 'GET', '/members/me')
  await execFileAsync(process.platform === 'win32' ? 'docker.exe' : 'docker', [
    'compose', '-f', composeFile, '-p', composeProject, 'exec', '-T', 'backend',
    'python', '-m', 'scripts.seed_scheduler_e2e',
    '--organization-id', String(member.organization_id),
    '--class-id', String(classId),
    '--subject-id', String(subjectId),
    '--preferred-end-date', preferredEndDate,
  ], { cwd: repoRoot, env: process.env, timeout: REQUEST_TIMEOUT_MS })
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
  const payload = { name: FIXTURE.subjectName, required_room_type: 'normal', modules: [module] }
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
  const payload = { name: FIXTURE.roomName, type: 'normal', capacity: 30 }
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
  await seedSchedulerV1Records(page, {
    classId: classroom.id,
    subjectId: subject.id,
    preferredEndDate: dates.schoolHardEndDate,
  })
  return classroom
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
