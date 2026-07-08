import { test, expect } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectRouteReady,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

const API_PREFIX = '/api/v1'
const FIXTURE = {
  subjectName: 'E2E Scheduler Subject',
  moduleName: 'E2E Scheduler Module',
  moduleCode: 'E2E-SCHED-1',
  courseName: 'E2E Scheduler Course',
  courseAbbreviation: 'E2ESCH',
  className: 'E2E Scheduler Class',
  roomName: 'E2E Scheduler Room',
  schoolStartDate: '2026-09-14',
  schoolHardEndDate: '2027-07-09',
  startYear: 2026,
  endYear: 2027,
}

async function apiRequest(page, method, path, body) {
  return await page.evaluate(
    async ({ apiPrefix, method: requestMethod, path: requestPath, body: requestBody }) => {
      let token = null
      try {
        token = await window.Clerk?.session?.getToken?.()
      } catch {
        token = null
      }
      if (!token) {
        try {
          const activeSession = window.Clerk?.client?.sessions?.find(
            (session) => session.status === 'active',
          ) || window.Clerk?.client?.sessions?.[0]
          token = await activeSession?.getToken?.()
        } catch {
          token = null
        }
      }
      const headers = {
        'Content-Type': 'application/json',
      }
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }
      const response = await fetch(`${apiPrefix}${requestPath}`, {
        method: requestMethod,
        credentials: 'same-origin',
        headers,
        body: requestBody === undefined ? undefined : JSON.stringify(requestBody),
      })
      const text = await response.text()
      const data = text ? JSON.parse(text) : null
      if (!response.ok) {
        throw new Error(`${requestMethod} ${requestPath} failed: ${response.status} ${text}`)
      }
      return data
    },
    { apiPrefix: API_PREFIX, method, path, body },
  )
}

async function rejectPendingDraftIfPresent(page) {
  const status = await apiRequest(page, 'GET', '/scheduler/status')
  if (status?.pending_draft_id) {
    await apiRequest(page, 'POST', `/scheduler/drafts/${status.pending_draft_id}/reject`)
  }
}

async function resetSchedulerYearIfConfigured(page) {
  const status = await apiRequest(page, 'GET', '/scheduler/status')
  if (status?.school_year_id) {
    await apiRequest(page, 'POST', '/scheduler/reset-year', { confirmed: true })
  }
}

async function findPreparedTeacherMember(page) {
  const teacherEmail = process.env.E2E_CLERK_TEACHER_EMAIL
  if (!teacherEmail) {
    throw new Error('E2E_CLERK_TEACHER_EMAIL is required for scheduler E2E.')
  }

  const members = await apiRequest(page, 'GET', '/members')
  const teacher = members.items.find(
    (member) => member.email.toLowerCase() === teacherEmail.toLowerCase(),
  )
  if (!teacher) {
    throw new Error(`Prepared E2E teacher member not found: ${teacherEmail}`)
  }
  return teacher
}

function singleFixtureModule(existingSubject) {
  const existingModule = existingSubject?.modules?.[0]
  return {
    ...(existingModule?.id ? { id: existingModule.id } : {}),
    name: FIXTURE.moduleName,
    code: FIXTURE.moduleCode,
    hours_total: 1,
    order: 0,
  }
}

async function ensureFixtureSubject(page) {
  const subjects = await apiRequest(page, 'GET', '/subjects/')
  const existing = subjects.find((subject) => subject.name === FIXTURE.subjectName)
  const payload = {
    name: FIXTURE.subjectName,
    required_room_type: 'normal',
    modules: [singleFixtureModule(existing)],
  }
  if (!existing) {
    return await apiRequest(page, 'POST', '/subjects/', payload)
  }
  return await apiRequest(page, 'PATCH', `/subjects/${existing.id}`, payload)
}

async function ensureFixtureCourse(page, subjectId) {
  const courses = await apiRequest(page, 'GET', '/courses/')
  const existing = courses.find((course) => course.name === FIXTURE.courseName)
  const payload = {
    name: FIXTURE.courseName,
    abbreviation: FIXTURE.courseAbbreviation,
    subject_ids: [subjectId],
  }
  if (!existing) {
    return await apiRequest(page, 'POST', '/courses/', {
      ...payload,
      teacher_assignments: [],
      classes_config: [],
    })
  }
  return await apiRequest(page, 'PATCH', `/courses/${existing.id}`, payload)
}

async function ensureFixtureClass(page, courseId) {
  const course = await apiRequest(page, 'GET', `/courses/${courseId}`)
  const existing = course.classes.find((classroom) => classroom.name === FIXTURE.className)
  const payload = {
    name: FIXTURE.className,
    size: 20,
    grade_level: 10,
    start_year: FIXTURE.startYear,
    end_year: FIXTURE.endYear,
  }
  if (!existing) {
    return await apiRequest(page, 'POST', `/courses/${courseId}/classes`, payload)
  }
  return await apiRequest(page, 'PATCH', `/courses/${courseId}/classes/${existing.id}`, payload)
}

async function ensureFixtureRoom(page) {
  const rooms = await apiRequest(page, 'GET', '/rooms/')
  const existing = rooms.find((room) => room.name === FIXTURE.roomName)
  const payload = {
    name: FIXTURE.roomName,
    type: 'normal',
    capacity: 30,
  }
  if (!existing) {
    return await apiRequest(page, 'POST', '/rooms/', payload)
  }
  return await apiRequest(page, 'PATCH', `/rooms/${existing.id}`, payload)
}

async function ensureFixtureClassSubject(page, classroomId, subjectId, teacherId) {
  const classSubjects = await apiRequest(page, 'GET', `/classes/${classroomId}/subjects`)
  const hasFixtureSubject = classSubjects.subjects.some(
    (subject) => subject.subject_id === subjectId,
  )
  if (!hasFixtureSubject) {
    await apiRequest(page, 'POST', `/classes/${classroomId}/subjects`, { subject_id: subjectId })
  }
  for (const subject of classSubjects.subjects) {
    if (subject.subject_id !== subjectId) {
      await apiRequest(page, 'DELETE', `/classes/${classroomId}/subjects/${subject.subject_id}`)
    }
  }
  await apiRequest(page, 'PATCH', `/classes/${classroomId}/subjects/${subjectId}`, {
    teacher_id: teacherId,
  })
}

async function e2eSubjectIds(page, fixtureSubjectId) {
  const subjects = await apiRequest(page, 'GET', '/subjects/')
  return subjects
    .filter((subject) => (
      subject.id === fixtureSubjectId
      || subject.name === FIXTURE.subjectName
      || subject.name.startsWith('E2E Horario ')
    ))
    .map((subject) => subject.id)
}

async function seedMinimalSchedulerInputs(page) {
  await resetSchedulerYearIfConfigured(page)
  await rejectPendingDraftIfPresent(page)

  const subject = await ensureFixtureSubject(page)

  const teacherMember = await findPreparedTeacherMember(page)
  const competencySubjectIds = Array.from(new Set([
    ...(teacherMember.subject_ids || []),
    ...(await e2eSubjectIds(page, subject.id)),
  ]))
  const updatedTeacher = await apiRequest(page, 'PATCH', `/members/${teacherMember.id}`, {
    capabilities: teacherMember.capabilities,
    teacher_access_mode: teacherMember.teacher_access_mode || 'scheduler_only',
    subject_ids: competencySubjectIds,
    lock_version: teacherMember.lock_version,
  })
  if (!updatedTeacher.teacher_id) {
    throw new Error('Prepared E2E teacher did not expose a teacher_id after subject assignment.')
  }

  await apiRequest(page, 'POST', '/school/settings/', {
    school_start_date: FIXTURE.schoolStartDate,
    school_hard_end_date: FIXTURE.schoolHardEndDate,
    repair_stability_window_days: 0,
  })
  await apiRequest(page, 'POST', '/school/grid-settings/', {
    lunch_window_start: '12:30',
    lunch_window_end: '14:00',
    lunch_min_duration_minutes: 60,
  })
  await apiRequest(page, 'POST', '/timeslots/generate', {
    start_time: '09:00',
    end_time: '11:00',
    slot_duration_minutes: 60,
    break_duration_minutes: 0,
    days_of_week: [0, 1, 2, 3, 4],
  })
  await ensureFixtureRoom(page)
  const course = await ensureFixtureCourse(page, subject.id)
  const classroom = await ensureFixtureClass(page, course.id)
  await ensureFixtureClassSubject(page, classroom.id, subject.id, updatedTeacher.teacher_id)

  const timeslots = await apiRequest(page, 'GET', '/timeslots/')
  await apiRequest(
    page,
    'POST',
    `/teachers/${updatedTeacher.teacher_id}/availability`,
    timeslots.map((slot) => ({ timeslot_id: slot.id, score: 2 })),
  )

  return { classId: classroom.id, subjectId: subject.id, teacherId: updatedTeacher.teacher_id }
}

async function waitForJobToSucceed(page, jobId) {
  let lastJob = null
  await expect.poll(
    async () => {
      lastJob = await apiRequest(page, 'GET', `/scheduler/jobs/${jobId}`)
      return lastJob.job_status
    },
    {
      message: `scheduler job ${jobId} should finish successfully`,
      intervals: [1000, 2000, 5000],
      timeout: 120_000,
    },
  ).toBe('SUCCEEDED')
  return lastJob
}

test.describe('Scheduler generation', () => {
  test('admin generates a real pending complete draft', async ({ page }) => {
    test.setTimeout(180_000)

    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
    await goTo(page, '/dashboard')
    await seedMinimalSchedulerInputs(page)

    await goTo(page, '/schedules')
    await expectRouteReady(page, '/schedules')
    await expect(page.getByText(/Erro na gera/i)).toHaveCount(0)

    const generateResponse = page.waitForResponse(
      (response) => response.url().includes('/api/v1/scheduler/generate')
        && response.request().method() === 'POST',
    )
    await page.getByRole('button', { name: /Gerar Hor.rio/i }).click()
    const response = await generateResponse
    const responseText = await response.text()
    expect(response.ok(), `scheduler generate failed: ${response.status()} ${responseText}`).toBeTruthy()
    const { job_id: jobId } = JSON.parse(responseText)

    const job = await waitForJobToSucceed(page, jobId)
    expect(job.job_status).toBe('SUCCEEDED')

    await expect(page.getByText(/Rascunho pronto para revis/i)).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Rascunho pendente').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Resultado completo').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/Erro na gera/i)).toHaveCount(0)
  })
})
